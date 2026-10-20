#!/usr/bin/env python3
"""세법 객관식 평가 — Solar Pro 4가 MCP 도구를 써서 객관식 문항을 푸는 종합 평가.

사용법:
    python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --dry-run
    python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42 --temperature 0.0

환경변수:
    UPSTAGE_API_KEY   — 필수 (Upstage API 키)
    UPSTAGE_API_BASE_URL — 선택 (기본: https://api.upstage.ai/v1)
    LAW_OC            — 선택 (법제처 OC, 조문 조회용)
    RESULTS_DIR       — 선택 (결과 폴더, 기본: eval/results/)
    CFG_OVERRIDE      — 선택 (JSON, RunConfig 필드 덮어쓰기. 예: {"routing": true, "calc_pipeline": true})

조건:
    HARNESS_V3=1     — 중립 하네스 + 반복 차단 (기본 켜짐)
    FIND_ARTICLE=1   — find_article 도구 포함 (기본 켜짐)
    도구 호출 상한: 15회 (RunConfig limit_tools로 변경 가능)
"""

import argparse
import asyncio
import dataclasses
import inspect
import json
import os
import random
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

# ── 실행 temperature (--temperature 인자로 설정, 기본 0.0) ─────────────────────────
_RUN_TEMP = 0.0

# ── 도구 호출 상한 (V3 기준, RunConfig로 제어) ─────────────────────────────────────
TOOL_LIMIT = 15

# ══════════════════════════════════════════════════════════════════════════════════════
# 실행 구성 (2단계: 실행 루프 통합)
# ══════════════════════════════════════════════════════════════════════════════════════

@dataclass
class RunConfig:
    """조건별 실행 구성. JSON 직렬화 가능.

    system_prompt/user_prompt: 프롬프트 상수 이름 (문자열).
    tool_set: "direct" | "tree" | "meta" | "none".
    repeat_block: True(일반 반복 안내) | "3rd_only"(3회째 차단) | False(비활성화).
    extra: 조건별 특수 옵션 (예: native_annot의 도구 교체).
    """
    name: str
    system_prompt: str
    user_prompt: str
    tool_set: str                 # "direct" | "tree" | "meta" | "none"
    limit_tools: int
    truncate_chars: int | None
    repeat_block: bool | str      # True | "3rd_only" | False
    clamp_dates: bool
    error_streak: bool
    nudge_tool: bool
    keep_content: bool
    extra: dict                   # 조건별 특수 옵션
    routing: bool = False         # 4단계 라우팅 (CFG_OVERRIDE로 켬)
    calc_pipeline: bool = False   # 5단계 계산형 파이프라인 (CFG_OVERRIDE로 켬)


# HARNESS_V2/V3에 따라 기본 시스템·사용자 프롬프트 결정
if HARNESS_V2:
    _ND_SYSTEM = "SYSTEM_NEUTRAL"
    _ND_USER = "USER_NEUTRAL"
    _NT_SYSTEM = "SYSTEM_NEUTRAL"
    _NT_USER = "USER_NEUTRAL"
else:
    _ND_SYSTEM = "SYSTEM_NEUTRAL_V3" if HARNESS_V3 else "SYSTEM_NATIVEDIRECT"
    _ND_USER = "USER_NATIVEDIRECT"
    _NT_SYSTEM = "SYSTEM_NATIVETREE"
    _NT_USER = "USER_NATIVETREE"

PRESETS: dict[str, RunConfig] = {
    # native_direct: V3 주력 (HARNESS_V3) — 중립 프롬프트, 안전장치 전부 ON
    "native_direct": RunConfig(
        name="native_direct",
        system_prompt=_ND_SYSTEM,
        user_prompt=_ND_USER,
        tool_set="direct",
        limit_tools=15,
        truncate_chars=None,
        repeat_block=True,
        clamp_dates=True,
        error_streak=True,
        nudge_tool=True,
        keep_content=True,
        extra={},
    ),
    # native_direct2: 도구 12회, 3000자 자름, 3회째 차단
    "native_direct2": RunConfig(
        name="native_direct2",
        system_prompt="SYSTEM_NATIVEDIRECT2",
        user_prompt="USER_NATIVEDIRECT2",
        tool_set="direct",
        limit_tools=12,
        truncate_chars=3000,
        repeat_block="3rd_only",
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={},
    ),
    # native2: 도구 8회, 3000자 자름, 3회째 차단
    "native2": RunConfig(
        name="native2",
        system_prompt="SYSTEM_NATIVE2",
        user_prompt="USER_NATIVE2",
        tool_set="direct",
        limit_tools=8,
        truncate_chars=3000,
        repeat_block="3rd_only",
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={},
    ),
    # native_tree: tree 도구, 안전장치 전부 OFF (중복 안내만)
    "native_tree": RunConfig(
        name="native_tree",
        system_prompt=_NT_SYSTEM,
        user_prompt=_NT_USER,
        tool_set="tree",
        limit_tools=15,
        truncate_chars=None,
        repeat_block=False,
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={},
    ),
    # native_search: V2 색인 검색 도구 추가
    "native_search": RunConfig(
        name="native_search",
        system_prompt=_NT_SYSTEM,
        user_prompt=_NT_USER,
        tool_set="tree",
        limit_tools=15,
        truncate_chars=None,
        repeat_block=False,
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={"add_tools": ["search_articles"]},
    ),
    # native_annot: 원문 보존 + 관계 표시 도구
    "native_annot": RunConfig(
        name="native_annot",
        system_prompt=_NT_SYSTEM,
        user_prompt=_NT_USER,
        tool_set="tree",
        limit_tools=15,
        truncate_chars=None,
        repeat_block=False,
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={"replace_tool": "article_structure", "replacement_tool": "article_annotated", "add_tools": ["search_articles"]},
    ),
    # B: meta 도구, nudge OFF
    "B": RunConfig(
        name="B",
        system_prompt="SYSTEM_B",
        user_prompt="USER_B",
        tool_set="meta",
        limit_tools=8,
        truncate_chars=None,
        repeat_block=False,
        clamp_dates=False,
        error_streak=False,
        nudge_tool=False,
        keep_content=False,
        extra={},
    ),
    # B2: meta 도구, nudge ON
    "B2": RunConfig(
        name="B2",
        system_prompt="SYSTEM_B2",
        user_prompt="USER_B2",
        tool_set="meta",
        limit_tools=8,
        truncate_chars=None,
        repeat_block=False,
        clamp_dates=False,
        error_streak=False,
        nudge_tool=True,
        keep_content=False,
        extra={},
    ),
}


def preset(name: str) -> RunConfig:
    """조건 이름으로 프리셋 구성 반환."""
    if name not in PRESETS:
        raise ValueError(f"Unknown condition: {name}")
    return PRESETS[name]


def with_overrides(cfg: RunConfig, overrides: dict) -> RunConfig:
    """원본 불변, 새 구성 반환. overrides의 키만 덮어씀."""
    return dataclasses.replace(cfg, **overrides)


def effective_config(name: str) -> RunConfig:
    """프리셋 + 환경변수(CFG_OVERRIDE JSON) 덮어쓰기 적용."""
    cfg = preset(name)
    override_json = os.environ.get("CFG_OVERRIDE", "")
    if override_json:
        try:
            overrides = json.loads(override_json)
            cfg = with_overrides(cfg, overrides)
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


# ── 4단계 라우팅 상수 ─────────────────────────────────────────────────────────────
# 프롬프트·설명 이름은 raw run_config에 기록용 (실체는 함수 아래).
ROUTING_CLASSIFY_PROMPT_NAME = "ROUTING_CLASSIFY_PROMPT"
ROUTING_EXPAND_TOOL_NAME = "expand_tools"

# 라우팅 매핑표 (eval/data/routing_table.json, 수정 금지 — 읽기만)
_ROUTING_TABLE = json.loads((Path(__file__).parent / "data/routing_table.json").read_text())
_ROUTING_TOPIC_KEYS = list(_ROUTING_TABLE["주제"].keys())


def replay_assistant_message(message: dict, keep_content: bool) -> dict:
    """공통 루프용 assistant 메시지 재구성.

    keep_content=True: 모델 원 메시지(content + tool_calls 전체)를 그대로 유지.
    keep_content=False: 옛 방식(content=None, 호출별 분리 전 상태).
    """
    if keep_content:
        return {"role": "assistant", "content": message.get("content"), "tool_calls": message.get("tool_calls", [])}
    return {"role": "assistant", "content": None, "tool_calls": message.get("tool_calls", [])}

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


def _build_native_direct_tools() -> tuple[list[dict], list[str], dict[str, tuple]]:
    """native_direct 도구 빌드 (calc_pipeline에서 fallback용으로 사용)."""
    return _build_tools()


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
    reasoning_effort: str | None = None,
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
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort

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
        except json.JSONDecodeError as e:
            last_exc = e
            time.sleep(2 ** attempt)
            attempt += 1
            continue
        except UnicodeDecodeError as e:
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
    basis_date: str = ""
    모델답: dict | None = None
    정답: int | str = 0
    정오: str = "무응답"
    근거: str = ""
    도구호출목록: list[str] = field(default_factory=list)
    토큰수: int = 0          # total_tokens (누적)
    입력토큰: int = 0        # 누적 prompt_tokens
    출력토큰: int = 0        # 누적 completion_tokens
    소요초: float = 0.0
    forced_final: bool = False
    reasoning: str | None = None
    reasoning_tokens: int = 0
    _tool_call_records: list = field(default_factory=list)
    _messages: list[dict] | None = None
    _run_config: dict | None = None
    _cfg: dict | None = None
    _harness_events: dict[str, Any] | None = None
    _error_raw: str | None = None
    _중복호출수: int = 0
    _도구미사용: bool = False


