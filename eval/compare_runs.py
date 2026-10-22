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


# ── 짝 통계 (오차막대 논문 식 7·9·10) ─────────────────────────────────────────────

_Z_ALPHA2_DEFAULT = 1.95996
_Z_BETA_DEFAULT = 0.84162


def _z_alpha2(alpha: float = 0.05) -> float:
    """양측 z_{alpha/2}. alpha=0.05 → 1.95996."""
    table = {0.05: _Z_ALPHA2_DEFAULT, 0.10: 1.64485, 0.20: 1.28155}
    return table.get(alpha, _Z_ALPHA2_DEFAULT)


def _z_beta(power: float = 0.8) -> float:
    """z_beta (beta = 1 - power). power=0.8 → beta=0.2 → 0.84162."""
    table = {0.8: _Z_BETA_DEFAULT, 0.9: 1.28155, 0.95: 1.64485}
    return table.get(power, _Z_BETA_DEFAULT)


def paired_stats(
    scores_a: dict[tuple, list[float]],
    scores_b: dict[tuple, list[float]],
    alpha: float = 0.05,
    power: float = 0.8,
) -> dict:
    """짝 통계 계산.

    입력: 문항 → 시드별 점수 리스트(0/1). 두 dict의 공통 문항만 사용.
    K = 시드 수(둘 다 같아야 함; 다르면 작은 쪽까지만 사용).
    """
    common = set(scores_a.keys()) & set(scores_b.keys())
    n = len(common)
    if n == 0:
        return {
            "n": 0, "K": 0, "mean_a": 0.0, "mean_b": 0.0,
            "diff": 0.0, "se_paired": 0.0, "ci95": (0.0, 0.0),
            "corr": None, "sigma2_a": 0.0, "sigma2_b": 0.0,
            "omega2": 0.0, "mde": 0.0, "n_needed": {},
        }

    K_a = min(len(v) for v in scores_a.values()) if scores_a else 0
    K_b = min(len(v) for v in scores_b.values()) if scores_b else 0
    K = min(K_a, K_b)
    if K == 0:
        return {
            "n": n, "K": 0, "mean_a": 0.0, "mean_b": 0.0,
            "diff": 0.0, "se_paired": 0.0, "ci95": (0.0, 0.0),
            "corr": None, "sigma2_a": 0.0, "sigma2_b": 0.0,
            "omega2": 0.0, "mde": 0.0, "n_needed": {},
        }

    mean_a_list: list[float] = []
    mean_b_list: list[float] = []
    diff_list: list[float] = []
    var_a_list: list[float] = []
    var_b_list: list[float] = []

    for key in common:
        va = scores_a[key][:K]
        vb = scores_b[key][:K]
        xa = sum(va) / K
        xb = sum(vb) / K
        mean_a_list.append(xa)
        mean_b_list.append(xb)
        diff_list.append(xa - xb)

        if K > 1:
            mean_a_v = sum((v - xa) ** 2 for v in va) / (K - 1)
            mean_b_v = sum((v - xb) ** 2 for v in vb) / (K - 1)
        else:
            mean_a_v = 0.0
            mean_b_v = 0.0
        var_a_list.append(mean_a_v)
        var_b_list.append(mean_b_v)

    mean_a = sum(mean_a_list) / n
    mean_b = sum(mean_b_list) / n
    diff = sum(diff_list) / n

    if n > 1:
        var_d = sum((d - diff) ** 2 for d in diff_list) / (n - 1)
        se_paired = math.sqrt(var_d / n)
    else:
        se_paired = 0.0

    ci95_lo = diff - 1.96 * se_paired
    ci95_hi = diff + 1.96 * se_paired

    # 피어슨 상관계수 (x̄_A, x̄_B)
    if n > 1:
        var_xa = sum((x - mean_a) ** 2 for x in mean_a_list) / (n - 1)
        var_xb = sum((x - mean_b) ** 2 for x in mean_b_list) / (n - 1)
        if var_xa > 0 and var_xb > 0:
            cov_ab = sum((mean_a_list[i] - mean_a) * (mean_b_list[i] - mean_b)
                         for i in range(n)) / (n - 1)
            corr = cov_ab / math.sqrt(var_xa * var_xb)
        else:
            corr = None
    else:
        corr = None

    sigma2_a = sum(var_a_list) / n
    sigma2_b = sum(var_b_list) / n

    if n > 1:
        var_xa_tot = sum((x - mean_a) ** 2 for x in mean_a_list) / (n - 1)
        var_xb_tot = sum((x - mean_b) ** 2 for x in mean_b_list) / (n - 1)
        cov_ab_tot = sum((mean_a_list[i] - mean_a) * (mean_b_list[i] - mean_b)
                         for i in range(n)) / (n - 1)
        omega2 = max(0.0, var_xa_tot + var_xb_tot - 2 * cov_ab_tot
                     - sigma2_a / K - sigma2_b / K)
    else:
        omega2 = 0.0

    z_a2 = _z_alpha2(alpha)
    z_b = _z_beta(power)
    pooled_var = omega2 + sigma2_a / K + sigma2_b / K
    mde = (z_a2 + z_b) * math.sqrt(pooled_var / n) if n > 0 else 0.0

    n_needed = {}
    for delta in (0.05, 0.10, 0.15):
        if delta > 0 and pooled_var > 0:
            n_needed[delta] = (z_a2 + z_b) ** 2 * pooled_var / (delta ** 2)
        else:
            n_needed[delta] = float('inf')

    return {
        "n": n,
        "K": K,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "diff": diff,
        "se_paired": se_paired,
        "ci95": (ci95_lo, ci95_hi),
        "corr": corr,
        "sigma2_a": sigma2_a,
        "sigma2_b": sigma2_b,
        "omega2": omega2,
        "mde": mde,
        "n_needed": n_needed,
    }


