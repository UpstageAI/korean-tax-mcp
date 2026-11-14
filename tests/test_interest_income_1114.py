"""interest_income_guide — 조문 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(국세법령정보시스템 연혁본, 응답 캐시): 소득세법 2016.1.1.(법률 제13558호)·2017.1.1.(제14389호)·2018.1.1.(제15225호)·2019.1.1.(제16104호)·
2020.1.1.(제16834호)·2021.1.1.(제17757호)·2022.1.1.(제18578호)·2023.1.1.(제19196호)·2024.1.1.(제19933호)·2025.1.1.(제20615호)·2026.1.1.(제21221호) 시행본
제14조제3항·제16조제1항·제129조제1항제1호·제2항과 부칙, 시행령 2016.2.17.(대통령령 제26982호)·2017.2.3.(제27829호)·2018.2.13.(제28637호)·2026.10.1. 시행본 제25조와 부칙.
기대값은 위 문언에서 손으로 옮긴 것:
  비실명 세율 38%(2016·2017 시행본)·40%(2018)·42%(2019~2022)·45%(2023~) — 각 부칙상 지급분 기준
  비영업대금 25%, 14% 단서는 2020 시행본(2020.12.31.까지 지급, 온라인 중개업자)·2021 이후 시행본(온라인투자연계금융업자), 2019 시행본에는 없음
  장기채권 분리과세 30%(2017 시행본 가목), 2018.1.1. 삭제·그 전 발행분 종전(법률 제15225호 부칙 경과조치)
  저축성보험 한도 2억원(2017.3.31.까지 계약)·1억원(2017.4.1.부터), 월적립식 월 150만원(2017.4.1.부터 계약), 2013.2.15. 전 계약 종전(대통령령 제24356호 부칙 제35조),
  유사 계약 제외는 2025.2.28. 이후 지급분(대통령령 제35349호 부칙 제5조). 종합과세기준금액 2천만원(2016~2026 시행본 제14조제3항제6호)."""
from korean_tax_mcp import interest_income as G

MAN, EOK = 10_000, 100_000_000


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def rate(d, kind, **facts):
    return J(G.guide(d, income_type=kind, facts=facts))["원천징수세율"]["판정"]


def test_overview_and_errors():
    o = G.guide()
    assert len(o["소득 유형"]) == 10 and "p2p" in o["facts 키"] and len(o["날짜에 따라 달라지는 것"]) == 6
    assert "error" in G.guide("2015-12-31", income_type="예금 이자")
    assert "error" in G.guide("2027-01-01", income_type="예금 이자")
    assert "error" in G.guide("2024-02-30", income_type="예금 이자")
    assert "error" in G.guide("2024-01-01", income_type="배당")
    assert "error" in G.guide("2024-01-01", income_type="예금 이자", facts={"없는키": 1})
    assert "error" in G.guide(income_type="예금 이자")
    assert "error" in G.guide("2024-01-01", year=2023, income_type="예금 이자")
    assert "error" in G.guide(year=2015, income_type="예금 이자")


def test_unverified_name_rate_boundaries():
    v = lambda d: rate(d, "예금 이자", unverified_name=True)
    assert v("2016-01-01") == "38%" and v("2017-12-31") == "38%"
    assert v("2018-01-01") == "40%" and v("2018-12-31") == "40%"
    assert v("2019-01-01") == "42%" and v("2022-12-31") == "42%"
    assert v("2023-01-01") == "45%" and v("2026-12-31") == "45%"
    assert rate("2024-01-01", "예금 이자", unverified_name=True, realname_act=True).startswith("금융실명법")
    assert J(G.guide("2024-01-01", income_type="예금 이자", facts={"unverified_name": True}))["과세 방법"]["판정"] == "분리과세"


def test_private_lending_and_p2p():
    assert rate("2019-12-31", "비영업대금의 이익") == "25%"
    assert rate("2019-12-31", "비영업대금의 이익", p2p=True) == "25%"
    assert rate("2020-01-01", "비영업대금의 이익", p2p=True) == "14%"
    r2020 = J(G.guide("2020-12-31", income_type="비영업대금의 이익", facts={"p2p": True}))["원천징수세율"]
    assert r2020["판정"] == "14%" and "2020.12.31.까지" in r2020["사유"]
    r2021 = J(G.guide("2021-01-01", income_type="비영업대금의 이익", facts={"p2p": True}))["원천징수세율"]
    assert r2021["판정"] == "14%" and "온라인투자연계금융업자" in r2021["사유"]
    assert rate("2026-06-30", "비영업대금의 이익") == "25%"


def test_lending_business_is_business_income():
    r = J(G.guide("2024-05-01", income_type="비영업대금의 이익", facts={"lending_business": True}))
    assert r["소득 구분"]["판정"] == "사업소득" and "제19조제1항제11호" in r["소득 구분"]["근거"] and "원천징수세율" not in r


def test_other_rates():
    assert rate("2024-01-01", "예금 이자") == "14%"
    assert rate("2016-01-01", "채권·증권 이자") == "14%"
    assert rate("2024-01-01", "직장공제회 초과반환금") == "기본세율"
    assert rate("2024-01-01", "법원 보증금·경락대금 이자") == "14%"
    assert J(G.guide("2024-01-01", income_type="직장공제회 초과반환금"))["과세 방법"]["판정"] == "분리과세"
    assert J(G.guide("2024-01-01", income_type="법원 보증금·경락대금 이자"))["과세 방법"]["판정"] == "분리과세"


