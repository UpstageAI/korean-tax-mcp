"""law_article 반환 범위 표기(긴 조문·keyword 일치 없음), 도구 설명 원문자, net 연결 실패 기억 주석 회귀 테스트.

조문 본문은 법제처 DRF에서 받은 기준일 20251231 시행본(fixtures/r5_law_articles.json: 법인세법 시행령 제72조,
국세기본법 제26조의2)을 되돌려 준다. 네트워크 없이 돈다.
"""
import asyncio
import inspect
import json
import os
import re
import socket
import urllib.parse
import urllib.request

import pytest

from korean_tax_mcp import law, net
from korean_tax_mcp.server import mcp

FX = os.path.join(os.path.dirname(__file__), "fixtures")
ARTS = json.load(open(os.path.join(FX, "r5_law_articles.json"), encoding="utf-8"))
AS_OF = "20251231"


@pytest.fixture(autouse=True)
def _clear_law_caches():
    def clear():
        for name in ("_versions", "_three_tier", "_raw_units", "_full_units", "_phrase_defs", "_en_versions"):
            f = getattr(law, name)
            (f.clear if hasattr(f, "clear") else f.cache_clear)()
        law._FIND_CACHE.clear()
    clear()
    net.reset()
    yield
    clear()
    net.reset()


def _mst(name):
    return str(sum(map(ord, name)) % 10**6)


def _fake_get(path, query):
    q = dict(kv.split("=", 1) for kv in query.split("&"))
    if path == "lawSearch.do":
        name = urllib.parse.unquote(q.get("query", ""))
        rows = [{"법령명한글": name, "법령일련번호": _mst(name), "시행일자": "20251001", "현행연혁코드": "현행"}] \
            if any(k.startswith(name + "|") for k in ARTS) else []
        return {"LawSearch": {"law": rows, "totalCnt": str(len(rows))}}
    if path == "lawService.do":
        for key, a in ARTS.items():
            name, art, _ = key.split("|")
            if law.jo6(art) == q.get("JO") and _mst(name) == q.get("MST"):
                return {"법령": {"조문": [{"조문내용": ln} for ln in a["본문"].split("\n")]}}
        return {"법령": {"조문": []}}
    return {}


