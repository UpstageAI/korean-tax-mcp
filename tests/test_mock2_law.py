"""모의 2차(2026-11-04) 응시 기록에서 확인된 law 서버 결함 회귀 테스트 — 네트워크 없이 돈다.

조문 본문은 2026-11-04 법제처 DRF에서 받은 기준일 20251231 시행본(fixtures/mock2_law_articles.json),
국세청 문서번호 검색 결과는 같은 날 국세법령정보시스템 응답(fixtures/mock2_ntis_docs.json)을 되돌려 준다.
"""
import asyncio
import json
import os
import re

import pytest

from korean_tax_mcp import casebook, cite, law, ntis
from korean_tax_mcp import timing_rules as T
from korean_tax_mcp.server import mcp

FX = os.path.join(os.path.dirname(__file__), "fixtures")
ARTS = json.load(open(os.path.join(FX, "mock2_law_articles.json"), encoding="utf-8"))
DOCS = json.load(open(os.path.join(FX, "mock2_ntis_docs.json"), encoding="utf-8"))
AS_OF = "20251231"


@pytest.fixture(autouse=True)
def _clear_law_caches():
    def clear():
        for name in ("_versions", "_three_tier", "_raw_units", "_full_units", "_phrase_defs", "_en_versions"):
            f = getattr(law, name)
            (f.clear if hasattr(f, "clear") else f.cache_clear)()
        law._FIND_CACHE.clear()
    clear()
    yield
    clear()


class FakeDRF:
    """법제처 DRF 대역 — 연혁 검색(lawSearch)은 법령마다 시행본 1건, 조문(lawService)은 녹화한 본문을 돌려준다."""

    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows  # {검색어: [연혁 행]} — 없으면 녹화한 조문 법령명으로 1건씩

    def __call__(self, path, query):
        self.calls.append((path, query))
        if path == "lawSearch.do":
            import time; time.sleep(0.05)   # 실제 조회처럼 시간이 걸려야 동시 조회 중복이 드러난다
        q = dict(kv.split("=", 1) for kv in query.split("&"))
        if path == "lawSearch.do":
            import urllib.parse
            name = urllib.parse.unquote(q.get("query", ""))
            if self.rows is not None:
                rows = self.rows.get(name, [])
            else:
                rows = [{"법령명한글": name, "법령일련번호": str(abs(hash(name)) % 10**6), "시행일자": "20251001",
                         "현행연혁코드": "현행"}] if any(k.startswith(name + "|") for k in ARTS) else []
            return {"LawSearch": {"law": rows, "totalCnt": str(len(rows))}}
        if path == "lawService.do":
            jo = q.get("JO")
            for key, a in ARTS.items():
                name, art, _ = key.split("|")
                if law.jo6(art) == jo and str(abs(hash(name)) % 10**6) == q.get("MST"):
                    return {"법령": {"조문": [{"조문내용": ln} for ln in a["본문"].split("\n")]}}
            return {"법령": {"조문": []}}
        raise AssertionError(f"예상 못 한 호출 {path}")


