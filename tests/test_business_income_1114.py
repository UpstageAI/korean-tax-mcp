"""business_income_guide — 조문·부칙 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(국세법령정보시스템 ASISTA002MR03 전문, 원자료 통합테스트/고도화_1114/raw_inc_business/):
  소득세법 2016.1.1.·2017.1.1.·2018.1.1.·2019.1.1.·2020.1.1.·2021.1.1.·2022.1.1.·2023.1.1.·2024.1.1.·2025.1.1.·2026.4.21. 시행본
    — 제12조제2호(9억원 → 12억원은 2023.1.1. 시행본, 제19196호 부칙 제2조·제11조; 조림 600만원 → 3천만원은 제21221호 부칙 제2조),
      제25조제1항(85㎡·3억 2016 / 60㎡·3억 2017~2018 / 40㎡·2억 2019~; 제2호 2주택은 제19933호 부칙 제1조제1호로 2026.1.1. 시행),
      제64조의2(2019.1.1. 시행본부터 50%·200만원, 등록 60%·400만원)
  소득세법 시행령 2016.12.5.·2017.11.21.·2018.10.23.·2019.12.31.·2020.12.10.·2021.7.1.·2022.10.27.·2023.10.1.·2024.11.12.·2025.10.1.·2026.10.1. 시행본
    — 제133조제1항(20억·10억·5억 → 15억·7억5천만·5억, 제28637호 부칙 제2조제1항), 제208조제5항(3억·1억5천만·7천500만, 2016~2026 같음),
      제143조제4항(6천만·3천600만·2천400만; 해당연도 수입금액 요건은 제28637호 부칙 제13조로 2019년부터; 인적용역 나목은 제33267호 부칙으로 2023년부터),
      제9조의5(어로어업 2020, 양식어업 2024), 제53조제1항(12억원, 제35349호 부칙 제1조제1호 2026.1.1. 시행)."""
from korean_tax_mcp import business_income as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["과세기간별 변화"]) >= 10 and "도매·소매업" in r["업종 구분"]["가목"]
    assert "error" in G.guide(2015)
    assert "error" in G.guide(2027)
    assert "error" in G.guide(2024, industry="없는업종")
    assert "error" in G.guide(2024, "제조업", revenue_prev=-1)
    assert "error" in G.guide(2024, house_count=2, small_house_count=3)
    assert "error" in G.guide(2024, "제조업", professional="예")
    assert "error" in G.guide(2024, house_count=1, house_prices=["10억"])


def test_one_house_cap_9_to_12_eok_2022_2023():
    # 법 제12조제2호나목 — 2023.1.1. 시행본부터 12억원, 2022.1.1. 시행본은 9억원
    assert J(G.guide(2022, house_count=1, house_prices=[1_000_000_000]))["주택임대 — 1주택 비과세"]["판정"] == "과세"
    assert J(G.guide(2023, house_count=1, house_prices=[1_000_000_000]))["주택임대 — 1주택 비과세"]["판정"] == "비과세"
    # 기준시가가 기준과 같으면 '초과'가 아님
    assert J(G.guide(2023, house_count=1, house_prices=[1_200_000_000]))["주택임대 — 1주택 비과세"]["판정"] == "비과세"
    assert J(G.guide(2022, house_count=1, house_prices=[900_000_000]))["주택임대 — 1주택 비과세"]["판정"] == "비과세"
    # 국외주택은 제외
    assert J(G.guide(2024, house_count=1, house_prices=[100_000_000], overseas_house=True))["주택임대 — 1주택 비과세"]["판정"] == "과세"


def test_two_crore_exempt_until_2018_then_separate_2019():
    j18 = J(G.guide(2018, house_count=3, rental_revenue=20_000_000))
    j19 = J(G.guide(2019, house_count=3, rental_revenue=20_000_000))
    assert j18["주택임대 — 2천만원 이하"]["판정"] == "비과세"
    assert j19["주택임대 — 과세 방식"]["판정"] == "분리과세 선택 가능"
    assert J(G.guide(2019, house_count=3, rental_revenue=20_000_001))["주택임대 — 과세 방식"]["판정"] == "종합과세"
    assert J(G.guide(2018, house_count=3, rental_revenue=20_000_001))["주택임대 — 과세 방식"]["판정"] == "종합과세"


def test_separate_tax_expense_rate_and_deduction():
    # 법 제64조의2제2항 — 등록 60%·400만원, 그 밖 50%·200만원, 다른 종합소득금액 2천만원 이하일 때만 공제
    reg = J(G.guide(2024, house_count=2, rental_revenue=15_000_000, registered_rental=True, other_income=20_000_000))["주택임대 — 과세 방식"]["사유"]
    non = J(G.guide(2024, house_count=2, rental_revenue=15_000_000, registered_rental=False, other_income=20_000_001))["주택임대 — 과세 방식"]["사유"]
    assert "60%" in reg and "400만원 추가 공제." in reg
    assert "50%" in non and "추가 공제 없음" in non
    # 국외주택은 등록임대주택 특례 불가(기준-2020-법령해석소득-0004)
    ov = J(G.guide(2024, house_count=1, house_prices=[1], overseas_house=True, rental_revenue=10_000_000, registered_rental=True))["주택임대 — 과세 방식"]["사유"]
    assert "50%" in ov and "국외주택" in ov


