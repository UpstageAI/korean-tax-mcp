#!/usr/bin/env python3
"""세법 객관식 평가 — Solar Pro 4가 MCP 도구를 써서 객관식 문항을 푸는 종합 평가.

사용법:
    python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --dry-run
    python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42

환경변수:
    UPSTAGE_API_KEY   — 필수 (Upstage API 키)
    UPSTAGE_API_BASE_URL — 선택 (기본: https://api.upstage.ai/v1)
    LAW_OC            — 선택 (법제처 OC, 조문 조회용)
    RESULTS_DIR       — 선택 (결과 폴더, 기본: eval/results/)

조건:
    HARNESS_V3=1     — 중립 하네스 + 반복 차단 (기본 켜짐)
    FIND_ARTICLE=1   — find_article 도구 포함 (기본 켜짐)
    도구 호출 상한: 15회
"""

import argparse
import asyncio
import inspect
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── Upstage API가 function 스키마로 거부하는 키워드 목록 ──────────────────────────
UPSTAGE_API_DENIED_KEYS = frozenset({"anyOf", "$defs", "allOf", "oneOf", "examples"})

# ── MCP 도구 직접 호출 (서버 띄우지 않음) ─────────────────────────────────────────
import korean_tax_mcp.server as ktm
import korean_tax_calc_mcp.server as ktcalc

# ── 하네스 버전 ────────────────────────────────────────────────────────────────────
HARNESS_V3 = os.environ.get("HARNESS_V3", "1") == "1"
HARNESS_V2 = os.environ.get("HARNESS_V2") == "1"
FIND_ARTICLE_ENABLED = os.environ.get("FIND_ARTICLE", "1") == "1"

# ── 도구 호출 상한 (V3 기준) ───────────────────────────────────────────────────────
TOOL_LIMIT = 15

# ══════════════════════════════════════════════════════════════════════════════════════
# 스키마 정리
# ══════════════════════════════════════════════════════════════════════════════════════

def _clean_input_schema(raw_schema: dict) -> tuple[dict, list[str]]:
    """input_schema에서 Upstage API가 거부하는 키워드를 제거."""
    removed: list[str] = []

    def _walk(obj, path: str = "$"):
        if not isinstance(obj, dict):
            return obj
        cleaned = {}
        for k, v in obj.items():
            if k in UPSTAGE_API_DENIED_KEYS:
                removed.append(f"{path}.{k}")
                continue
            cleaned[k] = _walk(v, f"{path}.{k}")
        return cleaned

    defs = raw_schema.get("$defs", {}) if isinstance(raw_schema, dict) else {}

    def _inline(o, depth=0):
        if isinstance(o, list):
            return [_inline(x, depth) for x in o]
        if not isinstance(o, dict):
            return o
        if "$ref" in o and depth < 6:
            name = o["$ref"].split("/")[-1]
            base = dict(defs.get(name, {}))
            base.update({k: v for k, v in o.items() if k != "$ref"})
            return _inline(base, depth + 1)
        if "anyOf" in o and isinstance(o["anyOf"], list):
            alts = [a for a in o["anyOf"] if not (isinstance(a, dict) and a.get("type") == "null")]
            if len(alts) == 1:
                merged = {k: v for k, v in o.items() if k != "anyOf"}
                merged.update(_inline(alts[0], depth))
                return _inline(merged, depth)
        return {k: _inline(v, depth) for k, v in o.items() if k != "$defs"}

    cleaned = _walk(_inline(raw_schema))
    return cleaned, removed


# ══════════════════════════════════════════════════════════════════════════════════════
# 도구 이름 목록
# ══════════════════════════════════════════════════════════════════════════════════════

def _get_ktm_tool_names() -> list[str]:
    """korean-tax-mcp의 도구 이름 목록 반환."""
    names = []
    for name, obj in inspect.getmembers(ktm):
        if (callable(obj) and not name.startswith('_')
                and hasattr(obj, '__wrapped__')
                and inspect.isfunction(obj.__wrapped__)):
            try:
                inspect.signature(obj)
                names.append(name)
            except (ValueError, TypeError):
                pass
    return sorted(names)


def _get_ktcalc_tool_names() -> list[str]:
    """korean-tax-calc-mcp의 도구 이름 목록 반환."""
    names = []
    for name, obj in inspect.getmembers(ktcalc):
        if (callable(obj) and not name.startswith('_')
                and hasattr(obj, '__wrapped__')
                and inspect.isfunction(obj.__wrapped__)):
            try:
                inspect.signature(obj)
                names.append(name)
            except (ValueError, TypeError):
                pass
    return sorted(names)


KTM_TOOL_NAMES = _get_ktm_tool_names()
KTcalc_TOOL_NAMES = _get_ktcalc_tool_names()


