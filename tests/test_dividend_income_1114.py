"""dividend_income_guide — 조문·부칙 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(국세법령정보시스템 조회):
  소득세법 2016.1.1.(제13558호)~2026.4.21.(제21548호) 연초 시행본 제14조·제17조·제56조·제62조·제129조·제131조,
    2023.12.31. 이전 시행본 제17조제3항 '100분의 11', 2024.1.1. 시행본(제19933호) '100분의 10', 2027.1.1. 시행본(제21221호) '100분의 11'
  개정 부칙: 제15225호 제3조·제10조제2항, 제16104호 제14조제2항, 제17757호 제3조, 제19196호 제20조, 제19933호 제14조, 제20615호 제2조·제5조, 제21221호 제1조제2호·제14조
  소득세법 시행령 2016.2.17.~2026.10.1. 시행본 제27조제4항·제27조의3·제46조·제116조의2
  조세특례제한법 2016.9.30.·2026.9.18. 시행본 제104조의27과 부칙(제21223호 제23조)"""
import datetime as dt

from korean_tax_mcp import dividend_income as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["지급일별 변화"]) == 5 and "의제배당_감자" in r["배당 유형"]
    assert "error" in G.guide("2015-12-31", "이익배당")
    assert "error" in G.guide("2027-01-01", "이익배당")
    assert "error" in G.guide("2024/01/01")
    assert "error" in G.guide("2024-01-01", "주식배당")
    assert "error" in G.guide("2024-01-01", "이익배당", {"foo": 1})
    assert "error" in G.guide("2024-01-01", "이익배당", {"total_financial_income": -1})
    assert "error" in G.guide("2024-01-01", "의제배당_자본전입", {"capitalization_source": "주식발행초과금"})
    assert "error" in G.guide("2024-01-01", "이익배당", {"withheld": "yes"})


def test_gross_up_rate_boundaries():
    # 제17조제3항: 2023.12.31. 이전 시행본 11%, 법률 제19933호(2024.1.1. 시행) 10% — 부칙 제14조 '시행 전에 지급받은 배당소득'은 종전
    assert J(G.guide("2023-12-31", "이익배당"))["배당가산(Gross-up)"]["가산율(%)"] == 11
    assert J(G.guide("2024-01-01", "이익배당"))["배당가산(Gross-up)"]["가산율(%)"] == 10
    assert J(G.guide("2026-12-31", "이익배당"))["배당가산(Gross-up)"]["가산율(%)"] == 10
    assert J(G.guide("2016-01-01", "인정배당"))["배당가산(Gross-up)"]["가산율(%)"] == 11
    # 법률 제21221호 부칙 제14조 — 2026.12.31. 이전 지급분은 종전, 2027.1.1. 시행본 '100분의 11'
    assert G.gross_up_rate(dt.date(2027, 1, 1))[0] == 11 and G.gross_up_rate(dt.date(2026, 12, 31))[0] == 10


def test_capital_reduction_exclusion_from_2025():
    # 제17조제3항제1호(법률 제20615호, 부칙 제5조: 2025.1.1. 이후 자본의 감소로 취득하는 소득분)
    before = J(G.guide("2024-12-31", "의제배당_감자", {"corp_tax_paid": False}))["배당가산(Gross-up)"]
    after = J(G.guide("2025-01-01", "의제배당_감자", {"corp_tax_paid": False}))["배당가산(Gross-up)"]
    taxed = J(G.guide("2025-01-01", "의제배당_감자", {"corp_tax_paid": True}))["배당가산(Gross-up)"]
    unknown = J(G.guide("2025-01-01", "의제배당_감자"))["배당가산(Gross-up)"]
    assert before["판정"] == "대상" and before["가산율(%)"] == 10
    assert after["판정"] == "대상 아님" and "제17조제3항제1호" in after["근거"]
    assert taxed["판정"] == "대상" and unknown["판정"] == "확인 필요"


