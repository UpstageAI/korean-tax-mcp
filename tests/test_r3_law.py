"""timing_rules 근거 문언 대조, net 연결 실패 기억(회로) 범위.

1) timing_rules — 표의 시기·예외 문언이 적힌 근거 조문에 실제로 있는지 기계 대조.
   조문 원문은 tests/fixtures/timing_rules_articles.json(law_article as_of 20251231 기록 + 현행 2건).
   KTM_LIVE_LAW=1과 LAW_OC가 있으면 기록 대신 법제처에서 바로 받는다(0.5초 간격, 조문당 1회).
2) net — 한 번의 연결 실패가 같은 사이트의 다른 요청을 줄줄이 막지 않는지. 네트워크 없이 urlopen을 가짜로.
실행: .venv/bin/python -m pytest tests/test_r3_law.py -q
"""
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import korean_tax_mcp
from korean_tax_mcp import law, net, ntis, server
from korean_tax_mcp import timing_rules as T

FIX = json.loads((Path(__file__).parent / "fixtures" / "timing_rules_articles.json").read_text(encoding="utf-8"))
RULES = T._DATA["규칙"]


def _n(s):
    """띄어쓰기·가운뎃점·쉼표·마침표·쌍점 차이를 무시하고 비교."""
    return re.sub(r"[\s·ㆍ,\.:：]", "", s or "")


_LAW = re.compile(r"((?:[가-힣]+법)(?:\s*시행령|\s*시행규칙)?)?\s*(제\d+조(?:의\d+)?)")


def _cited(basis):
    """'부가가치세법 제17조제4항, 시행령 제30조' → [('부가가치세법','제17조'), ('부가가치세법 시행령','제30조')]."""
    out, base = [], None
    for part in re.split(r",\s*", basis):
        m = _LAW.search(part)
        if not m: continue
        name = (m.group(1) or "").strip()
        if not name:
            pre = part[:m.start(2)].strip()       # '시행령 제30조'처럼 법 이름이 빠진 경우 앞 법을 이어 씀
            name = (base + " " + pre).strip() if base else pre
        elif name.startswith(("시행령", "시행규칙")) and base:
            name = base + " " + name
        base = re.sub(r"\s*(시행령|시행규칙)$", "", name)
        out.append((name, m.group(2)))
    return out


_live_cache = {}


def _article(name, art):
    key = f"{name} {art}"
    if os.environ.get("KTM_LIVE_LAW") == "1" and os.environ.get("LAW_OC"):
        if key not in _live_cache:
            if _live_cache: time.sleep(0.5)
            _live_cache[key] = server.law_article(name, art, as_of="20251231").get("본문") or ""
        return _live_cache[key]
    return FIX["20251231"][key]


# 시기·예외에 나오면 근거 조문에도 그대로 있어야 하는 법령 용어(문언 유래를 가르는 말)
TERMS = ["반환조건부", "동의조건부", "기한부", "시용", "위탁", "장기할부", "작업진행률", "완성도기준", "중간지급조건부",
         "원본", "해약", "해지일", "폐업", "선(기)적", "수입신고", "잉여금", "결산확정일", "합병등기", "잔여재산", "공탁",
         "일신전속", "무인판매기", "청산소득", "특약", "상품권", "가공"]


def _rows(pred):
    return [r for r in RULES if pred(r)]


GOODS = {"법인": "상품·제품 판매(부동산 제외)", "소득": "상품·제품 판매"}


# ── 1. timing_rules 문언 ↔ 근거 조문 ──

def test_cited_parser():
    assert _cited("부가가치세법 제17조제4항, 시행령 제30조") == [("부가가치세법", "제17조"), ("부가가치세법 시행령", "제30조")]
    assert _cited("법인세법 시행령 제68조제1항제1호") == [("법인세법 시행령", "제68조")]
    assert _cited("소득세법 시행령 제50조의2제1항") == [("소득세법 시행령", "제50조의2")]


def test_every_cited_article_is_recorded():
    for r in RULES:
        for name, art in _cited(r["근거"]):
            assert _article(name, art), (r["항목"], name, art)


def test_timing_terms_appear_in_cited_article():
    """시기·예외에 쓴 법령 용어가 근거 조문(2025.12.31. 시행본)에 없으면, 그 행이 언제부터인지(예외 적용)를 밝혀야 한다.
    '법인 상품 판매' 행이 조건부·기한부 단서를 근거 없이 2025년 조문에 붙인 것처럼 보이던 문제."""
    bad = []
    for r in RULES:
        hay = _n("".join(_article(n, a) for n, a in _cited(r["근거"])))
        said = r.get("시기", "") + " " + r.get("예외", "")
        missing = [t for t in TERMS if t in said and _n(t) not in hay]
        if missing and not r.get("예외 적용"):
            bad.append((r["세목"], r["항목"], r["근거"], missing))
    assert not bad, bad