# ══════════════════════════════════════════════════════════════════════════════════════
# 도구 목록 빌드 (native_direct + V3 + find_article)
# ══════════════════════════════════════════════════════════════════════════════════════

def _build_tools() -> tuple[list[dict], list[str], dict[str, tuple]]:
    """세법 MCP·계산 MCP의 도구를 function 스키마로 빌드.

    HARNESS_V3 + FIND_ARTICLE=1: find_article 포함.
    그 외: find_article 제외.
    """
    log_msgs: list[str] = []
    name_to_server: dict[str, tuple] = {}

    ktm_tools = asyncio.run(_async_list_tools(ktm))
    ktcalc_tools = asyncio.run(_async_list_tools(ktcalc))

    ktm_names = {t.name for t in ktm_tools}
    ktcalc_names = {t.name for t in ktcalc_tools}
    overlap = ktm_names & ktcalc_names

    if overlap:
        log_msgs.append(
            f"도구 이름 중복({len(overlap)}개): {', '.join(sorted(overlap))} → ktcalc 쪽에 calc__ 접두어"
        )

    tools: list[dict] = []
    denied_total = 0

    # find_article 제외 조건: FIND_ARTICLE=0 또는 미설정
    excluded = set() if FIND_ARTICLE_ENABLED else {"find_article"}
    for t in ktm_tools:
        if t.name in excluded:
            log_msgs.append(f"[{t.name}] 제외")
            continue
        name_to_server[t.name] = (ktm, t.name)
        description = t.description or ""
        raw_schema = t.input_schema or {}
        cleaned_schema, removed = _clean_input_schema(raw_schema)
        if removed:
            log_msgs.append(f"[{t.name}] input_schema 제거: {', '.join(removed)}")
            denied_total += len(removed)
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": description,
                "parameters": cleaned_schema,
            },
        })

    for t in ktcalc_tools:
        name = t.name
        if name in overlap:
            name = f"calc__{name}"
        name_to_server[name] = (ktcalc, t.name)
        description = t.description or ""
        raw_schema = t.input_schema or {}
        cleaned_schema, removed = _clean_input_schema(raw_schema)
        if removed:
            log_msgs.append(f"[{name}] input_schema 제거: {', '.join(removed)}")
            denied_total += len(removed)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": cleaned_schema,
            },
        })

    if denied_total:
        log_msgs.insert(0, f"Upstage API 거부 키워드 제거 총계: {denied_total}개")

    return tools, log_msgs, name_to_server


async def _async_list_tools(server) -> list:
    """mcp.list_tools()를 비동기로 호출."""
    return await server.mcp.list_tools()


# ══════════════════════════════════════════════════════════════════════════════════════
# API 설정·호출
# ══════════════════════════════════════════════════════════════════════════════════════

def get_api_config() -> tuple[str, str]:
    """API 엔드포인트와 키 반환."""
    key = os.environ.get("UPSTAGE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다."
        )
    base_url = os.environ.get("UPSTAGE_API_BASE_URL", "https://api.upstage.ai/v1")
    return base_url, key


def api_chat_complete(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    seed: int | None = None,
    max_tokens: int = 1024,
    tools: list | None = None,
) -> dict:
    """OpenAI 호환 chat completions API 호출. 재시도 3회(지수 백오프)."""
    import urllib.request
    import urllib.error

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if seed is not None:
        payload["seed"] = seed
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{base_url}/chat/completions"

    last_exc = None
    attempt = 0
    while attempt < 3:
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last_exc = e
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                time.sleep(5)
                attempt += 1
                continue
            if e.code >= 500:
                time.sleep(2 ** attempt)
                attempt += 1
                continue
            raise RuntimeError(f"API 오류 ({e.code}): {body[:200]}")
        except (urllib.error.URLError, TimeoutError) as e:
            last_exc = e
            time.sleep(2 ** attempt)
            attempt += 1
            continue
    raise RuntimeError(f"API 호출 최종 실패: {last_exc}")


# ══════════════════════════════════════════════════════════════════════════════════════
# 파싱
# ══════════════════════════════════════════════════════════════════════════════════════

ANSWER_PATTERN = re.compile(r'\{[^}]*"answer"\s*:\s*(\d)[^}]*\}')
REASON_PATTERN = re.compile(r'"reason"\s*:\s*"([^"]*)"')
ANSWER_LOOSE_PATTERN = re.compile(r'"answer"\s*:\s*"?\s*\(?([1-5①②③④⑤])')
TOOLS_PATTERN = re.compile(r'"tools_used"\s*:\s*\[([^\]]*)\]')


