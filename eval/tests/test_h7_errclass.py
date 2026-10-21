"""오답 원인 분류(하네스 점검 10번) 정답 테스트. 규칙 층: 실행실패·무응답/파싱·도구 미호출·인자 오류는 raw만 보고 결정. 판정 층: 나머지는 API(가짜)로 2·4·5 중 분류."""
import json, sys, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import classify_failures as cf

LAW = {"law_article", "article_history", "find_article", "verify_statement", "judge_options", "timing_rules", "search_tax_rulings", "expand_tools"}
CALC = {"corporate_tax", "depreciation_adjustment", "entertainment_adjustment"}


def _rec(jjo="X", answer=2, reason="근거", details=(), forced=False, error=None, year="C2023", qno=1):
    return {"연도": year, "번호": qno, "정오": jjo, "정답": 3, "모델답": None if answer is None else {"answer": answer, "reason": reason},
            "근거": reason, "forced_final": forced, "error": error, "tool_call_details": list(details), "harness_events": {}}


def _call(tool, args=None, err=False, preview="{}"):
    return {"tool": tool, "args": args or {"a": 1}, "result_preview": preview, "is_error": err}


def test_rule_execution_failure():
    r = cf.classify_record(_rec(jjo="실행실패", error="RuntimeError"), qtype="계산형", law_tools=LAW, calc_tools=CALC)
    assert r["분류"] == 7


def test_rule_no_answer_and_parse():
    r1 = cf.classify_record(_rec(jjo="무응답", answer=None, reason=""), qtype="서술형", law_tools=LAW, calc_tools=CALC)
    r2 = cf.classify_record(_rec(jjo="무응답", answer=None, reason="따라서 정답은 ③이다."), qtype="서술형", law_tools=LAW, calc_tools=CALC)
    assert r1["분류"] == 6 and "무응답" in r1["소분류"]
    assert r2["분류"] == 6 and "파싱" in r2["소분류"]                 # 답을 썼는데 추출 못 함


def test_rule_calc_without_calc_tool():
    r = cf.classify_record(_rec(details=[_call("law_article")] * 3), qtype="계산형", law_tools=LAW, calc_tools=CALC)
    assert r["분류"] == 1
    r2 = cf.classify_record(_rec(details=[_call("law_article")] * 3), qtype="서술형", law_tools=LAW, calc_tools=CALC)
    assert r2["분류"] is None                                          # 서술형은 판정 층으로


def test_rule_all_calc_calls_errored():
    d = [_call("law_article"), _call("depreciation_adjustment", err=True, preview='{"error": "입력 확인 필요"}'), _call("depreciation_adjustment", err=True)]
    r = cf.classify_record(_rec(details=d), qtype="계산형", law_tools=LAW, calc_tools=CALC)
    assert r["분류"] == 3
    d2 = d + [_call("depreciation_adjustment", args={"b": 2}, preview='{"상각범위액": 100}')]
    r2 = cf.classify_record(_rec(details=d2), qtype="계산형", law_tools=LAW, calc_tools=CALC)
    assert r2["분류"] is None and r2["flags"]["인자오류후복구"] is True


def test_flags_and_correct():
    d = [_call("law_article", {"article": "제50조"})] * 3 + [_call("corporate_tax", err=True)]
    r = cf.classify_record(_rec(jjo="O", details=d, forced=True), qtype="계산형", law_tools=LAW, calc_tools=CALC)
    f = r["flags"]
    assert r["분류"] == 0 and f["상한소진"] is True and f["최대반복"] == 3 and f["도구오류수"] == 1
    assert f["호출수"] == 4 and f["계산호출수"] == 1 and f["조문호출수"] == 3


