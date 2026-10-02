"""네트워크 없이 도는 테스트."""
import asyncio, json
from korean_tax_mcp import casebook, law, ntis
from korean_tax_mcp.server import mcp


def _call(name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


def test_tools():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"search_tax_rulings", "get_tax_ruling", "rulings_by_article", "basic_rules", "execution_standards",
                     "casebook_search", "law_article", "compare_with_case", "research_issue", "verify_citations",
                     "tax_treaty", "search_nts_publications", "search_local_documents", "treaty_withholding_rates", "search_forms", "article_history", "compare_outcomes"}


def test_codes():
    assert ntis.jo_code("제52조") == "0052005" and ntis.jo_code("제28조의2") == "0028025"
    assert law.jo6("제52조") == "005200" and law.jo6("제28조의2") == "002802"


def test_casebook():
    r = casebook.search("가지급금 인정이자", None, 3)
    assert r and all(x["문서번호"] for x in r) and "사례집" in r[0]["인용"]


def test_input_errors(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    assert "OC" in _call("law_article", {"law_name": "법인세법", "article": "제52조"})["error"]
    for name, args in (("search_tax_rulings", {"query": "x", "tax": "없음"}), ("casebook_search", {"query": "x", "area": "없음"})):
        try: r = asyncio.run(mcp.call_tool(name, args)); assert r.is_error
        except Exception: pass   # 스키마(enum)에서 거절
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)


def test_descriptions_complete():
    for t in asyncio.run(mcp.list_tools()):
        assert t.description and "언제" in t.description and t.annotations.read_only_hint
        assert all(v.get("description") for v in t.input_schema["properties"].values()), t.name


def test_base_date_and_cite_parse():
    from korean_tax_mcp import timeline, cite
    assert timeline.base_date("2023")[0] == "20231231" and timeline.base_date("2023-1", "부가")[0] == "20230630"
    assert timeline.base_date("2023-07-15")[0] == "20230715"
    t = "서면-2025-법인-3159, 대법원 2026두30419, 조심2025인4460, 상속세 및 증여세법 제45조의3, 국제조세조정에 관한 법률 제7조"
    assert len(list(cite.DOC.finditer(t))) == 3
    assert [m.group(1) for m in cite.LAWREF.finditer(t)] == ["상속세 및 증여세법", "국제조세조정에 관한 법률"]


def test_local_docs_needs_folder(monkeypatch):
    monkeypatch.delenv("KOREAN_TAX_MCP_DOCS", raising=False)
    assert "KOREAN_TAX_MCP_DOCS" in _call("search_local_documents", {"query": "x"})["error"]


def test_english_mode():
    from korean_tax_mcp import i18n
    r = i18n.localize({"결과": [{"구분": "질의회신", "기준일 조문과": "다른 시행본(20260701)이나 이 조 본문 동일"}]})
    assert r == {"results": [{"type": "NTS reply", "vs_base_date_text": "different version (20260701), same article text"}]}
    assert all("lang" in t.input_schema["properties"] for t in asyncio.run(mcp.list_tools()))
    out = _call("casebook_search", {"query": "가지급금", "k": 1, "lang": "en"})
    assert "results" in out and "language_note" in out


def test_onprem_solar_config(monkeypatch):
    from korean_tax_mcp import solar
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False); monkeypatch.delenv("KOREAN_TAX_MCP_SOLAR_KEY", raising=False)
    monkeypatch.delenv("KOREAN_TAX_MCP_SOLAR_BASE_URL", raising=False)
    assert not solar.available()
    monkeypatch.setenv("KOREAN_TAX_MCP_SOLAR_BASE_URL", "http://10.0.0.5:8000/v1/")
    base, key, model, onprem = solar.config()
    assert base == "http://10.0.0.5:8000/v1" and onprem and solar.available() and key == ""
    assert solar.where("en").startswith("on-prem")


def test_rate_extraction():
    from korean_tax_mcp import ntis
    txt = ("2. However, such dividends may also be taxed ... but the tax so charged shall not exceed:\n"
           "(a) 5 per cent of the gross amount of the dividends if the beneficial owner is a company which holds directly at least 25 per cent of the capital of the company paying the dividends;\n"
           "(b) 10 per cent of the gross amount of the dividends in all other cases.")
    rates, other = ntis._rate_items(txt)
    assert [r["세율(%)"] for r in rates] == [5.0, 10.0] and [o.get("지분요건(%)") for o in other] == [25.0]


