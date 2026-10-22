"""추출 정확도 — 정답 인자 세트와 모델 도구 호출을 대조해 인자 일치율을 측정.

작성 Claude 2026-10-22. 표준 라이브러리만 사용.
"""
import argparse
import json
import pathlib
import sys
from collections import defaultdict

# CLI로 직접 실행할 때 패키지 경로를 잡는다.
if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


# ── gold 로드 ──────────────────────────────────────────────────────────────────────

def load_gold(path: str) -> dict[tuple[str, int], dict]:
    """gold_args.jsonl을 읽어 {(연도, 번호): 레코드} 반환."""
    result: dict[tuple[str, int], dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            yr = str(obj.get("연도", ""))
            no = obj.get("번호")
            if not yr or no is None:
                continue
            result[(yr, int(no))] = obj
    return result


# ── 값 정규화 + 매칭 ──────────────────────────────────────────────────────────────

def norm_value(v) -> any:
    """비교용 정규화: bool 그대로, int/float → round(float, 4),
    str → strip, None → None, dict/list 그대로."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return round(float(v), 4)
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        return v.strip()
    return v  # dict, list 등 그대로


def _norm_numeric(v) -> float | str | None:
    """숫자 비교용 정규화: 숫자면 round(float, 4), 숫자 문자열이면 float로."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    if isinstance(v, str):
        s = v.strip()
        try:
            return round(float(s), 4)
        except (ValueError, OverflowError):
            return s
    return v


# ── 동치 적용 횟수 카운터 ─────────────────────────────────────────────────────────

_동치카운터 = {"비율": 0, "백분율": 0, "묶음": 0}


def _reset_동치카운터() -> None:
    _동치카운터["비율"] = 0
    _동치카운터["백분율"] = 0
    _동치카운터["묶음"] = 0


# ── 비율 동치 ─────────────────────────────────────────────────────────────────────

def _is_ratio_equivalent(gold_v: dict, model_v: dict) -> bool:
    """둘 다 dict이고 모든 값이 유한 비음수 숫자(bool 제외)이며
    키 집합이 같고 합이 0보다 크면 True."""
    if set(gold_v.keys()) != set(model_v.keys()):
        return False
    for v in gold_v.values():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v != v:
            return False
    for v in model_v.values():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v != v:
            return False
    if sum(gold_v.values()) == 0 or sum(model_v.values()) == 0:
        return False
    return True


def _ratio_compare(gold_v: dict, model_v: dict, tol: float = 1e-3) -> float:
    """각 키의 (값/합) 비율이 tol 이내면 1.0, 아니면 0.0."""
    gold_sum = sum(gold_v.values())
    model_sum = sum(model_v.values())
    for k in gold_v:
        g_ratio = gold_v[k] / gold_sum
        m_ratio = model_v[k] / model_sum
        if abs(g_ratio - m_ratio) > tol:
            return 0.0
    return 1.0


# ── 백분율 동치 ───────────────────────────────────────────────────────────────────

def _is_percent_equivalent(mn, gn) -> bool:
    """둘 다 float이고 하나가 0 < g ≤ 1, 다른 하나가 g×100(오차 1e-6)이면 True."""
    if not isinstance(mn, float) or not isinstance(gn, float):
        return False
    if 0 < gn <= 1 and abs(mn - gn * 100) < 1e-6:
        return True
    if 0 < mn <= 1 and abs(gn - mn * 100) < 1e-6:
        return True
    return False


_PERCENT_EXCLUDED_SUFFIXES = ("amount", "price", "금액", "base")


# ── match_value ────────────────────────────────────────────────────────────────────

def match_value(model_v, gold_v, _key: str | None = None) -> float:
    """0.0~1.0 일치율.

    스칼라: norm 후 같으면 1, 다르면 0. 숫자 문자열과 숫자는 같은 것으로 본다.
    dict:  먼저 비율 동치(모든 값이 유한 비음수 숫자, 합>0, 키 집합 동일)를 시도 →
           성립하면 비율 비교 결과(1.0/0.0) 반환.
           아니면 gold 키별 match_value 평균(gold 키 누락 시 0).
    list: dict 원소면 탐욕 매칭, 스칼라면 다중집합 교집합/gold 길이.
    백분율 동치: 스칼라에서 gold·model 중 하나가 0<g≤1, 다른 하나가 g×100이면 1.0.
    """
    if model_v is None and gold_v is None:
        return 1.0
    if model_v is None or gold_v is None:
        return 0.0

    # dict
    if isinstance(gold_v, dict):
        if not isinstance(model_v, dict):
            return 0.0
        if not gold_v:
            return 1.0
        # 비율 동치 우선 시도
        if _is_ratio_equivalent(gold_v, model_v):
            _동치카운터["비율"] += 1
            return _ratio_compare(gold_v, model_v)
        total = 0.0
        for k, gv in gold_v.items():
            mv = model_v.get(k)
            total += match_value(mv, gv, _key=k)
        return total / len(gold_v)

    # list
    if isinstance(gold_v, list):
        if not isinstance(model_v, list):
            return 0.0
        if not gold_v:
            return 1.0 if not model_v else 0.0
        if gold_v and isinstance(gold_v[0], dict):
            return _match_list_of_dicts(model_v, gold_v)
        else:
            return _match_scalar_list(model_v, gold_v)

    # 스칼라
    mn = _norm_numeric(model_v)
    gn = _norm_numeric(gold_v)
    # 백분율 동치 (금액 필드 제외)
    if _key is None or not _key.endswith(_PERCENT_EXCLUDED_SUFFIXES):
        if _is_percent_equivalent(mn, gn):
            _동치카운터["백분율"] += 1
            return 1.0
    return 1.0 if mn == gn else 0.0


def _match_list_of_dicts(model: list, gold: list) -> float:
    """gold 순서대로 각 gold 원소에 대해 model 원소 중 최고 match_value를 찾되
    한 model 원소는 한 번만 사용(탐욕)."""
    used = [False] * len(model)
    total = 0.0
    for gv in gold:
        best = 0.0
        best_idx = -1
        for i, mv in enumerate(model):
            if used[i]:
                continue
            m = match_value(mv, gv)
            if m > best:
                best = m
                best_idx = i
        if best_idx >= 0:
            used[best_idx] = True
        total += best
    return total / len(gold)


def _match_scalar_list(model: list, gold: list) -> float:
    """다중집합 교집합 크기 / gold 길이."""
    if not gold:
        return 1.0 if not model else 0.0
    gold_counts: dict[any, int] = defaultdict(int)
    for v in gold:
        nv = norm_value(v)
        gold_counts[nv] += 1
    model_counts: dict[any, int] = defaultdict(int)
    for v in model:
        nv = norm_value(v)
        model_counts[nv] += 1
    intersect = 0
    for k, gc in gold_counts.items():
        intersect += min(gc, model_counts.get(k, 0))
    return intersect / len(gold)


# ── score_call / score_record ─────────────────────────────────────────────────────

def score_call(model_args: dict, gold_args: dict) -> dict:
    """{"일치율", "누락", "틀림", "추가"}."""
    if not gold_args:
        return {"일치율": 1.0, "누락": [], "틀림": [], "추가": list(model_args.keys()) if model_args else []}
    if not model_args:
        return {"일치율": 0.0, "누락": list(gold_args.keys()), "틀림": [], "추가": []}
    누락: list[str] = []
    틀림: list[str] = []
    추가: list[str] = []
    total = 0.0
    for k, gv in gold_args.items():
        mv = model_args.get(k)
        if mv is None and gv is not None and not (isinstance(gv, (dict, list)) and not gv):
            누락.append(k)
            total += 0.0
        else:
            mv_score = match_value(mv, gv)
            total += mv_score
            if mv_score < 1.0:
                틀림.append(k)
    for k in model_args:
        if k not in gold_args:
            추가.append(k)
    일치율 = total / len(gold_args)
    return {"일치율": 일치율, "누락": 누락, "틀림": 틀림, "추가": 추가}


def score_record(rec: dict, gold: dict) -> dict:
    """추출 정확도 점수. gold['호출']이 비면 {"대상": False}만."""
    gold_calls = gold.get("호출", [])
    if not gold_calls:
        return {"대상": False}

    tool_calls = rec.get("tool_call_details", [])
    모델호출도구 = [tc.get("tool", "") for tc in tool_calls]
    정답도구 = set(c.get("도구", "") for c in gold_calls)

    도구선택 = any(t in 정답도구 for t in 모델호출도구)

    # 도구별 그룹화
    gold_by_tool: dict[str, list] = defaultdict(list)
    for gc in gold_calls:
        gold_by_tool[gc.get("도구", "")].append(gc)

    model_by_tool: dict[str, list] = defaultdict(list)
    for tc in tool_calls:
        model_by_tool[tc.get("tool", "")].append(tc)

    호출별: list[dict] = []
    총일치율 = 0.0

    for g_tool, g_calls in gold_by_tool.items():
        m_calls = model_by_tool.get(g_tool, [])
        gold_count = len(g_calls)
        model_count = len(m_calls)

        bundling = gold_count > 1 and model_count < gold_count
        factor = model_count / gold_count if bundling else 1.0

        if bundling:
            _동치카운터["묶음"] += gold_count

        for gc in g_calls:
            g_args = gc.get("인자", {})
            if not m_calls:
                s = score_call({}, g_args)
                s["도구명"] = g_tool
                if bundling:
                    s["묶음"] = True
                    s["일치율"] *= factor
                호출별.append(s)
                총일치율 += s["일치율"]
            else:
                best_score = 0.0
                best_s = None
                for tc in m_calls:
                    s = score_call(tc.get("args", {}), g_args)
                    if s["일치율"] > best_score:
                        best_score = s["일치율"]
                        best_s = s
                if best_s is not None:
                    best_s = dict(best_s)
                    best_s["도구명"] = g_tool
                    if bundling:
                        best_s["묶음"] = True
                        best_s["일치율"] *= factor
                    호출별.append(best_s)
                    총일치율 += best_s["일치율"]
                else:
                    s = score_call({}, g_args)
                    s["도구명"] = g_tool
                    if bundling:
                        s["묶음"] = True
                        s["일치율"] *= factor
                    호출별.append(s)
                    총일치율 += s["일치율"]

    n = len(gold_calls)
    평균일치율 = 총일치율 / n if n > 0 else 0.0
    완전일치 = 평균일치율 == 1.0

    return {
        "대상": True,
        "연도": rec.get("연도", ""),
        "번호": rec.get("번호"),
        "정오": rec.get("정오", ""),
        "도구선택": 도구선택,
        "일치율": 평균일치율,
        "완전일치": 완전일치,
        "호출별": 호출별,
    }


# ── run_dirs ───────────────────────────────────────────────────────────────────────

def run_dirs(dirs: list[str], gold_path: str = "eval/data/gold_args.jsonl"
             ) -> tuple[list[dict], dict]:
    """각 dir의 raw_*.jsonl을 gold와 대조.

    요약: {"실행", "도구선택률", "평균일치율", "완전일치율",
           "정오별_평균일치율", "필드별_틀림횟수", "동치_적용_횟수"}.
    각 dir에 extract_accuracy.jsonl 저장.
    """
    _reset_동치카운터()
    gold = load_gold(gold_path)
    all_rows: list[dict] = []
    dir_rows_map: dict[str, list[dict]] = {}

    대상외 = 0
    for d in dirs:
        dp = pathlib.Path(d)
        rows: list[dict] = []
        for fp in sorted(dp.glob("raw_*.jsonl")):
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
                    if not yr or no is None:
                        continue
                    key = (yr, int(no))
                    g = gold.get(key)
                    if g is None:
                        continue
                    scored = score_record(rec, g)
                    if not scored.get("대상"):
                        대상외 += 1
                        continue
                    scored["dir"] = dp.name
                    rows.append(scored)
        dir_rows_map[d] = rows
        all_rows.extend(rows)
        out_path = dp / "extract_accuracy.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 요약
    n_total = len(all_rows)
    n_tool_choice = sum(1 for r in all_rows if r.get("도구선택"))
    n_full = sum(1 for r in all_rows if r.get("완전일치"))
    총일치율_sum = sum(r.get("일치율", 0.0) for r in all_rows)

    avg_match = 총일치율_sum / n_total if n_total > 0 else 0.0
    도구선택률 = n_tool_choice / n_total if n_total > 0 else 0.0
    완전일치율 = n_full / n_total if n_total > 0 else 0.0

    정오별: dict[str, list[float]] = defaultdict(list)
    필드별_틀림: dict[str, int] = defaultdict(int)
    for r in all_rows:
        jung = r.get("정오", "")
        if r.get("일치율") is not None:
            정오별[jung].append(r["일치율"])
        for cb in r.get("호출별", []):
            for k in cb.get("틀림", []):
                필드별_틀림[f"{cb.get('도구명','?')}.{k}"] += 1

    정오별_평균 = {}
    for j, vals in 정오별.items():
        정오별_평균[j] = sum(vals) / len(vals) if vals else 0.0

    요약 = {
        "실행": n_total,
        "대상외": 대상외,
        "도구선택률": 도구선택률,
        "평균일치율": avg_match,
        "완전일치율": 완전일치율,
        "정오별_평균일치율": 정오별_평균,
        "필드별_틀림횟수": dict(필드별_틀림),
        "동치_적용_횟수": dict(_동치카운터),
    }
    return all_rows, 요약


# ── CLI ────────────────────────────────────────────────────────────────────────────

def _print_summary(summary: dict, rows: list[dict], dirs: list[str]) -> None:
    print("=== 추출 정확도 요약 ===")
    print(f"실행: {summary['실행']}")
    print(f"도구선택률: {summary['도구선택률']:.3f}")
    print(f"평균일치율: {summary['평균일치율']:.3f}")
    print(f"완전일치율: {summary['완전일치율']:.3f}")
    print()
    print("정오별 평균일치율:")
    for j, v in sorted(summary["정오별_평균일치율"].items()):
        print(f"  {j}: {v:.3f}")
    print()
    if summary["필드별_틀림횟수"]:
        print("필드별 틀림 횟수 (상위 20):")
        items = sorted(summary["필드별_틀림횟수"].items(), key=lambda x: -x[1])[:20]
        for k, v in items:
            print(f"  {k}: {v}")
        print()
    # 문항별 표
    문항별: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for r in rows:
        key = (r.get("연도", ""), r.get("번호"))
        seed_label = r.get("dir", "")
        문항별[key][seed_label] = r

    print("문항별 (연도-번호 | 시드별 정오 일치율% 누락 틀림):")
    for (yr, no), seed_map in sorted(문항별.items()):
        parts = []
        for seed, r in sorted(seed_map.items()):
            일치율 = r.get("일치율", 0.0)
            호출별 = r.get("호출별", [])
            누락_set = set()
            틀림_set = set()
            for cb in 호출별:
                for k in cb.get("누락", []):
                    누락_set.add(f"{cb.get('도구명','?')}.{k}")
                for k in cb.get("틀림", []):
                    틀림_set.add(f"{cb.get('도구명','?')}.{k}")
            누락_str = ",".join(sorted(누락_set)) if 누락_set else "-"
            틀림_str = ",".join(sorted(틀림_set)) if 틀림_set else "-"
            parts.append(f"{r.get('정오','')} {일치율:.0%} 누락={누락_str} 틀림={틀림_str}")
        print(f"  {yr}-{no}: " + " | ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description="추출 정확도 — 정답 인자 대조")
    parser.add_argument("dirs", nargs="+", help="raw_*.jsonl이 있는 디렉토리")
    parser.add_argument("--gold", default=None, help="gold_args.jsonl 경로")
    args = parser.parse_args()

    gold_path = args.gold or "eval/data/gold_args.jsonl"
    rows, summary = run_dirs(args.dirs, gold_path)
    _print_summary(summary, rows, args.dirs)


if __name__ == "__main__":
    main()