def parse_answer(text: str | None) -> dict | None:
    """모델 응답에서 answer, reason, tools_used 추출. 실패 시 None."""
    if text is None:
        text = ""
    m = ANSWER_PATTERN.search(text)
    if m:
        answer = int(m.group(1))
    else:
        m2 = ANSWER_LOOSE_PATTERN.search(text)
        if not m2:
            return None
        g = m2.group(1)
        answer = "①②③④⑤".index(g) + 1 if g in "①②③④⑤" else int(g)
    if answer not in range(1, 6):
        return None

    reason_m = REASON_PATTERN.search(text)
    reason = reason_m.group(1) if reason_m else ""

    tools_m = TOOLS_PATTERN.search(text)
    tools = []
    if tools_m:
        raw = tools_m.group(1)
        tools = [t.strip().strip('"') for t in raw.split(",") if t.strip()]

    return {"answer": answer, "reason": reason, "tools_used": tools}


# ══════════════════════════════════════════════════════════════════════════════════════
# 결과 타입
# ══════════════════════════════════════════════════════════════════════════════════════

@dataclass
class QuestionResult:
    """문항 실행 결과."""
    연도: str
    번호: int
    과목: str
    basis_date: str
    모델답: dict | None
    정답: int | str
    정오: str
    근거: str
    도구호출목록: list[str] = field(default_factory=list)
    토큰수: int = 0
    소요초: float = 0.0
    forced_final: bool = False
    _tool_call_records: list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════════════════════════════

def _format_tool_call_record(tc: dict) -> str:
    """도구 호출 기록을 도구 이름과 핵심 인자로 포맷."""
    args = tc.get("args", {})
    if isinstance(args, dict) and "tool" in args and "args" in args:
        tool_name = args["tool"]
        inner = args["args"]
    else:
        tool_name = tc.get("tool", "")
        inner = args if isinstance(args, dict) else {}
    key_args = []
    if "law_name" in inner:
        key_args.append(f"law={inner['law_name']}")
    if "article" in inner:
        key_args.append(f"article={inner['article']}")
    if "query" in inner:
        key_args.append(f"query={inner['query'][:30]}")
    if "base" in inner:
        key_args.append(f"base={inner['base']}")
    if "year" in inner:
        key_args.append(f"year={inner['year']}")
    if "kind" in inner:
        key_args.append(f"kind={inner['kind']}")
    if "amount" in inner:
        key_args.append(f"amount={inner['amount']}")
    suffix = f"[{','.join(key_args)}]" if key_args else ""
    return f"{tool_name}{suffix}"


def _normalize_args_for_cache(args: dict, fn_name: str | None = None) -> str:
    """캐시용 키 생성을 위해 인자 정규화."""
    if fn_name is not None:
        normalized_inner = json.dumps(args, ensure_ascii=False, sort_keys=True)
        return f"{fn_name}:{normalized_inner}"
    tool = args.get("tool", "")
    inner = args.get("args", {})
    normalized_inner = json.dumps(inner, ensure_ascii=False, sort_keys=True)
    return f"{tool}:{normalized_inner}"


def _fill_as_of_from_schema(inner_args: dict, basis_date: str, schema: dict) -> dict:
    """input_schema 기준으로 as_of/기준일 파라미터를 기준일로 자동 채움."""
    if not basis_date:
        return inner_args
    props = schema.get("properties", {})
    for pname in ("as_of", "기준일", "efYd"):
        if pname in props and not inner_args.get(pname):
            inner_args = {**inner_args, pname: basis_date}
            break
    return inner_args


def _truncate_result(result: dict, max_chars: int = 6000) -> dict:
    """도구 결과 JSON을 max_chars로 자름."""
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= max_chars:
        return result
    truncated = text[:max_chars]
    try:
        parsed = json.loads(truncated)
        parsed["_trunc_warning"] = f"(잘림: {max_chars}자 초과)"
        return parsed
    except json.JSONDecodeError:
        return {"_raw_truncated": truncated, "_trunc_warning": f"(잘림: {max_chars}자 초과)"}


def resolve_basis_date(question: dict, year: str, cmdline_basis_date: str | None) -> str:
    """문항별 기준일 우선순위에 따라 기준일을 결정한다.

    우선순위:
    1. 문항에 "기준일"(YYYYMMDD) 필드가 있으면 그 값
    2. 명령줄 --basis-date
    3. 연도 키가 4자리 숫자면 그 연도 12월 31일
    4. 오늘 날짜
    """
    if question.get("기준일"):
        return question["기준일"]
    if cmdline_basis_date:
        return cmdline_basis_date
    if len(year) == 4 and year.isdigit():
        return f"{year}1231"
    from datetime import date
    return date.today().strftime("%Y%m%d")


# ══════════════════════════════════════════════════════════════════════════════════════
# 프롬프트 (HARNESS_V3 + FIND_ARTICLE)
# ══════════════════════════════════════════════════════════════════════════════════════

