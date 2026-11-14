"""vat_exempt_zero_rate_guide — 부가가치세법 시행령 2022년 이후 개정분·시행규칙 대조 후 고친 판정(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(법제처 DRF): 부가가치세법 시행령 2021.9.24. 시행본(대통령령 제31543호)과 2026.4.1. 시행본(대통령령 제36133호)의 제32조·제33조·제35조~제37조·제40조·제41조·제101조와 연혁 부칙
- 제32419호(2022.2.15.) 제33조제2항제1호사목 '전자상거래 소매 중개업', 부칙 제5조(시행 전 공급분도 시행 이후 신고·결정·경정하면 적용)
- 제34270호(2024.2.29.) 제37조제1호가목1) 시외고급고속버스(별도 적용례 없음), 제41조제1항제2호 토지임대부 분양주택 부수토지(부칙 제1조 단서·제5조: 2024.7.1. 이후 공급분)
- 제33735호 부칙 제2조제1항(제35조제5호마목 '예방 및 치료', 2023.10.1. 이후 공급분), 제33271호 부칙 제2조(제101조 표, 2023.2.28. 이후 공급분)
- 시행규칙 2026.4.1. 시행본(재정경제부령 제9호) 제21조(25일), 제22조(외화 결제 방법), 제26조(전자출판물)."""
from korean_tax_mcp import vat_exempt_zero_rate as V


def P(r):
    return {x["항목"]: x["판정"] for x in r["판정"]}


def test_premium_express_bus_2024_02_29():
    assert P(V.guide("2024-02-28", "여객운송", {"transport": "시외고급고속버스"}))["여객운송"] == "면세"
    r = V.guide("2024-02-29", "여객운송", {"transport": "시외고급고속버스"})
    assert P(r)["여객운송"] == "과세" and "제34270호" in r["판정"][0]["근거"]
    assert P(V.guide("2024-02-29", "여객운송", {"transport": "일반 고속버스"}))["여객운송"] == "면세"
    assert P(V.guide("2018-05-01", "여객운송", {"transport": "시외우등고속버스"}))["여객운송"] == "과세"


def test_land_lease_housing_2024_07_01():
    f = {"lease": True, "land_lease_housing": True, "national_housing_size": True}
    assert P(V.guide("2024-06-30", "토지 공급", f))["토지 임대(토지임대부 분양주택)"] == "과세"
    r = V.guide("2024-07-01", "토지 공급", f)
    assert P(r)["토지 임대(토지임대부 분양주택)"] == "면세" and "제41조제1항제2호" in r["판정"][0]["근거"]
    assert P(V.guide("2024-07-01", "토지 공급", dict(f, national_housing_size=False)))["토지 임대(토지임대부 분양주택)"] == "과세"
    assert P(V.guide("2024-07-01", "토지 공급", dict(f, national_housing_size=None)))["토지 임대(토지임대부 분양주택)"] == "확인 필요"
    assert P(V.guide("2024-07-01", "토지 공급", {"lease": True}))["토지 임대"] == "과세"
    assert P(V.guide("2024-07-01", "토지 공급", {}))["토지 공급"] == "면세"


def test_ecommerce_brokerage_by_filing_date():
    base = {"counterparty_nonresident": True, "has_domestic_place": False, "service_kind": "전자상거래 소매 중개업", "payment": "외국환은행 원화"}
    # 2021.10. 공급, 2022-01-25 신고 → 열거 전이라 과세
    assert P(V.guide("2021-10-15", "외화 획득 용역", dict(base, filed_or_assessed_on="2022-01-25")))["외화 획득 용역"] == "과세"
    # 같은 공급, 2022-03-10 경정 → 부칙 제5조로 개정규정 적용 → 영세율
    assert P(V.guide("2021-10-15", "외화 획득 용역", dict(base, filed_or_assessed_on="2022-03-10")))["외화 획득 용역"] == "영세율"
    # 경계: 2022-02-14 신고 → 과세 / 2022-02-15 신고 → 영세율
    assert P(V.guide("2021-12-15", "외화 획득 용역", dict(base, filed_or_assessed_on="2022-02-14")))["외화 획득 용역"] == "과세"
    assert P(V.guide("2021-12-15", "외화 획득 용역", dict(base, filed_or_assessed_on="2022-02-15")))["외화 획득 용역"] == "영세율"
    # 2022.3. 공급 → 신고는 그 뒤일 수밖에 없어 영세율
    assert P(V.guide("2022-03-15", "외화 획득 용역", base))["외화 획득 용역"] == "영세율"
    # 시행 전 공급, 신고일 없음 → 확인 필요
    assert P(V.guide("2021-10-15", "외화 획득 용역", base))["외화 획득 용역"] == "확인 필요"
    assert "error" in V.guide("2021-10-15", "외화 획득 용역", dict(base, filed_or_assessed_on="2022/03/10"))
    # 상품 중개업은 그대로
    assert P(V.guide("2021-10-15", "외화 획득 용역", dict(base, service_kind="상품 중개업")))["외화 획득 용역"] == "영세율"


