"""기준일(as_of) 정규화 한 곳(law.as_of_or_today)과 항 번호 ①↔N 변환 한 곳(law.hang_circled·hang_num) — 네트워크 없이 돈다.

법제처 DRF 대역은 시행본 1건(시행일 20200101)과 항이 7개인 조문 하나를 돌려준다.
"""
import asyncio
import json
import urllib.parse

import pytest

from korean_tax_mcp import law, server
from korean_tax_mcp.server import mcp

HANG = [f"{law.hang_circled(i)} 제{i}항 본문 — 세무서장은 {i}천만원 이상이면 통지한다." for i in range(1, 8)]
UNIT = {"조문번호": "7", "조문가지번호": "00", "조문여부": "조문", "조문제목": "통지",
        "조문내용": "제7조(통지) ",
        "항": [{"항번호": law.hang_circled(i), "항내용": HANG[i - 1]} for i in range(1, 8)]}


def _drf(path, query):
    q = dict(kv.split("=", 1) for kv in query.split("&"))
    if path == "lawSearch.do":
        name = urllib.parse.unquote(q.get("query", ""))
        return {"LawSearch": {"law": [{"법령명한글": name, "법령일련번호": "1", "시행일자": "20200101", "현행연혁코드": "현행"}]}}
    if path == "lawService.do":
        return {"법령": {"조문": {"조문단위": [UNIT]}, "부칙": {"부칙단위": []}}}
    raise AssertionError(path)


