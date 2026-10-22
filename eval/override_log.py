"""덮어쓰기 로그 — 도구 출력에 정답이 포함됐는지, 모델이 그 값을 채택했는지를 자동 측정.

작성 Claude 2026-10-22. 표준 라이브러리만 사용.
"""
import argparse
import json
import math
import pathlib
import re
import sys
from collections import defaultdict

# CLI로 직접 실행할 때 패키지 경로를 잡는다.
if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


# ── 보기 금액 파싱 ─────────────────────────────────────────────────────────────────

_OPTION_RE = re.compile(r'([①②③④⑤])\s*([^①②③④⑤]*?)(?=(?:[①②③④⑤]|\Z))')

_CIRCLE_MAP = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}


def _parse_amount(text: str) -> int | None:
    """보기 텍스트에서 금액을 읽어 int로 반환. 숫자 아니면 None."""
    t = text.strip()
    if not t:
        return None
    만원 = t.endswith("만원")
    원 = t.endswith("원")
    if 만원:
        t = t[:-2]
    elif 원:
        t = t[:-1]
    else:
        return None
    t = t.replace(",", "").strip()
    try:
        v = int(t)
    except ValueError:
        try:
            v = int(float(t))
        except (ValueError, OverflowError):
            return None
    if 만원:
        v *= 10000
    return v


def option_values(body: str) -> dict[int, int]:
    """본문에서 ①~⑤ 뒤의 금액을 읽어 {1: 25480000, …} 반환.

    쉼표 제거, '원' 제거, '만원'이면 ×10,000, '0원'은 0.
    숫자가 아닌 보기(서술형)는 건너뛴다(빈 dict 가능).
    """
    result: dict[int, int] = {}
    for m in _OPTION_RE.finditer(body):
        num = _CIRCLE_MAP[m.group(1)]
        txt = m.group(2).strip()
        v = _parse_amount(txt)
        if v is not None:
            result[num] = v
    return result


# ── 도구 결과에서 숫자 수집 ────────────────────────────────────────────────────────

_INT_RE = re.compile(r'-?\d[\d,]*(?:\.\d+)?')


