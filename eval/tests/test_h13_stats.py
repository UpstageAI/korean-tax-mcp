"""짝 통계(SE·CI·MDE·필요 문항)와 깔때기 표 정답 테스트. 작성 Claude 2026-10-22."""
import json, sys, pathlib, math
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import compare_runs as cr


def test_paired_stats_known_values():
    A = {("C", 1): [1, 1], ("C", 2): [0, 1], ("C", 3): [1, 0], ("C", 4): [1, 1]}
    B = {("C", 1): [0, 1], ("C", 2): [0, 0], ("C", 3): [1, 1], ("C", 4): [1, 0]}
    s = cr.paired_stats(A, B)
    assert s["n"] == 4 and s["K"] == 2
    assert abs(s["mean_a"] - 0.75) < 1e-9 and abs(s["mean_b"] - 0.5) < 1e-9
    assert abs(s["diff"] - 0.25) < 1e-9 and abs(s["se_paired"] - 0.25) < 1e-9
    lo, hi = s["ci95"]
    assert abs(lo - (0.25 - 1.96 * 0.25)) < 1e-6 and abs(hi - (0.25 + 1.96 * 0.25)) < 1e-6
    assert s["sigma2_a"] > 0 and s["sigma2_b"] > 0 and s["omega2"] >= 0
    assert s["mde"] > 0 and s["n_needed"][0.05] > s["n_needed"][0.10] > s["n_needed"][0.15] > 0


def test_paired_stats_zero_variance_does_not_crash():
    A = {("C", i): [1, 1, 1] for i in range(5)}
    B = {("C", i): [0, 0, 0] for i in range(5)}
    s = cr.paired_stats(A, B)
    assert s["diff"] == 1.0 and s["se_paired"] == 0.0 and s["corr"] is None


def test_funnel_stage_order(tmp_path):
    from eval import funnel
    body = "① 1,000원 ② 2,000원 ③ 3,000원 ④ 4,000원 ⑤ 5,000원"
    gold = {"연도": "C2021", "번호": 1, "정답보기": 3, "정답값": 3000, "상태": "도구있음",
            "호출": [{"이름": "ct", "도구": "corporate_tax", "인자": {"base": 10}, "결과키": "결과.산출세액"}], "결합": "ct", "메모": ""}
    rec = {"연도": "C2021", "번호": 1, "모델답": {"answer": 3}, "정답": 3, "정오": "O", "도구호출목록": ["corporate_tax"],
           "tool_call_details": [{"tool": "corporate_tax", "args": {"base": 10}, "result_preview": '{"결과": {"산출세액": 3000}}', "is_error": False}],
           "messages": [{"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "corporate_tax", "arguments": "{}"}}]},
                        {"role": "tool", "tool_call_id": "c0", "content": '{"결과": {"산출세액": 3000}}'}], "harness_events": {}}
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    (d / "raw_native_direct_C2021.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"1": {"과목": "세법개론", "본문": body}}}, ensure_ascii=False), encoding="utf-8")
    stages = funnel.build([str(d)], str(g), str(q))
    assert [s["단계"] for s in stages] == ["도구선택", "인자일치", "도구정답출력", "채택", "최종정답"]
    assert all(s["비율"] == 1.0 for s in stages)


def test_funnel_cli_runs_from_repo_root():
    """`python eval/funnel.py --help`가 저장소 루트에서 바로 실행돼야 한다(다른 eval CLI와 동일)."""
    import subprocess, pathlib, sys
    root = pathlib.Path(__file__).resolve().parents[2]
    p = subprocess.run([sys.executable, str(root / "eval" / "funnel.py"), "--help"], capture_output=True, text=True, cwd=root)
    assert p.returncode == 0 and "--questions" in p.stdout


def test_paired_stats_block_prints_with_zero_variance(capsys):
    """분산 0이면 필요 문항 수가 무한대 — 출력 블록이 OverflowError 없이 '∞'로 찍혀야 한다(리뷰 반영)."""
    A = {("C", i): [1, 1, 1] for i in range(5)}
    B = {("C", i): [0, 0, 0] for i in range(5)}
    s = cr.paired_stats(A, B)
    cr._print_paired_stats_block(s)
    out = capsys.readouterr().out
    assert "짝 통계" in out and "∞" in out


def test_funnel_gold_only_uses_one_population(tmp_path):
    """--gold-only면 3~5단계도 정답 인자가 있는 문항만 분모로 삼는다(리뷰 반영)."""
    from eval import funnel
    body = "① 1,000원 ② 2,000원 ③ 3,000원 ④ 4,000원 ⑤ 5,000원"
    gold = {"연도": "C2021", "번호": 1, "정답보기": 3, "정답값": 3000, "상태": "도구있음",
            "호출": [{"이름": "ct", "도구": "corporate_tax", "인자": {"base": 10}, "결과키": "결과.산출세액"}], "결합": "ct", "메모": ""}
    def rec(no, jung):
        return {"연도": "C2021", "번호": no, "모델답": {"answer": 3}, "정답": 3, "정오": jung, "도구호출목록": ["corporate_tax"],
                "tool_call_details": [{"tool": "corporate_tax", "args": {"base": 10}, "result_preview": '{"결과": {"산출세액": 3000}}', "is_error": False}],
                "messages": [{"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "corporate_tax", "arguments": "{}"}}]},
                             {"role": "tool", "tool_call_id": "c0", "content": '{"결과": {"산출세액": 3000}}'}], "harness_events": {}}
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    (d / "raw_native_direct_C2021.jsonl").write_text(json.dumps(rec(1, "O"), ensure_ascii=False) + "\n" + json.dumps(rec(2, "X"), ensure_ascii=False) + "\n", encoding="utf-8")
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"1": {"과목": "세법개론", "본문": body}, "2": {"과목": "세법개론", "본문": body}}}, ensure_ascii=False), encoding="utf-8")
    both = funnel.build([str(d)], str(g), str(q))
    assert both[-1]["분모"] == 2 and both[-1]["모집단"] == "전체"
    only = funnel.build([str(d)], str(g), str(q), gold_only=True)
    assert only[-1]["분모"] == 1 and only[-1]["모집단"] == "정답 인자 있음" and only[-1]["비율"] == 1.0