class UsageAcc:
    """라운드별 API usage를 누적하는 어카운터.

    add(resp) → prompt/completion/total/reasoning 누적.
    usage 키가 없는 응답은 안전하게 무시.
    """

    def __init__(self) -> None:
        self.prompt: int = 0
        self.completion: int = 0
        self.total: int = 0
        self.reasoning: int = 0

    def add(self, resp: dict) -> None:
        usage = resp.get("usage")
        if not isinstance(usage, dict):
            return
        self.prompt += usage.get("prompt_tokens", 0) or 0
        self.completion += usage.get("completion_tokens", 0) or 0
        self.total += usage.get("total_tokens", 0) or 0
        details = usage.get("completion_tokens_details")
        if isinstance(details, dict):
            self.reasoning += details.get("reasoning_tokens", 0) or 0


@dataclass
class LoopResult:
    """run_tool_loop 실행 결과."""
    final_answer: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_records: list[tuple[str, dict, str, bool]] = field(default_factory=list)
    usage_acc: UsageAcc = field(default_factory=UsageAcc)
    duplicate_count: int = 0
    nudged: bool = False
    clamped_count: int = 0
    repeat_count: int = 0
    blocked_count: int = 0
    error_streak_count: int = 0
    force_break: bool = False
    last_assistant_content: str | None = None
    routing_bucket: str = ""
    routing_qtype: str = ""
    routing_expand_count: int = 0
    calc_pipeline_result: dict | None = None


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
REPEAT_MSG = "같은 입력으로 이미 받은 결과입니다. 기대가 다르면 입력값·조문·항·키워드를 바꾸거나, 지금까지 정보로 답하세요."
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
# 도구 오류 처리 (3단계)
# ══════════════════════════════════════════════════════════════════════════════════════

def coerce_args(args: dict, schema: dict) -> tuple[dict, list[str]]:
    """인자 값을 스키마의 properties 타입에 맞춰 변환.

    integer/number: '500,000,000원' → 500000000 (쉼표·'원'만 제거, 한글 단위 '억·만'은 변환하지 않음)
    boolean: '예·네·yes·true·해당·있음' → True, '아니오·no·false·해당없음·없음' → False
    string enum: 그대로 유지
    변환한 항목은 notes 리스트에 "base: '500,000,000원'→500000000" 형식으로 기록.
    """
    props = schema.get("properties", {})
    notes: list[str] = []
    out: dict[str, Any] = {}
    for key, val in args.items():
        prop = props.get(key, {})
        ptype = prop.get("type")
        if ptype == "integer" and isinstance(val, str):
            cleaned = val.replace(",", "").replace("원", "").strip()
            try:
                out[key] = int(cleaned)
                notes.append(f"{key}: {val!r}→{out[key]}")
                continue
            except ValueError:
                out[key] = val
        elif ptype == "number" and isinstance(val, str):
            cleaned = val.replace(",", "").replace("원", "").strip()
            try:
                num = float(cleaned)
                out[key] = int(num) if num == int(num) else num
                notes.append(f"{key}: {val!r}→{out[key]}")
                continue
            except ValueError:
                out[key] = val
        elif ptype == "boolean" and isinstance(val, str):
            v = val.strip().lower()
            if v in {"예", "네", "yes", "true", "해당", "있음", "y", "1"}:
                out[key] = True
                notes.append(f"{key}: {val!r}→True")
                continue
            if v in {"아니오", "아니요", "no", "false", "해당없음", "없음", "n", "0"}:
                out[key] = False
                notes.append(f"{key}: {val!r}→False")
                continue
        out[key] = val
    return out, notes


def validate_args(args: dict, schema: dict, tool_name: str) -> dict | None:
    """인자 검증. 문제 있으면 오류 dict, 정상이면 None.

    누락 required, 스키마에 없는 키(불필요), enum 위반, 타입 불일치를 모아
    {"error": "입력 오류: …", "도구": tool_name, "누락": [...], "불필요": [...],
     "허용값": {키: [...]}, "타입오류": {키: "기대 타입"}, "예시": {…}} 반환.
    bool은 boolean만 허용 (int 0/1 거부).
    """
    props = schema.get("properties", {})
    required = schema.get("required", [])
    errors: list[str] = []
    누락: list[str] = []
    불필요: list[str] = []
    허용값: dict[str, list] = {}
    타입오류: dict[str, str] = {}
    예시: dict[str, Any] = {}

    for key in required:
        예시[key] = _make_example(props.get(key, {}))

    for key in required:
        if key not in args:
            누락.append(key)
            errors.append(f"{key} 누락")

    for key in args:
        if key not in props:
            불필요.append(key)
            errors.append(f"불필요한 키 '{key}'")

    for key, val in args.items():
        if key not in props:
            continue
        prop = props[key]
        ptype = prop.get("type")
        enum = prop.get("enum")
        if enum is not None and val not in enum:
            허용값[key] = list(enum)
            errors.append(f"'{key}'은(는) 허용값이 {list(enum)}인데 '{val}'이 입력됨")
        elif ptype == "integer" and not isinstance(val, bool) and not (isinstance(val, int) and not isinstance(val, bool)):
            타입오류[key] = "integer"
            errors.append(f"'{key}'은(는) 정수여야 하는데 '{val}'({type(val).__name__})이 입력됨")
        elif ptype == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
            타입오류[key] = "number"
            errors.append(f"'{key}'은(는) 숫자여야 하는데 '{val}'({type(val).__name__})이 입력됨")
        elif ptype == "boolean" and not isinstance(val, bool):
            타입오류[key] = "boolean"
            errors.append(f"'{key}'은(는) boolean이어야 하는데 '{val}'({type(val).__name__})이 입력됨")
        elif ptype == "string" and not isinstance(val, str):
            타입오류[key] = "string"
            errors.append(f"'{key}'은(는) 문자열이어야 하는데 {type(val).__name__}이 입력됨")

    if not errors:
        return None

    return {
        "error": f"입력 오류: {'; '.join(errors)}",
        "도구": tool_name,
        "누락": 누락,
        "불필요": 불필요,
        "허용값": 허용값,
        "타입오류": 타입오류,
        "예시": 예시,
    }


def _make_example(prop: dict) -> Any:
    """스키마 prop에 따른 예시값 생성."""
    ptype = prop.get("type")
    enum = prop.get("enum")
    if enum:
        return enum[0]
    if ptype == "integer":
        return 500000000
    if ptype == "number":
        return 500000000.0
    if ptype == "boolean":
        return True
    return "…"  # string 또는 기타


def format_tool_error(exc: Exception, tool_name: str, schema: dict) -> dict:
    """예외를 절단 없이 전체 메시지로 구조화된 오류 dict로 변환.

    {"error": "타입이름: 메시지 전문", "도구": tool_name,
     "필수": required 목록, "입력형식": properties 요약(키: 타입·설명 40자)}
    """
    msg = f"{type(exc).__name__}: {exc}"
    props = schema.get("properties", {})
    required = schema.get("required", [])
    입력형식: dict[str, str] = {}
    for k, v in props.items():
        ptype = v.get("type", "any")
        desc = (v.get("description") or "")[:40]
        입력형식[k] = f"{ptype}" + (f" ({desc})" if desc else "")
    return {
        "error": msg,
        "도구": tool_name,
        "필수": list(required),
        "입력형식": 입력형식,
    }


def normalize_tool_result(text: str, tool_name: str) -> dict:
    """도구 결과 텍스트를 정규화.

    JSON이면 파싱, "Error executing tool"·"error"·"Traceback"으로 시작하면
    {"error": 전문}, 그 외 {"text": text}.
    """
    if not isinstance(text, str):
        return {"text": str(text)}
    text_stripped = text.strip()
    if not text_stripped:
        return {}
    try:
        parsed = json.loads(text_stripped)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    lower = text_stripped.lower()
    if lower.startswith("error executing tool") or lower.startswith("error:") or lower.startswith("traceback"):
        return {"error": text_stripped}
    return {"text": text_stripped}

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


def execute_tool_call(
    tc: dict,
    tools: list[dict],
    name_to_server: dict[str, tuple],
    cfg: RunConfig,
    exam_date: str,
) -> dict:
    """도구 호출 1개를 파싱→_fill_as_of→coerce→validate→실행→normalize→예외처리까지 수행.

    validate에서 오류면 실행 없이 오류 반환. coerce notes는 result["_harness_note"]에 병합.
    """
    fn_name = tc.get("function", {}).get("name", "")
    args_str = tc.get("function", {}).get("arguments", "{}")
    try:
        args = json.loads(args_str) if args_str else {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    # 스키마를 tools 목록에서 찾는다 (schemas는 별도로 전달하지 않음)
    tool_schema: dict = {}
    for t in tools:
        if t.get("function", {}).get("name") == fn_name:
            tool_schema = t.get("function", {}).get("parameters", {}) or {}
            break

    # _fill_as_of_from_schema
    args = _fill_as_of_from_schema(args, exam_date, tool_schema)

    # coerce
    args, notes = coerce_args(args, tool_schema)

    # validate (오류면 실행 없이 반환)
    validation_err = validate_args(args, tool_schema, fn_name)
    if validation_err is not None:
        result = validation_err
        result["_harness_note"] = "; ".join(notes) if notes else None
        return result

    # 실행
    try:
        if cfg.tool_set == "direct":
            server_and_name = name_to_server.get(fn_name)
            if server_and_name is None:
                result = {"error": f"알 수 없는 도구: {fn_name}"}
            else:
                server, actual_name = server_and_name
                if server == "_local_article_structure":
                    import structure_tool as _st
                    result = _st.article_structure(
                        law_name=args.get("law_name", ""),
                        article=args.get("article", ""),
                        paragraph=args.get("paragraph"),
                    )
                    result_text = json.dumps(result, ensure_ascii=False)
                elif server == "_local_annot":
                    import os as _o, sys as _s
                    _td = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "요건트리")
                    if _td not in _s.path:
                        _s.path.insert(0, _td)
                    import annotate as _AN
                    result_text = _AN.article_annotated(
                        args.get("law_name", ""), args.get("article", ""), args.get("paragraph") or None
                    )
                    result = {"text": result_text}
                elif server == "_local_search":
                    import os as _o, sys as _s
                    from pathlib import Path as _P
                    _td = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "요건트리")
                    if _td not in _s.path:
                        _s.path.insert(0, _td)
                    import retrieve as _R
                    _ln = (args.get("law_name") or "").replace(" 시행령", "").replace(" 시행규칙", "").strip()
                    _laws = [_ln] if _ln in _BASE_LAWS else _BASE_LAWS
                    _hits = _R.search(args.get("query", ""), _laws, k=5, index_dir=_P(_td) / "index_V2")
                    result = {"결과": [{"법령": h["법령"], "조": h["조"], "항": h.get("번호", ""), "원문": (h.get("원문") or "")[:150]} for h in _hits]}
                    result_text = json.dumps(result, ensure_ascii=False)
                else:
                    result_text = _sync_call_tool(server, actual_name, args)
                    if not (isinstance(server, str) and server.startswith("_local")):
                        try:
                            result = json.loads(result_text) if result_text else {}
                        except (json.JSONDecodeError, ValueError):
                            result = {"text": result_text}
                    else:
                        result = {"text": result_text}
        elif cfg.tool_set == "meta":
            tool_name_arg = args.get("tool", "")
            inner_args = args.get("args", {})
            if fn_name == "korean_tax_mcp":
                result = call_ktm(tool_name_arg, inner_args, exam_date, schema=tool_schema)
            elif fn_name == "korean_tax_calc_mcp":
                result = call_ktcalc(tool_name_arg, inner_args, exam_date, schema=tool_schema)
            else:
                result = {"error": f"알 수 없는 도구: {fn_name}"}
        else:
            result = {"error": f"알 수 없는 도구: {fn_name}"}
    except Exception as exc:
        result = format_tool_error(exc, fn_name, tool_schema)

    # normalize (MCP가 텍스트 오류를 돌려준 경우 detection)
    if "error" not in result and "text" not in result:
        result = normalize_tool_result(json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result, fn_name)

    # coerce notes 병합
    if notes:
        existing = result.get("_harness_note")
        result["_harness_note"] = (existing + "; " + "; ".join(notes)) if existing else "; ".join(notes)

    return result