def test_capitalization_sources_and_item_renumbering():
    # 자기주식소각이익 자본전입: 2024년 시행본 제3항제1호 → 2025.1.1. 시행본 제2호
    a = J(G.guide("2024-12-31", "의제배당_자본전입", {"capitalization_source": "자기주식소각이익"}))
    b = J(G.guide("2025-01-01", "의제배당_자본전입", {"capitalization_source": "자기주식소각이익"}))
    assert a["배당가산(Gross-up)"]["판정"] == "대상 아님" and a["배당가산(Gross-up)"]["근거"].endswith("제17조제3항제1호")
    assert b["배당가산(Gross-up)"]["근거"].endswith("제17조제3항제2호")
    land = J(G.guide("2020-05-01", "의제배당_자본전입", {"capitalization_source": "재평가적립금_토지"}))
    assert land["배당소득 해당"]["판정"] == "해당" and land["배당가산(Gross-up)"]["판정"] == "대상 아님"
    other = J(G.guide("2020-05-01", "의제배당_자본전입", {"capitalization_source": "재평가적립금_토지외"}))
    assert other["배당소득 해당"]["판정"] == "해당 없음" and "배당가산(Gross-up)" not in other
    reserve = J(G.guide("2020-05-01", "의제배당_자본전입", {"capitalization_source": "자본준비금"}))
    assert reserve["배당소득 해당"]["판정"] == "해당 없음"
    retained = J(G.guide("2020-05-01", "의제배당_자본전입", {"capitalization_source": "이익잉여금"}))
    assert retained["배당가산(Gross-up)"]["판정"] == "대상" and retained["배당가산(Gross-up)"]["가산율(%)"] == 11
    assert J(G.guide("2020-05-01", "의제배당_자본전입"))["배당소득 해당"]["판정"] == "확인 필요"
    # 제17조제2항제5호 지분 증가 — 2024년 제3항제3호, 2025년 제4호
    assert J(G.guide("2025-03-01", "의제배당_자기주식지분증가"))["배당가산(Gross-up)"]["근거"].endswith("제17조제3항제4호")


def test_reserve_reduction_and_reduced_corp():
    # 제17조제3항제6호·제7호(2025.1.1. 이후 감액으로 지급받는 소득분)
    assert J(G.guide("2024-12-31", "이익배당", {"reserve_reduction": "자본준비금"}))["배당가산(Gross-up)"]["판정"] == "확인 필요"
    cut = J(G.guide("2025-01-01", "이익배당", {"reserve_reduction": "자본준비금"}))["배당가산(Gross-up)"]
    assert cut["판정"] == "대상 아님" and "제7호" in cut["근거"]
    assert "제6호" in J(G.guide("2025-01-01", "이익배당", {"reserve_reduction": "재평가적립금"}))["배당가산(Gross-up)"]["근거"]
    # 시행령 제27조의3 — 제1항제1호 100분의 100, 제2호 산식 비율. 법 조문 번호 2024년 제4호 → 2025년 제5호
    full = J(G.guide("2024-06-30", "이익배당", {"reduced_corp": "전액감면"}))["배당가산(Gross-up)"]
    assert full["판정"] == "대상 아님" and "제17조제3항제4호" in full["근거"]
    assert "제17조제3항제5호" in J(G.guide("2025-06-30", "이익배당", {"reduced_corp": "전액감면"}))["배당가산(Gross-up)"]["근거"]
    part = J(G.guide("2025-06-30", "이익배당", {"reduced_corp": "일부감면"}))["배당가산(Gross-up)"]
    assert part["판정"] == "일부 대상" and part["가산율(%)"] == 10
    # 법인세 미과세라는 사실만으로는 제외 문언 없음
    assert J(G.guide("2025-06-30", "이익배당", {"corp_tax_paid": False}))["배당가산(Gross-up)"]["판정"] == "대상"


def test_non_gross_up_types():
    for t in ("외국법인배당", "출자공동사업자", "국조법간주배당", "유사배당"):
        assert J(G.guide("2022-04-01", t))["배당가산(Gross-up)"]["판정"] == "대상 아님", t
    # 제17조제3항 단서 + 시행령 제27조의3제3항(기관전용 사모집합투자기구)
    assert J(G.guide("2022-04-01", "집합투자기구", {"institutional_pef": True}))["배당가산(Gross-up)"]["판정"] == "대상"
    assert J(G.guide("2022-04-01", "집합투자기구", {"institutional_pef": False}))["배당가산(Gross-up)"]["판정"] == "대상 아님"
    assert J(G.guide("2022-04-01", "집합투자기구"))["배당가산(Gross-up)"]["판정"] == "확인 필요"


def test_scope_by_date():
    # 제17조제1항제5호의2 — 법률 제15225호 부칙 제3조(2018.1.1. 이후 지급분)
    assert J(G.guide("2017-12-31", "파생결합증권"))["배당소득 해당"]["판정"] == "확인 필요"
    assert J(G.guide("2018-01-01", "파생결합증권"))["배당소득 해당"]["판정"] == "해당"
    # 제2호의2 — 법률 제17757호 부칙 제3조(2021.1.1. 이후 신탁계약분)
    assert J(G.guide("2020-12-31", "법인과세신탁재산"))["배당소득 해당"]["판정"] == "해당 없음"
    t = J(G.guide("2021-01-01", "법인과세신탁재산"))
    assert t["배당소득 해당"]["판정"] == "해당" and t["배당가산(Gross-up)"]["판정"] == "대상 아님"
    # 제5호의3·제5호의4 — 법률 제20615호 부칙 제2조(2025.7.1. 이후 지급분)
    assert J(G.guide("2025-06-30", "수익증권·투자계약증권"))["배당소득 해당"]["판정"] == "확인 필요"
    assert J(G.guide("2025-07-01", "수익증권·투자계약증권"))["배당소득 해당"]["판정"] == "해당"
    scope = lambda d: G.guide(d, "이익배당")["요건"][0]["내용"]
    assert "파생결합증권" not in scope("2017-12-31") and "파생결합증권" in scope("2018-01-01")