def test_judge_with_fake_api(monkeypatch):
    seen = []
    def api(base_url, api_key, model, messages, **kw):
        seen.append(messages)
        return {"choices": [{"message": {"role": "assistant", "content": '{"분류": 5, "근거": "조문은 찾았으나 이혼 배우자 공제를 잘못 판단"}'}}], "usage": {}}
    d = [_call("law_article", preview="제50조 본문")] * 2
    r = cf.classify_record(_rec(details=d), qtype="서술형", law_tools=LAW, calc_tools=CALC, api=api, question_body="문항 본문 ① ② ③")
    assert r["분류"] == 5 and "이혼" in r["근거"]
    txt = json.dumps(seen[0], ensure_ascii=False)
    assert "문항 본문" in txt and "law_article" in txt and "제50조 본문" in txt     # 문항·호출·결과가 판정 입력에 포함
    def bad(base_url, api_key, model, messages, **kw):
        return {"choices": [{"message": {"role": "assistant", "content": "모르겠다"}}], "usage": {}}
    r2 = cf.classify_record(_rec(details=d), qtype="서술형", law_tools=LAW, calc_tools=CALC, api=bad)
    assert r2["분류"] is None and r2["소분류"] == "미판정"


def test_classify_dir_cache_and_summary(tmp_path, monkeypatch):
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    recs = [_rec(jjo="O", qno=1), _rec(jjo="X", qno=2, details=[_call("law_article")]),
            _rec(jjo="X", qno=3, details=[_call("corporate_tax", preview='{"세액": 1}')]), _rec(jjo="실행실패", qno=4, error="E")]
    (d / "raw_native_direct_C2023.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in recs) + "\n")
    questions = {"C2023": {"1": {"본문": "세액으로 옳은 것은? ① 1원 ② 2원"}, "2": {"본문": "세액으로 옳은 것은? ① 1원 ② 2원"},
                           "3": {"본문": "세액으로 옳은 것은? ① 1원 ② 2원"}, "4": {"본문": "옳은 설명은? ① 가 ② 나"}}}
    n = []
    def api(base_url, api_key, model, messages, **kw):
        n.append(1); return {"choices": [{"message": {"content": '{"분류": 2, "근거": "x"}'}}], "usage": {}}
    out = cf.classify_dir(d, questions, law_tools=LAW, calc_tools=CALC, api=api)
    by = {o["번호"]: o["분류"] for o in out}
    assert by == {1: 0, 2: 1, 3: 2, 4: 7} and len(n) == 2            # 판정 1회 + 미호출 문항의 도구 유무 질문 1회
    assert (d / "failure_classes.jsonl").exists()
    out2 = cf.classify_dir(d, questions, law_tools=LAW, calc_tools=CALC, api=api)
    assert len(n) == 2 and [o["분류"] for o in out2] == [o["분류"] for o in out]    # 캐시: API 재호출 없음
    s = cf.summarize(out)
    assert s["계산형"][1] == 1 and s["계산형"][2] == 1 and s["서술형"][7] == 1 and s["계산형"][0] == 1


def test_cli_prints_table(tmp_path):
    d = tmp_path / "calcset_y_s42"; d.mkdir()
    (d / "raw_native_direct_C2023.jsonl").write_text(json.dumps(_rec(jjo="X", qno=1, details=[_call("law_article")]), ensure_ascii=False) + "\n")
    qf = tmp_path / "q.json"; qf.write_text(json.dumps({"C2023": {"1": {"본문": "세액은? ① 1원 ② 2원"}}}, ensure_ascii=False))
    p = subprocess.run([sys.executable, str(pathlib.Path(cf.__file__)), str(d), "--questions", str(qf), "--no-judge"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "도구 미호출" in p.stdout and "계산형" in p.stdout


# ── h7b: 판정 층 보강 (계산형은 3 값 오추출 허용, 도구 결과를 사실로, 미호출은 도구 유무 소분류) ──

def test_judge_calc_may_pick_value_extraction(monkeypatch):
    seen = []
    def api(base_url, api_key, model, messages, **kw):
        seen.append(messages)
        return {"choices": [{"message": {"content": '{"분류": 3, "근거": "기본공제 미적용 옵션을 false로 넘김"}'}}], "usage": {}}
    d = [_call("capital_gains_income", {"apply_basic_deduction": False}, preview='{"양도소득금액": 27720000}')]
    r = cf.classify_record(_rec(details=d), qtype="계산형", law_tools=LAW, calc_tools=CALC | {"capital_gains_income"}, api=api, question_body="양도소득금액은?")
    assert r["분류"] == 3 and r["소분류"] == "값 오추출"
    sys_txt = seen[0][0]["content"]
    assert "값 오추출" in sys_txt and "인자" in sys_txt                       # 계산형 판정에 3 정의 포함
    def api2(base_url, api_key, model, messages, **kw):
        seen.append(messages); return {"choices": [{"message": {"content": '{"분류": 5, "근거": "x"}'}}], "usage": {}}
    cf.classify_record(_rec(details=[_call("law_article")]), qtype="서술형", law_tools=LAW, calc_tools=CALC, api=api2)
    assert "값 오추출" not in seen[-1][0]["content"]                           # 서술형에는 3 없음


def test_no_tool_call_subclass_by_tool_availability(monkeypatch):
    def api_no(base_url, api_key, model, messages, **kw):
        assert "inheritance_tax" in json.dumps(messages, ensure_ascii=False)   # 노출 도구 목록이 질문에 포함
        return {"choices": [{"message": {"content": '{"도구있음": false, "도구명": ""}'}}], "usage": {}}
    r = cf.classify_record(_rec(details=[_call("law_article")]), qtype="계산형", law_tools=LAW, calc_tools=CALC,
                           api=api_no, exposed_calc_tools=["inheritance_tax", "corporate_tax"], question_body="상속세 과세표준은?")
    assert r["분류"] == 1 and r["소분류"] == "도구 없음"
    def api_yes(base_url, api_key, model, messages, **kw):
        return {"choices": [{"message": {"content": '{"도구있음": true, "도구명": "inheritance_tax"}'}}], "usage": {}}
    r2 = cf.classify_record(_rec(details=[_call("law_article")]), qtype="계산형", law_tools=LAW, calc_tools=CALC,
                            api=api_yes, exposed_calc_tools=["inheritance_tax"], question_body="상속세 과세표준은?")
    assert r2["분류"] == 1 and r2["소분류"] == "도구 있음(inheritance_tax)"
    r3 = cf.classify_record(_rec(details=[_call("law_article")]), qtype="계산형", law_tools=LAW, calc_tools=CALC)   # api 없으면 소분류 그대로
    assert r3["분류"] == 1 and r3["소분류"] == "도구 미호출"


def test_classify_dir_exposed_tools_from_routing(tmp_path):
    d = tmp_path / "calcset_z_s42"; d.mkdir()
    rec = _rec(jjo="X", qno=1, details=[_call("law_article")]); rec["harness_events"] = {"routing_bucket": "상증세", "routing_qtype": "계산형"}
    (d / "raw_native_direct_C2023.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n")
    seen = []
    def api(base_url, api_key, model, messages, **kw):
        seen.append(json.dumps(messages, ensure_ascii=False)); return {"choices": [{"message": {"content": '{"도구있음": true, "도구명": "inheritance_tax"}'}}], "usage": {}}
    routing = {"공통": ["law_article"], "주제": {"상증세": ["inheritance_tax", "gift_tax"], "법인세_세액": ["corporate_tax"]}}
    out = cf.classify_dir(d, {"C2023": {"1": {"본문": "상속세 과세표준은? ① 1원"}}}, law_tools=LAW, calc_tools=CALC | {"inheritance_tax", "gift_tax"},
                          api=api, use_cache=False, routing_table=routing)
    assert out[0]["소분류"] == "도구 있음(inheritance_tax)"
    assert "inheritance_tax" in seen[0] and "corporate_tax" not in seen[0]      # 라우팅 주제의 계산 도구만 노출 목록으로
