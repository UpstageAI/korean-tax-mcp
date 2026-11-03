"""쟁점별 검색에서 최근 문서 검색만 실패하면 정확도 결과를 살리는지 (Claude 작성 2026-11-03) — 수정 금지."""
import urllib.error
from korean_tax_mcp import ntis, server


def test_recent_fail_keeps_relevance(monkeypatch):
    monkeypatch.setattr(ntis, "search", lambda q, *a, **k: [{"문서번호": "A", "id": "A", "제목": "A", "요지": "", "일자": "2020.01.01."}])
    def down(*a, **k): raise urllib.error.URLError("down")
    monkeypatch.setattr(ntis, "_search", down)
    r = server.search_rulings_by_issue(["쟁점"], recent_years=3)
    g = r["쟁점별"][0]
    assert [x["문서번호"] for x in g["결과"]] == ["A"] and "최근_오류" in g and "오류" not in g