def test_outcome_verdict():
    from korean_tax_mcp.outcome import verdict, WIN, LOSE, PART, OTHER
    assert verdict("주 문 \n 심판청구를 기각한다. \n 이 유 \n")[0] == LOSE
    assert verdict("주 문 \n 1. 원고의 청구를 기각한다. \n 이 유")[0] == LOSE
    assert verdict("주 문 \n 피고의 항소를 기각한다. \n 이 유")[0] == WIN
    assert verdict("주 문 \n ○○세무서장이 한 법인세 부과처분을 취소한다. \n 이 유")[0] == WIN
    assert verdict("주 문 \n 부과처분 중 일부를 취소하고, 나머지 청구를 기각한다. \n 이 유")[0] == PART
    assert verdict("주 문 \n 원심판결을 파기하고 환송한다. \n 이 유")[0] == OTHER
    assert verdict("... 4. 결 론 \n 이 건 심판청구는 청구법인의 주장이 이유있으므로 주문과 같이 결정한다.")[0] == WIN


def test_event_base_dates():
    import pytest
    from korean_tax_mcp.timeline import base_date
    assert base_date("2023-08-31", event="양도")[0] == "20230831"
    assert base_date("2023-08-31", event="양도", registered="2023-07-15")[0] == "20230715"
    assert base_date("2023-08-31", event="양도", registered="2023-09-15")[0] == "20230831"
    assert base_date("2022.3.4", tax="양도")[0] == "20220304"
    assert base_date("2021-05-10", event="상속")[0] == "20210510"
    assert "증여일" in base_date("2024-01-02", event="증여")[1]
    assert "지급" in base_date("2024-12-31", event="원천")[1]
    with pytest.raises(ValueError): base_date("2023", event="양도")
    with pytest.raises(ValueError): base_date("2023", tax="상증")
    assert base_date("2023-2")[0] == "20231231"


def test_outcome_formats():
    from korean_tax_mcp.outcome import verdict, WIN, LOSE
    assert verdict("[주 문] \n 심판청구를 기각한다. \n [이 유] \n 1.")[0] == LOSE
    assert verdict("문서번호 \n 적부-부산청-2025-0018 \n 결정유형 \n 기각 \n 세목")[0] == LOSE
    assert verdict("문서번호 \n x \n 결정유형 \n 취소 \n 세목")[0] == WIN
    assert verdict("주 문 \n 이 건 이의신청은 기각 합니다. \n 이 유")[0] == LOSE


def test_outcome_appellant():
    from korean_tax_mcp.outcome import verdict, WIN, LOSE
    assert verdict("원고, 상고인 \n AAA \n 피고, 피상고인 \n 세무서장 \n 주 문 \n 상고를 모두 기각한다. \n 이 유")[0] == LOSE
    assert verdict("원고, 피상고인 \n AAA \n 피고, 상고인 \n 세무서장 \n 주 문 \n 상고를 기각한다. \n 이 유")[0] == WIN


def test_outcome_adoption():
    from korean_tax_mcp.outcome import verdict, WIN, LOSE, PART
    assert verdict("주 문 \n 통지 중 1. 부가세는 【채택】결정하고, 2. 나머지 청구는 이를 【불채택】결정합니다. \n 이 유")[0] == PART
    assert verdict("주 문 \n 청구는 【불채택】결정합니다. \n 이 유")[0] == LOSE
    assert verdict("주 문 \n 세무조사결과 통지는 【채택】결정합니다. \n 이 유")[0] == WIN


def test_law_id_does_not_fallback_to_act(monkeypatch):
    from korean_tax_mcp import ntis
    monkeypatch.setattr(ntis, "laws", lambda: {"법인세법": "1", "법인세법 시행령": "2"})
    assert ntis.law_id("법인세법 시행령") == "2" and ntis.law_id("법인세법시행령") == "2"
    assert ntis.law_id("법인세법 시행규칙") is None