def test_paired_stats_block_finite_n_when_only_diff_variance_is_zero(capsys):
    """차이는 일정(se=0)해도 시드 간 분산이 있으면 필요 문항 수는 유한 — ∞가 아니어야 한다(리뷰 반영)."""
    A = {("C", 1): [1, 0], ("C", 2): [0, 1], ("C", 3): [1, 0], ("C", 4): [0, 1]}
    B = {("C", i): [0, 0] for i in range(1, 5)}
    s = cr.paired_stats(A, B)
    assert s["se_paired"] == 0.0 and s["sigma2_a"] > 0 and s["mde"] > 0
    cr._print_paired_stats_block(s)
    out = capsys.readouterr().out
    assert "∞" not in out


def test_funnel_stage_has_denominator_description(tmp_path):
    """각 단계에 분모가 무엇인지 적혀 있어야 한다(리뷰 반영)."""
    from eval import funnel
    body = "① 1,000원 ② 2,000원 ③ 3,000원 ④ 4,000원 ⑤ 5,000원"
    gold = {"연도": "C2021", "번호": 1, "정답보기": 3, "정답값": 3000, "상태": "도구있음",
            "호출": [{"이름": "ct", "도구": "corporate_tax", "인자": {"base": 10}, "결과키": "결과.산출세액"}], "결합": "ct", "메모": ""}
    rec = {"연도": "C2021", "번호": 1, "모델답": {"answer": 3}, "정답": 3, "정오": "O", "도구호출목록": ["corporate_tax"],
           "tool_call_details": [{"tool": "corporate_tax", "args": {"base": 10}, "result_preview": '{"결과": {"산출세액": 3000}}', "is_error": False}],
           "messages": [{"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "corporate_tax", "arguments": "{}"}}]},
                        {"role": "tool", "tool_call_id": "c0", "content": '{"결과": {"산출세액": 3000}}'}], "harness_events": {}}
    d = tmp_path / "calcset_x_s42"; d.mkdir()
    (d / "raw_native_direct_C2021.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"1": {"과목": "세법개론", "본문": body}}}, ensure_ascii=False), encoding="utf-8")
    stages = funnel.build([str(d)], str(g), str(q))
    descs = [s["분모"] for s in stages]
    assert all(isinstance(s.get("분모_설명"), str) and s["분모_설명"] for s in stages)
    assert stages[2]["분모_설명"] != stages[4]["분모_설명"]  # 3단계(도구 호출 실행)와 5단계(전체 실행)는 다른 분모


def test_funnel_gold_only_final_stage_counts_runs_not_questions(tmp_path):
    """--gold-only 5단계 분모는 고유 문항 수가 아니라 실행 수(시드 × 문항)여야 한다(리뷰 반영)."""
    from eval import funnel
    body = "① 1,000원 ② 2,000원 ③ 3,000원 ④ 4,000원 ⑤ 5,000원"
    gold = {"연도": "C2021", "번호": 1, "정답보기": 3, "정답값": 3000, "상태": "도구있음",
            "호출": [{"이름": "ct", "도구": "corporate_tax", "인자": {"base": 10}, "결과키": "결과.산출세액"}], "결합": "ct", "메모": ""}
    def rec(jung):
        return {"연도": "C2021", "번호": 1, "모델답": {"answer": 3}, "정답": 3, "정오": jung, "도구호출목록": ["corporate_tax"],
                "tool_call_details": [{"tool": "corporate_tax", "args": {"base": 10}, "result_preview": '{"결과": {"산출세액": 3000}}', "is_error": False}],
                "messages": [{"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "corporate_tax", "arguments": "{}"}}]},
                             {"role": "tool", "tool_call_id": "c0", "content": '{"결과": {"산출세액": 3000}}'}], "harness_events": {}}
    dirs = []
    for seed, jung in ((42, "O"), (43, "O"), (44, "X")):
        d = tmp_path / f"calcset_x_s{seed}"; d.mkdir()
        (d / "raw_native_direct_C2021.jsonl").write_text(json.dumps(rec(jung), ensure_ascii=False) + "\n", encoding="utf-8")
        dirs.append(str(d))
    g = tmp_path / "gold.jsonl"; g.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
    q = tmp_path / "q.json"; q.write_text(json.dumps({"C2021": {"1": {"과목": "세법개론", "본문": body}}}, ensure_ascii=False), encoding="utf-8")
    final = funnel.build(dirs, str(g), str(q), gold_only=True)[-1]
    assert final["분모"] == 3 and final["분자"] == 2 and abs(final["비율"] - 2 / 3) < 1e-9
