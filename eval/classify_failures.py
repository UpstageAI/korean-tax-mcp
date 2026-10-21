"""오답 원인 분류기 (하네스 점검 10번).

raw_*.jsonl 한 줄을 읽어 오답을 7분류 중 하나로 붙인다.
"""
import argparse
import json
import os
import pathlib
import re
import sys

CATEGORIES = {
    0: "정답",
    1: "도구 미호출",
    2: "잘못된 도구 선택",
    3: "인자 오류",
    4: "도구 결과 부족·오류",
    5: "판단 오류",
    6: "집계·파싱·무응답",
    7: "실행 실패",
}

CACHE_VERSION = 2


# ── flags 계산 ────────────────────────────────────────────────────────────────────

def _compute_flags(rec: dict, law_tools: set[str], calc_tools: set[str]) -> dict:
    tcs = rec.get("tool_call_details", [])
    forced = bool(rec.get("forced_final"))
    routing_bucket = rec.get("harness_events", {}).get("routing_bucket", "")

    call_count = len(tcs)
    calc_calls = sum(1 for tc in tcs if tc.get("tool") in calc_tools)
    law_calls = sum(1 for tc in tcs if tc.get("tool") in law_tools)
    err_count = sum(1 for tc in tcs if tc.get("is_error"))

    # 최대반복: 같은 tool+args(JSON sort_keys) 조합의 최대 횟수
    combo_counts: dict[tuple[str, str], int] = {}
    for tc in tcs:
        tool = tc.get("tool", "")
        args = tc.get("args", {})
        if isinstance(args, dict):
            key = json.dumps(args, sort_keys=True, ensure_ascii=False)
        else:
            key = str(args)
        combo = (tool, key)
        combo_counts[combo] = combo_counts.get(combo, 0) + 1
    max_repeat = max(combo_counts.values()) if combo_counts else 0

    # 인자오류후복구: 계산 호출 중 일부만 is_error
    calc_errs = sum(1 for tc in tcs if tc.get("tool") in calc_tools and tc.get("is_error"))
    인자오류후복구 = (calc_calls > 0 and 0 < calc_errs < calc_calls)

    return {
        "상한소진": forced,
        "호출수": call_count,
        "계산호출수": calc_calls,
        "조문호출수": law_calls,
        "도구오류수": err_count,
        "최대반복": max_repeat,
        "인자오류후복구": 인자오류후복구,
        "라우팅주제": routing_bucket,
    }


# ── 규칙 층 ───────────────────────────────────────────────────────────────────────

def _is_valid_answer(ans) -> bool:
    """모델답["answer"]가 1~5 정수인지."""
    if ans is None:
        return False
    try:
        v = int(ans)
    except (TypeError, ValueError):
        return False
    return 1 <= v <= 5


def _parse_subclass(근거: str) -> str:
    """근거 텍스트로 '파싱'/'무응답' 판정."""
    if re.search(r"정답은\s*[①②③④⑤1-5]", 근거):
        return "파싱"
    return "무응답"