def test_long_term_bond_2018_deletion():
    assert rate("2017-12-31", "채권·증권 이자", long_term_bond=True) == "30%"
    assert rate("2018-01-01", "채권·증권 이자", long_term_bond=True, bond_issued_before_2018=True) == "30%"
    assert rate("2018-01-01", "채권·증권 이자", long_term_bond=True, bond_issued_before_2018=False) == "14%"
    assert rate("2018-01-01", "채권·증권 이자", long_term_bond=True) == "확인 필요"
    assert J(G.guide("2018-01-01", income_type="채권·증권 이자", facts={"long_term_bond": True, "bond_issued_before_2018": False,
                                                                    "withheld": True, "financial_income_total": 1000 * MAN}))["과세 방법"]["판정"] == "분리과세"


def test_comprehensive_threshold_20m():
    t = lambda tot, w=True, y=2016: J(G.guide(year=y, income_type="예금 이자", facts={"withheld": w, "financial_income_total": tot}))["과세 방법"]["판정"]
    for y in (2016, 2021, 2026):
        assert t(2000 * MAN, y=y) == "분리과세" and t(2000 * MAN + 1, y=y) == "종합과세"
    assert t(100 * MAN, w=False) == "종합과세"
    assert J(G.guide(year=2024, income_type="예금 이자"))["과세 방법"]["판정"] == "확인 필요"
    assert J(G.guide(year=2024, income_type="예금 이자", facts={"public_interest_trust": True}))["과세 방법"]["판정"] == "비과세"
    assert J(G.guide(year=2024, income_type="예금 이자", facts={"nonprofit_group": True}))["과세 방법"]["판정"] == "분리과세"


def ins(pay, **f):
    return J(G.guide(pay, income_type="저축성보험 보험차익", facts=f))["저축성보험 보험차익"]["판정"]


def test_insurance_lump_sum_cap_by_contract_date():
    base = dict(premium_type="일시납·일반", holding_years=10)
    assert ins("2026-01-01", contract_date="2016-01-01", total_premium=2 * EOK, **base).startswith("이자소득 아님")
    assert ins("2026-01-01", contract_date="2016-01-01", total_premium=2 * EOK + 1, **base).startswith("과세")
    assert ins("2026-01-01", contract_date="2017-03-31", total_premium=15 * 10 ** 7, **base).startswith("이자소득 아님")
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=15 * 10 ** 7, **base).startswith("과세")
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=EOK, **base).startswith("이자소득 아님")
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=EOK, premium_type="일시납·일반", holding_years=9.9).startswith("과세")
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=EOK, annuity_within_10y=True, **base).startswith("과세")
    assert ins("2026-01-01", contract_date="2017-04-01", **base) == "확인 필요"


def test_insurance_monthly_cap_2017_04_01():
    m = dict(premium_type="월적립식", holding_years=10, payment_years=5, equal_monthly=True, monthly_premium=160 * MAN)
    assert ins("2026-01-01", contract_date="2017-03-31", **m).startswith("이자소득 아님")      # 2017.3.31.까지 계약 — 월 한도 없음
    assert ins("2026-01-01", contract_date="2017-04-01", **m) == "확인 필요"            # 일시납 등 요건(제25조제5항 단서)을 볼 total_premium이 없음
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=160 * MAN * 120, **m).startswith("과세")
    assert ins("2026-01-01", contract_date="2017-04-01", **{**m, "monthly_premium": 150 * MAN}).startswith("이자소득 아님")
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=2 * EOK, **{**m, "payment_years": 4}).startswith("과세")
    # 제25조제5항 단서 — 월적립식 요건을 못 갖춰도 일시납 등 요건(1억원 이하)이면 과세 제외
    assert ins("2026-01-01", contract_date="2017-04-01", total_premium=9000 * MAN, **m).startswith("이자소득 아님")


def test_insurance_old_contract_and_similar_contract():
    base = dict(premium_type="일시납·일반", holding_years=12, total_premium=EOK)
    assert ins("2024-01-01", contract_date="2013-02-14", **base) == "확인 필요"
    assert ins("2024-01-01", contract_date="2013-02-15", **base).startswith("이자소득 아님")
    assert ins("2025-02-27", contract_date="2015-01-01", similar_contract=True, **base) == "확인 필요"
    assert ins("2025-02-28", contract_date="2015-01-01", similar_contract=True, **base).startswith("과세")
    assert ins("2024-01-01", contract_date="2020-01-01", injury_benefit=True) == "이자소득 아님"
    assert ins("2024-01-01", contract_date="2020-01-01", premium_type="종신형 연금", lifetime_annuity_ok=True).startswith("이자소득 아님")
    r = J(G.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2020-01-01", **base}))
    assert "원천징수세율" not in r and r["과세 방법"]["판정"] == "해당 없음"
    r = J(G.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2020-01-01", **{**base, "holding_years": 5}}))
    assert r["원천징수세율"]["판정"] == "14%"


def test_output_shape():
    r = G.guide("2024-07-01", income_type="비영업대금의 이익", facts={"withheld": True, "financial_income_total": 1000 * MAN})
    for k in ("기준일", "판정", "요건", "한계", "관련 해석", "다음 단계", "확인 시행본"):
        assert k in r
    assert "financial_income_aggregate" in r["다음 단계"] and "withholding_tax" in r["다음 단계"] and "timing_rules" in r["다음 단계"]
    assert any("미확인" in x for x in r["한계"])
    assert J(r)["수입시기"]["근거"].startswith("소득세법 시행령 제45조")