SYSTEM_V3 = """세법 문제에 답하세요. 도구로 법령·자료를 확인한 뒤 답하세요.
- 계산이 필요하면 맞는 계산 도구가 있는지 먼저 보고 쓰세요.
- 같은 입력으로 같은 도구를 다시 부르지 마세요.
- 결론이 보기와 맞지 않으면 가까운 보기를 고르지 말고 입력값·조건·단서를 다시 확인하세요.
- 조문 번호가 확실하지 않으면 find_article(keyword)로 위치를 먼저 찾고, 번호를 알면 바로 law_article을 쓰세요.
응답 형식: {"reason": "근거 조문과 판단 한두 문장", "answer": 번호(1~5 숫자)}"""

NUDGE_TOOL = "답하기 전에 도구로 근거(조문 또는 계산)를 최소 1번 확인하세요."
REPEAT_MSG = "같은 입력으로 이미 받은 결과입니다. 기대와 다르면 입력값·조문·항·키워드를 바꾸거나, 지금까지 정보로 답하세요."
BLOCK_MSG = "같은 호출이 반복되어 실행하지 않았습니다. 다른 입력을 쓰거나 지금까지 정보로 답하세요."
ERROR_STREAK_MSG = "이 도구 입력이 3번 연속 거부되었습니다. 오류의 필요 입력·허용값을 확인하고, 맞는 값이 없으면 다른 도구나 조문으로 푸세요."


# ══════════════════════════════════════════════════════════════════════════════════════
# 날짜 clamping (V3)
# ══════════════════════════════════════════════════════════════════════════════════════

def _clamp_future_dates(args: dict, basis_date: str) -> tuple[dict, str | None]:
    """도구 인자에서 미래 날짜를 기준일로 clamping. 변경된 경우 note 문자열 반환."""
    if not basis_date:
        return args, None
    note_parts: list[str] = []
    exam_year = int(basis_date[:4])

    def parse_date(val: str) -> tuple[int, int, int] | None:
        if not isinstance(val, str):
            return None
        m = re.match(r'^(\d{4})(\d{2})(\d{2})$', val)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', val)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})$', val)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r'^(\d{4})$', val)
        if m:
            return (int(m.group(1)), 1, 1)
        return None

    def date_gt(val: str) -> bool:
        parsed = parse_date(val)
        if parsed is None:
            return False
        y, m, d = parsed
        ey, em, ed = int(basis_date[:4]), int(basis_date[4:6]), int(basis_date[6:8])
        return (y, m, d) > (ey, em, ed)

    for pname in ("as_of", "기준일", "efYd"):
        val = args.get(pname)
        if val and date_gt(val):
            old = val
            args = {**args, pname: basis_date}
            note_parts.append(f"기준 시점을 {old} → {basis_date}(문제 기준 시점)으로 맞췄습니다.")

    period = args.get("period")
    if period and isinstance(period, str):
        m = re.match(r'^(\d{4})(?:-(\d+))?$', period)
        if m:
            year_val = int(m.group(1))
            if year_val > exam_year:
                old = period
                args = {**args, "period": str(exam_year)}
                note_parts.append(f"기준 시점을 {old} → {exam_year}(문제 기준 시점)으로 맞췄습니다.")

    year_val = args.get("year")
    if year_val is not None:
        if isinstance(year_val, int) and year_val > exam_year:
            old = str(year_val)
            args = {**args, "year": exam_year}
            note_parts.append(f"기준 시점을 {old} → {exam_year}(문제 기준 시점)으로 맞췄습니다.")
        elif isinstance(year_val, str) and year_val.isdigit() and int(year_val) > exam_year:
            old = year_val
            args = {**args, "year": exam_year}
            note_parts.append(f"기준 시점을 {old} → {exam_year}(문제 기준 시점)으로 맞췄습니다.")

    note = "; ".join(note_parts) if note_parts else None
    return args, note


def _v3_repeat_or_block(cache_key, cached_result, call_count,
                         repeat_count, blocked_count):
    """V3 반복·차단 결과 생성. call_count는 이미 incremented된 값."""
    if call_count == 2:
        original_text = json.dumps(cached_result, ensure_ascii=False)
        repeat_result = {
            "_repeat": True,
            "_message": REPEAT_MSG,
            "_original_summary": original_text[:300],
        }
        result_json = json.dumps(repeat_result, ensure_ascii=False)
        result = cached_result
        repeat_count += 1
    else:
        block_result = {"_blocked": True, "_message": BLOCK_MSG}
        result_json = json.dumps(block_result, ensure_ascii=False)
        result = block_result
        blocked_count += 1
    return result, result_json, repeat_count, blocked_count


# ══════════════════════════════════════════════════════════════════════════════════════
# 도구 호출 래퍼
# ══════════════════════════════════════════════════════════════════════════════════════

def _sync_call_tool(server, name: str, args: dict) -> str:
    """mcp.call_tool(name, args)를 동기적으로 호출."""
    return asyncio.run(_async_call_tool(server, name, args))


