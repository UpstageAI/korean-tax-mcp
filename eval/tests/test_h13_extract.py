"""추출 정확도(정답 인자 대조) 정답 테스트. 작성 Claude 2026-10-22."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import extract_accuracy as ea

GOLD = {"연도": "C2021", "번호": 15, "정답보기": 3, "정답값": 29400000, "상태": "도구있음",
        "호출": [{"이름": "cg", "도구": "capital_gains_income", "인자": {"asset_type": "주택", "transfer_price": 1000000000, "acquisition_price": 500000000, "one_house": True}, "결과키": "결과.양도소득금액"}],
        "결합": "cg", "메모": ""}
GOLD_LIST = {"연도": "C2021", "번호": 35, "정답보기": 2, "정답값": 1900000, "상태": "도구있음",
             "호출": [{"이름": "di", "도구": "vat_deemed_input_credit", "인자": {"period": "2021-1", "items": [{"name": "돼지고기", "purchase_price": 26000000}, {"name": "밀가루", "purchase_price": 20800000}]}, "결과키": "결과.의제매입세액"}],
             "결합": "di", "메모": ""}


def _rec(no, tool, args, jung="O"):
    return {"연도": "C2021", "번호": no, "모델답": {"answer": 3}, "정답": 3, "정오": jung, "도구호출목록": [tool],
            "tool_call_details": [{"tool": tool, "args": args, "result_preview": "{}", "is_error": False}], "messages": [], "harness_events": {}}


def test_match_scalars_and_numeric_strings():
    assert ea.match_value(1000000000, 1000000000) == 1.0
    assert ea.match_value("1000000000", 1000000000) == 1.0
    assert ea.match_value(True, True) == 1.0 and ea.match_value(False, True) == 0.0
    assert ea.match_value(" 주택 ", "주택") == 1.0


def test_match_list_of_dicts_is_order_free_partial():
    gold = [{"name": "돼지고기", "purchase_price": 26000000}, {"name": "밀가루", "purchase_price": 20800000}]
    model = [{"name": "밀가루", "purchase_price": 20800000}, {"name": "돼지고기", "purchase_price": 1}]
    assert ea.match_value(model, gold) == 0.75  # 밀가루 1.0 + 돼지고기 0.5 → 평균


def test_score_call_reports_missing_wrong_extra():
    s = ea.score_call({"asset_type": "주택", "transfer_price": 1000000000, "acquisition_price": 0, "registered": True}, GOLD["호출"][0]["인자"])
    assert s["누락"] == ["one_house"] and s["틀림"] == ["acquisition_price"] and s["추가"] == ["registered"]
    assert abs(s["일치율"] - 0.5) < 1e-9


def test_score_record_full_match_and_tool_choice():
    full = ea.score_record(_rec(15, "capital_gains_income", GOLD["호출"][0]["인자"]), GOLD)
    assert full["대상"] and full["도구선택"] and full["완전일치"] and full["일치율"] == 1.0
    other = ea.score_record(_rec(15, "income_tax", {"base": 1}), GOLD)
    assert other["도구선택"] is False and other["일치율"] == 0.0 and other["완전일치"] is False
    none = ea.score_record(_rec(10, "income_tax", {}), {**GOLD, "호출": []})
    assert none == {"대상": False}


def test_run_dirs_summary(tmp_path):
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    recs = [_rec(15, "capital_gains_income", GOLD["호출"][0]["인자"]),
            _rec(35, "vat_deemed_input_credit", {"period": "2021-1", "items": [{"name": "돼지고기", "purchase_price": 26000000}]}, "X")]
    (d / "raw_native_direct_C2021.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(GOLD, ensure_ascii=False) + "\n" + json.dumps(GOLD_LIST, ensure_ascii=False) + "\n", encoding="utf-8")
    rows, summary = ea.run_dirs([str(d)], str(g))
    assert summary["실행"] == 2 and summary["도구선택률"] == 1.0 and summary["완전일치율"] == 0.5
    assert summary["정오별_평균일치율"]["O"] == 1.0 and 0 < summary["정오별_평균일치율"]["X"] < 1
    assert (d / "extract_accuracy.jsonl").exists()


def test_run_dirs_excludes_records_without_gold_calls(tmp_path):
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    recs = [_rec(15, "capital_gains_income", GOLD["호출"][0]["인자"]), _rec(10, "income_tax", {"base": 1})]
    (d / "raw_native_direct_C2021.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    no_call = {**GOLD, "번호": 10, "호출": [], "결합": None, "상태": "도구없음"}
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(GOLD, ensure_ascii=False) + "\n" + json.dumps(no_call, ensure_ascii=False) + "\n", encoding="utf-8")
    rows, summary = ea.run_dirs([str(d)], str(g))
    assert summary["실행"] == 1 and summary["대상외"] == 1 and len(rows) == 1 and rows[0]["dir"] == "calcset_x_s42"


def test_print_summary_runs(tmp_path, capsys):
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    (d / "raw_native_direct_C2021.jsonl").write_text(json.dumps(_rec(15, "capital_gains_income", {"asset_type": "주택", "transfer_price": 1}), ensure_ascii=False) + "\n", encoding="utf-8")
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(GOLD, ensure_ascii=False) + "\n", encoding="utf-8")
    rows, summary = ea.run_dirs([str(d)], str(g))
    ea._print_summary(summary, rows, [str(d)])
    out = capsys.readouterr().out
    assert "C2021-15" in out and "틀림" in out