def call_ktm(tool_name: str, args: dict, exam_date: str = "", schema: dict | None = None) -> dict:
    """korean-tax-mcp 도구 호출 래퍼."""
    if schema is None:
        schema = {}
    args = _fill_as_of_from_schema(args, exam_date, schema)
    args, _notes = coerce_args(args, schema)
    validation_err = validate_args(args, schema, tool_name)
    if validation_err is not None:
        return validation_err
    try:
        result_text = _sync_call_tool(ktm, tool_name, args)
        try:
            result = json.loads(result_text) if result_text else {}
        except (json.JSONDecodeError, ValueError):
            result = {"text": result_text}
    except Exception as exc:
        result = format_tool_error(exc, tool_name, schema)
    return result


def call_ktcalc(tool_name: str, args: dict, exam_date: str = "", schema: dict | None = None) -> dict:
    """korean-tax-calc-mcp 도구 호출 래퍼."""
    if schema is None:
        schema = {}
    args = _fill_as_of_from_schema(args, exam_date, schema)
    args, _notes = coerce_args(args, schema)
    validation_err = validate_args(args, schema, tool_name)
    if validation_err is not None:
        return validation_err
    try:
        result_text = _sync_call_tool(ktcalc, tool_name, args)
        try:
            result = json.loads(result_text) if result_text else {}
        except (json.JSONDecodeError, ValueError):
            result = {"text": result_text}
    except Exception as exc:
        result = format_tool_error(exc, tool_name, schema)
    return result

# ══════════════════════════════════════════════════════════════════════════════════════
# 4단계 2단계 라우팅: 분류·선택·상태
# ══════════════════════════════════════════════════════════════════════════════════════

CLASSIFY_SYSTEM = (
    "세법 문항을 아래 주제 키 중 하나와 유형(서술형|계산형)으로 분류하세요.\n"
    "답변은 JSON만: {\"주제\": \"<키>\", \"유형\": \"서술형\"|\"계산형\"}\n"
    "위 목록에 없는 경우는 {\"주제\": \"기타\", \"유형\": \"계산형\"} 또는 {\"주제\": \"기타\", \"유형\": \"서술형\"}으로."
)
CLASSIFY_USER_TEMPLATE = "문항:\n{body}\n\n주제 키 목록:\n{keys}"


def classify_question(
    body: str,
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    usage_acc: UsageAcc,
) -> tuple[str, str]:
    """짧은 분류 호출 1회. (bucket, qtype) 반환.

    파싱 실패·목록 밖 키면 ("기타", is_calc_type 추정 qtype) 반환.
    """
    keys_text = "\n".join(f"- {k}" for k in _ROUTING_TOPIC_KEYS)
    user_msg = CLASSIFY_USER_TEMPLATE.format(body=body[:2000], keys=keys_text)
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    resp = api_chat_complete(
        base_url, api_key, model, messages,
        temperature=_RUN_TEMP, seed=seed, max_tokens=100, tools=None,
    )
    usage_acc.add(resp)
    content = (resp.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
    try:
        parsed = json.loads(content)
        bucket = parsed.get("주제", "기타")
        qtype = parsed.get("유형", "계산형" if is_calc_type(body) else "서술형")
    except (json.JSONDecodeError, ValueError):
        bucket = "기타"
        qtype = "계산형" if is_calc_type(body) else "서술형"
    if bucket not in _ROUTING_TOPIC_KEYS:
        bucket = "기타"
    return bucket, qtype


def select_tools_for_bucket(bucket: str, all_tools: list[dict], question_type: str) -> list[dict]:
    """매핑표 기반 도구 선택. 원래 스키마 그대로 반환 + expand_tools 1개 추가.

    공통 + (서술형이면 공통_서술형) + 주제 도구. bucket이 표에 없으면 all_tools 전체 + expand_tools.
    """
    name_to_tool: dict[str, dict] = {t["function"]["name"]: t for t in all_tools}
    # expand_tools 도구 구성 (원래 스키마가 없으므로 고정 스키마)
    expand_tool = {
        "type": "function",
        "function": {
            "name": ROUTING_EXPAND_TOOL_NAME,
            "description": "지금 보이는 도구로 풀 수 없을 때 다른 주제의 도구를 추가. 입력: 주제 키(enum).",
            "parameters": {
                "type": "object",
                "properties": {
                    "주제": {
                        "type": "string",
                        "enum": _ROUTING_TOPIC_KEYS,
                        "description": "추가할 주제 키",
                    },
                },
                "required": ["주제"],
                "additionalProperties": False,
            },
        },
    }

    if bucket not in _ROUTING_TABLE["주제"]:
        # 표에 없는 키: 전체 도구 + expand_tools
        out = list(all_tools) + [expand_tool]
        return out

    chosen_names: set[str] = set()
    # 공통 도구
    for n in _ROUTING_TABLE.get("공통", []):
        if n in name_to_tool:
            chosen_names.add(n)
    # 서술형이면 공통_서술형 추가
    if question_type == "서술형":
        for n in _ROUTING_TABLE.get("공통_서술형", []):
            if n in name_to_tool:
                chosen_names.add(n)
    # 주제 도구
    for n in _ROUTING_TABLE["주제"][bucket]:
        if n in name_to_tool:
            chosen_names.add(n)

    out = [name_to_tool[n] for n in sorted(chosen_names) if n in name_to_tool]
    if ROUTING_EXPAND_TOOL_NAME not in name_to_tool:
        out.append(expand_tool)
    else:
        out.append(name_to_tool[ROUTING_EXPAND_TOOL_NAME])
    return out


@dataclass
class RoutingState:
    """라우팅 상태. current_tools()가 현재 노출 목록, 확장 이력을 관리."""

    bucket: str
    question_type: str
    all_tools: list[dict]
    _expand_history: list[str] = field(default_factory=list)  # 확장된 주제 키 목록
    _max_expands: int = 2

    def current_tools(self) -> list[dict]:
        """현재 노출 도구 목록. 확장된 주제 도구를 포함."""
        if not self._expand_history:
            return select_tools_for_bucket(self.bucket, self.all_tools, self.question_type)
        # 확장된 주제들의 도구를 모두 누적 (중복 없이)
        name_to_tool = {t["function"]["name"]: t for t in self.all_tools}
        chosen: dict[str, dict] = {}
        # 최초 bucket 도구
        for n in _ROUTING_TABLE.get("공통", []):
            if n in name_to_tool:
                chosen[n] = name_to_tool[n]
        if self.question_type == "서술형":
            for n in _ROUTING_TABLE.get("공통_서술형", []):
                if n in name_to_tool:
                    chosen[n] = name_to_tool[n]
        for n in _ROUTING_TABLE["주제"][self.bucket]:
            if n in name_to_tool:
                chosen[n] = name_to_tool[n]
        # 확장된 주제 도구
        for ext_key in self._expand_history:
            if ext_key in _ROUTING_TABLE["주제"]:
                for n in _ROUTING_TABLE["주제"][ext_key]:
                    if n in name_to_tool and n not in chosen:
                        chosen[n] = name_to_tool[n]
        out = list(chosen.values())
        if ROUTING_EXPAND_TOOL_NAME not in chosen:
            out.append({
                "type": "function",
                "function": {
                    "name": ROUTING_EXPAND_TOOL_NAME,
                    "description": "지금 보이는 도구로 풀 수 없을 때 다른 주제의 도구를 추가. 입력: 주제 키(enum).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "주제": {"type": "string", "enum": _ROUTING_TOPIC_KEYS, "description": "추가할 주제 키"},
                        },
                        "required": ["주제"],
                        "additionalProperties": False,
                    },
                },
            })
        return out

    def can_expand(self) -> bool:
        return len(self._expand_history) < self._max_expands