def classify_record(
    rec: dict,
    qtype: str,
    law_tools: set[str],
    calc_tools: set[str],
    api=None,
    question_body: str = "",
    model: str | None = None,
    exposed_calc_tools: list[str] | None = None,
) -> dict:
    """한 레코드를 분류. 규칙 층 → (필요 시 보충 API) → (api 있으면) 판정 층."""
    정오 = rec.get("정오", "")
    error = rec.get("error")
    모델답 = rec.get("모델답")
    근거 = rec.get("근거", "")

    flags = _compute_flags(rec, law_tools, calc_tools)

    # 1. 실행실패
    if 정오 == "실행실패" or (error and str(error).strip()):
        return {
            "연도": rec.get("연도", ""),
            "번호": rec.get("번호"),
            "정오": 정오,
            "유형": qtype,
            "분류": 7,
            "소분류": "실행실패",
            "근거": str(error) if error else "실행실패",
            "flags": flags,
        }

    # 2. 무응답 / 파싱
    answer_val = None
    if 모델답 and isinstance(모델답, dict):
        answer_val = 모델답.get("answer")
    if 정오 == "무응답" or 모델답 is None or not _is_valid_answer(answer_val):
        subclass = _parse_subclass(근거)
        return {
            "연도": rec.get("연도", ""),
            "번호": rec.get("번호"),
            "정오": 정오,
            "유형": qtype,
            "분류": 6,
            "소분류": subclass,
            "근거": 근거 or "무응답",
            "flags": flags,
        }

    # 3. 정답
    if 정오 == "O":
        return {
            "연도": rec.get("연도", ""),
            "번호": rec.get("번호"),
            "정오": 정오,
            "유형": qtype,
            "분류": 0,
            "소분류": "",
            "근거": 근거 or "",
            "flags": flags,
        }

    # 4. 계산형 + 계산 도구 호출 0회 → 분류 1 (소분류는 아래에서 보충 API로 결정)
    if qtype == "계산형" and flags["계산호출수"] == 0:
        result = {
            "연도": rec.get("연도", ""),
            "번호": rec.get("번호"),
            "정오": 정오,
            "유형": qtype,
            "분류": 1,
            "소분류": "도구 미호출",
            "근거": "계산형 문항이나 계산 도구를 호출하지 않음",
            "flags": flags,
        }
        # 보충 API: 노출된 계산 도구가 있으면 도구 유무 소분류 결정
        if api is not None and exposed_calc_tools:
            supp = _supplement_tool_availability(
                rec, api, question_body, exposed_calc_tools, model)
            if supp:
                result["소분류"] = supp["소분류"]
                result["근거"] = supp["근거"]
        return result

    # 5. 계산형 + 모든 계산 호출이 is_error → 3 (인자 오류)
    if qtype == "계산형" and flags["계산호출수"] > 0 and flags["계산호출수"] == flags["도구오류수"]:
        calc_errs = sum(1 for tc in rec.get("tool_call_details", [])
                        if tc.get("tool") in calc_tools and tc.get("is_error"))
        if calc_errs == flags["계산호출수"]:
            return {
                "연도": rec.get("연도", ""),
                "번호": rec.get("번호"),
                "정오": 정오,
                "유형": qtype,
                "분류": 3,
                "소분류": "인자 오류",
                "근거": "계산 도구 호출이 모두 검증 실패·값 오추출로 오류",
                "flags": flags,
            }

    # 6. 그 외 → 분류 None, 판정 층으로
    result = {
        "연도": rec.get("연도", ""),
        "번호": rec.get("번호"),
        "정오": 정오,
        "유형": qtype,
        "분류": None,
        "소분류": "",
        "근거": 근거 or "",
        "flags": flags,
    }

    # 판정 층 (분류가 None이고 api 있을 때만)
    if api is not None and result["분류"] is None:
        judged = _judge(result, qtype, rec.get("tool_call_details", []),
                        api, question_body, model, exposed_calc_tools)
        result["분류"] = judged["분류"]
        result["소분류"] = judged["소분류"]
        result["근거"] = judged["근거"]

    return result


def _supplement_tool_availability(
    rec: dict,
    api,
    question_body: str,
    exposed_calc_tools: list[str],
    model: str | None,
) -> dict | None:
    """계산형·분류==1일 때 도구 유무 판정용 보충 API 호출.

    반환: {"소분류": "...", "근거": "..."} 또는 None(실패 시 기존 유지).
    """
    try:
        base_url, api_key = _api_config(model)
    except Exception:
        return None

    tool_list = ", ".join(exposed_calc_tools) if exposed_calc_tools else "(없음)"
    user = (
        f"[문항 본문]\n{(question_body or '')[:2500]}\n\n"
        f"[노출된 계산 도구 목록] {tool_list}\n\n"
        f"위 목록 중 문항이 묻는 값을 계산할 도구가 있는가? "
        f"있다면 도구 이름을, 없다면 false로 답하라.\n\n"
        f"JSON 한 줄로만 답하라: {{\"도구있음\": bool, \"도구명\": \"...\" 또는 \"\"}}"
    )
    messages = [{"role": "user", "content": user}]

    try:
        resp = api(base_url, api_key, model or "solar-pro4",
                   messages, temperature=0.0, seed=0)
        choices = resp.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
    except Exception:
        return None

    m = re.search(r"\{[^{}]*\}", content)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    있음 = parsed.get("도구있음")
    도구명 = parsed.get("도구명", "")
    if isinstance(있음, bool) and 있음 and isinstance(도구명, str) and 도구명.strip():
        return {
            "소분류": f"도구 있음({도구명.strip()})",
            "근거": f"노출된 계산 도구 중 {도구명.strip()}가 문항이 묻는 값을 계산할 수 있음",
        }
    if isinstance(있음, bool) and not 있음:
        return {
            "소분류": "도구 없음",
            "근거": "노출된 계산 도구 목록에 문항이 묻는 값을 계산할 도구가 없음",
        }
    return None