async def _async_call_tool(server, name: str, args: dict) -> str:
    """mcp.call_tool(name, args)를 비동기로 호출."""
    result = await server.mcp.call_tool(name, args)
    if not result.content:
        return ""
    text = getattr(result.content[0], "text", "")
    return text if text else ""


# ══════════════════════════════════════════════════════════════════════════════════════
# 문항 실행 (native_direct + V3)
# ══════════════════════════════════════════════════════════════════════════════════════

def run_question(
    year: str,
    qno: int,
    question: dict,
    correct: int,
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    basis_date: str,
    tools: list[dict],
    schema_map: dict[str, dict],
    name_to_server: dict[str, tuple],
    progress_callback: Callable | None = None,
) -> QuestionResult:
    """문항 1개 실행 (native_direct + HARNESS_V3).

    흐름:
    1. 시스템·사용자 프롬프트 구성
    2. 도구 루프 (상한 15회): 모델 응답 → 도구 호출 → 결과 반영
    3. 답 추출 (parse_answer)
    4. 정·오 판정
    """
    t0 = time.time()
    subject = question.get("과목", "")
    body = question.get("본문", "")

    tool_calls: list[dict] = []
    tool_call_records: list[tuple[str, dict, str, bool]] = []
    call_cache: dict = {}
    final_answer = None

    messages = [
        {"role": "system", "content": SYSTEM_V3},
        {"role": "user", "content": body},
    ]

    nudged = False
    blocked_count = 0
    clamped_count = 0
    repeat_count = 0
    error_streak_count = 0
    cache_call_counts: dict[str, int] = {}
    tool_error_streak: dict[str, int] = {}
    force_break = False

    for round_idx in range(TOOL_LIMIT + 3):
        total_tool_calls = len(tool_calls)
        remaining = TOOL_LIMIT - total_tool_calls
        if total_tool_calls >= TOOL_LIMIT:
            messages.append({
                "role": "user",
                "content": "도구 호출 한도에 도달했습니다. 지금까지의 정보로 최종 답변을 JSON으로 응답하세요.",
            })
            break

        max_tok = 2048
        resp = api_chat_complete(
            base_url, api_key, model, messages,
            temperature=0.0, seed=seed + round_idx, max_tokens=max_tok,
            tools=tools,
        )

        choice = resp.get("choices", [{}])[0]
        message = choice.get("message", {})

        tcs = message.get("tool_calls", [])
        if tcs:
            for tc in tcs:
                if len(tool_calls) >= TOOL_LIMIT:
                    break
                fn_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}

                tool_calls.append({"tool": fn_name, "args": args})

                args = _fill_as_of_from_schema(args, basis_date, schema_map.get(fn_name, {}))
                if FIND_ARTICLE_ENABLED:
                    args, clamp_note = _clamp_future_dates(args, basis_date)
                    if clamp_note:
                        clamped_count += 1
                else:
                    clamp_note = None

                cache_key = _normalize_args_for_cache(args, fn_name)

                should_execute = True
                if cache_key in call_cache:
                    should_execute = False
                    cached_result = call_cache[cache_key]
                    call_count = cache_call_counts.get(cache_key, 0) + 1
                    cache_call_counts[cache_key] = call_count
                    result, result_json, repeat_count, blocked_count = _v3_repeat_or_block(
                        cache_key, cached_result, call_count,
                        repeat_count, blocked_count,
                    )
                else:
                    server_and_name = name_to_server.get(fn_name)
                    if server_and_name is None:
                        result = {"error": "알 수 없는 도구"}
                    else:
                        server, actual_name = server_and_name
                        try:
                            result_text = _sync_call_tool(server, actual_name, args)
                            try:
                                result = json.loads(result_text) if result_text else {}
                            except json.JSONDecodeError:
                                result = {"text": result_text}
                        except Exception as e:
                            result = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                    if clamp_note:
                        existing_note = result.get("_harness_note")
                        if existing_note:
                            result["_harness_note"] = existing_note + "; " + clamp_note
                        else:
                            result["_harness_note"] = clamp_note
                    result["_remaining_calls"] = remaining - 1
                    call_cache[cache_key] = result
                    cache_call_counts[cache_key] = 1
                    result_json = json.dumps(result, ensure_ascii=False)

                is_error = isinstance(result, dict) and "error" in result
                if is_error:
                    tool_error_streak[fn_name] = tool_error_streak.get(fn_name, 0) + 1
                    if tool_error_streak[fn_name] >= 3:
                        existing_note = result.get("_harness_note")
                        if existing_note:
                            result["_harness_note"] = existing_note + "; " + ERROR_STREAK_MSG
                        else:
                            result["_harness_note"] = ERROR_STREAK_MSG
                        error_streak_count += 1
                else:
                    tool_error_streak[fn_name] = 0

                preview = result_json[:200]
                tool_call_records.append((fn_name, args, preview, is_error))

                messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_json})
                total_tool_calls += 1
                if blocked_count >= 3:
                    force_break = True
                    break
        if force_break:
            break
        elif not tcs:
            if not tool_calls and not nudged:
                content = message.get("content") or ""
                if content:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": NUDGE_TOOL})
                nudged = True
                continue

            content = message.get("content") or ""
            parsed = parse_answer(content)
            if parsed:
                final_answer = parsed
                used_tools = [_format_tool_call_record(tc) for tc in tool_calls]
                final_answer["tools_used"] = used_tools
            break

    elapsed = time.time() - t0
    usage = resp.get("usage", {})
    token_count = usage.get("total_tokens", 0)

    forced_final = False
    if final_answer is None:
        messages.append({
            "role": "user",
            "content": "지금까지 정보로 최종 답변을 JSON으로만 응답하세요. {\"reason\": \"...\", \"answer\": 1} 형식이어야 합니다.",
        })
        resp2 = api_chat_complete(base_url, api_key, model, messages, temperature=0.0, seed=seed + 999, max_tokens=2048, tools=None)
        content2 = resp2.get("choices", [{}])[0].get("message", {}).get("content") or ""
        parsed_final = parse_answer(content2)
        usage2 = resp2.get("usage", {})
        token_count += usage2.get("total_tokens", 0)
        if not parsed_final:
            messages.append({"role": "assistant", "content": content2})
            messages.append({
                "role": "user",
                "content": "보기 ①~⑤ 중 정답은 반드시 하나 있습니다. 가장 맞는 번호 하나를 골라 {\"reason\": \"한두 문장\", \"answer\": 번호} 형식 JSON으로만 짧게 답하세요.",
            })
            resp3 = api_chat_complete(base_url, api_key, model, messages, temperature=0.0, seed=seed + 998, max_tokens=1024, tools=None)
            parsed_final = parse_answer(resp3.get("choices", [{}])[0].get("message", {}).get("content") or "")
            token_count += resp3.get("usage", {}).get("total_tokens", 0)
        if parsed_final:
            final_answer = parsed_final
            forced_final = True
            if tool_calls:
                final_answer["tools_used"] = [_format_tool_call_record(tc) for tc in tool_calls]

    if final_answer is None:
        정오 = "무응답"
        모델답 = None
        근거 = ""
    else:
        모델답 = final_answer
        if isinstance(correct, int):
            정답번호 = correct
            if final_answer["answer"] == 정답번호:
                정오 = "O"
            else:
                정오 = "X"
        else:
            정오 = "제외"
        근거 = final_answer.get("reason", "")

    tc_list = [_format_tool_call_record(tc) for tc in tool_calls] if tool_calls else []
    result = QuestionResult(
        연도=year,
        번호=qno,
        과목=subject,
        basis_date=basis_date,
        모델답=모델답,
        정답=correct,
        정오=정오,
        근거=근거,
        도구호출목록=tc_list,
        토큰수=token_count,
        소요초=round(elapsed, 2),
        forced_final=forced_final,
    )
    result._tool_call_records = tool_call_records

    if progress_callback:
        progress_callback(result)

    return result


