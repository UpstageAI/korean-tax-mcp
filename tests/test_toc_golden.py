"""law_article 목차 정답 테스트 (Claude 10-15, 수정 금지).
fixtures/toc_units.json: 법제처 lawService.do 조문단위(시행본 원문 그대로, 조문내용 앞 80자).
목적: 모델이 조문 번호를 하나씩 넘겨 보지 않고 목차에서 바로 고르게 — 작은 법령은 전체 목차, 큰 법령은 장·절·관 개요 + 요청 조가 속한 곳의 조문 제목."""
import json, os
from pathlib import Path
import pytest
from korean_tax_mcp import law

F = json.loads((Path(__file__).parent / "fixtures" / "toc_units.json").read_text(encoding="utf-8"))["법령"]
SMALL, CORP, INC_DEC = F["조세범 처벌법|20160302"], F["법인세법|20200101"], F["소득세법 시행령|20200701"]


def test_small_law_gets_full_toc():
    r = law.toc_outline(SMALL, "제2조")
    assert set(r) == {"전체"}
    assert "제22조 공소시효 기간" in r["전체"]
    assert "제4조의2 면세유류 구입카드등의 부정 발급" in r["전체"]
    assert r["전체"].startswith("제1조 목적 · 제2조 정의")


def test_large_law_outline_and_section():
    r = law.toc_outline(CORP, "제34조")
    assert "전체" not in r
    assert "제4관 준비금 및 충당금의 손금산입(제29조~제38조)" in r["개요"]
    assert "제1장 총칙(제1조~제12조)" in r["개요"]
    assert "<개정" not in r["개요"]
    assert r["이 조가 속한 곳"] == "제4관 준비금 및 충당금의 손금산입"
    s = r["같은 곳 조문"]
    assert s.startswith("제29조 비영리내국법인의 고유목적사업준비금의 손금산입 · ")
    assert "제34조 대손충당금의 손금산입" in s
    assert "제32조" not in s          # 삭제된 조는 뺌
    assert s.endswith("제38조 보험차익으로 취득한 자산가액의 손금산입")


def test_article_input_is_normalized():
    assert law.toc_outline(CORP, "제34조 제1항") == law.toc_outline(CORP, "제34조")
    assert law.toc_outline(CORP, "34") == law.toc_outline(CORP, "제34조")


def test_lowest_heading_is_used():
    assert law.toc_outline(INC_DEC, "제89조")["이 조가 속한 곳"] == "제4절 소득금액의 계산"
    assert law.toc_outline(CORP, "제1조")["이 조가 속한 곳"] == "제1장 총칙"


def test_caps():
    for units, art in ((CORP, "제34조"), (INC_DEC, "제89조")):
        r = law.toc_outline(units, art)
        assert all(len(v) <= 1500 for v in r.values())
    r = law.toc_outline(CORP, "제34조", max_chars=300)
    assert len(r["개요"]) <= 300
    assert "제4관" not in r["개요"] and "제1장 총칙(제1조~제12조)" in r["개요"]   # 관·절을 먼저 빼고 장만


def test_unknown_article_gives_outline_only():
    r = law.toc_outline(CORP, "제999조")
    assert set(r) == {"개요"}


@pytest.mark.skipif(not os.environ.get("LAW_OC"), reason="LAW_OC 없음")
def test_live_law_article_has_toc():
    from korean_tax_mcp import server
    fn = getattr(server.law_article, "fn", server.law_article)
    r = fn(law_name="조세범 처벌법", article="제3조", as_of="20180421")
    assert "제22조 공소시효 기간" in r["목차"]["전체"]
    assert r["본문"]
    r2 = fn(law_name="법인세법", article="제34조", as_of="20200808")
    assert r2["목차"]["이 조가 속한 곳"].startswith("제4관")