@pytest.fixture
def drf(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    f = FakeDRF()
    monkeypatch.setattr(law, "_get", f)
    monkeypatch.setattr(law, "toc", lambda *a, **k: {"개요": "제1장 총칙", "이 조가 속한 곳": "제2장", "같은 곳 조문": "제19조의2"})
    monkeypatch.setattr(law, "links", lambda *a, **k: {
        "상위": [{"법령": "법인세법", "조": "제19조의2", "항": "제1항", "구절": "대통령령으로 정하는 사유", "확인": "원문인용"}],
        "하위": [{"법령": "법인세법 시행규칙", "조": "제10조의4", "확인": "공식표"}]})
    return f


@pytest.fixture
def nts(monkeypatch):
    def fake(query, kinds=("해석", "판례"), tax=None, sort="정확도", n=5, **k):
        if query in DOCS:
            return DOCS[query]
        if query.startswith("국심"):
            return [{"문서번호": "국심-1998-서-0164", "제목": "국심 결정", "일자": "1998-03-01", "링크": "https://x"}]
        return []
    monkeypatch.setattr(ntis, "_search", fake)


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


def _hangul_keys(o, path=""):
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            if re.search(r"[가-힣]", str(k)): out.append(f"{path}/{k}")
            out += _hangul_keys(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): out += _hangul_keys(v, f"{path}[{i}]")
    return out


# ── verify_citations (#70·#33) ─────────────────────────────────────────────

def test_verify_reads_court_judgment_citation_style(nts, monkeypatch):
    """#70 '대법원 2002. 9. 24. 선고 2001두489 판결' 형식(두 자리 연도 포함)을 문서번호로 읽는다."""
    monkeypatch.delenv("LAW_OC", raising=False)
    r = cite.verify("대법원 2002. 9. 24. 선고 2001두489 판결과 대법원 1990. 3. 13. 선고 88누3123 판결에 따르면 …")
    got = {d["문서번호"] for d in r["문서번호"] if d["결과"] == "확인"}
    assert got == {"대법원-2001-두-489", "대법원-88-누-3123"}, r
    assert "확인 안 된 것 0건" in r["요약"]


def test_verify_reads_tribunal_numbers(nts, monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    r = cite.verify("조심 2015전1925 결정과 국심 98서164 결정")
    got = {d["문서번호"] for d in r["문서번호"] if d["결과"] == "확인"}
    assert got == {"조심-2015-전-1925", "국심-1998-서-0164"}, r


def test_verify_reports_unparsed_citations_instead_of_zero(nts, monkeypatch):
    """#70 인식 못 한 인용은 '형식 미인식'으로 세고, 요약이 '확인 안 된 것 0건'이 되지 않는다."""
    monkeypatch.delenv("LAW_OC", raising=False)
    r = cite.verify("대법원 2020. 1. 30. 선고 판결(사건번호 생략)과 같은 법 제26조의2에 따라 경정청구가 가능하다.")
    assert r.get("형식 미인식"), r
    assert "확인 안 된 것 0건" not in r["요약"]
    assert re.search(r"형식 미인식 \d+건", r["요약"])


def test_verify_keeps_paragraph_and_item(drf):
    """#33 항·호를 버리지 않고, 없는 항은 '확인'이라 하지 않는다."""
    r = cite.verify("법인세법 제25조 제4항 제2호와 법인세법 제999조, 국세기본법 제26조의2 제1항, 법인세법 제25조 제9항에 따라 판단한다.", AS_OF)
    by = {x["인용"]: x for x in r["조문"]}
    assert by["법인세법 제25조 제4항 제2호"]["결과"] == "확인", by
    assert by["국세기본법 제26조의2 제1항"]["결과"] == "확인", by
    assert by["법인세법 제999조"]["결과"] == "조문 없음", by
    assert by["법인세법 제25조 제9항"]["결과"] != "확인", by


def test_verify_fetches_version_list_once_per_law(drf):
    """같은 법령을 여러 번 인용해도 연혁 목록·조문은 한 번만 받는다."""
    cite.verify("법인세법 제25조 제1항, 법인세법 제25조 제4항, 법인세법 제25조 제2항, 법인세법 제999조", AS_OF)
    searches = [q for p, q in drf.calls if p == "lawSearch.do"]
    jo25 = [q for p, q in drf.calls if p == "lawService.do" and "JO=002500" in q]
    assert len(searches) == 1, searches
    assert len(jo25) == 1, jo25


# ── law_article (#65·#66·#67·#38) ──────────────────────────────────────────

def test_reading_note_labels_branch_item(drf):
    """#65 9의2호의 단서 위치를 '제1항 제9호'가 아니라 '제1항 제9호의2'로."""
    r = _call("law_article", {"law_name": "법인세법 시행령", "article": "제19조의2", "as_of": AS_OF})
    notes = {n["원문"]: n["위치"] for n in r.get("읽기 주의", [])}
    hit = [v for k, v in notes.items() if k.startswith("다만, 특수관계인과의 거래")]
    assert hit == ["제1항 제9호의2"], notes


def test_keyword_matches_branch_item_separately(drf):
    """#67 keyword='회수기일' → 9의2호·11호. 9호로 묶지 않는다."""
    r = _call("law_article", {"law_name": "법인세법 시행령", "article": "제19조의2", "as_of": AS_OF, "keyword": "회수기일"})
    assert r["일치_위치"] == ["제1항 제9호의2", "제1항 제11호"], r["일치_위치"]
    r = _call("law_article", {"law_name": "법인세법 시행령", "article": "제19조의2", "as_of": AS_OF, "keyword": "부도"})
    assert "회수기일이 2년" not in r["본문"], r["본문"]


def test_keyword_result_has_no_duplicate_paragraph(drf):
    """#66 keyword='부도' → ②가 본문에 한 번만."""
    r = _call("law_article", {"law_name": "법인세법 시행령", "article": "제19조의2", "as_of": AS_OF, "keyword": "부도"})
    assert r["본문"].count("제1항제9호에 따른 부도발생일은") == 1, r["본문"]


def test_article_text_has_no_raw_img_tag(drf):
    """#38 <img> 태그는 본문에서 빼고 그림 링크는 따로."""
    r = _call("law_article", {"law_name": "법인세법", "article": "제25조", "as_of": AS_OF, "paragraph": "④"})
    assert "<img" not in r["본문"], r["본문"][:300]
    assert any("flSeq=54190791" in u for u in r.get("그림", [])), r.get("그림")


# ── timing_rules (#37·#71) ─────────────────────────────────────────────────

def test_timing_rules_says_when_tax_has_no_own_rules():
    r = T.lookup("양도")
    assert "law_article" in r.get("안내", "") and "제98조" in r["안내"], r


def test_timing_rules_kind_ignores_spacing():
    assert T.lookup("법인", "손익귀속")["규칙"]


def test_timing_rules_zero_hits_give_notice():
    r = T.lookup("법인", None, "대손")
    assert r["규칙"] == [] and "해당 규칙 없음" in r.get("안내", "") and "law_article" in r["안내"], r


def test_timing_rules_warns_for_past_year():
    r = _call("timing_rules", {"tax": "법인", "as_of": "20251231"})
    assert "현행" in r.get("기준일 주의", ""), r.keys()
    assert "기준일 주의" not in _call("timing_rules", {"tax": "법인"})


# ── casebook_search (#72) ──────────────────────────────────────────────────

def test_casebook_drops_unrelated_cases():
    assert casebook.search("부당행위 시가 판단 시점") == []
    r = _call("casebook_search", {"query": "부당행위 시가 판단 시점"})
    assert r["결과"] == [] and "search_tax_rulings" in r.get("안내", ""), r
    top = casebook.search("합병 세액공제", None, 5)
    assert top and "합병" in top[0]["쟁점"]
    assert casebook.search("가지급금 인정이자", None, 3)


# ── lang='en' (#34·#35·#36) ────────────────────────────────────────────────

def test_english_keys_timing_casebook_residency():
    for name, args in (("timing_rules", {"tax": "부가", "lang": "en"}), ("timing_rules", {"lang": "en"}),
                       ("timing_rules", {"tax": "양도", "lang": "en", "as_of": "20251231"}),
                       ("casebook_search", {"query": "가지급금 인정이자", "lang": "en"}),
                       ("casebook_search", {"query": "부당행위 시가 판단 시점", "lang": "en"}),
                       ("residency_check", {"judgment_year": 2025, "domestic_stay_days": 200, "lang": "en"})):
        r = _call(name, args)
        assert not _hangul_keys(r), (name, _hangul_keys(r)[:10])


def test_english_keys_law_article_and_find_article(drf, monkeypatch):
    monkeypatch.setattr(law, "article_en", lambda *a: {"error": "No official English translation found"})
    r = _call("law_article", {"law_name": "법인세법", "article": "제25조", "lang": "en"})
    assert not _hangul_keys(r), _hangul_keys(r)
    monkeypatch.setattr(law, "find_article", lambda *a, **k: {
        "결과": [{"법령": "국세징수법", "조": "제41조", "제목": "압류금지 재산", "적용 시행일": "20261002", "일치 문장": ["18. …"]}],
        "관련 부칙": [{"법령": "국세징수법", "부칙": "…"}], "다음 단계": "law_article(law_name, 조, keyword=...)로 해당 항만 조회"})
    r = _call("find_article", {"keyword": "압류금지 생계비계좌", "law_name": "국세징수법", "lang": "en"})
    assert not _hangul_keys(r), _hangul_keys(r)


def test_english_keys_verify_citations(nts, monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    r = _call("verify_citations", {"text": "대법원 2002. 9. 24. 선고 2001두489 판결, 법인세법 제25조 제4항, 같은 법 제5조", "lang": "en"})
    assert not _hangul_keys(r), _hangul_keys(r)


def test_english_input_values_accepted(monkeypatch):
    """#36 lang='en'이면 영어 소득 종류·세목도 받는다."""
    seen = {}
    monkeypatch.setattr(ntis, "withholding_rates", lambda country, income: seen.setdefault("income", income) and {"국가": country})
    asyncio.run(mcp.call_tool("treaty_withholding_rates", {"country": "미국", "income": "interest", "lang": "en"}))
    assert seen["income"] == "이자"
    r = _call("timing_rules", {"tax": "VAT", "lang": "en"})
    assert r.get("tax") == "VAT" and r.get("rules"), r


# ── 법령명 띄어쓰기·옛 이름 (coordinator 추가) ─────────────────────────────

NAME_ROWS = {
    "상속세및증여세법": [
        {"법령명한글": "상속세및증여세법", "법령일련번호": "OLD", "시행일자": "20050114", "현행연혁코드": "연혁"},
        {"법령명한글": "상속세및증여세법", "법령일련번호": "OLDER", "시행일자": "20031230", "현행연혁코드": "연혁"},
        {"법령명한글": "상속세 및 증여세법", "법령일련번호": "NEW", "시행일자": "20251001", "현행연혁코드": "연혁"},
        {"법령명한글": "상속세 및 증여세법", "법령일련번호": "CUR", "시행일자": "20260102", "현행연혁코드": "현행"},
        {"법령명한글": "상속세 및 증여세법 시행규칙", "법령일련번호": "RULE", "시행일자": "20260320", "현행연혁코드": "현행"},
    ],
    "옛세법": [{"법령명한글": "옛세법", "법령일련번호": "GONE", "시행일자": "19991231", "현행연혁코드": "연혁"}],
}


def test_law_name_without_spaces_resolves_to_version_in_force(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    monkeypatch.setattr(law, "_get", FakeDRF(NAME_ROWS))
    assert law.version("상속세및증여세법", AS_OF) == ("NEW", "20251001")
    assert law.version("상속세및증여세법", "20040101") == ("OLDER", "20031230")


def test_article_reports_official_name_and_warns_on_stale_law(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    f = FakeDRF(NAME_ROWS)
    def get(path, query):
        if path == "lawService.do":
            return {"법령": {"조문": [{"조문내용": "제35조(저가 양수 또는 고가 양도에 따른 이익의 증여)"}]}}
        return f(path, query)
    monkeypatch.setattr(law, "_get", get)
    r = law.article("상속세및증여세법", "제35조", AS_OF)
    assert r["적용 시행일"] == "20251001" and r["법령"] == "상속세 및 증여세법", r
    r = law.article("옛세법", "제1조", AS_OF)
    assert "법령명 경고" in r, r


# ── tax_treaty keyword 순서 (coordinator 추가, 낮은 우선) ──────────────────

def test_treaty_keyword_puts_title_match_first(monkeypatch):
    monkeypatch.setattr(ntis, "treaties", lambda: {"미국": {"id": "X", "발효일": "1979.10.20."}})
    rows = [{"txaAgrmTextUqnm": "제5조", "txaAgrmTextNm": "일반적 과세규칙", "txaAgrmTextCntn": "… 배당 …"},
            {"txaAgrmTextUqnm": "제12조", "txaAgrmTextNm": "배당", "txaAgrmTextCntn": "배당에 대하여 …"}]
    monkeypatch.setattr(ntis, "_act", lambda *a, **k: {"txaTraDVOList": rows})
    r = ntis.treaty("미국", "", "배당")
    assert [x["조"] for x in r["조문"]] == ["제12조", "제5조"], r["조문"]