# ══════════════════════════════════════════════════════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════════════════════════════════════════════════════

def load_items(path: Path) -> dict:
    """문항 JSON 로드. 형식: {"연도": {"번호": {"과목": "...", "본문": "..."}}}"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_answers(path: Path) -> dict:
    """정답 JSON 로드. 형식: {"연도": {"번호": 정답(1~5)}}"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════════════
# 결과 저장
# ══════════════════════════════════════════════════════════════════════════════════════

def _append_raw_one(res: QuestionResult, path: Path):
    """raw jsonl에 문항 1개 즉시 append."""
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "연도": res.연도,
        "번호": res.번호,
        "과목": res.과목,
        "basis_date": res.basis_date,
        "모델답": res.모델답,
        "정답": res.정답,
        "정오": res.정오,
        "근거": res.근거,
        "도구호출목록": res.도구호출목록,
        "토큰수": res.토큰수,
        "소요초": res.소요초,
        "forced_final": res.forced_final,
    }
    if res._tool_call_records:
        obj["tool_call_details"] = [
            {"tool": name, "args": args, "result_preview": preview, "is_error": is_error}
            for name, args, preview, is_error in res._tool_call_records
        ]
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def save_raw(results: list[QuestionResult], path: Path):
    """results raw jsonl 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            obj = {
                "연도": r.연도,
                "번호": r.번호,
                "과목": r.과목,
                "basis_date": r.basis_date,
                "모델답": r.모델답,
                "정답": r.정답,
                "정오": r.정오,
                "근거": r.근거,
                "도구호출목록": r.도구호출목록,
                "토큰수": r.토큰수,
                "소요초": r.소요초,
                "forced_final": r.forced_final,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def compute_summary(results: list[QuestionResult]) -> dict:
    """결과 요약 통계."""
    total = 0
    correct = 0
    wrong = 0
    unanswered = 0
    by_year: dict[str, dict[str, int]] = {}
    total_tool_calls = 0
    total_tokens = 0
    total_time = 0.0

    for r in results:
        if r.정오 == "제외":
            continue
        총목록 = by_year.setdefault(r.연도, {"total": 0, "correct": 0, "wrong": 0, "unanswered": 0})
        총목록["total"] += 1
        total += 1

        tc = len(r.도구호출목록)
        total_tool_calls += tc
        total_tokens += r.토큰수
        total_time += r.소요초

        if r.정오 == "O":
            correct += 1
            총목록["correct"] += 1
        elif r.정오 == "X":
            wrong += 1
            총목록["wrong"] += 1
        elif r.정오 == "무응답":
            unanswered += 1
            총목록["unanswered"] += 1

    accuracy = correct / total if total > 0 else 0
    by_year_summary = {}
    for yr, stats in by_year.items():
        by_year_summary[yr] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "unanswered": stats["unanswered"],
            "accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] > 0 else 0,
        }

    return {
        "condition": "native_direct",
        "harness": "V3",
        "find_article": FIND_ARTICLE_ENABLED,
        "total_응답": total,
        "correct": correct,
        "wrong": wrong,
        "unanswered": unanswered,
        "accuracy": round(accuracy, 4),
        "by_year": by_year_summary,
        "avg_tool_calls": round(total_tool_calls / total, 2) if total > 0 else 0,
        "avg_tokens": round(total_tokens / total, 0) if total > 0 else 0,
        "avg_time_sec": round(total_time / total, 2) if total > 0 else 0,
    }


def save_summary_json(summaries: list[dict], path: Path):
    """summary.json 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════════════
