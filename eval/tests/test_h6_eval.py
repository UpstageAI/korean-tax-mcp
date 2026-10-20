"""6단계 평가 체계 정답 테스트 (하네스 점검). 작성 Claude 2026-10-20."""
import json, sys, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import compare_runs as cr


def _w(path, rows):
    with open(path, "w") as f:
        for q, s in rows: f.write(json.dumps({"연도": "C2023", "번호": q, "정오": s}) + "\n")


def test_pairing_and_mcnemar(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    _w(a / "raw_native_direct_C2023.jsonl", [(i, "O" if i <= 20 else "X") for i in range(1, 41)])
    _w(b / "raw_native_direct_C2023.jsonl", [(i, "O" if i <= 26 else "X") for i in range(1, 41)])
    r = cr.compare(a, b)
    assert r["n"] == 40 and r["a_correct"] == 20 and r["b_correct"] == 26
    assert r["b_only"] == 6 and r["a_only"] == 0 and 0 < r["mcnemar_p"] < 0.05
    assert r["ci_a"][0] < 0.5 < r["ci_a"][1]                       # Wilson 95% 구간


def test_mcnemar_no_difference(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    rows = [(i, "O" if i % 2 else "X") for i in range(1, 45)]
    _w(a / "raw_native_direct_C2023.jsonl", rows); _w(b / "raw_native_direct_C2023.jsonl", rows[:22] + [(q, "X" if s == "O" else "O") for q, s in rows[22:24]] + rows[24:])
    r = cr.compare(a, b)
    assert r["mcnemar_p"] > 0.3 and r["verdict"] == "차이 없음"


def test_duplicates_and_failures_handled(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    _w(a / "raw_native_direct_C2023.jsonl", [(1, "O"), (1, "X"), (2, "실행실패"), (3, "O")])
    _w(b / "raw_native_direct_C2023.jsonl", [(1, "X"), (2, "O"), (3, "O")])
    r = cr.compare(a, b)
    assert r["n"] == 2 and r["excluded_failed"] == 1                 # 중복은 마지막 줄, 실행실패는 짝에서 제외


def test_multi_seed_aggregate(tmp_path):
    for s in (42, 43):
        for lab in ("A", "B"):
            d = tmp_path / f"calcset_{lab}_s{s}"; d.mkdir()
            _w(d / "raw_native_direct_C2023.jsonl", [(i, "O" if (i + s) % 3 else "X") for i in range(1, 11)])
    r = cr.compare_seeds(tmp_path, "A", "B", seeds=(42, 43))
    assert r["seeds"] == 2 and r["n_pairs"] == 20 and "mcnemar_p" in r


def test_cli_prints_table(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    _w(a / "raw_native_direct_C2023.jsonl", [(1, "O"), (2, "X")]); _w(b / "raw_native_direct_C2023.jsonl", [(1, "O"), (2, "O")])
    out = subprocess.run([sys.executable, str(pathlib.Path(cr.__file__)), str(a), str(b)], capture_output=True, text=True).stdout
    assert "McNemar" in out and "B만 맞음" in out