@pytest.fixture
def drf(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    monkeypatch.setattr(law, "_get", _fake_get)
    monkeypatch.setattr(law, "toc", lambda *a, **k: {"개요": "", "이 조가 속한 곳": "", "같은 곳 조문": ""})
    monkeypatch.setattr(law, "links", lambda *a, **k: {"상위": [], "하위": []})


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


def _full(name, art):
    return ARTS[f"{name}|{art}|{AS_OF}"]["본문"]


# ── keyword 일치 없음: 본문을 말없이 자르지 않는다 ─────────────────────────
def test_keyword_no_match_returns_whole_short_article(drf):
    """법인세법 시행령 제72조(3,533자)에 '시가를 초과'가 없을 때 — 4,000자 이하이므로 본문 전체."""
    r = _call("law_article", {"law_name": "법인세법 시행령", "article": "제72조", "as_of": AS_OF, "keyword": "시가를 초과"})
    assert "error" not in r, r
    assert r.get("일치 없음") and r.get("항_호_목록"), r
    assert r["반환 범위"].startswith("일치 없음"), r["반환 범위"]
    full = _full("법인세법 시행령", "제72조")
    assert len(full) > 2000
    assert len(r["본문"]) >= len(full) - 40, (len(r["본문"]), len(full))     # 줄바꿈 정리 차이만 허용
    assert "⑤" in r["본문"] and "③" in r["본문"]                               # 제3항~제5항까지 들어 있음


def test_keyword_no_match_long_article_marks_omission(monkeypatch):
    """4,000자를 넘는 조문에서 일치가 없으면 항 단위로 자르고 생략된 항·반환 범위를 밝힌다."""
    body = "제90조(긴 조문)\n" + "\n".join(f"{c} " + f"제{i}항 내용 문장입니다. " * 60 for i, c in enumerate("①②③④⑤⑥⑦⑧", 1))
    assert len(body) > 4000
    monkeypatch.setattr(law, "article", lambda *a, **k: {"법령": "가상법", "조": "제90조", "본문": body})
    a = law._article_body_with_scope("가상법", "제90조", None, AS_OF, None, "없는낱말")
    assert a["반환 범위"].startswith("일치 없음"), a["반환 범위"]
    assert a.get("생략된 항"), a
    omitted = a["생략된 항"]
    assert f"{omitted[0]}~{omitted[-1]}" in a["반환 범위"] and "생략" in a["반환 범위"], a["반환 범위"]
    assert len(a["본문"]) <= 4000
    for hang in omitted:
        n = int(re.sub(r"\D", "", hang))
        assert "①②③④⑤⑥⑦⑧"[n - 1] not in a["본문"], (hang, a["본문"][-80:])


# ── 긴 조문: '반환 범위'가 실제로 돌려준 항을 말함 ─────────────────────────────
def test_long_article_scope_names_returned_paragraphs(drf):
    r = _call("law_article", {"law_name": "국세기본법", "article": "제26조의2", "as_of": AS_OF})
    assert "error" not in r, r
    omitted = r.get("생략된 항")
    assert omitted, r
    scope = r["반환 범위"]
    assert scope != "항 목록", scope
    first_omitted = int(re.sub(r"\D", "", omitted[0]))
    last_full = first_omitted - 1 - (1 if r.get("잘린 항") else 0)
    assert f"제1항~제{last_full}항" in scope, scope
    assert f"{omitted[0]}~{omitted[-1]}" in scope and "생략" in scope, scope
    assert "항 목록" in r
    for i in range(1, last_full + 1):
        assert "①②③④⑤⑥⑦⑧⑨⑩"[i - 1] in r["본문"], (i, scope)


def test_long_article_scope_r5_values(drf):
    r = _call("law_article", {"law_name": "국세기본법", "article": "제26조의2", "as_of": AS_OF})
    assert r["생략된 항"] == ["제7항", "제8항", "제9항"], r.get("생략된 항")
    assert "제1항~제6항" in r["반환 범위"] and "제7항~제9항" in r["반환 범위"], r["반환 범위"]


# ── 도구 설명·인자 설명에 원문자 없음(일부 클라이언트에서 숫자로 풀려 조문 번호와 붙음) ─────
_CIRCLED = re.compile("[①-⓿❶-➓㉑-㉟㊱-㊿]")


def test_no_circled_numbers_in_tool_descriptions():
    bad = []
    for t in asyncio.run(mcp.list_tools()):
        text = (t.description or "") + json.dumps(t.input_schema, ensure_ascii=False)
        if _CIRCLED.search(text):
            bad.append((t.name, sorted(set(_CIRCLED.findall(text)))))
    assert not bad, bad


def test_treaty_description_reads_article_as_text():
    t = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "treaty_withholding_rates")
    assert "제98조의7제1항제2호" in t.description, t.description


# ── net: 시간 초과도 기억(다음 요청은 1회만) — 주석과 동작이 같음 ─────────────────
def test_timeout_remembered_then_single_attempt(monkeypatch):
    calls = []

    def slow(req, context=None, timeout=None):
        calls.append(1)
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", slow)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    tries = []
    for _ in range(3):
        before = len(calls)
        with pytest.raises(net.Unreachable) as e:
            net.request(urllib.request.Request("https://taxlaw.nts.go.kr/x"), site="nts")
        tries.append(len(calls) - before)
        assert e.value.kind == "timeout"
    assert tries == [3, 1, 1]


def test_net_comments_match_timeout_behavior():
    src = inspect.getsource(net)
    assert not re.search(r"시간 초과[^\n]{0,20}기억하지 않", src), "시간 초과를 기억하지 않는다는 주석이 남아 있음"
    doc = net.__doc__
    assert re.search(r"시간 초과[^\n]*한 번만 시도|끊김·시간 초과[^\n]*한 번만", doc), doc