# 진행 표시
# ══════════════════════════════════════════════════════════════════════════════════════

def _progress_printer(total_expected: int):
    """진행 표시 콜백 생성."""
    counter = [0]

    def callback(res: QuestionResult):
        counter[0] += 1
        n = counter[0]
        tool_count = len(res.도구호출목록)
        t = res.소요초
        print(f"[{n}/{total_expected}] {res.연도} {res.번호}번 ({res.basis_date}) {res.정오} 도구{tool_count}회 {t}초", flush=True)

    return callback


# ══════════════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="세법 객관식 평가 — Solar Pro 4가 MCP 도구를 써서 객관식 문항을 푸는 종합 평가"
    )
    parser.add_argument("--qset", type=Path, default=Path("eval/examples/items.json"),
                        help="문항 파일 경로 (기본: eval/examples/items.json)")
    parser.add_argument("--anset", type=Path, default=Path("eval/examples/answers.json"),
                        help="정답 파일 경로 (기본: eval/examples/answers.json)")
    parser.add_argument("--year", type=str, default=None,
                        help="연도 필터 (기본: 문항 파일의 모든 연도)")
    parser.add_argument("--limit", type=int, default=None,
                        help="실행 문항 수 제한")
    parser.add_argument("--model", type=str, default="solar-pro4",
                        help="모델 이름 (기본: solar-pro4)")
    parser.add_argument("--seed", type=int, default=42,
                        help="랜덤 시드 (기본: 42)")
    parser.add_argument("--basis-date", type=str, default=None,
                        help="기본 기준일 (YYYYMMDD). 문항에 기준일 필드가 없으면 이 값을 사용, 없으면 연도 말 또는 오늘 날짜 사용)")
    parser.add_argument("--dry-run", action="store_true",
                        help="API 호출 없이 문항 수·도구 수만 출력하고 종료")
    parser.add_argument("--resume", action="store_true",
                        help="기존 raw 결과에서 완료된 문항 건너뛰고 이어서 실행")
    parser.add_argument("--results-dir", type=Path, default=None,
                        help="결과 폴더 (기본: eval/results/)")
    args = parser.parse_args()

    # 파일 존재 확인
    if not args.qset.exists():
        print(f"오류: 문항 파일이 없습니다: {args.qset}", file=sys.stderr)
        sys.exit(1)
    if not args.anset.exists():
        print(f"오류: 정답 파일이 없습니다: {args.anset}", file=sys.stderr)
        sys.exit(1)

    items = load_items(args.qset)
    answers = load_answers(args.anset)

    # 연도 필터링
    if args.year:
        if args.year not in items:
            print(f"오류: 문항 파일에 연도 '{args.year}'가 없습니다.", file=sys.stderr)
            sys.exit(1)
        years = [args.year]
    else:
        years = sorted(items.keys())

    # 도구 목록 빌드 (로그 출력)
    tools, tool_logs, name_to_server = _build_tools()
    schema_map = {t["function"]["name"]: t["function"].get("parameters", {}) for t in tools}

    print(f"조건: native_direct (HARNESS_V3={HARNESS_V3}, FIND_ARTICLE={FIND_ARTICLE_ENABLED})")
    print(f"도구: {len(tools)}개 (세법 MCP + 계산 MCP 직접 import)")
    for msg in tool_logs:
        print(f"  [{ 'tool' }] {msg}", flush=True)
    print(f"도구 호출 상한: {TOOL_LIMIT}회")
    print(f"모델: {args.model}, 시드: {args.seed}")
    print("-" * 50)

    if args.dry_run:
        total_items = 0
        for y in years:
            year_items = items.get(y, {})
            total_items += len(year_items)
        print(f"문항 수: {total_items}개 (연도: {', '.join(years)})")
        print(f"도구 수: {len(tools)}개")
        print()
        print("문항별 기준일:")
        for y in years:
            year_items = items.get(y, {})
            for qno_str, q in sorted(year_items.items(), key=lambda x: int(x[0])):
                qno = int(qno_str)
                bd = resolve_basis_date(q, y, args.basis_date)
                print(f"  {y} {qno}번: {bd}")
        print("dry-run 완료 — API 호출 없이 종료.")
        return

    # API 설정
    try:
        base_url, api_key = get_api_config()
    except RuntimeError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"API: {base_url}")
    print(f"문항 파일: {args.qset}")
    print(f"정답 파일: {args.anset}")
    print("-" * 50)

    results_dir = args.results_dir or Path("eval/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    # raw 경로
    raw_path = results_dir / "raw_native_direct.jsonl"

    # 완료된 문항 추적
    completed = set()
    if args.resume and raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    completed.add((obj.get("연도", ""), int(obj.get("번호", 0))))
                except json.JSONDecodeError:
                    pass
        print(f"기존 완료 문항 {len(completed)}개 로드 (--resume)", flush=True)

    # 문항 수집
    run_items: list[tuple[str, int, dict, int, str]] = []
    for y in years:
        year_items = items.get(y, {})
        year_answers = answers.get(y, {})
        for qno_str, q in sorted(year_items.items(), key=lambda x: int(x[0])):
            qno = int(qno_str)
            if args.limit is not None and len(run_items) >= args.limit:
                break
            if (y, qno) in completed:
                continue
            correct = year_answers.get(qno_str, 0)
            basis_date = resolve_basis_date(q, y, args.basis_date)
            run_items.append((y, qno, q, correct, basis_date))

    if not run_items:
        print("실행할 문항이 없습니다.", flush=True)
        return

    total_expected = len(run_items)
    progress_cb = _progress_printer(total_expected)

    results: list[QuestionResult] = []
    for y, qno, q, correct, basis_date in run_items:
        try:
            res = run_question(
                year=y,
                qno=qno,
                question=q,
                correct=correct,
                base_url=base_url,
                api_key=api_key,
                model=args.model,
                seed=args.seed,
                basis_date=basis_date,
                tools=tools,
                schema_map=schema_map,
                name_to_server=name_to_server,
                progress_callback=progress_cb,
            )
        except Exception as e:
            print(f"  !! {y} {qno}번 예외 → 무응답 처리: {type(e).__name__}: {str(e)[:200]}", flush=True)
            res = QuestionResult(
                연도=y, 번호=qno, 과목=q.get("과목", ""),
                basis_date=basis_date,
                모델답=None, 정답=correct, 정오="무응답", 근거="",
                도구호출목록=[], 토큰수=0, 소요초=0.0,
            )
        results.append(res)
        _append_raw_one(res, raw_path)

    # 요약
    summary = compute_summary(results)
    summary["year"] = args.year or "all"
    summary_path = results_dir / "summary.json"
    save_summary_json([summary], summary_path)

    print("-" * 50)
    print(f"응답: {summary['total_응답']}, 정답: {summary['correct']}, 오답: {summary['wrong']}, 무응답: {summary['unanswered']}")
    print(f"정답률: {summary['accuracy']:.1%}")
    print()
    print("연도별 정답률:")
    for yr in sorted(summary['by_year'].keys()):
        ys = summary['by_year'][yr]
        print(f"  {yr}: {ys['correct']}/{ys['total']} ({ys['accuracy']:.1%})")
    print()
    print(f"도구 호출: {summary['avg_tool_calls']}회 (평균)")
    print(f"토큰: {summary['avg_tokens']:.0f}개 (평균)")
    print(f"시간: {summary['avg_time_sec']}초 (평균)")
    print()
    print(f"raw 결과: {raw_path}")
    print(f"summary.json: {summary_path}")


if __name__ == "__main__":
    main()