def _fmt_pp(val: float) -> str:
    """소수 비율을 퍼센트포인트 문자열로 (부호 포함, 소수 1자리)."""
    pp = val * 100
    sign = "+" if pp >= 0 else "-"
    return f"{sign}{abs(pp):.1f}"


def _print_paired_stats_block(s: dict) -> None:
    """짝 통계 블록을 표준출력."""
    n = s["n"]
    K = s["K"]
    mean_a = s["mean_a"]
    mean_b = s["mean_b"]
    diff = s["diff"]
    se = s["se_paired"]
    lo, hi = s["ci95"]
    corr = s["corr"]
    sigma2_a = s["sigma2_a"]
    sigma2_b = s["sigma2_b"]
    omega2 = s["omega2"]
    mde = s["mde"]
    nn = s["n_needed"]

    corr_str = f"{corr:.2f}" if corr is not None else "N/A"

    print()
    print("[짝 통계] "
          f"n={n} K={K}  "
          f"A {mean_a:.1%}  B {mean_b:.1%}  "
          f"차(A−B) {_fmt_pp(diff)}p (SE {_fmt_pp(se)}p)  "
          f"95% CI ({_fmt_pp(lo)}, {_fmt_pp(hi)})  "
          f"상관 {corr_str}")
    print(f"시드 간 분산 A {sigma2_a:.3f} B {sigma2_b:.3f}  "
          f"문항 간 분산(ω²) {omega2:.3f}  "
          f"→ 이 설정으로 볼 수 있는 최소 차이(MDE) {_fmt_pp(mde)}p")
    n5 = nn.get(0.05, float('inf'))
    n10 = nn.get(0.10, float('inf'))
    print(f"5%p 차이를 보려면 문항 {int(math.ceil(n5))}개(K={K}), "
          f"10%p면 {int(math.ceil(n10))}개")


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
    scores_a: dict[tuple, list[float]] = {}
    scores_b: dict[tuple, list[float]] = {}

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

        # 문항별 시드 점수 수집 (paired_stats용)
        qa = load_dir(dir_a)
        qb = load_dir(dir_b)
        for key, va in qa.items():
            score_a = 1.0 if va == "O" else 0.0
            scores_a.setdefault(key, []).append(score_a)
        for key, vb in qb.items():
            score_b = 1.0 if vb == "O" else 0.0
            scores_b.setdefault(key, []).append(score_b)

    ci_a = wilson_ci(total_a_correct, n_pairs)
    ci_b = wilson_ci(total_b_correct, n_pairs)
    p = mcnemar_p(total_a_only, total_b_only)

    if p < 0.05:
        verdict = "B 우세" if total_b_correct > total_a_correct else ("A 우세" if total_a_correct > total_b_correct else "차이 없음")
    else:
        verdict = "차이 없음"

    stats = paired_stats(scores_a, scores_b)

    return {
        "n": n_pairs,
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
        "stats": stats,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────────

def _print_table(r: dict) -> None:
    """비교 결과를 표 형태로 표준출력."""
    n = r.get("n", r.get("n_pairs"))
    seed_scores = r.get("seed_scores")
    if seed_scores:
        print("시드별:")
        for s in seed_scores:
            print(f"  s{s['seed']}  A {s['a_correct']}/{s['n']}  B {s['b_correct']}/{s['n']}  p={s['p']:.3f}")
        print(f"합산 (문항×시드 짝): {n}")
        print()
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

    # 짝 통계 블록 (--seeds 모드)
    if "stats" in r:
        _print_paired_stats_block(r["stats"])


def main() -> None:
    parser = argparse.ArgumentParser(description="compare_runs — 두 실행 결과 비교")
    parser.add_argument("a", help="디렉토리(기본) 또는 --seeds 모드에서는 라벨 A")
    parser.add_argument("b", help="디렉토리(기본) 또는 --seeds 모드에서는 라벨 B")
    parser.add_argument("--seeds", help="콤마 구분 시드 목록 (예: 42,43,44)")
    parser.add_argument("--root", help="results 루트 디렉토리 (--seeds 사용 시 필수)")
    parser.add_argument("--label-a", default=None, help="A 라벨 (--seeds 사용 시, 미지정 시 a 사용)")
    parser.add_argument("--label-b", default=None, help="B 라벨 (--seeds 사용 시, 미지정 시 b 사용)")
    args = parser.parse_args()

    if args.seeds is not None:
        if not args.root:
            print("--seeds 사용 시 --root 필수", file=sys.stderr)
            sys.exit(2)
        seeds = tuple(int(s.strip()) for s in args.seeds.split(",") if s.strip())
        if not seeds:
            print("시드 목록이 비어 있음", file=sys.stderr)
            sys.exit(2)
        label_a = args.label_a if args.label_a is not None else args.a
        label_b = args.label_b if args.label_b is not None else args.b
        r = compare_seeds(args.root, label_a, label_b, seeds)
    else:
        r = compare(args.a, args.b)

    _print_table(r)


if __name__ == "__main__":
    main()