def handle_expand_tools(args: dict, state: RoutingState) -> dict:
    """expand_tools 호출 처리. 실제 서버 호출 없이 노출 목록에 추가.

    반환: {"추가": [...도구 이름]} 또는 {"error": "...", "가능한 주제": [...]}.
    """
    topic = args.get("주제", "")
    if topic not in _ROUTING_TOPIC_KEYS:
        return {
            "error": f"알 수 없는 주제 키: {topic}",
            "가능한 주제": _ROUTING_TOPIC_KEYS,
        }
    if topic in state._expand_history:
        return {"추가": [], "_note": f"이미 확장된 주제: {topic}"}
    if not state.can_expand():
        return {"error": "확장 한도(최대 2회) 도달", "가능한 주제": _ROUTING_TOPIC_KEYS}
    state._expand_history.append(topic)
    name_to_tool = {t["function"]["name"]: t for t in state.all_tools}
    added: list[str] = []
    for n in _ROUTING_TABLE["주제"][topic]:
        if n in name_to_tool and n not in {t["function"]["name"] for t in state.current_tools()}:
            added.append(n)
    return {"추가": added}

# ══════════════════════════════════════════════════════════════════════════════════════
# 5단계 계산 파이프라인
# ══════════════════════════════════════════════════════════════════════════════════════

def parse_option_amounts(body: str) -> dict[int, int]:
    """보기 ①~⑤의 금액(쉼표·원 제거)을 정수로 반환.

    금액 아닌 보기는 제외. 예: '① 50,000,000원 ② 75,000,000원 …' → {1: 50000000, 2: 75000000, …}.
    """
    result: dict[int, int] = {}
    for idx, marker in enumerate("①②③④⑤", 1):
        pos = body.find(marker)
        if pos < 0:
            continue
        rest = body[pos + len(marker):]
        m = re.match(r'\s*([\d,]+(?:원|만원|억원)?)\s*', rest)
        if not m:
            continue
        raw = m.group(1)
        cleaned = raw.replace(",", "").replace("원", "").replace("만원", "").replace("억원", "").strip()
        try:
            result[idx] = int(cleaned)
        except ValueError:
            continue
    return result


def match_amount_to_option(value: int, opts: dict[int, int], tolerance: float = 0.001) -> int | None:
    """상대오차 tolerance 이내인 보기 번호를 반환. 둘은 가장 가까운 것, 없으면 None."""
    if not opts:
        return None
    exact = [k for k, v in opts.items() if v == value]
    if exact:
        return exact[0]
    within: list[tuple[int, float]] = []
    for k, v in opts.items():
        if v == 0:
            if value == 0:
                within.append((k, 0.0))
            continue
        rel = abs(value - v) / abs(v)
        if rel <= tolerance:
            within.append((k, rel))
    if not within:
        return None
    within.sort(key=lambda x: x[1])
    return within[0][0]


def is_calc_type(body: str) -> bool:
    """계산형 문항 여부를 판별.

    보기 영역에 '원'/'개' 금액 수치가 있거나, 발문이 액·금액·과세표준·세액·공제액·한도로 끝나면 계산형.
    """
    if re.search(r'[\d,]+(?:원|개)', body):
        return True
    tail = body.rstrip("?").strip()
    if re.search(r'(액|금액|과세표준|세액|공제액|한도)$', tail):
        return True
    return False


def _stem_type_of(stem: str) -> str:
    """발문 형식 분류 (극성 반영)."""
    if "옳지 않은 것은" in stem or "옳지 아니한 것은" in stem or "틀린 것은" in stem:
        return "옳지 않은 것은"
    if "옳지 않은 것" in stem or "틀린 것" in stem or "옳은 것은" in stem:
        return "옳은 것은" if "옳은" in stem else "옳지 않은 것은"
    if "모두 고른 것은" in stem:
        return "모두 고른 것은"
    if "몇 개" in stem:
        return "몇 개"
    return "기타"


def classify_stem(stem: str) -> tuple[str, str]:
    """발문을 (극성, 형식)으로 분류. 극성='옳음'|'틀림', 형식='단일'|'모두'|'개수'."""
    # 극성: '옳지 않은' 계열이면 틀림, '옳은' 계열이면 옳음
    if "옳지 않은" in stem or "옳지 아니한" in stem or "틀린" in stem:
        polarity = "틀림"
    elif "옳은" in stem:
        polarity = "옳음"
    else:
        polarity = "틀림"
    # 형식
    if "몇 개" in stem:
        fmt = "개수"
    elif "모두 고른 것은" in stem:
        fmt = "모두"
    else:
        fmt = "단일"
    return (polarity, fmt)


def aggregate_verdicts(stem: str, verdicts: list[dict], options: list[dict]) -> int | None:
    """진술별 판정 결과로 규칙 기반 정답 번호 결정. 규칙 불가 시 None(→모델 종합)."""
    polarity, fmt = classify_stem(stem)
    if not verdicts or len(options) < 5:
        return None
    if polarity == "틀림":
        tgt = [i for i, v in enumerate(verdicts) if v["판정"] == "틀림"]
        un = [i for i, v in enumerate(verdicts) if v["판정"] == "불확실"]
    else:
        tgt = [i for i, v in enumerate(verdicts) if v["판정"] == "옳음"]
        un = [i for i, v in enumerate(verdicts) if v["판정"] == "불확실"]
    if fmt == "단일":
        if len(tgt) == 1:
            return tgt[0] + 1
        if len(tgt) == 0 and len(un) == 1:
            return un[0] + 1
        return None
    if fmt == "모두":
        s = set(tgt)
        if not s:
            return None
        for opt in options:
            nums = {"ㄱㄴㄷㄹㅁ".index(ch) for ch in opt["text"] if ch in "ㄱㄴㄷㄹㅁ"}
            if s == nums:
                return "①②③④⑤".index(opt["id"]) + 1
        return None
    if fmt == "개수":
        c = len(tgt)
        if c == 0 and len(un) == 1:
            c = 1
        for opt in options:
            m = re.search(r'(\d+)개', opt["text"])
            if m and int(m.group(1)) == c:
                return "①②③④⑤".index(opt["id"]) + 1
        return None


def extract_numbers_from_result(result: dict) -> list[int | float]:
    """결과 dict에서 숫자 값들을 추출(최상위·1단 중첩)."""
    nums: list[int | float] = []
    for key, val in result.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            nums.append(val)
        elif isinstance(val, dict):
            for sub_val in val.values():
                if isinstance(sub_val, (int, float)) and not isinstance(sub_val, bool):
                    nums.append(sub_val)
    return nums


