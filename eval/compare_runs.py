"""하네스 6단계: 평가 체계 — 두 실행 결과 비교 (작성 Claude, 2026-10-20).

표준 라이브러리만 사용 (scipy 금지). McNemar 정확 이항검정, Wilson 95% 신뢰구간.
"""

import argparse
import json
import math
import pathlib
import sys
from collections import defaultdict


# ── Wilson 95% 신뢰구간 ──────────────────────────────────────────────────────────

def _z_95() -> float:
    """95% 양측 z값 (1.96)."""
    return 1.959963984540054


def wilson_ci(success: int, n: int, z: float | None = None) -> tuple[float, float]:
    """Wilson score 신뢰구간 (95%). (하한, 상한)."""
    if n == 0:
        return (0.0, 0.0)
    if z is None:
        z = _z_95()
    p_hat = success / n
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)


# ── 이항분포 누적확률 (정확 McNemar 검정을 위해) ─────────────────────────────────

def _log_comb(n: int, k: int) -> float:
    """log C(n, k)를 안정적으로 계산 (Stirling 보정 없이 순차 곱)."""
    if k < 0 or k > n:
        return -float("inf")
    if k == 0 or k == n:
        return 0.0
    k = min(k, n - k)
    s = 0.0
    for i in range(1, k + 1):
        s += math.log(n - k + i) - math.log(i)
    return s


def _binom_pval(n: int, k: int, p: float = 0.5) -> float:
    """P(X <= k) for X ~ Binomial(n, p), k = min including 0.

    작은 n (≤ 약 2000)에 대해 log-space로 안정적 계산.
    """
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    log_p = math.log(p)
    log_q = math.log(1.0 - p)
    total = 0.0
    for x in range(0, k + 1):
        total += math.exp(_log_comb(n, x) + x * log_p + (n - x) * log_q)
    return min(total, 1.0)


# ── McNemar 정확 이항검정 (양측) ──────────────────────────────────────────────────

def mcnemar_p(a_only: int, b_only: int) -> float:
    """McNemar 정확 이항검정 p값 (양측).

    b = a_only + b_only (불일치 쌍 총수), k = min(a_only, b_only),
    p = 2 * P(X <= k), X ~ Binomial(b, 0.5), 상한 1.0.
    b = 0 (불일치 없음)이면 p = 1.0.
    """
    b = a_only + b_only
    if b == 0:
        return 1.0
    k = min(a_only, b_only)
    # 정확 이항검정 양측 p값
    p_one_sided = _binom_pval(b, k, 0.5)
    p_two_sided = 2.0 * p_one_sided
    return min(p_two_sided, 1.0)


# ── load_dir ─────────────────────────────────────────────────────────────────────