def test_withholding_rates():
    # 제129조제1항제2호: 배당 14%, 출자공동사업자 25% (2016~2026 시행본 같음)
    assert J(G.guide("2016-01-01", "이익배당"))["원천징수세율"]["판정"] == "14%"
    assert J(G.guide("2026-12-31", "출자공동사업자"))["원천징수세율"]["판정"] == "25%"
    # 제129조제2항제2호 실지명의 미확인: 38% → 40%(2018.1.1. 이후 지급) → 42%(2019.1.1.) → 45%(2023.1.1.)
    u = lambda d: J(G.guide(d, "이익배당", {"real_name_unverified": True}))["원천징수세율"]["판정"]
    assert (u("2017-12-31"), u("2018-01-01"), u("2018-12-31"), u("2019-01-01"), u("2022-12-31"), u("2023-01-01")) == ("38%", "40%", "40%", "42%", "42%", "45%")
    assert J(G.guide("2023-01-01", "이익배당", {"real_name_unverified": True}))["종합과세 여부"]["판정"] == "분리과세"


def test_global_taxation_threshold():
    # 제14조제3항제6호 — 합계액 2천만원 '이하'이면서 원천징수된 소득은 합산하지 않음
    j = lambda **f: J(G.guide("2024-05-01", "이익배당", f))["종합과세 여부"]["판정"]
    assert j(total_financial_income=20_000_000) == "분리과세"
    assert j(total_financial_income=20_000_001) == "종합과세"
    assert j(total_financial_income=1_000_000, withheld=False) == "종합과세"
    assert j() == "확인 필요"
    # 출자공동사업자 배당은 기준금액 계산에서 빠지고 항상 합산
    assert J(G.guide("2024-05-01", "출자공동사업자", {"total_financial_income": 0}))["종합과세 여부"]["판정"] == "종합과세"


def test_timing_and_accrual_year():
    r = G.guide("2024-01-15", "이익배당", accrual_date="2023-12-20")
    assert r["귀속연도"].startswith("2023년")
    assert J(r)["수입시기"]["근거"].endswith("제46조제2호·제1호")
    assert J(r)["배당가산(Gross-up)"]["가산율(%)"] == 10   # 부칙 문언은 지급일 기준
    assert "결산확정일" in J(G.guide("2022-03-31", "인정배당"))["수입시기"]["사유"]
    assert "합병등기" in J(G.guide("2022-03-31", "의제배당_합병"))["수입시기"]["사유"]
    assert J(G.guide("2022-03-31", "법인으로보는단체"))["수입시기"]["판정"] == "확인 필요"


def test_high_dividend_special_rule():
    # 조세특례제한법 제104조의27(2025.12.23. 신설) — 부칙 제23조: 2026.1.1. 이후 받는 배당소득부터
    assert "고배당기업 배당 특례" in J(G.guide("2026-01-01", "이익배당"))
    assert "고배당기업 배당 특례" not in J(G.guide("2025-12-31", "이익배당"))
    # 구 제104조의27(2015~2017 사업연도 결산기 배당)
    assert "100분의 9" in J(G.guide("2017-04-01", "이익배당"))["고배당기업 배당 특례"]["사유"]
    assert "고배당기업 배당 특례" not in J(G.guide("2019-01-01", "이익배당"))


def test_requirements_text_follows_date():
    req = lambda d: {x["요건"]: x for x in G.guide(d, "이익배당")["요건"]}
    assert "100분의 11" in req("2023-12-31")["배당가산율"]["내용"] and "100분의 10" in req("2024-01-01")["배당가산율"]["내용"]
    assert "제6호" not in req("2024-12-31")["배당가산(Gross-up) 대상"]["내용"] and "제7호" in req("2025-01-01")["배당가산(Gross-up) 대상"]["내용"]
    assert "100분의 45" in req("2023-01-01")["원천징수세율"]["내용"] and "100분의 42" in req("2022-12-31")["원천징수세율"]["내용"]
    r = G.guide("2024-01-01", "이익배당")
    assert r["관련 해석"] and all("확인" in x["내용"] for x in r["관련 해석"])
    assert "dividend_tax_credit" in r["다음 단계"]
