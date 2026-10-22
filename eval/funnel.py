"""깔때기 표 — 라우팅→추출→채택→최종정답 단계별 비율.

작성 Claude 2026-10-22. 표준 라이브러리만 사용.
"""
import argparse
import pathlib
import sys

# CLI로 직접 실행할 때 패키지 경로를 잡는다.
if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from eval import compare_runs as cr
from eval import extract_accuracy as ea
from eval import override_log as ol


def build(
    dirs: list[str],
    gold_path: str = "eval/data/gold_args.jsonl",
    questions_path: str = "",
) -> list[dict]:
    """5단계 깔때기 비율을 계산.

    반환: [{"단계": 이름, "분자": n, "분모": m, "비율": n/m}, ...] (순서 고정).
    1. 도구선택  2. 인자일치  3. 도구정답출력  4. 채택  5. 최종정답
    """
    ea_rows, ea_summary = ea.run_dirs(dirs, gold_path)
    ol_rows, ol_summary = ol.run_dirs(dirs, questions_path, no_judge=True)

    # 1. 도구선택
    도구선택_분자 = sum(1 for r in ea_rows if r.get("도구선택"))
    도구선택_분모 = ea_summary["실행"]
    도구선택_비율 = 도구선택_분자 / 도구선택_분모 if 도구선택_분모 > 0 else 0.0

    # 2. 인자일치
    인자일치_분자 = sum(1 for r in ea_rows if r.get("완전일치"))
    인자일치_분모 = 도구선택_분모
    인자일치_비율 = 인자일치_분자 / 인자일치_분모 if 인자일치_분모 > 0 else 0.0
    평균일치율 = ea_summary["평균일치율"]

    # 3. 도구정답출력 (구분 ∈ {채택, 덮어씀} / 계산 도구 호출 실행 수)
    도구호출_실행 = sum(1 for r in ol_rows if r.get("도구호출"))
    도구정답출력_분자 = sum(1 for r in ol_rows
                            if r.get("도구호출") and r.get("구분") in ("채택", "덮어씀"))
    도구정답출력_분모 = 도구호출_실행
    도구정답출력_비율 = (도구정답출력_분자 / 도구정답출력_분모
                          if 도구정답출력_분모 > 0 else 0.0)

    # 4. 채택 (채택 / (채택+덮어씀))
    채택_분자 = sum(1 for r in ol_rows if r.get("구분") == "채택")
    덮어씀_수 = sum(1 for r in ol_rows if r.get("구분") == "덮어씀")
    채택_분모 = 채택_분자 + 덮어씀_수
    채택_비율 = (채택_분자 / 채택_분모 if 채택_분모 > 0 else 0.0)

    # 5. 최종정답 (정오 'O' / 전체 실행 수)
    최종정답_분자 = sum(1 for r in ol_rows if r.get("정오") == "O")
    최종정답_분모 = len(ol_rows)
    최종정답_비율 = (최종정답_분자 / 최종정답_분모 if 최종정답_분모 > 0 else 0.0)

    stages = [
        {"단계": "도구선택", "분자": 도구선택_분자, "분모": 도구선택_분모, "비율": 도구선택_비율},
        {"단계": "인자일치", "분자": 인자일치_분자, "분모": 인자일치_분모, "비율": 인자일치_비율,
         "평균일치율": 평균일치율},
        {"단계": "도구정답출력", "분자": 도구정답출력_분자, "분모": 도구정답출력_분모,
         "비율": 도구정답출력_비율},
        {"단계": "채택", "분자": 채택_분자, "분모": 채택_분모, "비율": 채택_비율},
        {"단계": "최종정답", "분자": 최종정답_분자, "분모": 최종정답_분모, "비율": 최종정답_비율},
    ]
    return stages


def _print_funnel(stages: list[dict], label: str = "") -> None:
    """깔때기 표를 표준출력."""
    if label:
        print(f"=== {label} 깔때기 ===")
    else:
        print("=== 깔때기 ===")
    print()
    header = f"{'단계':<12} {'분자':>6} {'분모':>6} {'비율':>8}"
    print(header)
    print("-" * len(header))
    for s in stages:
        extra = ""
        if "평균일치율" in s:
            extra = f"  (평균일치율 {s['평균일치율']:.3f})"
        print(f"{s['단계']:<12} {s['분자']:>6} {s['분모']:>6} {s['비율']:>7.1%}{extra}")
    print()


def _print_seeds_mode(root: str, label_a: str, label_b: str, seeds: tuple[int, ...]) -> None:
    """--seeds 모드: 두 라벨의 깔때기를 나란히 출력."""
    dirs_a = [str(pathlib.Path(root) / f"calcset_{label_a}_s{s}") for s in seeds]
    dirs_b = [str(pathlib.Path(root) / f"calcset_{label_b}_s{s}") for s in seeds]

    stages_a = build(dirs_a)
    stages_b = build(dirs_b)

    print(f"=== 깔때기 비교: {label_a} vs {label_b} (시드 {seeds}) ===")
    print()
    col_w = 38
    print(f"{'':12} {'─' * col_w}  {'─' * col_w}")
    print(f"{'단계':<12} {f'{label_a}':^{col_w}}  {f'{label_b}':^{col_w}}")
    print(f"{'':12} {'─' * col_w}  {'─' * col_w}")
    for i, (sa, sb) in enumerate(zip(stages_a, stages_b)):
        def fmt(s: dict) -> str:
            base = f"{s['분자']}/{s['분모']} ({s['비율']:.1%})"
            if "평균일치율" in s:
                base += f"\n    평균일치율 {s['평균일치율']:.3f}"
            return base
        print(f"{sa['단계']:<12} {fmt(sa):<{col_w}}  {fmt(sb):<{col_w}}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="깔때기 표 — 단계별 정답률")
    parser.add_argument("dirs", nargs="*", help="raw_*.jsonl이 있는 디렉토리(단독 mode)")
    parser.add_argument("--gold", default=None, help="gold_args.jsonl 경로")
    parser.add_argument("--questions", required=True, help="문제 JSON 경로")
    parser.add_argument("--seeds", default=None, help="콤마 구분 시드 목록 (예: 42,43,44)")
    parser.add_argument("--root", default=None, help="results 루트 (--seeds 사용 시 필수)")
    parser.add_argument("--label-a", default=None, help="A 라벨 (--seeds 사용 시)")
    parser.add_argument("--label-b", default=None, help="B 라벨 (--seeds 사용 시)")
    args = parser.parse_args()

    gold_path = args.gold or "eval/data/gold_args.jsonl"
    questions_path = args.questions

    if args.seeds is not None:
        if not args.root:
            print("--seeds 사용 시 --root 필수", file=sys.stderr)
            sys.exit(2)
        seeds = tuple(int(s.strip()) for s in args.seeds.split(",") if s.strip())
        if not seeds:
            print("시드 목록이 비어 있음", file=sys.stderr)
            sys.exit(2)
        label_a = args.label_a or args.dirs[0] if args.dirs else "A"
        label_b = args.label_b or args.dirs[1] if len(args.dirs) > 1 else "B"
        _print_seeds_mode(args.root, label_a, label_b, seeds)
    else:
        if not args.dirs:
            print("dirs 또는 --seeds 필요", file=sys.stderr)
            sys.exit(2)
        stages = build(args.dirs, gold_path, questions_path)
        _print_funnel(stages)


if __name__ == "__main__":
    main()