def test_quoted_original_text_is_in_cited_article():
    """'원문'을 둔 행은 그 문언이 근거 조문 현행 시행본에 글자 그대로(띄어쓰기 무시) 있어야 한다."""
    quoted = _rows(lambda r: r.get("원문"))
    assert len(quoted) >= 2
    for r in quoted:
        (name, art), = _cited(r["근거"])[:1]
        cur = FIX["현행"].get(f"{name} {art}", {}).get("본문") or _article(name, art)
        assert _n(r["원문"]) in _n(cur), (r["항목"], r["원문"])


@pytest.mark.parametrize("tax", ["법인", "소득"])
def test_goods_sale_conditional_exception_dated(tax):
    """조건부·기한부 판매 단서는 2026.2.27. 개정으로 생김 — 2025.12.31. 원문에는 '인도한 날'뿐.
    표(현행 기준)는 단서를 두되 적용 시작과 종전 문언, 부가가치세 같은 문언과의 관계를 밝혀야 한다."""
    r, = _rows(lambda r: r["세목"] == tax and r["항목"] == GOODS[tax])
    name, art = _cited(r["근거"])[0]
    old, new = _n(FIX["20251231"][f"{name} {art}"]), _n(FIX["현행"][f"{name} {art}"]["본문"])
    assert _n("반환조건부") not in old and _n("반환조건부") in new           # 기록 자체가 개정 전후를 보여 줌
    assert "반환조건부" in r["예외"] and "2026.2.27" in r["예외"], r["예외"]
    note = r.get("예외 적용", "")
    assert "2026.2.27" in note and "부칙" in note and "개시하는" in note, note
    assert "인도한 날" in note, note                                          # 그 전 사업연도·과세기간의 문언
    assert "부가가치세법 시행령 제28조제2항" in note, note                    # 같은 문언의 부가가치세 규정은 별개
    assert _n(r["원문"]) in new and _n(r["원문"]) not in old


def test_goods_sale_note_reaches_tool_output():
    r = server.timing_rules(tax="법인", keyword="반환조건부")
    hit = [x for x in r["규칙"] if x["항목"] == GOODS["법인"]]
    assert hit and "예외 적용" in hit[0], r
    en = _call_en("timing_rules", {"tax": "법인", "lang": "en"})
    assert not re.search(r"[가-힣]", "".join(k for row in en["rules"] for k in row)), en["rules"][:2]


def _call_en(name, args):
    import asyncio
    from korean_tax_mcp.server import mcp
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


# ── 2. net 연결 실패 기억 ──

class _Resp:
    def __init__(self, data): self._data = data
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, *a): d, self._data = self._data, b""; return d


