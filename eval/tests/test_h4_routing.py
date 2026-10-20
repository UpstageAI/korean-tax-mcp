"""4단계 2단계 라우팅 정답 테스트 (하네스 점검). 작성 Claude 2026-10-20. API 호출 없음."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "data/routing_table.json").read_text())


def _all_tools():
    names = set(TABLE["공통"]) | set(TABLE["공통_서술형"]) | {n for v in TABLE["주제"].values() for n in v}
    return [{"type": "function", "function": {"name": n, "description": n, "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}}}} for n in sorted(names)]


def test_table_tools_exist_and_buckets_small():
    for key, names in TABLE["주제"].items():
        assert 1 <= len(names) <= 10, key


def test_select_tools_limits_and_keeps_schema():
    tools = _all_tools()
    sel = run.select_tools_for_bucket("법인세_세액", tools, question_type="계산형")
    names = [t["function"]["name"] for t in sel]
    assert set(TABLE["주제"]["법인세_세액"]) <= set(names) and "law_article" in names and "expand_tools" in names
    assert len([n for n in names if n != "expand_tools"]) <= 10 + len(TABLE["공통"]) + len(TABLE["공통_서술형"])
    assert "verify_statement" not in names                                   # 계산형은 서술형 공통 제외
    orig = next(t for t in tools if t["function"]["name"] == "corporate_tax")
    assert next(t for t in sel if t["function"]["name"] == "corporate_tax")["function"]["parameters"] == orig["function"]["parameters"]  # 원래 스키마 그대로
    sel2 = run.select_tools_for_bucket("법인세_세액", tools, question_type="서술형")
    assert "judge_options" in [t["function"]["name"] for t in sel2]


def test_unknown_bucket_falls_back_to_all():
    tools = _all_tools()
    assert len(run.select_tools_for_bucket("없는키", tools, question_type="계산형")) == len(tools) + 1   # 전체 + expand


def test_classify_parses_model_output(monkeypatch):
    def api(base_url, api_key, model, messages, **kw):
        assert "법인세_세액" in messages[-1]["content"]          # 키 목록을 프롬프트에 보여줌
        return {"choices": [{"message": {"content": '{"주제": "소득세_근로연말정산", "유형": "계산형"}'}}], "usage": {"prompt_tokens": 500, "completion_tokens": 20, "total_tokens": 520}}
    monkeypatch.setattr(run, "api_chat_complete", api)
    acc = run.UsageAcc()
    bucket, qtype = run.classify_question("근로자 갑의 총급여액은? ① 1 ② 2", base_url="x", api_key="x", model="m", seed=1, usage_acc=acc)
    assert (bucket, qtype) == ("소득세_근로연말정산", "계산형") and acc.total == 520


def test_expand_tools_adds_bucket(monkeypatch):
    tools = _all_tools()
    state = run.RoutingState(bucket="법인세_세액", question_type="계산형", all_tools=tools)
    before = len(state.current_tools())
    out = run.handle_expand_tools({"주제": "부가세_과세표준매입세액"}, state)
    assert "common_input_tax" in [t["function"]["name"] for t in state.current_tools()] and len(state.current_tools()) > before
    assert "추가" in json.dumps(out, ensure_ascii=False)
    err = run.handle_expand_tools({"주제": "없는키"}, state)
    assert "error" in err and "법인세_세액" in json.dumps(err, ensure_ascii=False)   # 가능한 키 안내


def test_routing_config_flag():
    cfg = run.preset("native_direct")
    assert cfg.routing is False
    cfg2 = run.with_overrides(cfg, {"routing": True})
    assert cfg2.routing is True and cfg2.name == "native_direct"


def test_raw_written_once_per_question(tmp_path, monkeypatch):
    # 실측(10/20 21:47): 문항이 raw에 두 번 기록됨 — 한 번만
    written = []
    monkeypatch.setattr(run, "_append_raw_one", lambda res, path, **kw: written.append(res.번호))
    def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(run, "api_chat_complete", boom)
    monkeypatch.setattr(run, "_build_native_direct_tools", lambda: ([], [], {}))
    q = {"과목": "세법개론", "본문": "문제 ① 가 ② 나"}
    run.run_condition_one(cond="native_direct", year="C2023", qno=5, question=q, correct=1, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", limit_tools=15, raw_path=tmp_path / "r.jsonl")
    assert written == [5]


def test_cfg_override_reaches_run_question(monkeypatch):
    # 실측(10/20 22:25): CFG_OVERRIDE routing=true로 실행해도 raw run_config.routing이 False — run_question이 preset()만 씀
    monkeypatch.setenv("CFG_OVERRIDE", '{"routing": true, "calc_pipeline": true, "limit_tools": 3}')
    def api(base_url, api_key, model, messages, **kw):
        return {"choices": [{"message": {"content": '{"reason": "r", "answer": 1}'}}], "usage": {"total_tokens": 5}}
    monkeypatch.setattr(run, "api_chat_complete", api)
    monkeypatch.setattr(run, "_build_native_direct_tools", lambda: ([], [], {}))
    q = {"과목": "세법개론", "본문": "다음 중 옳은 것은? ① 가 ② 나 ③ 다 ④ 라 ⑤ 마"}
    res = run.run_question(cond="native_direct", year="C2023", qno=1, question=q, correct=1, base_url="x", api_key="x",
                           model="m", seed=1, exam_date="20230101", limit_tools=15)
    cfg = res._run_config
    assert cfg["routing"] is True and cfg["calc_pipeline"] is True and cfg["limit_tools"] == 3
