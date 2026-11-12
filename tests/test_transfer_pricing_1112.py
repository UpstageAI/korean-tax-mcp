"""transfer_pricing_guide(2026-11-12, Claude). 표는 국조법·시행령 2021.12.31.·2026.11.1. 시행본, 시행규칙 제3조 2021·2023·2025 시행본 대조."""
import asyncio
import json
from korean_tax_mcp import server as S
from korean_tax_mcp import transfer_pricing as T


def test_goods_default_lists_six_methods_in_statutory_order():
    r = T.guide("재화")
    assert r["적용 규정"]["적용"] == "국조법 정상가격 조정" and "제4조②" in r["적용 규정"]["근거"]
    assert [m["호"] for m in r["산출방법"]] == [1, 2, 3, 4, 5, 6]
    assert [m["방법"] for m in r["산출방법"]][:3] == ["비교가능 제3자 가격방법", "재판매가격방법", "원가가산방법"]
    assert "제1호~제5호로 산출할 수 없는 경우에만" in r["순서"]
    assert "먼저 볼 방법" not in r and len(r["선택 기준"]["내용"]) == 5
    assert any("판정하지 않는다" in s for s in r["한계"])
    assert len(r["적용 규정"]["예외 유형"]) == 4


def test_facts_mark_methods_that_fit_the_statutory_definition():
    r = T.guide("재화", facts={"buyer_resells": True, "internal_comparable": False})
    assert r["먼저 볼 방법"]["방법"] == ["재판매가격방법"] and "시행령 제14조" in r["먼저 볼 방법"]["이유"]
    by = {m["방법"]: m for m in r["산출방법"]}
    assert by["재판매가격방법"]["입력 사실"] == "해당" and by["비교가능 제3자 가격방법"]["입력 사실"] == "해당 없음"
    assert "입력 사실" not in by["거래순이익률방법"]
    r = T.guide("재화", facts={"internal_comparable": True, "seller_cost_known": True})
    assert r["먼저 볼 방법"]["방법"] == ["비교가능 제3자 가격방법", "원가가산방법"]


def test_loan_rules_and_fallback_rate():
    r = T.guide("금전대차")
    text = json.dumps(r["거래 유형 특칙"], ensure_ascii=False)
    assert "채무액" in text and "당좌대출이자율" in text and "1.5퍼센트" in text and "산출할 수 없는 경우에만" in text
    assert "시행규칙 제3조" in r["거래 유형 특칙"]["근거"]
    assert any("제11조" in x.get("확인할 조문", "") for x in r["다음 단계"])
    assert "기준일 주의" in T.guide("금전대차", as_of="20211231") and "기준일 주의" not in T.guide("금전대차", as_of="20251231")


def test_service_and_guarantee_rules():
    s = json.dumps(T.guide("용역")["거래 유형 특칙"], ensure_ascii=False)
    assert "5퍼센트" in s and "저부가가치용역거래" in s and "문서를 보관" in s
    g = json.dumps(T.guide("지급보증")["거래 유형 특칙"], ensure_ascii=False)
    assert "이자율 차이" in g and "기대편익" in g and "제12조" in g


def test_exception_types_go_to_corporate_tax_act():
    r = T.guide("금전대차", exception="무상이전·채무면제")
    assert r["적용 규정"]["적용"] == "법인세법 제52조" and "채무를 면제" in r["적용 규정"]["결론"] and "시행령 제4조" in r["적용 규정"]["근거"]
    assert "기타소득" in r["소득처분"]["내용"] and "제106조" in r["소득처분"]["근거"] and "산출방법" not in r
    assert T.guide("재화", exception="자본거래")["적용 규정"]["적용"] == "법인세법 제52조"


def test_domestic_counterparty():
    r = T.guide("재화", foreign_related=False)
    assert r["적용 규정"]["적용"] == "법인세법 제52조" and "산출방법" not in r


def test_old_law_warning_and_input_errors():
    assert "구 국제조세조정에 관한 법률" in T.guide("재화", as_of="2020-12-31")["기준일 주의"]
    assert "기준일 주의" not in T.guide("재화", as_of="20210101")
    assert "error" in T.guide("부동산") and "error" in T.guide("재화", exception="기타") and "error" in T.guide("재화", facts={"x": True})


def test_tool_registered_and_english():
    tools = {t.name: t for t in asyncio.run(S.mcp.list_tools())}
    assert "transfer_pricing_guide" in tools and len(tools) == 29
    f = getattr(S.transfer_pricing_guide, "fn", S.transfer_pricing_guide)
    r = f(transaction="재화", facts={"buyer_resells": True})
    assert r["먼저 볼 방법"]["방법"] == ["재판매가격방법"]
    en = f(transaction="재화", lang="en")
    assert isinstance(en, dict) and en
