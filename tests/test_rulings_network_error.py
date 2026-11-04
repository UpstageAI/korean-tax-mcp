"""판례·해석 검색이 네트워크 실패를 '0건'으로 숨기지 않는지 정답 테스트 (Claude 작성 2026-11-03) — 수정 금지.
실행: .venv/bin/python -m pytest tests/test_rulings_network_error.py -q
"""
import urllib.error
import pytest
from korean_tax_mcp import ntis, server

LONG = "업무무관 가지급금 인정이자 익금산입 시기 판단 기준"   # 핵심어 3개 이상 → 여러 검색어로 모으는 경로
ROW = {"구분": "질의회신", "문서번호": "서면-2025-법인-1", "제목": "업무무관 가지급금 인정이자", "요지": "인정이자 익금산입",
       "세목": "법인", "일자": "2025.01.02.", "id": "1", "링크": "x", "전체건수": 1}


def _down(*a, **k):
    raise urllib.error.URLError("network down")


def test_all_fail_raises(monkeypatch):
    monkeypatch.setattr(ntis, "_search", _down)
    with pytest.raises(Exception):
        ntis.search(LONG)


def test_tool_returns_error_not_empty(monkeypatch):
    monkeypatch.setattr(ntis, "_search", _down)
    r = server.search_tax_rulings(LONG)
    assert "error" in r and "결과" not in r


def test_partial_fail_keeps_results(monkeypatch):
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1: raise urllib.error.URLError("first fails")
        return [dict(ROW)]
    monkeypatch.setattr(ntis, "_search", flaky)
    out = ntis.search(LONG)
    assert out and out[0]["문서번호"] == ROW["문서번호"]


def test_no_hits_is_still_empty(monkeypatch):
    monkeypatch.setattr(ntis, "_search", lambda *a, **k: [])
    assert ntis.search(LONG) == []