def _collect_ints(obj) -> set[int]:
    """중첩 dict/list에서 정수(또는 정수와 같은 float)를 수집. bool 제외."""
    result: set[int] = set()
    if isinstance(obj, bool):
        return result
    if isinstance(obj, int):
        result.add(obj)
    elif isinstance(obj, float):
        iv = int(obj)
        if obj == iv and not math.isinf(obj) and not math.isnan(obj):
            result.add(iv)
    elif isinstance(obj, dict):
        for v in obj.values():
            result |= _collect_ints(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            result |= _collect_ints(v)
    return result


def tool_numbers(result_text: str) -> set[int]:
    """도구 결과(JSON 문자열)를 파싱해 중첩 어디든 있는 정수값(또는 정수와 같은 float)을 전부 모은다.

    파싱 실패면 정규식으로 \\d[\\d,]* 숫자를 모은다(쉼표 제거). bool은 제외.
    """
    if not result_text:
        return set()
    try:
        data = json.loads(result_text)
        return _collect_ints(data)
    except (json.JSONDecodeError, TypeError):
        pass
    nums: set[int] = set()
    for m in _INT_RE.finditer(result_text):
        s = m.group(0).replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        if math.isinf(v) or math.isnan(v):
            continue
        iv = int(v)
        if v == iv:
            nums.add(iv)
    return nums


# ── 분류 ───────────────────────────────────────────────────────────────────────────

def _tool_content_map(rec: dict) -> dict[str, str]:
    """tool_call_id → tool 메시지 content 매핑."""
    result: dict[str, str] = {}
    for msg in rec.get("messages", []):
        if msg.get("role") == "tool":
            tid = msg.get("tool_call_id")
            if tid:
                result[tid] = msg.get("content", "") or ""
    return result


def _calc_tool_nums(rec: dict, calc_tools: set[str]) -> set[int]:
    """계산 도구 호출의 결과만 숫자로 수집."""
    nums: set[int] = set()
    msg_by_id = _tool_content_map(rec)
    tcs = rec.get("tool_call_details", [])
    tool_msgs = [msg for msg in rec.get("messages", []) if msg.get("role") == "tool"]

    for i, tc in enumerate(tcs):
        tool = tc.get("tool", "")
        if tool not in calc_tools:
            continue
        # tool_call_id로 매칭
        tc_id = tc.get("tool_call_id")
        content = None
        if tc_id and tc_id in msg_by_id:
            content = msg_by_id[tc_id]
        elif i < len(tool_msgs):
            content = tool_msgs[i].get("content", "") or ""
        if content:
            nums |= tool_numbers(content)
        # result_preview도 추가
        preview = tc.get("result_preview") or ""
        if preview:
            nums |= tool_numbers(preview)
    return nums


def classify_record(rec: dict, body: str, calc_tools: set[str]) -> dict:
    """한 레코드를 덮어쓰기 분류.

    반환 키: 연도, 번호, 정오, 도구호출(bool), 호출도구(리스트),
    정답값, 모델값, 도구값_정답포함(bool), 모델값_도구출력에있음(bool),
    구분, 이유유형(None).
    """
    tools_called = rec.get("도구호출목록", [])
    tcs = rec.get("tool_call_details", [])

    # 계산 도구 호출 여부
    calc_called = any((tc.get("tool") or "") in calc_tools for tc in tcs)
    호출도구 = [tc.get("tool", "") for tc in tcs]

    opt_vals = option_values(body)

    모델답 = rec.get("모델답")
    model_ans = None
    if isinstance(모델답, dict):
        model_ans = 모델답.get("answer")
    모델값 = opt_vals.get(model_ans) if model_ans is not None else None

    정답 = rec.get("정답")
    정답값 = opt_vals.get(정답) if 정답 is not None else None

    정오 = rec.get("정오", "")

    # 도구 결과 숫자 수집 (계산 도구만)
    tool_nums = _calc_tool_nums(rec, calc_tools) if calc_called else set()

    도구값_정답포함 = 정답값 is not None and 정답값 in tool_nums
    모델값_도구출력에있음 = 모델값 is not None and 모델값 in tool_nums

    # 구분 결정
    if not calc_called:
        구분 = "미호출"
    elif model_ans is None or 정오 in ("무응답", "실행실패"):
        구분 = "무응답"
    elif 도구값_정답포함:
        구분 = "채택" if 정오 == "O" else "덮어씀"
    else:
        구분 = "도구값없음_정답" if 정오 == "O" else "도구값없음_오답"

    return {
        "연도": rec.get("연도", ""),
        "번호": rec.get("번호"),
        "정오": 정오,
        "도구호출": calc_called,
        "호출도구": 호출도구,
        "정답값": 정답값,
        "모델값": 모델값,
        "도구값_정답포함": 도구값_정답포함,
        "모델값_도구출력에있음": 모델값_도구출력에있음,
        "구분": 구분,
        "이유유형": None,
    }


# ── 덮어씀 이유 판정 (classify_failures.py의 판정 패턴 재사용) ────────────────────

_REASON_TYPES = {
    "단위오해", "반올림·절사", "자기계산우선", "도구불신",
    "조건추가적용", "보기대조실수", "기타",
}


def judge_reason(rec: dict, body: str, api) -> str | None:
    """구분이 '덮어씀'인 레코드만. classify_failures.py의 Solar 판정 호출 방식을 재사용.

    system: "도구 호출의 인자·결과 JSON이 사실이고 모델 서술은 주장일 뿐이다."
    user: 문항 본문, 정답값, 모델값, 계산 도구 결과(전문, 각 1,500자까지), 모델 근거 서술.
    응답: {"이유유형": "...", "근거": "..."} 중 하나.
    파싱 실패·예외 → None.
    """
    tcs = rec.get("tool_call_details", [])
    calc_tools_set: set[str] = set()
    # calc_tools는 classify_record 쪽에서 넘어오는 게 바람직하나 여기서는 재추출
    # classify_failures 패턴을 따라 api 호출로만 구성
    도구결과목록 = []
    for tc in tcs:
        tool = tc.get("tool", "")
        preview = tc.get("result_preview") or ""
        # messages에서 전체 content 찾기
        content = ""
        for msg in rec.get("messages", []):
            if msg.get("role") == "tool" and msg.get("tool_call_id") == tc.get("tool_call_id"):
                content = msg.get("content", "") or ""
                break
        if not content and preview:
            content = preview
        if content:
            도구결과목록.append((tool, content[:1500]))

    모델답 = rec.get("모델답")
    근거 = ""
    if isinstance(모델답, dict):
        근거 = 모델답.get("reason", "") or ""

    정답값 = rec.get("정답값")
    모델값 = rec.get("모델값")

    도구결과_text = "\n\n".join(
        f"[{tool}] {txt}" for tool, txt in 도구결과목록
    ) if 도구결과목록 else "(도구 결과 없음)"

    user = (
        f"[문항 본문]\n{body[:2500]}\n\n"
        f"[정답값] {정답값}\n\n"
        f"[모델값] {모델값}\n\n"
        f"[계산 도구 결과]\n{도구결과_text}\n\n"
        f"[모델 근거 서술]\n{근거[:1500]}"
    )
    system = "도구 호출의 인자·결과 JSON이 사실이고 모델 서술은 주장일 뿐이다."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    for _ in range(2):
        try:
            resp = api(messages, temperature=0.0, seed=0)
            choices = resp.get("choices", [])
            if not choices:
                continue
            content = choices[0].get("message", {}).get("content", "")
            m = re.search(r"\{[^{}]*\}", content)
            if not m:
                continue
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                이유 = parsed.get("이유유형")
                if isinstance(이유, str) and 이유 in _REASON_TYPES:
                    return 이유
        except Exception:
            continue
    return None


# ── run_dirs ───────────────────────────────────────────────────────────────────────

def _load_calc_tools(calc_tools: set[str] | None) -> set[str]:
    if calc_tools is not None:
        return calc_tools
    tc_path = pathlib.Path(__file__).parent / "data" / "tool_catalog.json"
    if tc_path.exists():
        try:
            tc = json.loads(tc_path.read_text(encoding="utf-8"))
            return set(tc.get("calc", []))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def run_dirs(
    dirs: list[str],
    questions_path: str,
    calc_tools: set[str] | None = None,
    no_judge: bool = False,
    no_cache: bool = False,
    api=None,
) -> tuple[list[dict], dict]:
    """각 dir의 raw_*.jsonl 전부 처리.

    결과를 각 dir에 override_log.jsonl로 쓴다(판정버전: 1 포함).
    no_cache가 아니면 같은 (연도,번호)·같은 판정버전은 재사용.
    no_judge가 아니고 api가 있으면 '덮어씀'에 judge_reason 적용.

    반환: (결과 리스트, 요약 dict).
    """
    calc_tools = _load_calc_tools(calc_tools)
    questions = {}
    qp = pathlib.Path(questions_path)
    if qp.exists():
        try:
            questions = json.loads(qp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    all_rows: list[dict] = []

    dir_recs: dict[str, list[dict]] = {}
    for d in dirs:
        dp = pathlib.Path(d)
        recs: list[dict] = []
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
                    recs.append(rec)
        dir_recs[d] = recs

    for d in dirs:
        dp = pathlib.Path(d)
        recs = dir_recs[d]

        # dir마다 별도 캐시: 기존 override_log.jsonl에서 판정버전이 맞는 것만
        cache: dict[tuple[str, int], dict] = {}
        캐시버전 = 1
        if not no_cache:
            existing = dp / "override_log.jsonl"
            if existing.exists():
                try:
                    with open(existing, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                row = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            yr = str(row.get("연도", ""))
                            no = row.get("번호")
                            if yr and no is not None and row.get("판정버전") == 캐시버전:
                                cache[(yr, int(no))] = row
                except (OSError, json.JSONDecodeError):
                    pass

        rows: list[dict] = []
        seen_keys: set[tuple[str, int]] = set()
        for rec in recs:
            yr = str(rec.get("연도", ""))
            no = rec.get("번호")
            if not yr or no is None:
                continue
            key = (yr, int(no))
            if not no_cache and key not in seen_keys and key in cache:
                cached = cache[key]
                if cached.get("판정버전") == 캐시버전:
                    rows.append(cached)
                    seen_keys.add(key)
                    continue
            body = questions.get(yr, {}).get(str(no), {}).get("본문", "")
            row = classify_record(rec, body, calc_tools)
            if not no_judge and api is not None and row["구분"] == "덮어씀":
                row["이유유형"] = judge_reason(rec, body, api)
            row["판정버전"] = 캐시버전
            row["dir"] = dp.name
            if not no_cache:
                cache[key] = row
            seen_keys.add(key)
            rows.append(row)
        all_rows.extend(rows)
        out_path = dp / "override_log.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 요약
    by_gu = defaultdict(int)
    n_채택 = n_덮어씀 = n_도구호출 = 0
    이유별: dict[str, int] = defaultdict(int)
    도구별: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in all_rows:
        g = row["구분"]
        by_gu[g] += 1
        if g == "채택":
            n_채택 += 1
        elif g == "덮어씀":
            n_덮어씀 += 1
            if row["이유유형"]:
                이유별[row["이유유형"]] += 1
        if row["도구호출"]:
            n_도구호출 += 1
        for tool in row["호출도구"]:
            if row["도구호출"]:
                if g == "채택":
                    도구별[tool]["채택"] += 1
                elif g == "덮어씀":
                    도구별[tool]["덮어씀"] += 1

    분모 = n_채택 + n_덮어씀
    요약 = {
        "실행": len(all_rows),
        "구분별": dict(by_gu),
        "채택률": (n_채택 / 분모) if 분모 > 0 else None,
        "도구정답포함률": ((n_채택 + n_덮어씀) / n_도구호출) if n_도구호출 > 0 else None,
        "이유유형별": dict(이유별),
        "도구별": {k: dict(v) for k, v in 도구별.items()},
    }
    return all_rows, 요약


# ── CLI ────────────────────────────────────────────────────────────────────────────

def _print_summary(summary: dict, rows: list[dict], dirs: list[str]) -> None:
    print("=== 덮어쓰기 로그 요약 ===")
    print(f"실행: {summary['실행']}")
    print()
    print("구분별:")
    for g, c in sorted(summary["구분별"].items()):
        print(f"  {g}: {c}")
    print()
    ar = summary["채택률"]
    print(f"채택률: {ar:.3f}" if ar is not None else "채택률: N/A")
    di = summary["도구정답포함률"]
    print(f"도구정답포함률: {di:.3f}" if di is not None else "도구정답포함률: N/A")
    print()
    if summary["이유유형별"]:
        print("이유유형별:")
        for t, c in sorted(summary["이유유형별"].items()):
            print(f"  {t}: {c}")
        print()
    if summary["도구별"]:
        print("도구별:")
        for tool, d in sorted(summary["도구별"].items()):
            print(f"  {tool}: 채택 {d.get('채택', 0)}, 덮어씀 {d.get('덮어씀', 0)}")
        print()
    # 덮어씀 상세
    덮어씀_행 = [r for r in rows if r["구분"] == "덮어씀"]
    if 덮어씀_행:
        print("덮어씀 상세:")
        for r in 덮어씀_행:
            print(
                f"  {r['연도']}-{r['번호']} | "
                f"정답값={r['정답값']} 모델값={r['모델값']} "
                f"모델값_도구출력에있음={r['모델값_도구출력에있음']} "
                f"이유유형={r['이유유형']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="덮어쓰기 로그 — 도구 출력 정답 포함 측정")
    parser.add_argument("dirs", nargs="+", help="raw_*.jsonl이 있는 디렉토리")
    parser.add_argument("--questions", required=True, help="문제 JSON 경로")
    parser.add_argument("--no-judge", action="store_true", help="판정 API 호출 생략")
    parser.add_argument("--no-cache", action="store_true", help="캐시 사용 안 함")
    parser.add_argument("--calc-tools", default=None, help="calc 도구 목록 JSON 파일")
    args = parser.parse_args()

    calc_tools = None
    if args.calc_tools:
        try:
            calc_tools = set(json.loads(pathlib.Path(args.calc_tools).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass

    api = None
    if not args.no_judge:
        try:
            from eval import run_eval as _run
            if hasattr(_run, "api_chat_complete"):
                def _api(messages, temperature=0.0, seed=0):
                    base_url, api_key = _run.get_api_config()
                    return _run.api_chat_complete(base_url, api_key, "solar-pro4",
                                                     messages, temperature=temperature, seed=seed)
                api = _api
        except Exception:
            pass

    rows, summary = run_dirs(args.dirs, args.questions, calc_tools=calc_tools,
                              no_judge=args.no_judge, no_cache=args.no_cache, api=api)
    _print_summary(summary, rows, args.dirs)


if __name__ == "__main__":
    main()
