"""실사용 점검(2026-11-04)에서 확인된 law 서버 결함 회귀 테스트 — 네트워크 없이 돈다.

조문 본문은 2026-11-04 법제처 DRF에서 받은 기준일 20251231 시행본(fixtures/b_law_articles.json),
조세조약은 같은 날 국세법령정보시스템 응답(fixtures/b_law_treaties.json, 일본·싱가포르 — 필요한 조문만 남김)을 되돌려 준다.
"""
import asyncio
import json
import os

import pytest

from korean_tax_mcp import law, ntis
from korean_tax_mcp.server import mcp

FX = os.path.join(os.path.dirname(__file__), "fixtures")
ARTS = json.load(open(os.path.join(FX, "b_law_articles.json"), encoding="utf-8"))
TREATY = json.load(open(os.path.join(FX, "b_law_treaties.json"), encoding="utf-8"))
AS_OF = "20251231"


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


@pytest.fixture
def arts(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    monkeypatch.setattr(law, "article", lambda name, art, ef="": dict(ARTS[f"{name}|{art}|{AS_OF}"]))
    monkeypatch.setattr(law, "toc", lambda *a, **k: {})
    monkeypatch.setattr(law, "links", lambda *a, **k: {"상위": [], "하위": []})


@pytest.fixture
def treaties(monkeypatch):
    ntis.treaties.cache_clear()
    by_id = {x["txaAgrmBscId"]: x["txaAgrmNtnNm"] for x in TREATY["목록"]}

    def fake_act(action, param, timeout=40):
        if action == "ASISTC001MR01":
            return {"txaTraDVOList": TREATY["목록"]}
        if action == "ASISTC002MR01":
            return {"txaTraDVOList": TREATY["조문"][by_id[param["txaAgrmBscId"]]]}
        raise AssertionError(f"예상 못 한 호출 {action}")
    monkeypatch.setattr(ntis, "_act", fake_act)
    yield
    ntis.treaties.cache_clear()


# ── law_article keyword (#92·#100) ─────────────────────────────────────────

def test_keyword_found_in_paragraph_head(arts):
    """#92 '한도'는 부가령 제84조 ②·③의 각 호 앞 문장에 있다 — '일치 없음'이 아니다."""
    r = _call("law_article", {"law_name": "부가가치세법 시행령", "article": "제84조", "as_of": AS_OF, "keyword": "한도"})
    assert r["반환 범위"] != "일치 없음", r["반환 범위"]
    assert r["일치_위치"] == ["제2항 각 호 외의 부분", "제3항 각 호 외의 부분"], r["일치_위치"]
    assert "금액의 한도를 다음 각 호의 구분에 따라" in r["본문"], r["본문"][:500]
    assert "④ 제1항부터 제3항까지의 규정에 따라" not in r["본문"]


def test_keyword_ignores_spacing(arts):
    """#92 띄어쓰기가 달라도 같은 말로 찾는다."""
    r = _call("law_article", {"law_name": "부가가치세법 시행령", "article": "제84조", "as_of": AS_OF, "keyword": "금액의한도를"})
    assert r["일치_위치"] == ["제2항 각 호 외의 부분"], r.get("일치_위치") or r["반환 범위"]


def test_keyword_scope_separates_context_items(arts):
    """#100 '동거봉양'은 ②·④ 각 호 앞 문장과 ⑤에만 있다. 맥락으로 붙인 호는 '일치'로 적지 않는다."""
    r = _call("law_article", {"law_name": "소득세법 시행령", "article": "제155조", "as_of": AS_OF, "keyword": "동거봉양"})
    assert r["일치_위치"] == ["제2항 각 호 외의 부분", "제4항 각 호 외의 부분", "제5항"], r["일치_위치"]
    assert r["맥락_위치"] == ["제2항 제1호~제4호", "제4항 제1호~제3호"], r.get("맥락_위치")
    scope = r["반환 범위"]
    assert scope.startswith("keyword 일치"), scope
    head = scope.split("맥락")[0]
    assert "제2항 제1호" not in head and "제4항 제1호" not in head, scope
    # 맥락 호 본문은 그대로 함께 — 단서·순위를 놓치지 않게
    assert "피상속인이 소유한 기간이 가장 긴 1주택" in r["본문"]
    assert r["본문"].count("동거봉양하는 무주택자") == 1


# ── law_article paragraph 호 목록 (#110) ───────────────────────────────────

@pytest.mark.parametrize("spec", ["5호,6호", "5,6호", "제5호, 제6호", "5~6호", "①5호,6호", "제1항 제5호~제6호", "제1항 5호·6호"])
def test_paragraph_item_list(arts, spec):
    r = _call("law_article", {"law_name": "법인세법", "article": "제98조", "as_of": AS_OF, "paragraph": spec})
    assert r["반환 범위"] == "제1항 제5호, 제6호", (spec, r["반환 범위"], r.get("안내"))
    assert "5. 제93조제7호에 따른 국내원천 부동산등양도소득" in r["본문"]
    assert "6. 제93조제8호에 따른 국내원천 사용료소득" in r["본문"]
    assert "7. 제93조제9호" not in r["본문"] and "4. 제93조제6호" not in r["본문"]
    assert "인식할 수 없음" not in r.get("안내", "")


def test_paragraph_item_without_paragraph_says_first_paragraph(arts):
    r = _call("law_article", {"law_name": "법인세법", "article": "제98조", "as_of": AS_OF, "paragraph": "6호"})
    assert r["반환 범위"] == "제1항 제6호", r["반환 범위"]
    assert "제1항" in r.get("안내", ""), r.get("안내")


def test_paragraph_item_list_reports_missing_item(arts):
    r = _call("law_article", {"law_name": "법인세법", "article": "제98조", "as_of": AS_OF, "paragraph": "제1항 8호,9호"})
    assert r["반환 범위"] == "제1항 제8호", r["반환 범위"]
    assert "제9호" in r.get("안내", ""), r.get("안내")


# ── 조세조약 발효일·지방소득세 (#108·#88) ──────────────────────────────────

def test_japan_treaty_effective_date_is_current_treaty(treaties):
    """#108 한일조약은 1998 서명·1999.11.22. 발효 신협정 — 1970.10.29.은 최초 협정."""
    r = _call("tax_treaty", {"country": "일본", "article": "제2조"})
    assert r["발효일"] == "1999.11.22.", r
    assert r["최초 협정 발효일"] == "1970.10.29.", r
    assert "최초협정(1970.10.29.)" in r["종전 협정 문서"], r


def test_singapore_treaty_effective_date_is_current_treaty(treaties):
    """#88 한싱조약 조문은 2019 신협정(2019.12.31. 발효) — 1981.02.11.은 최초 협정."""
    r = _call("tax_treaty", {"country": "싱가포르"})
    assert r["발효일"] == "2019.12.31.", {k: r[k] for k in r if k != "조문"}
    assert r["서명일"] == "2019.05.13."
    assert r["최초 협정 발효일"] == "1981.02.11."
    # 2010 서명 개정의정서는 종전 협정을 고친 것 — 현행 협정의 개정 문서처럼 보이지 않게
    assert "개정의정서(2013.06.28)" in r["종전 협정 문서"], r


def test_japan_withholding_local_tax_included(treaties):
    """#108 한일조약 대상조세에 주민세 → 제한세율은 지방소득세 포함 상한(법인세법 제98조의7①2호)."""
    r = _call("treaty_withholding_rates", {"country": "일본", "income": "사용료"})
    assert r["발효일"] == "1999.11.22.", r["발효일"]
    lt = r["지방소득세"]
    assert lt["대상조세 포함"] is True, lt
    assert "주민세" in lt["근거"], lt
    assert "제98조의7" in lt["안내"] and "포함" in lt["안내"], lt
    assert "지방소득세 별도" not in r["주의"], r["주의"]
    royalty = r["제한세율"][0]
    assert [x["세율(%)"] for x in royalty["세율"]] == [10.0], royalty["세율"]
    assert "최초협정(1970.10.29.)" not in royalty["개정 문서 언급"], royalty["개정 문서 언급"]


def test_singapore_withholding_local_tax_included(treaties):
    r = _call("treaty_withholding_rates", {"country": "싱가포르", "income": "이자"})
    assert r["지방소득세"]["대상조세 포함"] is True, r["지방소득세"]
    assert "지방소득세" in r["지방소득세"]["근거"]
    assert "개정의정서(2013.06.28)" not in r["제한세율"][0]["개정 문서 언급"], r["제한세율"][0]


def test_treaty_english_keys(treaties):
    r = _call("treaty_withholding_rates", {"country": "일본", "income": "royalties", "lang": "en"})
    import re
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k; yield from keys(v)
        elif isinstance(o, list):
            for v in o: yield from keys(v)
    assert not [k for k in keys(r) if re.search(r"[가-힣]", k)], r