def test_deemed_rent_three_houses_and_small_house():
    # 3주택, 보증금 3억원 초과일 때만(같으면 대상 아님)
    assert J(G.guide(2024, house_count=3, deposit_total=300_000_000))["주택임대 — 간주임대료"]["판정"] == "대상 아님"
    assert J(G.guide(2024, house_count=3, deposit_total=300_000_001))["주택임대 — 간주임대료"]["판정"] == "대상"
    # 소형주택 1채 빼면 2채 → 2025년은 대상 아님
    assert J(G.guide(2025, house_count=3, small_house_count=1, deposit_total=500_000_000))["주택임대 — 간주임대료"]["판정"] == "대상 아님"
    assert "85㎡" in G.guide(2016)["그 해 기준"]["간주임대료 소형주택(주택 수 제외)"]
    assert "60㎡" in G.guide(2017)["그 해 기준"]["간주임대료 소형주택(주택 수 제외)"]
    assert "60㎡" in G.guide(2018)["그 해 기준"]["간주임대료 소형주택(주택 수 제외)"]
    assert "40㎡" in G.guide(2019)["그 해 기준"]["간주임대료 소형주택(주택 수 제외)"]


def test_deemed_rent_two_houses_from_2026():
    # 법 제25조제1항제2호 — 2026.1.1. 시행(제19933호 부칙 제1조제1호, 경과조치: 시행 전 개시 과세기간은 종전)
    kw = dict(house_count=2, house_prices=[1_300_000_000, 1_500_000_000], deposit_total=1_300_000_000)
    assert J(G.guide(2025, **kw))["주택임대 — 간주임대료"]["판정"] == "대상 아님"
    assert J(G.guide(2026, **kw))["주택임대 — 간주임대료"]["판정"] == "대상"
    # 12억원 이하 주택은 주택 수에서 뺌, 보증금 12억원 초과여야
    assert J(G.guide(2026, house_count=2, house_prices=[1_200_000_000, 1_500_000_000], deposit_total=1_300_000_000))["주택임대 — 간주임대료"]["판정"] == "대상 아님"
    assert J(G.guide(2026, house_count=2, house_prices=[1_300_000_000, 1_500_000_000], deposit_total=1_200_000_000))["주택임대 — 간주임대료"]["판정"] == "대상 아님"


def test_faithful_filing_2017_2018():
    # 시행령 제133조제1항 — 2018.2.13. 개정, 시행일이 속하는 과세기간부터 15억·7억5천만·5억
    assert J(G.guide(2017, "도매·소매업", revenue_curr=1_500_000_000))["성실신고확인"]["판정"] == "대상 아님"
    assert J(G.guide(2018, "도매·소매업", revenue_curr=1_500_000_000))["성실신고확인"]["판정"] == "대상"
    assert J(G.guide(2017, "도매·소매업", revenue_curr=2_000_000_000))["성실신고확인"]["판정"] == "대상"
    assert J(G.guide(2017, "제조업", revenue_curr=750_000_000))["성실신고확인"]["판정"] == "대상 아님"
    assert J(G.guide(2018, "제조업", revenue_curr=750_000_000))["성실신고확인"]["판정"] == "대상"
    assert J(G.guide(2026, "부동산임대업", revenue_curr=499_999_999))["성실신고확인"]["판정"] == "대상 아님"
    # 별표 3의3 사업서비스업은 5억원
    assert J(G.guide(2024, "제조업", revenue_curr=500_000_000, business_service=True))["성실신고확인"]["판정"] == "대상"


def test_faithful_filing_asset_sale_exclusion_from_2019():
    kw = dict(revenue_curr=1_600_000_000, asset_sale_curr=200_000_000)
    assert J(G.guide(2018, "도매·소매업", **kw))["성실신고확인"]["판정"] == "대상"
    assert J(G.guide(2019, "도매·소매업", **kw))["성실신고확인"]["판정"] == "대상 아님"


