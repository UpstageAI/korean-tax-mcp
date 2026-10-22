"""덮어쓰기 로그 정답 테스트. 작성 Claude 2026-10-22. 가짜 raw로 override_log의 분류를 확인."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import override_log as ol

BODY = "갑의 양도소득금액으로 옳은 것은?\n① 25,480,000원   ② 29,340,000원   ③ 29,400,000원\n④          0원   ⑤ 1,000만원"
CALC = {"capital_gains_income", "corporate_tax"}


def _rec(answer, jung, tools, tool_results):
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": BODY}]
    for i, (t, res) in enumerate(zip(tools, tool_results)):
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": t, "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": res})
    return {"연도": "C2021", "번호": 15, "모델답": {"answer": answer, "reason": "r"}, "정답": 3, "정오": jung,
            "도구호출목록": list(tools), "messages": msgs,
            "tool_call_details": [{"tool": t, "args": {}, "result_preview": r[:50], "is_error": False} for t, r in zip(tools, tool_results)],
            "harness_events": {}}


def test_option_values_parses_amounts():
    assert ol.option_values(BODY) == {1: 25480000, 2: 29340000, 3: 29400000, 4: 0, 5: 10000000}


def test_tool_numbers_collects_nested_ints():
    nums = ol.tool_numbers('{"결과": {"양도소득금액": 29400000, "공제율": 0.4, "비과세": false}, "근거": "제95조"}')
    assert 29400000 in nums and True not in nums


def test_adopt_when_tool_has_answer_and_correct():
    rec = _rec(3, "O", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}'])
    out = ol.classify_record(rec, BODY, CALC)
    assert out["구분"] == "채택" and out["도구값_정답포함"] is True and out["정답값"] == 29400000


def test_override_when_tool_has_answer_but_model_wrong():
    rec = _rec(2, "X", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}'])
    out = ol.classify_record(rec, BODY, CALC)
    assert out["구분"] == "덮어씀" and out["모델값"] == 29340000 and out["모델값_도구출력에있음"] is False


def test_no_tool_value_and_wrong():
    rec = _rec(1, "X", ["capital_gains_income"], ['{"결과": {"양도소득금액": 12345}}'])
    assert ol.classify_record(rec, BODY, CALC)["구분"] == "도구값없음_오답"


def test_law_tool_numbers_ignored_and_uncalled():
    rec = _rec(3, "O", ["law_article"], ['{"본문": "… 29,400,000원 …"}'])
    out = ol.classify_record(rec, BODY, CALC)
    assert out["구분"] == "미호출" and out["도구호출"] is False


def test_run_dirs_writes_log_and_summary(tmp_path):
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    recs = [_rec(3, "O", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}']),
            _rec(2, "X", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}'])]
    recs[1]["번호"] = 15
    (d / "raw_native_direct_C2021.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"15": {"과목": "세법개론", "본문": BODY}}}, ensure_ascii=False), encoding="utf-8")
    rows, summary = ol.run_dirs([str(d)], str(q), calc_tools=CALC, no_judge=True, no_cache=True)
    assert len(rows) == 2 and (d / "override_log.jsonl").exists()
    assert summary["구분별"]["채택"] == 1 and summary["구분별"]["덮어씀"] == 1 and summary["채택률"] == 0.5
    assert summary["도구별"]["capital_gains_income"]["덮어씀"] == 1


def test_run_dirs_cache_is_per_dir(tmp_path):
    """같은 (연도, 번호)라도 dir(시드)이 다르면 각자 분류해야 한다 — 첫 dir의 row를 재사용하면 안 됨."""
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"15": {"과목": "세법개론", "본문": BODY}}}, ensure_ascii=False), encoding="utf-8")
    d1 = tmp_path / "calcset_x_s42"; d1.mkdir(); d2 = tmp_path / "calcset_x_s43"; d2.mkdir()
    r1 = _rec(3, "O", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}'])
    r2 = _rec(2, "X", ["capital_gains_income"], ['{"결과": {"양도소득금액": 29400000}}'])
    (d1 / "raw_native_direct_C2021.jsonl").write_text(json.dumps(r1, ensure_ascii=False) + "\n", encoding="utf-8")
    (d2 / "raw_native_direct_C2021.jsonl").write_text(json.dumps(r2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows, summary = ol.run_dirs([str(d1), str(d2)], str(q), calc_tools=CALC, no_judge=True)
    assert summary["구분별"].get("채택", 0) == 1 and summary["구분별"].get("덮어씀", 0) == 1
    assert sorted(r["dir"] for r in rows) == ["calcset_x_s42", "calcset_x_s43"]
    rows2, summary2 = ol.run_dirs([str(d1), str(d2)], str(q), calc_tools=CALC, no_judge=True)  # 캐시 사용 2회째도 동일
    assert summary2["구분별"] == summary["구분별"]