# ── 판정 층 ───────────────────────────────────────────────────────────────────────

def _build_system(qtype: str, 인자오류후복구: bool) -> str:
    """분류 정의 system 프롬프트."""
    parts = [
        "당신은 하네스 점검 실행 기록을 보고 오답 원인을 분류하는 분류기입니다.",
        "오답 원인 7분류:",
        "  2 = 잘못된 도구 선택: 호출한 계산 도구가 문항 주제와 다름.",
        "  4 = 도구 결과 부족·오류: 인자는 맞는데 결과가 틀리거나, 필요한 자료(별표·조문)를 "
        "도구가 못 돌려줌.",
        "  5 = 판단 오류: 도구 결과는 맞고 충분한데, 합산·차감·보기 대조 단계에서 틀림.",
        "",
        "** 도구 호출의 인자와 결과 JSON이 사실이다. 모델의 근거 서술은 모델의 주장일 뿐이며 "
        "도구 결과와 다르면 도구 결과를 믿는다. **",
    ]
    if qtype == "계산형":
        parts.append("  3 = 값 오추출: 도구 **인자**가 문항 사실관계와 다름(필요 항목 누락, "
                     "잘못된 금액·날짜, 옵션(True/False) 잘못 지정). 도구 결과 자체는 인자대로 맞음.")
        parts.append("  계산형 기준.")
        if 인자오류후복구:
            parts.append("  ※ 이 레코드는 계산 도구 호출 중 일부가 인자 오류로 실패했으나 "
                         "이후 정상 호출로 복구됨(인자오류후복구). 3이 아닌 4·5·2 중 하나로 분류하라.")
        parts.append("  n은 2·3·4·5 중 하나. 해당 없으면 null.")
    else:
        parts.append("  서술형에서는 1(도구 미호출)·3(인자 오류)은 해당 없음. 분류 후보는 4·5 또는 None.")
        parts.append("  n은 4·5 중 하나(서술형). 해당 없으면 null.")
    parts.append("")
    parts.append("JSON 한 줄로만 답하라: {\"분류\": n, \"근거\": \"한 줄\"}")
    return "\n".join(parts)


def _build_user(rec: dict, qtype: str, question_body: str,
                correct_answer, model_answer, tools: list[dict],
                상한소진: bool, exposed_calc_tools: list[str] | None = None) -> str:
    """판정용 user 메시지."""
    body = (question_body or "")[:2500]
    lines = [f"[문항 본문]\n{body}", ""]

    if correct_answer is not None:
        lines.append(f"[정답 번호] {correct_answer}")
    else:
        lines.append("[정답 번호] (없음)")

    if model_answer is not None:
        ma = model_answer.get("answer") if isinstance(model_answer, dict) else None
        mr = model_answer.get("reason", "") if isinstance(model_answer, dict) else ""
        mr = (mr or "")[:1500]
        lines.append(f"[모델 답 번호] {ma}")
        lines.append(f"[모델 답 근거] {mr}")
    else:
        lines.append("[모델 답] (없음)")

    lines.append("")
    if tools:
        lines.append("[도구 호출 목록]")
        for i, tc in enumerate(tools, 1):
            tool = tc.get("tool", "?")
            args = tc.get("args", {})
            err = tc.get("is_error", False)
            preview = (tc.get("result_preview") or "")[:600]
            args_s = json.dumps(args, ensure_ascii=False)[:200]
            err_mark = " [오류]" if err else ""
            lines.append(f"  {i}. {tool}{err_mark}")
            lines.append(f"     인자: {args_s}")
            lines.append(f"     결과: {preview}")
    else:
        lines.append("[도구 호출] 없음")

    if exposed_calc_tools:
        lines.append("")
        lines.append(f"[노출된 계산 도구 목록] {', '.join(exposed_calc_tools)}")

    lines.append("")
    lines.append(f"[상한 소진] {'예 (forced_final)' if 상한소진 else '아니오'}")
    return "\n".join(lines)


