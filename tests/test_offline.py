"""네트워크 없이 도는 테스트."""
import asyncio, json
from korean_tax_mcp import casebook, law, ntis
from korean_tax_mcp.server import mcp


def _call(name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


def test_tools():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"search_tax_rulings", "get_tax_ruling", "rulings_by_article", "basic_rules", "execution_standards",
                     "casebook_search", "law_article", "compare_with_case"}


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