def run_calc_pipeline(
    body: str,
    tools: list[dict],
    name_to_server: dict[str, tuple],
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    exam_date: str,
    usage_acc: UsageAcc,
) -> dict:
    """계산형 파이프라인: 추출→실행→보기 대조, 불일치 시 최대 3회 재추출(3회 다수결).

    반환 dict:
      - 일치 시: {"answer": 번호, "tool": 이름, "args": {...}, "result": 결과dict, "extractions": n}
      - fallback 시: {"answer": None, "fallback": True, "extractions": 3,
                     "last_tool": 이름, "last_args": {...}, "last_result": 결과dict}
    """
    opts = parse_option_amounts(body)
    if not opts:
        return {"answer": None, "fallback": True, "extractions": 0, "opts": opts}

    # 후보 도구 목록: 라우팅 활성 시 라우팅 선택 도구, 아니면 전체 도구(≤10개)
    if hasattr(run_tool_loop, "_routing_active") and run_tool_loop._routing_active:
        candidate_tools = run_tool_loop._routing_candidate_tools
    else:
        candidate_tools = list(tools)[:10]

    tool_blocks = []
    for t in candidate_tools:
        fn = t.get("function", {})
        name = fn.get("name", "")
        desc = fn.get("description", "") or ""
        schema = fn.get("parameters", {}) or {}
        tool_blocks.append(f'    {{"이름": "{name}", "설명": """{desc}""", "파라미터": {json.dumps(schema, ensure_ascii=False)}}}')

    tool_desc = "\n".join(tool_blocks)
    system = "세법 계산 문제. 아래 도구 목록과 문제 보기(①~⑤ 금액)를 보고, 계산에 쓸 도구 호출(JSON만)을 응답하세요."
    user = f"""【문제】
{body}

【사용 가능한 계산 도구 (이름, 설명, 파라미터 스키마)】
{tool_desc}

응답 형식(JSON만):
{{"tool": "도구이름", "args": {{...}}}}"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    last_tool = None
    last_args = None
    last_result = None
    answer = None
    extractions = 0
    votes: dict[int, int] = {}
    last_matched = None
    attempts: list[dict] = []

    for attempt in range(3):
        resp = api_chat_complete(base_url, api_key, model, messages, temperature=_RUN_TEMP, seed=seed + attempt, max_tokens=1024, tools=None)
        usage_acc.add(resp)
        content = (resp.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""

        # 도구 호출 파싱: content의 {"tool":..., "args":...} JSON 우선, 없으면 tool_calls에서 추출
        extracted = None
        jm = re.search(r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}', content)
        if jm:
            tool_name = jm.group(1)
            arg_match = re.search(r'"args"\s*:\s*(\{)', content)
            if arg_match:
                start = arg_match.end() - 1
                depth = 0
                end = start
                for i in range(start, len(content)):
                    if content[i] == '{':
                        depth += 1
                    elif content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                try:
                    args = json.loads(content[start:end])
                    extracted = {"tool": tool_name, "args": args}
                except (json.JSONDecodeError, ValueError):
                    pass
        if extracted is None:
            tcs = (resp.get("choices", [{}])[0].get("message", {}) or {}).get("tool_calls", [])
            if tcs:
                tc = tcs[0]
                fn_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except (json.JSONDecodeError, ValueError):
                    args = {}
                extracted = {"tool": fn_name, "args": args}

        if extracted is None:
            # 파싱 실패도 기록으로 남김 (실측 fallback 원인 추적용)
            result_truncated = None
            attempts.append({
                "content": content[:600],
                "tool": None,
                "args": None,
                "validation": None,
                "result": result_truncated,
                "candidates": [],
                "matched": None,
            })
            messages.append({"role": "user", "content": "도구 호출(JSON: {\"tool\": \"...\", \"args\": {...}})을 응답하세요."})
            continue

        tool_name = extracted["tool"]
        args = extracted["args"]
        last_tool = tool_name
        last_args = dict(args)

        # 스키마 조회 → coerce → validate → 실행
        tool_schema = {}
        for t in tools:
            if t.get("function", {}).get("name") == tool_name:
                tool_schema = t.get("function", {}).get("parameters", {}) or {}
                break
        args_coerced, _coerce_notes = coerce_args(args, tool_schema)
        validation_err = validate_args(args_coerced, tool_schema, tool_name)
        if validation_err is not None:
            result = validation_err
        else:
            result = execute_direct_tool_call(tool_name, args_coerced, tools, name_to_server, exam_date)
        last_result = result

        extractions += 1

        nums = extract_numbers_from_result(result)
        prio_keys = ("산출세액", "납부할세액", "세액", "한도초과액", "손금불산입액", "소득금액", "과세표준")
        for k in prio_keys:
            if k in result and isinstance(result[k], (int, float)) and not isinstance(result[k], bool):
                v = result[k]
                if v not in nums:   # extract_numbers_from_result와 중복 추가 방지
                    nums.append(v)
        if not nums:
            for v in result.values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nums.append(v)
                    break

        matched = None
        for num in nums:
            num_int = int(num) if isinstance(num, float) and num == int(num) else num
            m = match_amount_to_option(num_int, opts)
            if m is not None:
                matched = m
                break

        # 시도 기록 (결과 JSON 최대 1000자 — 필드 단위로 잘라서 역직렬화 가능한 dict 구성)
        result_json = json.dumps(result, ensure_ascii=False)
        if len(result_json) <= 1000:
            result_truncated = result
        else:
            # 큰 결과는 필드 단위로 쌓아서 1000자 이하 dict 구성
            acc: dict = {}
            acc_json = ""
            for k, v in result.items():
                trial = {**acc, k: v}
                trial_json = json.dumps(trial, ensure_ascii=False)
                if len(trial_json) > 1000:
                    break
                acc = trial
                acc_json = trial_json
            if acc:
                acc["_trunc_warning"] = "(1000자 초과 잘림)"
                result_truncated = acc
            else:
                # 첫 필드부터 이미 1000자 초과인 경우(소형 요약만)
                result_truncated = {
                    "_trunc_warning": "(1000자 초과 잘림)",
                    "_keys": list(result.keys())[:5],
                }
        attempts.append({
            "content": content[:600],
            "tool": tool_name,
            "args": dict(args),
            "validation": validation_err,
            "result": result_truncated,
            "candidates": nums,
            "matched": matched,
        })

        if matched is not None:
            votes[matched] = votes.get(matched, 0) + 1
            if answer is None:
                answer = matched
                last_matched = matched
                if attempt == 0:
                    # 첫 시도에서 보기 일치 → 즉시 확정 (재추출 불필요)
                    return {"answer": answer, "tool": last_tool, "args": last_args, "result": last_result, "extractions": extractions, "attempts": attempts}
            if votes[matched] >= 2:
                # 같은 보기 2회 이상 → 즉시 확정
                answer = matched
                break
        else:
            last_matched = None
            hint = f"이전 추출 {json.dumps(args)}로 계산한 결과 {json.dumps(result)}이 보기와 맞지 않음. 입력을 다시 확인"
            messages.append({"role": "user", "content": hint})

    if answer is not None:
        return {"answer": answer, "tool": last_tool, "args": last_args, "result": last_result, "extractions": extractions, "attempts": attempts}

    return {
        "answer": None,
        "fallback": True,
        "extractions": extractions,
        "last_tool": last_tool,
        "last_args": last_args,
        "last_result": last_result,
        "opts": opts,
        "attempts": attempts,
    }


def execute_direct_tool_call(
    tool_name: str,
    args: dict,
    tools: list[dict],
    name_to_server: dict[str, tuple],
    exam_date: str,
) -> dict:
    """calc_pipeline용 도구 실행: coerce·validate 후 서버 호출."""
    tool_schema = {}
    for t in tools:
        if t.get("function", {}).get("name") == tool_name:
            tool_schema = t.get("function", {}).get("parameters", {}) or {}
            break
    args, _coerce_notes = coerce_args(args, tool_schema)
    validation_err = validate_args(args, tool_schema, tool_name)
    if validation_err is not None:
        return validation_err
    server_and_name = name_to_server.get(tool_name)
    if server_and_name is None:
        return {"error": f"알 수 없는 도구: {tool_name}"}
    server, actual_name = server_and_name
    try:
        result_text = _sync_call_tool(server, actual_name, args)
        try:
            result = json.loads(result_text) if result_text else {}
        except (json.JSONDecodeError, ValueError):
            result = {"text": result_text}
    except Exception as exc:
        result = format_tool_error(exc, tool_name, tool_schema)
    return result

# ══════════════════════════════════════════════════════════════════════════════════════
# 2단계: 실행 루프 통합 (run_tool_loop)
# ══════════════════════════════════════════════════════════════════════════════════════

def run_tool_loop(
    cfg: RunConfig,
    messages: list[dict],
    tools: list[dict],
    name_to_server: dict[str, tuple],
    schema_map: dict[str, dict],
    exam_date: str,
    seed: int,
    base_url: str,
    api_key: str,
    model: str,
    cond: str,
    reasoning: str | None = None,
) -> LoopResult:
    """공통 도구 루프 실행 (2단계: 실행 루프 통합).

    native 계열(native, native_direct, native_direct2, native2, native_tree,
    native_search, native_annot)과 meta 계열(B, B2)의 공통 루프를 통합.
    안전장치는 cfg 플래그로만 제어 (cond == "native_direct" 같은 조건 분기 제거).

    lawmcp, per_option, tree_bundle은 별도 루프 사용 (이번 범위 밖).
    """
    tool_calls: list[dict] = []
    tool_responses: list[dict] = []
    tool_call_records: list[tuple[str, dict, str, bool]] = []
    call_cache: dict = {}
    usage_acc = UsageAcc()

    # 카운터 (cfg 플래그로 제어)
    nudged = False
    duplicate_count = 0
    clamped_count = 0
    repeat_count = 0
    blocked_count = 0
    error_streak_count = 0
    force_break = False

    # 도구 호출별 오류 스트릭 추적
    tool_error_streak: dict[str, int] = {}

    # 반복 호출 카운트 (cfg.repeat_block 추적용)
    cache_call_counts: dict[str, int] = {}

    # native2/native_direct2의 3회째 차단용 호출 횟수
    native2_call_counts: dict[str, int] = {} if cfg.repeat_block == "3rd_only" else {}

    # B2의 첫 응답 도구 미사용 처리용
    no_tool_first = (cond == "B2")
    last_assistant_content = None

    # ── 4단계 라우팅 초기화 ──────────────────────────────────────────────────────
    routing_state: RoutingState | None = None
    body = ""
    if cfg.routing:
        # body 추출: user 메시지에서 (messages[1] = user)
        for m in messages:
            if m.get("role") == "user":
                body = m.get("content", "")
                break
        bucket, qtype = classify_question(body, base_url, api_key, model, seed, usage_acc)
        routing_state = RoutingState(bucket=bucket, question_type=qtype, all_tools=tools)
        # 라우팅 시 노출 도구를 state.current_tools()로 교체
        tools = routing_state.current_tools()

    # ── 5단계 계산형 파이프라인 (cfg.calc_pipeline) ──────────────────────────────
    calc_pipeline_result: dict | None = None
    if cfg.calc_pipeline:
        # body 추출 (라우팅이 이미 추출했으면 재사용, 없으면 user 메시지에서)
        if not body:
            for m in messages:
                if m.get("role") == "user":
                    body = m.get("content", "")
                    break
        is_calc = (routing_state is not None and routing_state.question_type == "계산형") or is_calc_type(body)
        if is_calc:
            # 라우팅 활성 시 라우팅 선택 도구, 아니면 native_direct 도구 사용
            if routing_state is not None:
                calc_tools = routing_state.current_tools()
                calc_nts = name_to_server
            else:
                nd_tools, _nd_logs, nd_nts = _build_native_direct_tools()
                calc_tools = nd_tools
                calc_nts = nd_nts
            cp_result = run_calc_pipeline(body, calc_tools, calc_nts, base_url, api_key, model, seed, exam_date, usage_acc)
            calc_pipeline_result = cp_result
            if cp_result.get("answer") is not None:
                tool_name = cp_result.get("tool", "")
                args = cp_result.get("args", {})
                result = cp_result.get("result", {})
                ans = cp_result["answer"]
                reason = f"calc_pipeline: 도구={tool_name}, 입력={json.dumps(args)}, 결과={json.dumps(result)}, 보기#{ans}"
                final_answer = {"answer": ans, "reason": reason, "tools_used": [tool_name]}
                # 마지막 assistant 메시지 content 기록 (messages에 미포함)
                last_assistant_content = reason
                # 최종 답변을 messages에 추가 (이미 assistant+tool 메시지 구조가 없는 상태)
                messages.append({"role": "assistant", "content": reason, "tool_calls": []})
            else:
                # fallback: 파이프라인 시도 내역을 messages 앞에 요약으로 추가
                attempt_lines: list[str] = []
                for i, att in enumerate(cp_result.get("attempts", [])):
                    tool_name = att.get("tool") or "없음"
                    args_str = json.dumps(att.get("args")) if att.get("args") is not None else "{}"
                    res = att.get("result")
                    if isinstance(res, dict):
                        vals = [v for v in res.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
                        res_str = str(vals[0]) if vals else json.dumps(res)[:80]
                    else:
                        res_str = str(res)[:80] if res is not None else "None"
                    matched = att.get("matched")
                    mismatch = f"보기#{matched}" if matched is not None else "불일치"
                    attempt_lines.append(f"  시도{i+1}: 도구={tool_name}, 입력={args_str}, 결과값={res_str}, {mismatch}")
                fallback_note = (
                    f"[calc_pipeline 시도: 도구 호출 {cp_result.get('extractions', 0)}회, "
                    f"보기 일치 없음 → 일반 루프로 진행]\n" +
                    "\n".join(attempt_lines)
                )
                messages.insert(1, {"role": "user", "content": fallback_note})

    for round_idx in range(cfg.limit_tools + 3):
        total_tool_calls = len(tool_calls)
        remaining = cfg.limit_tools - total_tool_calls
        if total_tool_calls >= cfg.limit_tools:
            messages.append({"role": "user", "content": f"도구 호출 한도에 도달했습니다 (남은 호출: 0회). 지금까지의 정보로 최종 답변을 JSON으로 응답하세요."})
            break

        max_tok = 16000 if reasoning else 2048
        resp = api_chat_complete(
            base_url, api_key, model, messages,
            temperature=_RUN_TEMP, seed=seed + round_idx, max_tokens=max_tok,
            tools=tools if cfg.tool_set in ("direct", "meta") else None,
            reasoning_effort=reasoning,
        )
        usage_acc.add(resp)

        choice = resp.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls_in_msg = message.get("tool_calls", [])
        if tool_calls_in_msg:
            no_tool_first = False
            for tc in tool_calls_in_msg:
                if total_tool_calls >= cfg.limit_tools:
                    break
                fn_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}

                # ── 4단계 라우팅: expand_tools 특별 처리 ──────────────────────────
                if cfg.routing and routing_state is not None and fn_name == ROUTING_EXPAND_TOOL_NAME:
                    if not routing_state.can_expand():
                        expand_result = {"error": "확장 한도(최대 2회) 도달", "가능한 주제": _ROUTING_TOPIC_KEYS}
                    else:
                        expand_result = handle_expand_tools(args, routing_state)
                        # 노출 도구 목록 갱신
                        tools = routing_state.current_tools()
                    routing_state._expand_history  # side-effect already applied
                    tool_calls.append({"tool": fn_name, "args": args})
                    result_json = json.dumps(expand_result, ensure_ascii=False)
                    preview = result_json[:200]
                    is_error = isinstance(expand_result, dict) and "error" in expand_result
                    tool_call_records.append((fn_name, args, preview, is_error))
                    tool_responses.append({"tool_call_id": tc.get("id", ""), "content": result_json})
                    assistant_replay = replay_assistant_message({"role": "assistant", "content": message.get("content"), "tool_calls": [tc]}, cfg.keep_content)
                    messages.append(assistant_replay)
                    messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_json})
                    # expand_tools는 실제 서버 호출이 아니며 상한 카운트에서 제외
                    continue

                tool_calls.append({"tool": fn_name, "args": args})

                # 날짜 clamping (cfg.clamp_dates)
                clamp_note = None
                was_clamped = False
                if cfg.clamp_dates:
                    args, clamp_note = _clamp_future_dates(args, exam_date)
                    if clamp_note:
                        clamped_count += 1
                        was_clamped = True

                # 캐시 키 (tool_set에 따라 다름)
                if cfg.tool_set == "meta":
                    cache_key = _normalize_args_for_cache(args, None)
                else:
                    cache_key = _normalize_args_for_cache(args, fn_name)

                # 중복·반복·차단 처리 (cfg.repeat_block)
                should_execute = True
                if cache_key in call_cache:
                    should_execute = False
                    duplicate_count += 1
                    cached_result = call_cache[cache_key]

                    if cfg.repeat_block == "3rd_only":
                        # native2/native_direct2 스타일: 3회째 차단
                        call_count = native2_call_counts.get(cache_key, 0) + 1
                        native2_call_counts[cache_key] = call_count
                        if call_count >= 3:
                            block_msg = "이미 같은 결과를 2번 받았습니다. 더 이상 동일 도구를 호출하지 말고 지금까지 정보로 최종 답변을 JSON으로 응답하세요."
                            result = {"_blocked": True, "_message": block_msg}
                            result_json = json.dumps(result, ensure_ascii=False)
                        else:
                            original_text = json.dumps(cached_result, ensure_ascii=False)
                            summary_500 = original_text[:500]
                            dup_result = {
                                "_cached": True,
                                "_message": "이미 같은 결과를 받았습니다. 다른 조문·키워드를 쓰거나 지금까지 정보로 답하세요.",
                                "_original_summary": summary_500,
                                "_call_number": call_count,
                            }
                            result_json = json.dumps(dup_result, ensure_ascii=False)
                            result = cached_result
                    elif cfg.repeat_block is True:
                        # V3 스타일: 2회째 반복 안내, 3회째 차단
                        call_count = cache_call_counts.get(cache_key, 0) + 1
                        cache_call_counts[cache_key] = call_count
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
                    else:
                        # repeat_block=False: 단순 중복 안내
                        duplicate_result = {"_cached": True, "_message": "이미 받은 결과와 같습니다 (동일 호출)", "_original": cached_result}
                        result_json = json.dumps(duplicate_result, ensure_ascii=False)
                        result = cached_result

                if should_execute:
                    # 도구 실행: execute_tool_call이 _fill_as_of·coerce·validate·실행·normalize·예외처리 수행
                    result = execute_tool_call(
                        tc, tools, name_to_server, cfg, exam_date,
                    )

                    # 결과 자르기 (cfg.truncate_chars)
                    if cfg.truncate_chars is not None:
                        result = _truncate_result(result, max_chars=cfg.truncate_chars)

                    # clamping note 반영
                    if clamp_note:
                        existing_note = result.get("_harness_note")
                        if existing_note:
                            result["_harness_note"] = existing_note + "; " + clamp_note
                        else:
                            result["_harness_note"] = clamp_note

                    # 오류 스트릭 (cfg.error_streak)
                    is_error = isinstance(result, dict) and "error" in result
                    if cfg.error_streak and is_error:
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

                    result["_remaining_calls"] = remaining - 1
                    call_cache[cache_key] = result
                    if cfg.repeat_block is not True:
                        cache_call_counts[cache_key] = 1
                    result_json = json.dumps(result, ensure_ascii=False)

                # 도구 호출 기록
                if cfg.tool_set == "direct":
                    result_text_for_record = json.dumps(result, ensure_ascii=False)
                else:
                    result_text_for_record = result_json
                preview = result_text_for_record[:200]
                is_error = isinstance(result, dict) and "error" in result
                tool_call_records.append((fn_name, args, preview, is_error))

                tool_responses.append({"tool_call_id": tc.get("id", ""), "content": result_json})
                # replay_assistant_message 사용 (cfg.keep_content)
                assistant_replay = replay_assistant_message({"role": "assistant", "content": message.get("content"), "tool_calls": [tc]}, cfg.keep_content)
                messages.append(assistant_replay)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_json})
                total_tool_calls += 1

                # V3 스타일 차단 한도 체크 (cfg.repeat_block is True)
                if cfg.repeat_block is True and blocked_count >= 3:
                    force_break = True
                    break
        if force_break:
            break
        elif not tool_calls_in_msg:
            content = message.get("content") or ""
            last_assistant_content = content
            parsed = parse_answer(content)

            # B2 첫 응답 도구 미사용 nudge
            if cond == "B2" and no_tool_first and parsed:
                messages.append({"role": "user", "content": "핵심 조문을 먼저 확인하세요. (law_article로 핵심 조문을 최소 1회 확인한 뒤 답할 것)"})
                no_tool_first = False
                continue

            # nudge_tool (cfg.nudge_tool)
            if cfg.nudge_tool and not tool_calls and not nudged:
                if content:
                    messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": NUDGE_TOOL})
                nudged = True
                continue

            if parsed:
                final_answer = parsed
                used_tools = [_format_tool_call_record(tc) for tc in tool_calls]
                final_answer["tools_used"] = used_tools
            break
    else:
        final_answer = None

    return LoopResult(
        final_answer=final_answer if 'final_answer' in locals() else None,
        tool_calls=tool_calls,
        tool_call_records=tool_call_records,
        usage_acc=usage_acc,
        duplicate_count=duplicate_count,
        nudged=nudged,
        clamped_count=clamped_count,
        repeat_count=repeat_count,
        blocked_count=blocked_count,
        error_streak_count=error_streak_count,
        force_break=force_break,
        last_assistant_content=last_assistant_content,
        routing_bucket=routing_state.bucket if routing_state else "",
        routing_qtype=routing_state.question_type if routing_state else "",
        routing_expand_count=len(routing_state._expand_history) if routing_state else 0,
        calc_pipeline_result=calc_pipeline_result,
    )

# ── 1단계 측정: make_failed_result, score_counts ──────────────────────────────────

def make_failed_result(year: str, qno: int, subject: str, correct: int | str, exc: Exception) -> QuestionResult:
    """실행 중 예외 발생 시 '실행실패' 결과를 생성.

    정오='실행실패', _error_raw='예외종류: 메시지(300자)'.
    score_counts에서 O/X/무응답과 별도로 집계되며, 분모(정답률 계산)에서 제외된다.
    """
    raw_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
    res = QuestionResult(
        연도=year, 번호=qno, 과목=subject,
        모델답=None, 정답=correct, 정오="실행실패", 근거="",
        도구호출목록=[], 토큰수=0, 입력토큰=0, 출력토큰=0, 소요초=0.0,
    )
    res._tool_call_records = []
    res._error_raw = raw_msg
    return res


def score_counts(results: list[QuestionResult]) -> dict[str, int]:
    """결과 리스트에서 정오별 개수를 센다.

    반환: {"O": n, "X": n, "무응답": n, "실행실패": n, "제외": n}
    실행실패는 분모에서 빼고 별도 표시한다.
    """
    counts: dict[str, int] = {"O": 0, "X": 0, "무응답": 0, "실행실패": 0, "제외": 0}
    for r in results:
        jjo = r.정오
        if jjo in counts:
            counts[jjo] += 1
        else:
            counts[jjo] = counts.get(jjo, 0) + 1
    return counts


# ══════════════════════════════════════════════════════════════════════════════════════
# 6단계 평가: summarize_by_type
# ══════════════════════════════════════════════════════════════════════════════════════

def summarize_by_type(results: list[QuestionResult], questions: dict) -> dict:
    """서술형·계산형 유형별 정답 통계.

    반환: {"서술형": {"n": N, "O": N, "X": N, "무응답": N, "실행실패": N},
           "계산형": {"n": N, "O": N, "X": N, "무응답": N, "실행실패": N}}
    """
    types = {"서술형": {}, "계산형": {}}
    for r in results:
        qno_key = str(r.번호)
        body = ""
        # questions가 {"연도": {...}} 구조 또는 평탄한 구조 모두 지원
        q = None
        if r.연도 in questions and isinstance(questions[r.연도], dict):
            q = questions.get(r.연도, {}).get(qno_key, {})
        if q is None:
            q = questions.get(qno_key, {})
        if isinstance(q, dict):
            body = q.get("본문", "")
        key = "계산형" if is_calc_type(body) else "서술형"
        bucket = types[key]
        jjo = r.정오
        bucket["n"] = bucket.get("n", 0) + 1
        bucket[jjo] = bucket.get(jjo, 0) + 1
    out = {}
    for k, v in types.items():
        out[k] = {"n": v.get("n", 0),
                  "O": v.get("O", 0),
                  "X": v.get("X", 0),
                  "무응답": v.get("무응답", 0),
                  "실행실패": v.get("실행실패", 0)}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# 결과 저장
# ══════════════════════════════════════════════════════════════════════════════════════

def _append_raw_one(
    res: QuestionResult,
    path: Path,
    excluded: bool = False,
    tool_call_records: list[tuple[str, dict, str, bool]] | None = None,
    messages: list[dict] | None = None,
    run_config: dict | None = None,
):
    """raw jsonl에 문항 1개 즉시 append.

    messages: 해당 문항의 전체 대화 기록 (tool 메시지 포함).
    run_config: cond, harness 버전, limit_tools, 안전장치 on/off, 시드, 모델, 프롬프트 이름.
    도구 결과 미리보기 200자 제한은 그대로 유지하되, 전문은 messages에 남긴다.
    messages/run_config가 생략되면 res._messages/res._run_config를 사용한다.
    """
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
        "입력토큰": res.입력토큰,
        "출력토큰": res.출력토큰,
        "소요초": res.소요초,
        "excluded": excluded,
        "forced_final": res.forced_final,
        "reasoning": res.reasoning,
        "reasoning_tokens": res.reasoning_tokens,
        "error": getattr(res, "_error_raw", None),
    }
    if messages is None:
        messages = getattr(res, "_messages", None)
    if messages is not None:
        obj["messages"] = messages
    if run_config is None:
        run_config = getattr(res, "_run_config", None)
    if run_config is not None:
        obj["run_config"] = run_config
    if tool_call_records:
        obj["tool_call_details"] = [
            {"tool": name, "args": args, "result_preview": preview, "is_error": is_error}
            for name, args, preview, is_error in tool_call_records
        ]
    if getattr(res, "_harness_events", None):
        obj["harness_events"] = res._harness_events
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def save_raw(results: list[QuestionResult], cond: str, year: str, reasoning: str | None = None) -> Path:
    """results/raw_{cond}_{year}.jsonl 저장."""
    RESULTS_DIR.mkdir(exist_ok=True)
    reasoning_suffix = f"_r{reasoning}" if reasoning else ""
    path = RESULTS_DIR / f"raw_{cond}_{year}{reasoning_suffix}.jsonl"
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
                "입력토큰": r.입력토큰,
                "출력토큰": r.출력토큰,
                "소요초": r.소요초,
                "forced_final": r.forced_final,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path

def compute_summary(results: list[QuestionResult]) -> dict:
    """결과 요약 통계."""
    total = 0
    correct = 0
    wrong = 0
    unanswered = 0
    failed = 0
    by_year: dict[str, dict[str, int]] = {}
    total_tool_calls = 0
    total_tokens = 0
    total_time = 0.0

    for r in results:
        if r.정오 == "제외":
            continue
        총목록 = by_year.setdefault(r.연도, {"total": 0, "correct": 0, "wrong": 0, "unanswered": 0, "failed": 0})
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
        elif r.정오 == "실행실패":
            failed += 1
            총목록["failed"] += 1

    accuracy = correct / total if total > 0 else 0
    by_year_summary = {}
    for yr, stats in by_year.items():
        by_year_summary[yr] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "unanswered": stats["unanswered"],
            "failed": stats.get("failed", 0),
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
        "failed": failed,
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
        suffix = " 도구미사용" if getattr(res, "_도구미사용", False) else ""
        print(f"[{n}/{total_expected}] {res.연도} {res.번호}번 ({res.basis_date}) {res.정오} 도구{tool_count}회 {t}초{suffix}", flush=True)

    return callback


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
# 메인
# ══════════════════════════════════════════════════════════════════════════════════════

# 결과 저장 디렉토리 (기본: eval/results/)
RESULTS_DIR = Path("eval/results")

# 제외 문항 집합 (필요 시 설정)
EXCEPT_QUESTION: set[tuple[str, str]] = set()

# base laws 목록 (search 도구에서 사용)
_BASE_LAWS = ["소득세법", "법인세법", "부가가치세법", "상속세 및 증여세법", "국세기본법"]


def run_question(
    cond: str,
    year: str,
    qno: int,
    question: dict,
    correct: int | str,
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    exam_date: str,
    limit_tools: int = 8,
    progress_callback: Callable | None = None,
    reasoning: str | None = None,
) -> QuestionResult:
    """문항 1개 실행 (2단계: 실행 루프 통합).

    native 계열(native, native_direct, native_direct2, native2, native_tree,
    native_search, native_annot)과 meta 계열(B, B2)은 RunConfig + run_tool_loop로 통합.
    lawmcp은 별도 비동기 루프 사용 (이번 범위 밖).
    A(도구 없음)는 직접 처리.
    """
    t0 = time.time()
    subject = question.get("과목", "")
    body = question.get("본문", "")

    if (year, str(qno)) in EXCEPT_QUESTION:
        res = QuestionResult(연도=year, 번호=qno, 과목=subject, 모델답=None, 정답=correct, 정오="제외", 근거="")
        res._tool_call_records = []
        return res

    # 조건별 cfg, messages, tools, name_to_server, schema_map 설정
    cfg: RunConfig | None = None
    messages: list[dict] | None = None
    tools: list[dict] | None = None
    name_to_server: dict[str, tuple] | None = None
    schema_map: dict[str, dict] | None = None

    if cond == "A":
        # 도구 없음: 직접 처리 (run_tool_loop 사용하지 않음)
        system = SYSTEM_V3 if HARNESS_V3 else "SYSTEM_A"
        user = body
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        tools = None
        cfg = effective_config("A")

    elif cond in ("native", "native_direct", "native_direct2", "native2",
                  "native_tree", "native_search", "native_annot", "B", "B2"):
        # 프리셋 + CFG_OVERRIDE 적용 (effective_config 경유) + 조건별 도구 빌드
        cfg = effective_config(cond)

        # messages 설정 (프롬프트 상수 이름으로 부터 실제 프롬프트 구성)
        if cond == "native":
            system = "SYSTEM_NATIVE"
            user = body
        elif cond == "native_direct":
            system = SYSTEM_V3
            user = body
        elif cond == "native2":
            system = "SYSTEM_NATIVE2"
            user = body
        elif cond == "native_direct2":
            system = "SYSTEM_NATIVEDIRECT2"
            user = body
        elif cond in ("native_tree", "native_search", "native_annot"):
            system = "SYSTEM_NATIVETREE"
            user = body
        elif cond == "B2":
            system = "SYSTEM_B2"
            user = body
        else:  # B
            system = "SYSTEM_B"
            user = body

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        # 도구 빌드
        if cond == "native":
            built_tools, logs, name_to_server = _build_tools()
        elif cond == "native_direct":
            built_tools, logs, name_to_server = _build_tools()
        elif cond == "native2":
            built_tools, logs, name_to_server = _build_tools()
        elif cond == "native_direct2":
            built_tools, logs, name_to_server = _build_tools()
        elif cond in ("native_tree", "native_search", "native_annot"):
            built_tools, logs, name_to_server = _build_tools()
            # cfg.extra에 따른 도구 수정
            extra = cfg.extra if cfg else {}
            if extra.get("replace_tool") and extra.get("replacement_tool"):
                # article_structure → article_annotated 교체 (native_annot)
                built_tools = [t for t in built_tools if t["function"]["name"] != extra["replace_tool"]]
                name_to_server.pop(extra["replace_tool"], None)
                built_tools.append({"type": "function", "function": {
                    "name": extra["replacement_tool"],
                    "description": "언제: 조문을 읽을 때. 입력: 법령명, 조문 번호(선택: 항). 원문 전체에 관계 표시를 붙여 반환.",
                    "parameters": {"type": "object", "properties": {
                        "law_name": {"type": "string", "description": "법령명 (예: '소득세법 시행령')"},
                        "article": {"type": "string", "description": "조문 번호 (예: '제72조')"},
                        "paragraph": {"type": "string", "description": "항 번호(선택, 예: '②')"}},
                        "required": ["law_name", "article"]}}})
                name_to_server[extra["replacement_tool"]] = ("_local_annot", extra["replacement_tool"])
            if extra.get("add_tools"):
                # search_articles 추가 (native_search, native_annot)
                for add_tool_name in extra["add_tools"]:
                    if add_tool_name == "search_articles":
                        built_tools.append({"type": "function", "function": {
                            "name": "search_articles",
                            "description": "언제: 진술·쟁점에 해당하는 조문 번호를 모를 때. 입력: 진술 문장(query), 법령명(선택).",
                            "parameters": {"type": "object", "properties": {
                                "query": {"type": "string", "description": "검색할 진술 또는 쟁점 문장"},
                                "law_name": {"type": "string", "description": "법령명(선택, 예: '소득세법'). 시행령·시행규칙 포함해 검색"}},
                                "required": ["query"]}}})
                        name_to_server["search_articles"] = ("_local_search", "search_articles")
        elif cond in ("B", "B2"):
            built_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "korean_tax_mcp",
                        "description": "한국 세법 근거 조회 도구 (korean-tax-mcp).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tool": {"type": "string", "enum": KTM_TOOL_NAMES},
                                "args": {"type": "object"},
                            },
                            "required": ["tool", "args"],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "korean_tax_calc_mcp",
                        "description": "한국 세금 계산 도구 (korean-tax-calc-mcp).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tool": {"type": "string", "enum": KTcalc_TOOL_NAMES},
                                "args": {"type": "object"},
                            },
                            "required": ["tool", "args"],
                            "additionalProperties": False,
                        },
                    },
                },
            ]
            name_to_server = {}
        else:
            built_tools = []
            name_to_server = {}

        tools = built_tools
        schema_map = {t["function"]["name"]: t["function"].get("parameters", {}) for t in built_tools}

    else:
        raise ValueError(f"Unknown condition: {cond}")

    assert cfg is not None and messages is not None and tools is not None
    assert name_to_server is not None and schema_map is not None

    loop_result = run_tool_loop(
        cfg=cfg,
        messages=messages,
        tools=tools,
        name_to_server=name_to_server,
        schema_map=schema_map,
        exam_date=exam_date,
        seed=seed,
        base_url=base_url,
        api_key=api_key,
        model=model,
        cond=cond,
        reasoning=reasoning,
    )

    # 최종 답변 처리 (run_tool_loop 이후)
    elapsed = time.time() - t0
    final_answer = loop_result.final_answer
    tool_calls = loop_result.tool_calls
    tool_call_records = loop_result.tool_call_records
    usage_acc = loop_result.usage_acc
    duplicate_count = loop_result.duplicate_count
    nudged = loop_result.nudged
    clamped_count = loop_result.clamped_count
    repeat_count = loop_result.repeat_count
    blocked_count = loop_result.blocked_count
    error_streak_count = loop_result.error_streak_count
    last_assistant_content = loop_result.last_assistant_content

    # run_tool_loop 내부에서 최종 답변을 받고 break한 경우, 마지막 assistant 메시지를 messages에 보충
    if last_assistant_content is not None and final_answer is not None:
        messages.append({"role": "assistant", "content": last_assistant_content})

    forced_final = False
    if final_answer is None:
        messages.append({"role": "user", "content": "지금까지 정보로 최종 답변을 JSON으로만 응답하세요. {\"reason\": \"...\", \"answer\": 1} 형식이어야 합니다(근거를 먼저 쓰고, 근거에서 나온 번호를 answer에)."})
        resp2 = api_chat_complete(base_url, api_key, model, messages, temperature=_RUN_TEMP, seed=seed+999, max_tokens=2048, tools=None)
        usage_acc.add(resp2)
        content2 = resp2.get("choices", [{}])[0].get("message", {}).get("content") or ""
        parsed_final = parse_answer(content2)
        if not parsed_final:
            messages.append({"role": "assistant", "content": content2})
            messages.append({"role": "user", "content": "보기 ①~⑤ 중 정답은 반드시 하나 있습니다. 가장 맞는 번호 하나를 골라 {\"reason\": \"한두 문장\", \"answer\": 번호} 형식 JSON으로만 짧게 답하세요."})
            resp3 = api_chat_complete(base_url, api_key, model, messages, temperature=_RUN_TEMP, seed=seed+998, max_tokens=1024, tools=None)
            usage_acc.add(resp3)
            parsed_final = parse_answer(resp3.get("choices", [{}])[0].get("message", {}).get("content") or "")
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
        정답번호 = correct if isinstance(correct, int) else None
        if 정답번호 is None:
            정오 = "제외"
        elif final_answer["answer"] == 정답번호:
            정오 = "O"
        else:
            정오 = "X"
        근거 = final_answer.get("reason", "")

    도구미사용 = (cond == "B2" and not tool_calls)

    result = QuestionResult(
        연도=year,
        번호=qno,
        과목=subject,
        basis_date=exam_date,
        모델답=모델답,
        정답=correct,
        정오=정오,
        근거=근거,
        도구호출목록=[_format_tool_call_record(tc) for tc in tool_calls] if tool_calls else [],
        토큰수=usage_acc.total,
        입력토큰=usage_acc.prompt,
        출력토큰=usage_acc.completion,
        소요초=round(elapsed, 2),
        forced_final=forced_final,
        reasoning=reasoning,
        reasoning_tokens=usage_acc.reasoning,
    )
    result._중복호출수 = duplicate_count
    result._도구미사용 = 도구미사용
    result._tool_call_records = tool_call_records
    result._messages = messages
    if cfg is not None:
        result._run_config = {"cond": cond, "harness": "V3" if HARNESS_V3 else "V2", **dataclasses.asdict(cfg)}
        result._cfg = dataclasses.asdict(cfg)
    else:
        result._run_config = None
        result._cfg = None
    if cfg.routing or cfg.calc_pipeline or HARNESS_V3:
        events: dict[str, Any] = {}
        if cfg.routing:
            events["routing_bucket"] = loop_result.routing_bucket
            events["routing_qtype"] = loop_result.routing_qtype
            events["routing_expand_count"] = loop_result.routing_expand_count
        if cfg.calc_pipeline and loop_result.calc_pipeline_result is not None:
            cp = loop_result.calc_pipeline_result
            events["calc_pipeline"] = {
                "answer": cp.get("answer"),
                "fallback": cp.get("fallback", False),
                "extractions": cp.get("extractions", 0),
                "tool": cp.get("tool"),
                "attempts": cp.get("attempts", []),
            }
        if HARNESS_V3:
            events["nudged"] = nudged
            events["clamped"] = clamped_count
            events["repeat"] = repeat_count
            events["blocked"] = blocked_count
            events["error_streak"] = error_streak_count
        result._harness_events = events

    if progress_callback:
        progress_callback(result)

    return result


def run_question_safe(
    cond: str,
    year: str,
    qno: int,
    question: dict,
    correct: int | str,
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    exam_date: str,
    limit_tools: int = 8,
    progress_callback: Callable | None = None,
    reasoning: str | None = None,
) -> QuestionResult:
    """run_question을 감싸 예외 발생 시 make_failed_result로 정오="실행실패" 반환.

    run_condition의 모든 except 경로가 이 함수 또는 make_failed_result를 사용한다
    (정오="무응답" 직접 생성은 0곳).
    """
    try:
        return run_question(
            cond=cond, year=year, qno=qno, question=question, correct=correct,
            base_url=base_url, api_key=api_key, model=model, seed=seed,
            exam_date=exam_date, limit_tools=limit_tools,
            progress_callback=progress_callback, reasoning=reasoning,
        )
    except Exception as e:
        return make_failed_result(year=year, qno=qno, subject=question.get("과목", ""), correct=correct, exc=e)


def run_condition_one(
    cond: str,
    year: str,
    qno: int,
    question: dict,
    correct: int | str,
    base_url: str,
    api_key: str,
    model: str,
    seed: int,
    exam_date: str,
    limit_tools: int,
    raw_path: Path,
    **kw,
) -> QuestionResult:
    """문항 1개 실행 + raw 기록을 한 함수로 묶음. _append_raw_one은 정확히 1회 호출.

    호출 측(run_condition)은 이 함수만 사용하고 별도 _append_raw_one을 호출하지 않는다.
    """
    progress_callback = kw.get("progress_callback", None)

    # ── A(도구 없음) 및 native/B 계열: run_question → _append_raw_one 1회 ───────
    try:
        res = run_question(
            cond=cond, year=year, qno=qno, question=question, correct=correct,
            base_url=base_url, api_key=api_key, model=model, seed=seed,
            exam_date=exam_date, limit_tools=limit_tools,
            progress_callback=progress_callback,
            reasoning=kw.get("reasoning", None),
        )
    except Exception as e:
        res = make_failed_result(year=year, qno=qno, subject=question.get("과목", ""), correct=correct, exc=e)
    _append_raw_one(res, raw_path, excluded=kw.get("excluded", False), tool_call_records=getattr(res, '_tool_call_records', []))
    if progress_callback:
        progress_callback(res)
    return res

# ══════════════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════════════

def main():
    global _RUN_TEMP

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
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="API temperature (기본: 0.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="API 호출 없이 문항 수·도구 수만 출력하고 종료")
    parser.add_argument("--resume", action="store_true",
                        help="기존 raw 결과에서 완료된 문항 건너뛰고 이어서 실행")
    parser.add_argument("--results-dir", type=Path, default=None,
                        help="결과 폴더 (기본: eval/results/)")
    args = parser.parse_args()

    _RUN_TEMP = args.temperature

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
        print(f"  [tool] {msg}", flush=True)
    print(f"도구 호출 상한: {TOOL_LIMIT}회")
    print(f"모델: {args.model}, 시드: {args.seed}, temperature: {args.temperature}")
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

    results_dir = args.results_dir or RESULTS_DIR
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
                cond="native_direct",
                year=y,
                qno=qno,
                question=q,
                correct=correct,
                base_url=base_url,
                api_key=api_key,
                model=args.model,
                seed=args.seed,
                exam_date=basis_date,
                limit_tools=TOOL_LIMIT,
                progress_callback=progress_cb,
                reasoning=None,
            )
        except Exception as e:
            print(f"  !! {y} {qno}번 예외 → 실행실패 처리: {type(e).__name__}: {str(e)[:200]}", flush=True)
            res = make_failed_result(year=y, qno=qno, subject=q.get("과목", ""), correct=correct, exc=e)
        results.append(res)
        _append_raw_one(res, raw_path)

    # 요약
    summary = compute_summary(results)
    summary["year"] = args.year or "all"
    summary_path = results_dir / "summary.json"
    save_summary_json([summary], summary_path)

    print("-" * 50)
    print(f"응답: {summary['total_응답']}, 정답: {summary['correct']}, 오답: {summary['wrong']}, 무응답: {summary['unanswered']}, 실행실패: {summary.get('failed', 0)}")
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