def _parse_classify_response(content: str):
    """응답 content에서 첫 {...} JSON 추출."""
    m = re.search(r"\{[^{}]*\}", content)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _judge(
    rec: dict,
    qtype: str,
    tool_calls: list[dict],
    api,
    question_body: str,
    model: str | None,
    exposed_calc_tools: list[str] | None = None,
) -> dict:
    """판정 층: api 호출로 분류."""
    try:
        base_url, api_key = _api_config(model)
    except Exception:
        return {"분류": None, "소분류": "미판정", "근거": "API 설정 불가"}

    system = _build_system(qtype, rec["flags"]["인자오류후복구"])
    user = _build_user(
        rec, qtype, question_body,
        rec.get("정답", rec.get("correct_answer")),
        rec.get("모델답"),
        tool_calls,
        rec["flags"]["상한소진"],
        exposed_calc_tools=exposed_calc_tools,
    )
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    ALLOWED: set[int] = {2, 3, 4, 5} if qtype == "계산형" else {4, 5}

    for attempt in range(2):  # 최초 + 1회 재시도
        try:
            resp = api(base_url, api_key, model or "solar-pro4",
                       messages, temperature=0.0, seed=0)
            choices = resp.get("choices", [])
            if not choices:
                continue
            content = choices[0].get("message", {}).get("content", "")
            parsed = _parse_classify_response(content)
            if parsed and isinstance(parsed.get("분류"), int) and parsed["분류"] in ALLOWED:
                cls = parsed["분류"]
                sub = "값 오추출" if cls == 3 else ""
                return {"분류": cls,
                        "소분류": sub,
                        "근거": parsed.get("근거", "")[:500]}
        except Exception:
            continue

    return {"분류": None, "소분류": "미판정", "근거": "판정 불가"}


def _api_config(model: str | None):
    """run.get_api_config 또는 env에서 base_url·api_key 획득."""
    try:
        from eval import run_eval as _run
        if hasattr(_run, "get_api_config"):
            return _run.get_api_config()
    except Exception:
        pass
    base_url = os.environ.get("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1")
    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if not api_key:
        raise RuntimeError("UPSTAGE_API_KEY 없음")
    return base_url, api_key


# ── classify_dir ──────────────────────────────────────────────────────────────────

