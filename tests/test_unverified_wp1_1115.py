"""소득세 요건 안내 8개 도구 — 원문 대조로 바뀐 판정의 경계 정답(2026-11-15).

대조한 시행본(법제처 국가법령정보 공동활용, 2026-11-15 조회 — 원자료 raw_wp1/):
  소득세법 시행령 제25조 2012.9.14.(대통령령 제24104호)·2013.11.5.·2014.12.31. 시행본, 대통령령 제24356호 부칙 제35조·제25193호 부칙 제3조
  소득세법 시행령 제187조 2017.11.21.·2020.2.18. 시행본, 대통령령 제30395호 부칙 제20조, 금융실명거래 및 비밀보장에 관한 법률 제5조
  소득세법 시행령 제26조의3제6항 2016.12.5.~2025.11.28. 시행본, 제46조 2016.12.5.~2026.10.1. 시행본, 국제조세조정에 관한 법률 제19조·제31조
  조세특례제한법 제104조의27 2016.9.30.·2017.4.1.·2026.9.18. 시행본과 법률 제14390호 부칙 제30조
  소득세법 시행규칙 별지 제37호의4서식·제11조의2, 소득세법 시행령 제9조~제9조의5·제87조제3호·별표 3의3
  소득세법 시행령 제155조제1항제2호(2020.12.10. 시행본), 제152조의3·제154조제2항, 소득세법 제88조제6호
  소득세법 제48조·제55조제2항 2012.8.2.·2015.7.1. 시행본, 근로자퇴직급여 보장법 시행령 제3조 2015.12.15.~2026.3.24. 시행본
  소득세법 제12조제3호머목 2024.7.1.·2025.10.1. 시행본
  소득세법 제17조제3항 2024.7.1.·2025.10.1.·2026.7.1. 시행본(제6호·제7호)과 법인세법 제18조제8호 2024.1.1.·2025.10.1. 시행본"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from korean_tax_mcp import (business_income as B, dividend_income as DV, interest_income as I, one_house_exemption as H,   # noqa: E402
                            other_income as O, pension_income as P, retirement_income as R, wage_income as W)

EOK = 100_000_000


def J(r):
    return {x["항목"]: x for x in r["판정"]}


def test_interest_old_insurance_contract_boundary():
    # 계약일 2013.2.14.(종전 규정: 10년 기준만, 한도 없음) / 2013.2.15.(2억원 한도)
    f = dict(premium_type="일시납·일반", holding_years=12, total_premium=3 * EOK)
    old = J(I.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2013-02-14", **f}))["저축성보험 보험차익"]
    new = J(I.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2013-02-15", **f}))["저축성보험 보험차익"]
    assert old["판정"] == "이자소득 아님(과세 제외)" and "제24356호" in old["근거"]
    assert new["판정"] == "과세(이자소득)"
    # 종전 규정에서도 10년 미만, 10년 전 확정기간 연금 분할은 과세
    f9 = {**f, "holding_years": 9, "contract_date": "2010-01-01"}
    assert J(I.guide("2018-01-01", income_type="저축성보험 보험차익", facts=f9))["저축성보험 보험차익"]["판정"] == "과세(이자소득)"
    fa = {**f, "annuity_within_10y": True, "contract_date": "2010-01-01"}
    assert J(I.guide("2024-01-01", income_type="저축성보험 보험차익", facts=fa))["저축성보험 보험차익"]["판정"] == "과세(이자소득)"
    # 종신형 연금보험 연금액 한도는 2014.2.21. 이후 계약부터
    a = J(I.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2014-02-20", "premium_type": "종신형 연금", "lifetime_annuity_ok": True}))["저축성보험 보험차익"]
    b = J(I.guide("2024-01-01", income_type="저축성보험 보험차익", facts={"contract_date": "2014-02-21", "premium_type": "종신형 연금", "lifetime_annuity_ok": True}))["저축성보험 보험차익"]
    assert "제25193호" in a["사유"] and "제25193호" not in b["사유"] and "연금액 한도" in b["사유"]


def test_interest_realname_and_decree_187():
    r = J(I.guide("2024-01-01", income_type="예금 이자", facts={"unverified_name": True, "realname_act": True}))["원천징수세율"]
    assert r["판정"].startswith("90%") and "금융실명거래" in r["근거"]
    p2p = J(I.guide("2020-06-30", income_type="비영업대금의 이익", facts={"p2p": True}))["원천징수세율"]
    assert p2p["판정"] == "14%" and "제187조" in p2p["근거"] and "등록" in p2p["사유"]
    bond = J(I.guide("2017-12-31", income_type="채권·증권 이자", facts={"long_term_bond": True}))["원천징수세율"]
    assert bond["판정"] == "30%" and "10년 이상" in bond["사유"]
    assert not any("미확인" in x for x in I.guide("2024-01-01", income_type="예금 이자")["한계"])


def test_dividend_reserve_reduction_boundaries():
    g = lambda d: J(DV.guide(d, "이익배당", {"reserve_reduction": "자본준비금"}))
    # 가산 제외 호(제7호)는 2025.1.1. 이후 감액으로 지급받는 분부터
    assert g("2024-12-31")["배당가산(Gross-up)"]["판정"] == "대상(배당소득에 해당하는 경우)"
    # 제7호는 법인세법 제18조제8호 '나목 및 다목'의 자본준비금만 뺌 — 가목이면 가산 대상이라 판정은 준비금 종류 확인
    cut = g("2025-01-01")["배당가산(Gross-up)"]
    assert cut["판정"] == "확인 필요" and "나목·다목" in cut["사유"] and "가목" in cut["사유"] and "법인세법 제18조제8호" in cut["근거"]
    assert J(DV.guide("2025-01-01", "이익배당", {"reserve_reduction": "재평가적립금"}))["배당가산(Gross-up)"]["판정"] == "대상 아님"   # 제6호
    # 시행령 제26조의3제6항 개정은 2025.2.28. 이후 지급분(부칙 제21조)
    assert "제17조제2항제2호 각 목" in g("2025-02-27")["배당소득 해당"]["사유"]
    assert "법인세법 제18조제8호" in g("2025-02-28")["배당소득 해당"]["사유"]


def test_dividend_timing_and_high_dividend():
    assert J(DV.guide("2025-06-30", "수익증권·투자계약증권"))["배당소득 해당"]["판정"] == "확인 필요"
    t = J(DV.guide("2025-07-01", "수익증권·투자계약증권"))["수입시기"]
    assert t["판정"] == "안내" and "제46조제9호" in t["근거"]
    c = J(DV.guide("2022-03-31", "국조법간주배당"))["수입시기"]
    assert "60일" in c["사유"] and c["근거"].startswith("국제조세조정에 관한 법률 제31조")
    hd = J(DV.guide("2026-04-30", "이익배당"))["고배당기업 배당 특례"]
    assert [x["세율"] for x in hd["세율표"]][0] == "총 금액의 14%" and "30%" in hd["세율표"][-1]["세율"]
    # 누진 기준세액 검산: 2천만원 × 14% = 280만원, 280만원 + 2억8천만원 × 20% = 5,880만원, 5,880만원 + 47억원 × 25% = 12억3,380만원
    assert 20_000_000 * 14 // 100 == 2_800_000 and 2_800_000 + 280_000_000 * 20 // 100 == 58_800_000 and 58_800_000 + 4_700_000_000 * 25 // 100 == 1_233_800_000
    old = J(DV.guide("2017-04-30", "이익배당"))["고배당기업 배당 특례"]
    assert "100분의 5" in old["사유"] and "제14390호" in old["근거"]
    assert not any("미확인" in x or "미대조" in x for x in DV.guide("2024-01-01", "이익배당")["한계"])


def test_business_exempt_over_limit():
    # 작물재배업: 수입금액 12억원·소득금액 1억2천만원 → 비과세 1억원(별지 제37호의4서식 예시)
    r = J(B.guide(2024, "작물재배업", revenue_curr=1_200_000_000, exempt_income=120_000_000))["작물재배업 비과세"]
    assert r["판정"] == "일부 비과세" and r["비과세 소득금액"] == 100_000_000 and r["과세 소득금액"] == 20_000_000
    assert J(B.guide(2024, "작물재배업", revenue_curr=1_000_000_000, exempt_income=120_000_000))["작물재배업 비과세"]["판정"] == "비과세"
    # 농어가부업 3천만원: 초과분 과세 / 전통주 1천200만원: 넘으면 전액 과세
    f = J(B.guide(2024, "농어가부업", exempt_income=30_000_001))["농어가부업 비과세"]
    assert f["판정"] == "일부 비과세" and f["과세 소득금액"] == 1
    assert J(B.guide(2024, "농어가부업", exempt_income=30_000_000))["농어가부업 비과세"]["판정"] == "비과세"
    t = J(B.guide(2024, "전통주 제조", exempt_income=12_000_001))["전통주 제조 비과세"]
    assert t["판정"] == "전액 과세" and t["과세 소득금액"] == 12_000_001
    assert J(B.guide(2024, "전통주 제조", exempt_income=12_000_000))["전통주 제조 비과세"]["판정"] == "비과세"
    # 조림: 2025년 600만원, 2026년 3천만원까지 비과세
    assert J(B.guide(2025, "조림(임목 벌채·양도)", exempt_income=10_000_000))["조림(임목 벌채·양도) 비과세"]["과세 소득금액"] == 4_000_000
    assert J(B.guide(2026, "조림(임목 벌채·양도)", exempt_income=10_000_000))["조림(임목 벌채·양도) 비과세"]["판정"] == "비과세"
    # 어로어업 5천만원 초과: 해석 없음 — 두 결과 함께
    e = J(B.guide(2024, "연근해·내수면어업", exempt_income=60_000_000))["연근해·내수면어업 비과세"]
    assert e["한도까지 비과세로 볼 때"]["과세 소득금액"] == 10_000_000 and e["전액 과세로 볼 때"]["과세 소득금액"] == 60_000_000 and "서면질의" in e["사유"]


def test_business_accounts_by_year():
    def acc(y):
        return J(B.guide(y, "도매·소매업", revenue_prev=1_000_000_000, revenue_curr=1_000_000_000))
    assert "제81조제9항" in acc(2019)["사업용계좌"]["근거"] and "제81조의8" in acc(2020)["사업용계좌"]["근거"]
    assert "1천분의 2" in acc(2016)["사업용계좌"]["사유"]
    assert "백화점" in acc(2024)["현금영수증"]["사유"] and "백화점" not in acc(2023)["현금영수증"]["사유"]
    assert 2025 not in acc(2024)["현금영수증"]["별표 3의3 연도별 추가 업종"]
    assert "1만분의 7" in acc(2016)["추계 신고·결정"]["사유"]
    assert not any("미확인" in x or "미대조" in x for x in B.guide(2024, "도매·소매업")["한계"])


def test_one_house_tenant_exception_and_household_basis():
    base = dict(acquisition_date="2015-01-01", new_house_acquisition_date="2020-03-01", both_adjusted_at_new_acquisition=True)
    # 2019.12.17. 이후 취득분: 1년 이내 양도·전입. 기존 임차인 임대차 종료일이 취득일부터 1년 뒤면 그 날까지(2년 한도)
    late = J(H.guide(transfer_date="2021-06-30", moved_in_date="2021-06-30", **base))
    assert late["일시적 2주택 — 처분기한"]["판정"] == "미충족" and late["일시적 2주택 — 신규 주택 전입"]["판정"] == "미충족"
    ok = J(H.guide(transfer_date="2021-06-30", moved_in_date="2021-06-30", existing_tenant_lease_end="2021-06-30", **base))
    assert ok["일시적 2주택 — 처분기한"]["판정"] == "충족" and ok["일시적 2주택 — 신규 주택 전입"]["판정"] == "충족"
    over = J(H.guide(transfer_date="2021-07-01", moved_in_date="2021-06-30", existing_tenant_lease_end="2021-06-30", **base))
    assert over["일시적 2주택 — 처분기한"]["판정"] == "미충족"
    # 임대차 종료일이 2년을 넘어도 취득일부터 2년 한도
    cap = J(H.guide(transfer_date="2022-03-02", moved_in_date="2022-03-01", existing_tenant_lease_end="2022-12-31", **base))
    assert cap["일시적 2주택 — 처분기한"]["판정"] == "미충족" and cap["일시적 2주택 — 신규 주택 전입"]["판정"] == "충족"
    # 종료일이 취득일부터 1년 이내면 연장 없음
    no = J(H.guide(transfer_date="2021-03-02", moved_in_date="2021-03-01", existing_tenant_lease_end="2021-03-01", **base))
    assert no["일시적 2주택 — 처분기한"]["판정"] == "미충족"
    # 1세대 정의 조문: 2016년은 시행령 제154조, 2017.1.1.부터 법 제88조제6호
    hh = lambda d: [x for x in H.guide(transfer_date=d)["요건"] if x["요건"] == "1세대"][0]["근거"]
    assert "제154조제1항·제2항" in hh("2016-12-31") and "제88조제6호" not in hh("2016-12-31").split(" — ")[0]
    assert hh("2017-01-01").startswith("소득세법 제88조제6호") and "제154조제2항(2017.2.3. 전)" in hh("2017-01-01")
    assert "제152조의3" in hh("2017-02-03") and "사실상 이혼" not in hh("2018-12-31") and "사실상 이혼" in hh("2019-01-01")


def test_other_religious_expense_table():
    # 시행령 제87조제3호 표 — 구간 경계
    for amt, exp in ((20_000_000, 16_000_000), (20_000_001, 16_000_000.5), (40_000_000, 26_000_000), (60_000_000, 32_000_000), (80_000_000, 36_000_000)):
        assert O.religious_expense(amt)[0] == exp
    r = O.guide("2024-06-30", "종교인소득", 50_000_000)
    assert not any("미확인" in x for x in r["한계"])
    j = J(O.guide("2024-01-01", "직무발명보상금", facts={"retired": False}))["소득 구분"]
    assert "제20조제1항제5호" in j["근거"] and "미확인" not in j["사유"]


def test_pension_withdrawal_limit_text():
    lim = " ".join(P._LIMITS)
    assert "150만원" in lim and "200만원" in lim and "미확인" not in lim


def test_retirement_old_rule_and_interim_reasons():
    assert any("1천분의 125" in x for x in R.interim_reasons(R.D(2020, 4, 30))) and not any("1천분의 125" in x for x in R.interim_reasons(R.D(2020, 4, 29)))
    assert any("제6호의3" in x for x in R.interim_reasons(R.D(2018, 6, 19))) and not any("제6호의3" in x for x in R.interim_reasons(R.D(2018, 6, 18)))
    r = R.guide(retirement_date="2017-06-30")
    txt = " ".join(str(x) for x in r["요건"])
    assert "100분의 40" in txt and "제11611호" in txt and "미확인" not in txt
    assert not any("미확인" in x for x in r["한계"])


def test_wage_birth_support_before_2021():
    b = W.guide(payment_date="2024-06-01", items=[{"항목": "출산지원금", "금액": 5_000_000, "자녀출생일": "2020-12-31", "지급차수": 1}])
    row = [x for x in b["판정"] if x.get("항목") == "출산지원금"][0]
    assert row["판정"] == "월 20만원 한도" and "제20615호" in row["근거"]
    assert not any("해석·원문 확인 필요" in x for x in b["한계"])