def load_dir(dir_path: str | pathlib.Path) -> dict[tuple[str, int], str]:
    """dir 안 raw_*.jsonl 전부 읽어 {(연도, 번호): 정오} 반환.

    같은 (연도, 번호) 중복은 마지막 줄 사용.
    """
    result: dict[tuple[str, int], str] = {}
    d = pathlib.Path(dir_path)
    if not d.is_dir():
        return result
    for fp in sorted(d.glob("raw_*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yr = str(rec.get("연도", ""))
                no = rec.get("번호")
                jung = rec.get("정오", "")
                if not yr or no is None:
                    continue
                result[(yr, int(no))] = str(jung)
    return result


# ── compare ───────────────────────────────────────────────────────────────────────

def compare(dir_a: str | pathlib.Path, dir_b: str | pathlib.Path) -> dict:
    """두 실행 결과 디렉토리를 비교.

    양쪽에 모두 있고 둘 다 실행실패가 아닌 문항만 짝지어 분석.
    """
    data_a = load_dir(dir_a)
    data_b = load_dir(dir_b)

    shared = set(data_a.keys()) & set(data_b.keys())

    a_correct = b_correct = both = a_only = b_only = neither = 0
    excluded_failed = 0

    for key in shared:
        va = data_a[key]
        vb = data_b[key]
        if va == "실행실패" or vb == "실행실패":
            excluded_failed += 1
            continue
        a_ok = va == "O"
        b_ok = vb == "O"
        if a_ok:
            a_correct += 1
        if b_ok:
            b_correct += 1
        if a_ok and b_ok:
            both += 1
        elif a_ok and not b_ok:
            a_only += 1
        elif not a_ok and b_ok:
            b_only += 1
        else:
            neither += 1

    n = len(shared) - excluded_failed

    # Wilson 95% 신뢰구간
    ci_a = wilson_ci(a_correct, n)
    ci_b = wilson_ci(b_correct, n)

    # McNemar 정확 이항검정
    p = mcnemar_p(a_only, b_only)

    # 판정
    if p < 0.05:
        verdict = "B 우세" if b_correct > a_correct else ("A 우세" if a_correct > b_correct else "차이 없음")
    else:
        verdict = "차이 없음"

    return {
        "n": n,
        "a_correct": a_correct,
        "b_correct": b_correct,
        "both": both,
        "a_only": a_only,
        "b_only": b_only,
        "neither": neither,
        "excluded_failed": excluded_failed,
        "mcnemar_p": p,
        "ci_a": ci_a,
        "ci_b": ci_b,
        "verdict": verdict,
    }


# ── compare_seeds ────────────────────────────────────────────────────────────────

def compare_seeds(
    results_root: str | pathlib.Path,
    label_a: str,
    label_b: str,
    seeds: tuple[int, ...],
) -> dict:
    """results_root/calcset_{label}_s{seed} 폴더들을 시드별로 짝지어 합산.

    문항 × 시드가 한 짝. 모든 시드 결과를 누적하여 McNemar 검정.
    """
    root = pathlib.Path(results_root)

    total_a_correct = total_b_correct = total_both = total_a_only = total_b_only = total_neither = 0
    total_excluded_failed = 0
    n_pairs = 0
    seed_scores: list[dict] = []

    for seed in seeds:
        dir_a = root / f"calcset_{label_a}_s{seed}"
        dir_b = root / f"calcset_{label_b}_s{seed}"
        r = compare(dir_a, dir_b)
        total_a_correct += r["a_correct"]
        total_b_correct += r["b_correct"]
        total_both += r["both"]
        total_a_only += r["a_only"]
        total_b_only += r["b_only"]
        total_neither += r["neither"]
        total_excluded_failed += r["excluded_failed"]
        n_pairs += r["n"]
        seed_scores.append({
            "seed": seed,
            "n": r["n"],
            "a_correct": r["a_correct"],
            "b_correct": r["b_correct"],
            "p": r["mcnemar_p"],
        })

    ci_a = wilson_ci(total_a_correct, n_pairs)
    ci_b = wilson_ci(total_b_correct, n_pairs)
    p = mcnemar_p(total_a_only, total_b_only)

    if p < 0.05:
        verdict = "B 우세" if total_b_correct > total_a_correct else ("A 우세" if total_a_correct > total_b_correct else "차이 없음")
    else:
        verdict = "차이 없음"

    return {
        "seeds": len(seeds),
        "n_pairs": n_pairs,
        "a_correct": total_a_correct,
        "b_correct": total_b_correct,
        "both": total_both,
        "a_only": total_a_only,
        "b_only": total_b_only,
        "neither": total_neither,
        "excluded_failed": total_excluded_failed,
        "mcnemar_p": p,
        "ci_a": ci_a,
        "ci_b": ci_b,
        "verdict": verdict,
        "seed_scores": seed_scores,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────────

def _print_table(r: dict) -> None:
    """비교 결과를 표 형태로 표준출력."""
    n = r["n"]
    print(f"문항수: {n}")
    print(f"A 정답: {r['a_correct']}/{n}  (95% CI: [{r['ci_a'][0]:.3f}, {r['ci_a'][1]:.3f}])")
    print(f"B 정답: {r['b_correct']}/{n}  (95% CI: [{r['ci_b'][0]:.3f}, {r['ci_b'][1]:.3f}])")
    print()
    print(f"둘 다 맞음: {r['both']}")
    print(f"A만 맞음  : {r['a_only']}")
    print(f"B만 맞음  : {r['b_only']}")
    print(f"둘 다 틀림: {r['neither']}")
    print(f"제외(실행실패): {r['excluded_failed']}")
    print()
    print(f"McNemar p: {r['mcnemar_p']:.6g}")
    print(f"판정      : {r['verdict']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="compare_runs — 두 실행 결과 비교")
    parser.add_argument("dir_a", help="비교 대상 A 디렉토리")
    parser.add_argument("dir_b", help="비교 대상 B 디렉토리")
    parser.add_argument("--seeds", help="콤마 구분 시드 목록 (예: 42,43,44)")
    parser.add_argument("--root", help="results 루트 디렉토리 (--seeds 사용 시 필수)")
    parser.add_argument("--label-a", default="A", help="A 라벨 (--seeds 사용 시)")
    parser.add_argument("--label-b", default="B", help="B 라벨 (--seeds 사용 시)")
    args = parser.parse_args()

    if args.seeds is not None:
        if not args.root:
            print("--seeds 사용 시 --root 필수", file=sys.stderr)
            sys.exit(2)
        seeds = tuple(int(s.strip()) for s in args.seeds.split(",") if s.strip())
        if not seeds:
            print("시드 목록이 비어 있음", file=sys.stderr)
            sys.exit(2)
        r = compare_seeds(args.root, args.label_a, args.label_b, seeds)
    else:
        r = compare(args.dir_a, args.dir_b)

    _print_table(r)


if __name__ == "__main__":
    main()
