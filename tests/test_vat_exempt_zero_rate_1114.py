"""vat_exempt_zero_rate_guide — 부가가치세법 2016~2026 각 연말 시행본(제21조~제28조)과 부칙, 시행령 2016~2021 각 연말 시행본
(2016.9.1.·2017.12.21.·2018.9.28.·2019.6.25.·2020.12.10.·2021.9.24.)의 제31조~제38조·제40조·제41조·제57조·제101조와 부칙을
국세법령정보시스템 연혁본으로 대조(2026-11-14). 경계일은 부칙 적용례로 정함. Claude 작성. 외부 호출 없음."""
from korean_tax_mcp import vat_exempt_zero_rate as V


def P(r):
    return {p["항목"]: p["판정"] for p in r["판정"]}


def test_overview_and_errors():
    o = V.guide()
    assert len(o["날짜에 따라 달라지는 것"]) == 7 and "주택 임대" in o["면세 유형"] and "외화 획득 용역" in o["영세율 유형"]
    assert "error" in V.guide("2015-12-31", "교육") and "error" in V.guide("2024-02-30", "교육") and "error" in V.guide("2024-01-01", "없는 유형")
    assert "error" in V.guide(category="교육")
    assert V.guide("2024-01-01")["안내"].startswith("category")


def test_reading_room_2023():          # 법률 제19194호 부칙 제2조 — 2023.1.1. 이후 공급분
    assert P(V.guide("2022-12-31", "도서·신문", {"reading_room": True}))["실내 도서열람 용역"] == "과세"
    assert P(V.guide("2023-01-01", "도서·신문", {"reading_room": True}))["실내 도서열람 용역"] == "면세"
    assert P(V.guide("2024-01-01", "도서·신문", {"advertising": True}))["도서·신문"] == "과세"


def test_animal_blood_2025():          # 2024.12.31. 개정 부칙 제2조 — 2025.1.1. 이후 공급분
    assert P(V.guide("2024-12-31", "의료보건", {"animal_blood": True}))["동물의 혈액"] == "과세"
    assert P(V.guide("2025-01-01", "의료보건", {"animal_blood": True}))["동물의 혈액"] == "면세"


def test_cosmetic_medical():           # 시행령 제35조제1호 단서 가목·나목
    assert P(V.guide("2021-06-01", "의료보건", {"provider": "의사등", "cosmetic_listed": True}))["의료보건 용역"] == "과세"
    assert P(V.guide("2021-06-01", "의료보건", {"provider": "의사등", "cosmetic_listed": True, "reconstructive": True}))["의료보건 용역"] == "면세"
    assert P(V.guide("2021-06-01", "의료보건", {"provider": "의사등", "cosmetic_listed": False}))["의료보건 용역"] == "면세"
    assert P(V.guide("2021-06-01", "의료보건", {"provider": "수의사", "animal_listed": False}))["수의사 용역"] == "과세"
    r = V.guide("2024-06-01", "의료보건", {"provider": "의사등", "cosmetic_listed": True})
    assert "미확인" in r["판정"][0]["사유"] and any(x["문서번호"] == "서면-2024-부가-5065" for x in r["관련 해석"])


def test_education_and_social_coop_2020():   # 시행령 제36조제1항제7호 — 2020.7.1.(2020.2.11. 개정령 부칙 제1조 단서)
    assert P(V.guide("2018-03-01", "교육", {"registered": True}))["교육 용역"] == "면세"
    assert P(V.guide("2018-03-01", "교육", {"registered": True, "academy_kind": "자동차운전학원"}))["교육 용역"] == "과세"
    assert P(V.guide("2018-03-01", "교육", {"registered": False}))["교육 용역"] == "과세"
    assert P(V.guide("2020-06-30", "교육", {"social_coop": True}))["교육 용역"] == "확인 필요"
    assert P(V.guide("2020-07-01", "교육", {"social_coop": True}))["교육 용역"] == "면세"


