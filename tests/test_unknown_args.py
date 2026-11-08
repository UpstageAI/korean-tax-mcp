"""모르는 인자는 조용히 버리지 않고 오류로 알린다 (Claude 2026-11-08).
law_article에 기준일을 date로 넣으면 그동안 무시되어 오늘 시행본이 나왔다 — 2025 사업연도 판단에 2026 조문을 쓰게 되는 위험."""
import asyncio, json
import pytest
from korean_tax_mcp.server import mcp


def _call(name, args):
    try:
        r = asyncio.run(mcp.call_tool(name, args))
    except Exception as e:      # ToolError
        return True, str(e)
    return getattr(r, "is_error", False), r.content[0].text if getattr(r, "content", None) else ""


def test_date_rejected_with_as_of_hint():
    err, text = _call("law_article", {"law_name": "법인세법", "article": "제24조", "date": "2025-12-31"})
    assert err and "date" in text and "as_of" in text


def test_law_alias_hint():
    err, text = _call("law_article", {"law": "법인세법", "article": "제24조"})
    assert err and "law → law_name" in text


def test_unknown_on_other_tools():
    err, text = _call("search_tax_rulings", {"query": "부당행위", "nonsense": 1})
    assert err and "nonsense" in text


def test_known_args_still_work(monkeypatch):
    from korean_tax_mcp import law
    monkeypatch.setenv("LAW_OC", "test")
    seen = {}
    def fake(name, art, ef=""):
        seen["ef"] = ef
        return {"법령명": name, "조문": art, "본문": "제24조(기부금의 손금불산입)", "시행일": ef or "20260101"}
    monkeypatch.setattr(law, "article", fake)
    monkeypatch.setattr(law, "toc", lambda *a, **k: {})
    err, text = _call("law_article", {"law_name": "법인세법", "article": "제24조", "as_of": "20251231"})
    assert not err, text
    assert seen.get("ef") == "20251231"
