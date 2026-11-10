"""행정규칙(고시) 조문 조회 폴백 — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
픽스처: 법제처 DRF target=admrul 실제 응답(외국환거래규정, 2026.11.2 시행, 제9장 제1절 발췌). 네트워크 없음(law._get 대체).
"""
import json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "admrul_1110.json"), encoding="utf-8"))


def _fake_get(path, query):
    if path == "lawSearch.do" and "target=admrul" in query:
        return FX["search"]
    if path == "lawService.do" and "target=admrul" in query:
        return FX["service"]
    if "target=eflaw" in query or "target=elaw" in query:
        return {"LawSearch": {"totalCnt": "0", "law": []}}       # 법령에는 없음
    raise AssertionError(f"unexpected call {path} {query}")


def test_split_articles_hyphen_numbering():
    from korean_tax_mcp import admrul
    arts = dict(admrul.split_articles(FX["service"]["AdmRulService"]["조문내용"]))
    assert "제9-5조" in arts and arts["제9-5조"].startswith("제9-5조(해외직접투자의 신고 등)")
    assert "제9-9조" in arts and "6월 이내" in arts["제9-9조"] and "청산보고서" in arts["제9-9조"]
    assert "제9-6조" in arts and "분배잔여재산" in arts["제9-6조"]
    full = FX["service"]["AdmRulService"]["조문내용"]
    assert all(v in full for v in arts.values())                     # 원문 부분 문자열


def test_normalize_variants():
    from korean_tax_mcp import admrul
    assert admrul.normalize("제9-5조") == "제9-5조" and admrul.normalize("9-5") == "제9-5조"
    assert admrul.normalize("제12조") == "제12조" and admrul.normalize("제12조의2") == "제12조의2"


def test_article_lookup_with_fake_network(monkeypatch):
    from korean_tax_mcp import admrul, law
    monkeypatch.setattr(law, "_get", _fake_get)
    r = admrul.article("외국환거래규정", "제9-5조")
    assert r["법령"] == "외국환거래규정" and r["구분"].startswith("행정규칙") and r["조"] == "제9-5조"
    assert r["적용 시행일"] == "20261102" and r["소관"] == "재정경제부"
    assert "외국환은행의 장" in r["본문"] and r["링크"].startswith("https://www.law.go.kr/")
    assert "현행본" in r["주의"]
    r2 = admrul.article("외국환거래규정", "제9-99조")
    assert r2["본문"].startswith("조문 없음")


def test_law_article_falls_back_to_admrul(monkeypatch):
    from korean_tax_mcp import server, law
    monkeypatch.setattr(law, "_get", _fake_get)
    law.clear_caches() if hasattr(law, "clear_caches") else None
    r = server.law_article("외국환거래규정", "제9-9조", as_of="20261231")
    assert "error" not in r, r
    assert r["구분"].startswith("행정규칙") and "연간사업실적보고서" in r["본문"]
    assert any("as_of" in str(v) or "현행본" in str(v) for v in [r.get("주의", "")])


def test_law_article_unknown_name_still_errors(monkeypatch):
    from korean_tax_mcp import server, law
    monkeypatch.setattr(law, "_get", lambda path, query: {"LawSearch": {"totalCnt": "0", "law": []}} if "admrul" not in query else {"AdmRulSearch": {"totalCnt": "0", "admrul": []}})
    law.clear_caches() if hasattr(law, "clear_caches") else None
    r = server.law_article("없는규정", "제1조")
    assert "error" in r and "행정규칙" in r["error"]


def test_find_article_in_admrul(monkeypatch):
    from korean_tax_mcp import server, law
    monkeypatch.setattr(law, "_get", _fake_get)
    law.clear_caches() if hasattr(law, "clear_caches") else None
    r = server.find_article("청산보고서 원리금회수", law_name="외국환거래규정", n=3)
    rows = r.get("결과") or []
    assert rows and rows[0]["법령"] == "외국환거래규정" and rows[0]["조"] == "제9-9조"