def test_housing_land_limit():         # 시행령 제41조 — 연면적과 정착면적 × 5배(도시지역 밖 10배) 중 넓은 면적
    j = P(V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 120, "building_footprint": 60, "land_area": 400}))
    assert j["주택 임대"] == "면세" and j["부수토지"] == "일부 과세"          # 한도 max(120, 300)=300 → 100㎡ 토지 임대
    r = V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 120, "building_footprint": 60, "land_area": 400})
    assert "100㎡" in [p for p in r["판정"] if p["항목"] == "부수토지"][0]["사유"]
    assert P(V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 120, "building_footprint": 60, "land_area": 400, "outside_urban": True}))["부수토지"] == "면세"
    j = P(V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 100, "business_floor_area": 150, "building_footprint": 60, "land_area": 800}))
    assert j["겸용주택"] == "과세(사업용 건물 부분)" and j["부수토지"] == "일부 과세"   # 800 × 0.4 = 320 > 300
    j = P(V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 100, "business_floor_area": 150, "building_footprint": 60, "land_area": 700}))
    assert j["부수토지"] == "확인 필요"     # 700 × 0.4 = 280 — 전체 정착면적 한도 300 안, 비율 정착면적 한도 120 밖
    assert P(V.guide("2020-05-01", "주택 임대", {"residential": True, "house_floor_area": 160, "business_floor_area": 150}))["겸용주택"] == "면세"
    assert P(V.guide("2020-05-01", "주택 임대", {"residential": False}))["주택 임대"] == "과세"


def test_passenger_2019():             # 법 제26조제1항제7호나목(2019.1.1.), 시행령 제37조제2호(2019.2.12.)
    assert P(V.guide("2018-12-31", "여객운송", {"transport": "삭도"}))["여객운송"] == "확인 필요"
    assert P(V.guide("2019-01-20", "여객운송", {"transport": "삭도"}))["여객운송"] == "확인 필요"
    assert P(V.guide("2019-02-12", "여객운송", {"transport": "삭도"}))["여객운송"] == "과세"
    assert P(V.guide("2017-05-01", "여객운송", {"transport": "택시"}))["여객운송"] == "과세"
    assert P(V.guide("2017-05-01", "여객운송", {"transport": "일반 고속버스"}))["여객운송"] == "면세"


def test_food_finance_land():
    assert P(V.guide("2018-01-01", "미가공식료품", {"primary_processing_only": True}))["미가공식료품"] == "면세"
    assert P(V.guide("2018-01-01", "미가공식료품", {"primary_processing_only": False}))["미가공식료품"] == "과세"
    assert P(V.guide("2018-01-01", "미가공식료품", {"edible": False, "domestic": False}))["미가공식료품"] == "과세"
    assert P(V.guide("2018-01-01", "금융·보험", {"listed_business": True, "excluded_service": True}))["금융·보험 용역"] == "과세"
    assert P(V.guide("2018-01-01", "금융·보험", {"listed_business": True}))["금융·보험 용역"] == "면세"
    assert P(V.guide("2018-01-01", "토지 공급"))["토지 공급"] == "면세"
    assert P(V.guide("2018-01-01", "토지 공급", {"lease": True}))["토지 임대"] == "과세"
    assert P(V.guide("2018-01-01", "국민주택 공급"))["국민주택 공급"] == "확인 필요"


def test_bonded_area_export_2019():    # 시행령 제31조제1항제6호 — 2019.2.12. 개정 일반적 적용례
    f = {"export_form": "보세구역 물품 반출", "domestic_place_contract": True}
    assert P(V.guide("2019-02-11", "중계무역 등 수출", f))["보세구역 물품 반출"] == "확인 필요"
    assert P(V.guide("2019-02-12", "중계무역 등 수출", f))["보세구역 물품 반출"] == "영세율"
    assert P(V.guide("2018-06-01", "중계무역 등 수출", {"export_form": "중계무역", "domestic_place_contract": False}))["중계무역"] == "과세"
    assert P(V.guide("2018-06-01", "중계무역 등 수출", {"export_form": "원료 무상 반출"}))["원료 무상 반출"] == "영세율"