def _reset():
    return urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """urlopen 가짜. plan(req, n) → 응답 bytes 또는 예외. 호출 기록을 돌려준다."""
    monkeypatch.setenv("LAW_OC", "test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(ntis, "CACHE", tmp_path)           # 디스크 캐시가 결과를 대신 주지 않게
    for f in (law._versions.clear, law._three_tier.cache_clear, law._raw_units.cache_clear,
              law._full_units.cache_clear, law._phrase_defs.cache_clear, ntis.laws.cache_clear):
        f()
    law.clear_caches()
    net.reset()
    calls, box = [], {}

    def urlopen(req, context=None, timeout=None):
        calls.append({"url": req.full_url, "ua": req.get_header("User-agent")})
        out = box["plan"](req, len(calls))
        if isinstance(out, BaseException): raise out
        return _Resp(out)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    def use(plan):
        box["plan"] = plan
        calls.clear()
        return calls
    yield use
    net.reset()


def _get(jo):
    return law._get("lawService.do", f"target=eflaw&MST=1&JO={jo}")


def test_one_reset_failure_does_not_fail_next_article(fake):
    """재현: 제19조의2 요청이 연결 재설정 3번으로 실패한 직후 다른 조문(제45조의2) 요청은 다시 시도해 성공해야 한다."""
    calls = fake(lambda req, n: _reset() if "001902" in req.full_url else b'{"ok": 1}')
    with pytest.raises(net.Unreachable) as e:
        _get("001902")
    assert len(calls) == 3 and "법제처" in str(e.value) and "끊" in str(e.value)
    assert _get("004502") == {"ok": 1}                # 시도 없이 실패하지 않음
    assert len(calls) == 4


def test_law_article_chain_after_reset(fake):
    """law_article 수준: 한 조문이 끊김으로 실패해도 바로 다음 조문 조회는 본문을 받는다."""
    art = {"법령": {"조문": {"조문단위": [{"조문여부": "조문", "조문번호": "45", "조문가지번호": "02",
                                        "조문내용": "제45조의2(경정 등의 청구) ① 과세표준신고서를 …"}]}}}
    state = {"fail": 3}

    def plan(req, n):
        if state["fail"]:
            state["fail"] -= 1
            return _reset()
        if "lawSearch.do" in req.full_url:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            return json.dumps({"LawSearch": {"totalCnt": "1", "law": [
                {"법령명한글": q["query"][0], "법령일련번호": "1", "시행일자": "20250101"}]}}).encode()
        return json.dumps(art).encode()

    fake(plan)
    r1 = server.law_article("법인세법 시행령", "제19조의2", as_of="20251231")
    assert "법제처" in r1.get("error", ""), r1
    r2 = server.law_article("국세기본법", "제45조의2", as_of="20251231")
    assert "경정 등의 청구" in r2.get("본문", ""), r2


def test_circuit_keyed_by_site_and_kind(fake):
    fake(lambda req, n: _reset())
    with pytest.raises(net.Unreachable):
        _get("000100")
    assert ("law", "reset") in net._down and not any(k[0] == "nts" for k in net._down), net._down
    calls = fake(lambda req, n: urllib.error.URLError(ConnectionRefusedError(111, "refused")))
    with pytest.raises(net.Unreachable) as e:
        _get("000200")
    assert len(calls) == 1 and "거부" in str(e.value)  # 앞의 끊김 기억이 다른 종류의 실패 안내를 가리지 않음
    assert ("law", "refused") in net._down
    # 다른 사이트는 영향 없음
    calls = fake(lambda req, n: json.dumps({"status": "SUCCESS", "data": {"X": {"ok": 1}}}).encode())
    assert ntis._fetch("X", {}, 10) == {"ok": 1} and len(calls) == 1


def test_success_clears_circuit(fake):
    state = {"mode": "reset"}
    calls = fake(lambda req, n: _reset() if state["mode"] == "reset" else b'{"ok": 1}')
    with pytest.raises(net.Unreachable):
        _get("000100")
    assert net._blocked("law") == "reset"
    state["mode"] = "ok"
    assert _get("000200") == {"ok": 1}
    assert net._blocked("law") is None and not net._down
    state["mode"] = "reset"
    calls.clear()
    with pytest.raises(net.Unreachable) as e:
        _get("000300")
    assert len(calls) == 3 and "3회 시도" in str(e.value)   # 기억이 지워졌으니 다시 끝까지 시도


def test_reset_memory_allows_single_quick_attempt(fake):
    """끊김을 기억하는 동안의 다음 요청은 재시도 없이 한 번만 시도 — 막힌 사이트에서 대기를 곱절로 쌓지 않음."""
    calls = fake(lambda req, n: _reset())
    with pytest.raises(net.Unreachable):
        _get("000100")
    calls.clear()
    with pytest.raises(net.Unreachable) as e:
        _get("000200")
    assert len(calls) == 1
    msg = str(e.value)
    assert "직전 20초 안에 같은 실패" in msg and "연결 재설정" in msg and "다시 시도" in msg and "로컬" in msg, msg


@pytest.mark.parametrize("exc,word", [
    (lambda: urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")), "거부"),
    (lambda: urllib.error.URLError(socket.gaierror(-2, "Name or service not known")), "주소를 찾지 못했습니다"),
])
def test_connection_level_failures_still_short_circuit(fake, exc, word):
    calls = fake(lambda req, n: exc())
    with pytest.raises(net.Unreachable):
        _get("000100")
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(net.Unreachable) as e:
        _get("000200")
    assert len(calls) == 0                                    # 연결 단계 거절은 잠시 시도 없이 실패(기존 동작)
    assert word in str(e.value) and "직전 20초 안에 같은 실패가 있어 다시 시도하지 않음" in str(e.value)


def test_repeated_timeouts_allow_single_quick_attempt(fake):
    """끝까지 다 시도해도 시간 초과면 끊김처럼 기억 — 다음 요청은 한 번만 시도해 매 호출 ~39초 대기가 쌓이지 않음."""
    calls = fake(lambda req, n: socket.timeout("timed out"))
    with pytest.raises(net.Unreachable):
        _get("000100")
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(net.Unreachable) as e:
        _get("000200")
    assert len(calls) == 1 and "직전 20초 안에 같은 실패" in str(e.value)


def test_single_slow_response_then_success_no_trip(fake):
    calls = fake(lambda req, n: socket.timeout("timed out") if n == 1 else b'{"ok": 1}')
    assert _get("000100") == {"ok": 1} and len(calls) == 2
    assert not net._down


def test_budget_cut_never_trips_law(fake):
    fake(lambda req, n: _reset())
    with net.budget(1.5):
        with pytest.raises(net.BudgetExceeded):
            net.request(urllib.request.Request("https://www.law.go.kr/x"), site="law")
    assert not net._down


def test_honest_user_agent_kept(fake):
    calls = fake(lambda req, n: b'{"ok": 1}')
    _get("000100")
    ua = calls[0]["ua"]
    assert ua.startswith(f"korean-tax-mcp/{korean_tax_mcp.__version__}") and "Mozilla" not in ua