def test_housing_paragraph_numbers_2024_07_01():
    f = {"residential": True, "house_floor_area": 100, "building_footprint": 50, "land_area": 400, "business_floor_area": 50}
    old = {x["항목"]: x["근거"] for x in V.guide("2024-06-30", "주택 임대", f)["판정"]}
    new = {x["항목"]: x["근거"] for x in V.guide("2024-07-01", "주택 임대", f)["판정"]}
    assert old["겸용주택"].endswith("제41조제2항제1호") and new["겸용주택"].endswith("제41조제3항제1호")
    assert old["부수토지"].endswith("제41조제1항 후단") and new["부수토지"].endswith("제41조제2항")
    # 배율·판정은 같음: 한도 max(100, 50×5=250) < 400 → 일부 과세
    assert P(V.guide("2024-07-01", "주택 임대", f))["부수토지"] == P(V.guide("2024-06-30", "주택 임대", f))["부수토지"] == "일부 과세"


def test_vet_and_wording_by_date():
    a = V.guide("2023-09-30", "의료보건", {"provider": "수의사", "animal_listed": True})["판정"][0]["사유"]
    b = V.guide("2023-10-01", "의료보건", {"provider": "수의사", "animal_listed": True})["판정"][0]["사유"]
    assert "예방 및 치료" not in a.split("(")[0] and "예방 및 치료" in b
    r = V.guide("2022-05-01", "내국신용장·구매확인서", {"issued_in_time": True})
    assert P(r)["내국신용장·구매확인서"] == "영세율" and "시행규칙 제21조" in r["판정"][0]["근거"] and "미확인" not in r["판정"][0]["사유"]
    assert "재정경제부령" in V.guide("2026-03-01", "내국신용장·구매확인서", {"issued_in_time": True})["판정"][0]["사유"]
    assert "기획재정부령" in V.guide("2025-12-31", "내국신용장·구매확인서", {"issued_in_time": True})["판정"][0]["사유"]
    r = V.guide("2022-05-01", "외화 획득 용역", {"counterparty_nonresident": True, "has_domestic_place": False, "service_kind": "통신업", "payment": "외화 현금"})
    assert "시행규칙 제22조" in r["판정"][-1]["근거"]
    assert "시행규칙 제26조" in V.guide("2022-05-01", "도서·신문", {})["판정"][0]["사유"]


def test_attachments_split_2023_02_28():
    old = V.guide("2023-02-27", "주한 국제연합군·미군 공급")["영세율 첨부서류"]
    new = V.guide("2023-02-28", "주한 국제연합군·미군 공급")["영세율 첨부서류"]
    assert "군납완료증명서 또는" in old["서류"] or "군납완료증명서(" in old["서류"]
    assert "군납완료증명서 삭제" in new["서류"] and "제33271호" in new["근거"]
    fx = V.guide("2023-02-28", "외화 획득 용역")["영세율 첨부서류"]["서류"]
    assert "투자자문업" in fx and "제52조제1항" in fx
    assert "투자자문업" not in V.guide("2023-02-27", "외화 획득 용역")["영세율 첨부서류"]["서류"]


def test_unverified_tail_removed_after_2022():
    for cat, f in (("교육", {"registered": True}), ("금융·보험", {"listed_business": True}), ("주택 임대", {"residential": True})):
        r = V.guide("2025-05-01", cat, f)
        assert all("미확인" not in x["사유"] for x in r["판정"]), cat
    assert "미확인" in V.guide("2025-05-01", "미가공식료품", {"simple_processed": True})["판정"][0]["사유"]   # 별표 1은 남김
    assert P(V.guide("2025-05-01", "국민주택 공급", {}))["국민주택 공급"] == "확인 필요"