def _load_routing_table(routing_table: dict | None = None) -> dict | None:
    """routing_table 인자 없거나 None이면 eval/data/routing_table.json 읽기."""
    if routing_table is not None:
        return routing_table
    rt_path = pathlib.Path(__file__).parent / "data" / "routing_table.json"
    if rt_path.exists():
        try:
            return json.loads(rt_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _compute_exposed_tools(
    routing_bucket: str,
    routing_table: dict | None,
    calc_tools: set[str],
) -> tuple[list[str], bool]:
    """라우팅 버킷에 해당하는 주제 도구 ∩ calc_tools. 없으면 calc_tools 전체.

    반환: (exposed_tools, routing_on). routing_on은 버킷이 라우팅 테이블에 매칭되었는지.
    """
    if routing_table and "주제" in routing_table and routing_bucket in routing_table["주제"]:
        주제도구 = set(routing_table["주제"][routing_bucket])
        exposed = sorted(주제도구 & calc_tools)
        routing_on = True
    else:
        exposed = sorted(calc_tools)
        routing_on = False
    return exposed, routing_on


def classify_dir(dir_path, questions: dict, law_tools, calc_tools,
                 api=None, use_cache=True, judge=True,
                 routing_table: dict | None = None):
    """dir 내 raw_*.jsonl 전부를 분류. 캐시 지원."""
    d = pathlib.Path(dir_path)
    cache_path = d / "failure_classes.jsonl"
    cache: dict[tuple[str, int], dict] = {}

    if use_cache and cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (str(obj.get("연도", "")), obj.get("번호"))
                if key[0] and key[1] is not None:
                    cache[key] = obj

    raw_recs: dict[tuple[str, int], dict] = {}
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
                if not yr or no is None:
                    continue
                raw_recs[(yr, int(no))] = rec  # 마지막 줄 승리

    result: list[dict] = []
    rt = _load_routing_table(routing_table)

    for (yr, no) in sorted(raw_recs):
        rec = raw_recs[(yr, no)]
        key = (yr, no)

        # qtype 결정
        he = rec.get("harness_events", {})
        qtype = he.get("routing_qtype")
        if not qtype:
            qentry = questions.get(yr, {}).get(str(no), {})
            body = qentry.get("본문", "")
            qtype = "계산형" if _is_calc_type_star(body) else "서술형"

        # 노출 계산 도구 계산 (라우팅 버킷 기준)
        routing_bucket = he.get("routing_bucket", "")
        exposed_calc_tools, routing_on = _compute_exposed_tools(routing_bucket, rt, calc_tools)

        # 캐시 확인
        if use_cache and key in cache:
            cached = cache[key]
            cached_ver = cached.get("판정버전")
            if cached_ver == CACHE_VERSION:
                result.append(cached)
                continue
            # 버전이 다르거나 없으면 재판정

        qb = questions.get(yr, {}).get(str(no), {}).get("본문", "")
        obj = classify_record(rec, qtype, law_tools, calc_tools,
                              api=api if judge else None,
                              question_body=qb,
                              exposed_calc_tools=exposed_calc_tools if judge else None)

        # 캐시 버전 기록
        if use_cache:
            obj["판정버전"] = CACHE_VERSION
            cache[key] = obj

        result.append(obj)

    # 캐시 파일 쓰기
    if use_cache:
        with open(cache_path, "w", encoding="utf-8") as f:
            for obj in result:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return result


def _is_calc_type_star(body: str) -> bool:
    """run.is_calc_type과 동일한 로직."""
    import re as _re
    if _re.search(r"[\d,]+(?:원|개)", body):
        return True
    tail = body.rstrip("?").strip()
    if _re.search(r"(액|금액|과세표준|세액|공제액|한도)$", tail):
        return True
    return False


# ── summarize ─────────────────────────────────────────────────────────────────────

def summarize(records: list[dict]) -> dict[str, dict[int | None, int]]:
    """유형별 분류 집계. 키는 0~7 + None 항상 존재."""
    calc: dict[int | None, int] = {}
    narr: dict[int | None, int] = {}
    for n in range(8):
        calc[n] = 0
        narr[n] = 0
    calc[None] = 0
    narr[None] = 0

    for r in records:
        tbl = calc if r["유형"] == "계산형" else narr
        c = r["분류"]
        tbl[c] = tbl.get(c, 0) + 1

    return {"계산형": calc, "서술형": narr}


# ── CLI ────────────────────────────────────────────────────────────────────────────

def _load_tool_sets(args):
    """law_tools·calc_tools 집합 로드."""
    law = set()
    calc = set()

    # --law-tools / --calc-tools 파일
    tc_path = pathlib.Path(__file__).parent / "data" / "tool_catalog.json"
    if tc_path.exists():
        try:
            tc = json.loads(tc_path.read_text(encoding="utf-8"))
            law = set(tc.get("law", []))
            calc = set(tc.get("calc", []))
        except (json.JSONDecodeError, OSError):
            pass

    if args.law_tools:
        try:
            law = set(json.loads(pathlib.Path(args.law_tools).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    if args.calc_tools:
        try:
            calc = set(json.loads(pathlib.Path(args.calc_tools).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass

    # fallback: run.py 내부 함수 시도
    if not law or not calc:
        try:
            from eval import run_eval as _run
            if not law:
                law = set(getattr(_run, "_get_ktm_tool_names", lambda: [])())
            if not calc:
                calc = set(getattr(_run, "_get_ktcalc_tool_names", lambda: [])())
        except Exception:
            pass

    return law, calc


def _print_table(summ: dict[str, dict], records: list[dict]):
    """표 출력."""
    print(f"분류 | 계산형 | 서술형 | 합계")
    total_calc = sum(summ["계산형"].values())
    total_narr = sum(summ["서술형"].values())
    for n in range(8):
        cn = summ["계산형"].get(n, 0)
        nn = summ["서술형"].get(n, 0)
        t = cn + nn
        print(f"{CATEGORIES[n]} | {cn} | {nn} | {t}")
    # 미판정(None)
    cn = summ["계산형"].get(None, 0)
    nn = summ["서술형"].get(None, 0)
    t = cn + nn
    print(f"미판정 | {cn} | {nn} | {t}")

    print()
    # flags 요약
    wrong = [r for r in records if r["분류"] in (1, 2, 3, 4, 5, 6, 7) or r["분류"] is None]
    if wrong:
        소진 = sum(1 for r in wrong if r["flags"].get("상한소진"))
        print(f"오답 중 상한소진 비율: {소진}/{len(wrong)} ({소진/len(wrong):.1%})")
        반복들 = [r["flags"]["최대반복"] for r in wrong if r["flags"]["호출수"] > 0]
        if 반복들:
            print(f"평균 최대반복: {sum(반복들)/len(반복들):.2f}")
        도구오류 = sum(1 for r in wrong if r["flags"].get("도구오류수", 0) > 0)
        print(f"도구오류 있는 오답 수: {도구오류}")

    print()
    print("오답 목록:")
    for r in sorted(records, key=lambda x: (str(x.get("연도", "")), x.get("번호") or 0)):
        c = r["분류"]
        if c == 0 or c is None:
            continue
        cname = CATEGORIES.get(c, "미판정") if c is not None else "미판정"
        근거 = (r.get("근거") or "")[:70]
        print(f"  {r.get('연도','')}-{r.get('번호')} {cname} / {r['소분류']} — {근거}")


def main():
    parser = argparse.ArgumentParser(
        description="오답 원인 분류기 (하네스 점검 10번)")
    parser.add_argument("dirs", nargs="+", help="raw_*.jsonl이 있는 디렉토리")
    parser.add_argument("--questions", default=None, help="문제 JSON 경로")
    parser.add_argument("--no-judge", action="store_true", help="규칙 층만 사용")
    parser.add_argument("--no-cache", action="store_true", help="캐시 사용 안 함")
    parser.add_argument("--model", default=None, help="모델 이름")
    parser.add_argument("--law-tools", default=None, help="law 도구 목록 JSON 파일")
    parser.add_argument("--calc-tools", default=None, help="calc 도구 목록 JSON 파일")
    parser.add_argument("--routing-table", default=None, help="라우팅 테이블 JSON 파일")
    args = parser.parse_args()

    # questions
    qenv = os.environ.get("QSET_Q")
    qpath = args.questions or qenv or str(pathlib.Path(__file__).parent / "examples" / "items.json")
    try:
        questions = json.loads(pathlib.Path(qpath).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        questions = {}

    law_tools, calc_tools = _load_tool_sets(args)

    rt = None
    if args.routing_table:
        try:
            rt = json.loads(pathlib.Path(args.routing_table).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    judge = not args.no_judge
    use_cache = not args.no_cache
    model = args.model

    all_records: list[dict] = []
    for dp in args.dirs:
        records = classify_dir(dp, questions, law_tools, calc_tools,
                               api=_api_call if judge else None,
                               use_cache=use_cache, judge=judge,
                               routing_table=rt)
        all_records.extend(records)

    summ = summarize(all_records)
    _print_table(summ, all_records)


def _api_call(base_url, api_key, model, messages, temperature=0.0, seed=0):
    """기본 run.api_chat_complete 사용."""
    try:
        from eval import run_eval as _run
        if hasattr(_run, "api_chat_complete"):
            return _run.api_chat_complete(base_url, api_key, model,
                                           messages, temperature=temperature, seed=seed)
    except Exception:
        pass
    raise RuntimeError("api_chat_complete 없음")


if __name__ == "__main__":
    main()