@pytest.fixture
def drf(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    for name in ("_versions", "_three_tier", "_raw_units", "_full_units", "_phrase_defs", "_en_versions"):
        f = getattr(law, name)
        (f.clear if hasattr(f, "clear") else f.cache_clear)()
    law._FIND_CACHE.clear()
    law.clear_caches()
    monkeypatch.setattr(law, "_get", _drf)
    monkeypatch.setattr(law, "toc", lambda *a, **k: {})
    monkeypatch.setattr(law, "links", lambda *a, **k: {"상위": [], "하위": []})
    yield
    law._versions.clear(); law._full_units.cache_clear(); law._FIND_CACHE.clear(); law.clear_caches()


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


# ── as_of_or_today ──

def test_as_of_or_today_formats_and_errors():
    assert law.as_of_or_today("2025-03-01") == law.as_of_or_today("2025.03.01") == law.as_of_or_today("20250301") == "20250301"
    assert law.as_of_or_today("") == law.as_of_or_today(None) == law.today()
    assert len(law.today()) == 8 and law.today().isdigit()
    with pytest.raises(ValueError) as e: law.as_of_or_today("2025-3-1")
    assert "2025-3-1" in str(e.value) and "YYYYMMDD" in str(e.value)


FORMATS = ("2025-03-01", "2025.03.01", "20250301")


def _seen(monkeypatch, name):
    """law.<name>(…, ef)가 받은 기준일을 기록 — 결과에 기준일 필드가 없는 도구용."""
    got, real = [], getattr(law, name)
    def spy(*a, **k):
        got.append(a[-1] if len(a) > 1 else k.get("as_of"))
        return real(*a, **k)
    monkeypatch.setattr(law, name, spy)
    return got


def test_law_article_as_of_formats(drf):
    rs = [_call("law_article", {"law_name": "국세징수법", "article": "제7조", "as_of": f}) for f in FORMATS]
    assert all("error" not in r for r in rs), rs
    assert {r["적용 기준일"] for r in rs} == {"2025년 3월 1일"}
    assert all("기준일 안내" not in r for r in rs)
    r = _call("law_article", {"law_name": "국세징수법", "article": "제7조", "as_of": ""})
    t = law.today()
    assert r["적용 기준일"] == f"{t[:4]}년 {int(t[4:6])}월 {int(t[6:8])}일" and "기준일 안내" in r
    assert "2025-3-1" in _call("law_article", {"law_name": "국세징수법", "article": "제7조", "as_of": "2025-3-1"})["error"]


def test_find_article_as_of_formats(drf, monkeypatch):
    got = _seen(monkeypatch, "_fetch_law_articles")
    for f in FORMATS + ("",):
        law._FIND_CACHE.clear(); got.clear()
        r = _call("find_article", {"keyword": "통지", "law_name": "국세징수법", "as_of": f})
        assert r.get("결과"), r
        assert set(got) == {law.today() if f == "" else "20250301"}, (f, got)   # 조문 수집이 받은 기준일(호출마다 여러 번)


def test_verify_citations_as_of_formats(drf, monkeypatch):
    got = _seen(monkeypatch, "article")
    for f in FORMATS + ("",):
        r = _call("verify_citations", {"text": "국세징수법 제7조 제3항에 따르면", "as_of": f})
        assert r["조문"] and r["조문"][0]["결과"] == "확인", r
    assert got == ["20250301"] * 3 + [law.today()], got


@pytest.mark.parametrize("tool,extra", [("verify_statement", {"statement": "세무서장은 3천만원 이상이면 통지한다.", "article": "제7조"}),
                                        ("judge_options", {"statements": ["세무서장은 3천만원 이상이면 통지한다."], "articles": ["제7조"]})])
def test_verify_and_judge_as_of_formats(drf, tool, extra):
    rs = [_call(tool, {"law_name": "국세징수법", "as_of": f, **extra}) for f in FORMATS]
    assert all("error" not in r for r in rs), rs
    assert {r["시행본"] for r in rs} == {"20250301"}
    assert _call(tool, {"law_name": "국세징수법", "as_of": "", **extra})["시행본"] == law.today()


# ── hang_circled / hang_num ──

def test_hang_round_trip_1_to_20():
    for n in range(1, 21):
        c = law.hang_circled(n)
        assert len(c) == 1 and 0x2460 <= ord(c) <= 0x2473 and law.hang_num(c) == n
    assert law.hang_circled(1) == "①" and law.hang_circled(20) == "⑳"
    assert law.hang_circled(0) is None and law.hang_circled(21) is None
    assert law.hang_num("1") is None and law.hang_num("") is None and law.hang_num(None) is None
    assert law.hang_num("㉑") is None          # 21 이상은 어느 조문 처리도 쓰지 않음 — 지원 안 함
    assert law.hang_num("⑥2호") == 6           # 첫 글자만 본다


def test_hang_six_plus_renders_and_matches(drf):
    """항이 7개인 조문: 제6항·제7항 지정이 ⑥·⑦ 단위와 맞고(verify_statement·law_article paragraph), 보기 번호는 ①~⑤만 원문자."""
    r = _call("verify_statement", {"law_name": "국세징수법", "article": "제7조", "statement": "세무서장은 6천만원 이상이면 통지한다.", "paragraph": "제6항"})
    assert "error" not in r and r["근거"]["위치"] == "제7조 ⑥", r
    r = _call("verify_statement", {"law_name": "국세징수법", "article": "제7조", "statement": "세무서장은 7천만원 이상이면 통지한다.", "paragraph": "7"})
    assert r["근거"]["위치"] == "제7조 ⑦", r
    r = _call("law_article", {"law_name": "국세징수법", "article": "제7조", "paragraph": "제6항"})
    assert "⑥ 제6항 본문" in r["본문"] and "⑦" not in r["본문"], r
    assert law.normalize_article("제7조 ⑥") == ("제7조", "제6항") and law.normalize_article("제7조 제6항") == ("제7조", "제6항")
    assert [o["id"] for o in server._split_options("ㄱ. 가 ㄴ. 나 ㄷ. 다 ㄹ. 라 ㅁ. 마")] == ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ"]
    r = _call("judge_options", {"law_name": "국세징수법", "articles": ["제7조"],
                                "statements": [f"세무서장은 {i}천만원 이상이면 통지한다." for i in range(1, 8)]})
    assert [b["id"] for b in r["보기별"]] == ["①", "②", "③", "④", "⑤", "6", "7"], r
    assert r["보기별"][5]["근거"]["위치"] == "제7조 ⑥" and r["보기별"][6]["근거"]["위치"] == "제7조 ⑦", r