def test_bookkeeping():
    assert J(G.guide(2024, "도매·소매업", revenue_prev=300_000_000))["기장 의무"]["판정"] == "복식부기의무자"
    assert J(G.guide(2024, "도매·소매업", revenue_prev=299_999_999))["기장 의무"]["판정"] == "간편장부대상자"
    assert J(G.guide(2016, "제조업", revenue_prev=150_000_000))["기장 의무"]["판정"] == "복식부기의무자"
    assert J(G.guide(2016, "부동산임대업", revenue_prev=74_999_999))["기장 의무"]["판정"] == "간편장부대상자"
    assert J(G.guide(2024, "보건업·사회복지서비스업", revenue_prev=1, professional=True))["기장 의무"]["판정"] == "복식부기의무자"
    assert J(G.guide(2024, "도매·소매업", new_business=True))["기장 의무"]["판정"] == "간편장부대상자"
    # 사업용 유형자산 양도 수입금액 제외 — 2020년 과세기간부터(시행령 2020.2.11. 개정 부칙)
    kw = dict(revenue_prev=320_000_000, asset_sale_prev=30_000_000)
    assert J(G.guide(2019, "도매·소매업", **kw))["기장 의무"]["판정"] == "복식부기의무자"
    assert J(G.guide(2020, "도매·소매업", **kw))["기장 의무"]["판정"] == "간편장부대상자"
    # 복식부기의무자면 사업용계좌 의무
    assert J(G.guide(2024, "도매·소매업", revenue_prev=300_000_000))["사업용계좌"]["판정"] == "의무"


def test_simple_ratio_current_year_test_from_2019():
    kw = dict(revenue_prev=50_000_000, revenue_curr=400_000_000)
    assert J(G.guide(2018, "도매·소매업", **kw))["추계 — 경비율"]["판정"] == "단순경비율"
    assert J(G.guide(2019, "도매·소매업", **kw))["추계 — 경비율"]["판정"] == "기준경비율"
    assert J(G.guide(2024, "도매·소매업", revenue_prev=60_000_000, revenue_curr=1))["추계 — 경비율"]["판정"] == "기준경비율"
    # 신규 사업자 — 해당 과세기간 수입금액이 복식부기 기준 미만
    assert J(G.guide(2024, "제조업", new_business=True, revenue_curr=149_999_999))["추계 — 경비율"]["판정"] == "단순경비율"
    assert J(G.guide(2024, "제조업", new_business=True, revenue_curr=150_000_000))["추계 — 경비율"]["판정"] == "기준경비율"
    assert J(G.guide(2024, "도매·소매업", revenue_prev=1, revenue_curr=1, professional=True))["추계 — 경비율"]["판정"] == "기준경비율"


def test_personal_service_36m_from_2023():
    kw = dict(revenue_prev=30_000_000, revenue_curr=30_000_000)
    assert J(G.guide(2022, "수리·기타 개인서비스업(인적용역)", **kw))["추계 — 경비율"]["판정"] == "기준경비율"
    assert J(G.guide(2023, "수리·기타 개인서비스업(인적용역)", **kw))["추계 — 경비율"]["판정"] == "단순경비율"
    assert J(G.guide(2023, "수리·기타 개인서비스업", **kw))["추계 — 경비율"]["판정"] == "기준경비율"


def test_other_exemptions_by_year():
    # 조림 — 2025년까지 600만원, 2026년 3천만원(법 2025.12.23. 개정 부칙 제2조)
    assert J(G.guide(2025, "조림(임목 벌채·양도)", exempt_income=10_000_000))["조림(임목 벌채·양도) 비과세"]["판정"] == "확인 필요"
    assert J(G.guide(2026, "조림(임목 벌채·양도)", exempt_income=10_000_000))["조림(임목 벌채·양도) 비과세"]["판정"] == "비과세"
    assert J(G.guide(2025, "조림(임목 벌채·양도)", exempt_income=6_000_000))["조림(임목 벌채·양도) 비과세"]["판정"] == "비과세"
    # 어로어업 사목 — 2020년부터, 양식어업 — 2024년부터
    assert "농어가부업" in J(G.guide(2019, "연근해·내수면어업", exempt_income=1))["연근해·내수면어업 비과세"]["사유"]
    assert J(G.guide(2020, "연근해·내수면어업", exempt_income=50_000_000))["연근해·내수면어업 비과세"]["판정"] == "비과세"
    assert "양어" in J(G.guide(2023, "양식어업", exempt_income=1))["양식어업 비과세"]["사유"]
    assert J(G.guide(2024, "양식어업", exempt_income=50_000_000))["양식어업 비과세"]["판정"] == "비과세"
    # 작물재배업 10억원, 곡물 재배는 사업소득 아님, 전통주 1천200만원
    assert J(G.guide(2016, "작물재배업", revenue_curr=1_000_000_000))["작물재배업 비과세"]["판정"] == "비과세"
    assert J(G.guide(2024, "곡물·식량작물 재배업"))["사업소득 범위"]["판정"] == "사업소득 아님"
    assert J(G.guide(2024, "전통주 제조", exempt_income=12_000_000))["전통주 제조 비과세"]["판정"] == "비과세"
    assert J(G.guide(2024, "농어가부업", exempt_income=30_000_001))["농어가부업 비과세"]["판정"] == "확인 필요"


def test_scope_asset_sale_from_2018():
    assert "제20호" not in J(G.guide(2017, "제조업"))["사업소득 범위"]["사유"]
    assert "제20호" in J(G.guide(2018, "제조업"))["사업소득 범위"]["사유"]