def test_fx_service_dates():           # 시행령 제33조제2항 — 2017.2.7.(비거주자 범위), 2020.7.1.(투자자문업)
    base = {"counterparty_nonresident": True, "has_domestic_place": False, "payment": "외국환은행 원화", "reciprocal": True}
    assert P(V.guide("2020-06-30", "외화 획득 용역", {**base, "service_kind": "투자자문업"}))["외화 획득 용역"] == "과세"
    assert P(V.guide("2020-07-01", "외화 획득 용역", {**base, "service_kind": "투자자문업"}))["외화 획득 용역"] == "영세율"
    assert P(V.guide("2017-02-07", "외화 획득 용역", {**base, "service_kind": "통신업", "excluded_person": True}))["외화 획득 용역"] == "과세"
    assert P(V.guide("2017-02-06", "외화 획득 용역", {**base, "service_kind": "통신업", "excluded_person": True}))["공급받는 자"] == "확인 필요"
    assert P(V.guide("2018-06-01", "외화 획득 용역", {**base, "service_kind": "전문서비스업", "reciprocal": False}))["상호면세"] == "과세"
    assert P(V.guide("2018-06-01", "외화 획득 용역", {**base, "service_kind": "통신업", "payment": "외화 현금"}))["대금 결제"] == "과세"
    assert P(V.guide("2018-06-01", "외화 획득 용역", {**base, "service_kind": "그 밖의 업종"}))["외화 획득 용역"] == "과세"
    j = P(V.guide("2018-06-01", "외화 획득 용역", {**base, "service_kind": "통신업", "has_domestic_place": True, "direct_contract_foreign": False}))
    assert j["외화 획득 용역"] == "과세"
    assert P(V.guide("2018-06-01", "외화 획득 용역", {**base, "counterparty_nonresident": False}))["외화 획득 용역"] == "과세"


def test_other_zero_rate():
    assert P(V.guide("2018-06-01", "내국신용장·구매확인서", {"gold_bullion": True}))["금지금"] == "과세"
    assert P(V.guide("2018-06-01", "내국신용장·구매확인서", {"issued_in_time": True}))["내국신용장·구매확인서"] == "영세율"
    assert P(V.guide("2018-06-01", "수출재화임가공", {"direct_contract_exporter": True, "separate_vat_invoice": True}))["수출재화임가공"] == "과세"
    assert P(V.guide("2018-06-01", "외항선박 등 공급", {"separate_vat_invoice": False}))["외항선박 등 공급"] == "영세율"
    assert P(V.guide("2018-06-01", "비거주자 지정 인도 재화", {"direct_contract": True, "paid_krw_fx_bank": True, "delivered_to_designated": True, "exported_by_designee": False}))["비거주자 지정 인도 재화"] == "과세"
    assert P(V.guide("2018-06-01", "직수출", {"supplier_nonresident": True, "reciprocal": False}))["상호주의(공급자가 비거주자·외국법인)"] == "과세"
    assert P(V.guide("2018-06-01", "외교공관등 공급", {"honorary_consulate": True}))["외교공관등 공급"] == "과세"
    r = V.guide("2018-06-01", "직수출")
    assert "수출실적명세서" in r["영세율 첨부서류"]["서류"] and "2019 시행본" in r["영세율 첨부서류"]["근거"]


def test_waiver():                     # 법 제28조제1항 — 영세율 대상 또는 제26조제1항제12호·제15호·제18호
    assert V.guide("2018-06-01", "미가공식료품", {"primary_processing_only": True})["면세포기"]["대상"] == "대상 아님"
    assert V.guide("2018-06-01", "미가공식료품", {"primary_processing_only": True, "also_zero_rated": True})["면세포기"]["대상"] == "가능"
    w = V.guide("2018-06-01", "주택 임대", {"residential": True}, waive_exemption=True)["면세포기"]
    assert w["대상"] == "가능" and "3년" in w["절차"] and "효과" in w
