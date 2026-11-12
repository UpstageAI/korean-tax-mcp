"""0.12.26 employment_credit_requirements_guide — 조문 문언 대조 테스트(2026-11-12, Claude 작성). 외부 호출 없음.
근거: 조세특례제한법 제29조의7·제29조의8·제127조④⑪·제144조①, 시행령 제26조의7·제26조의8·제23조⑩·제29조③(2018~2025 각 연말·2026.11.12. 시행본)과 개정 부칙."""
from korean_tax_mcp import employment_requirements as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def R(r):
    return {p["요건"]: p for p in r["요건"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["연도별 변화"]) >= 8 and r["제도 구분"] == ["고용증대", "통합고용"]
    assert "error" in G.guide(2017) and "error" in G.guide(2022, credit="통합고용") and "error" in G.guide(2024, size="대기업")
    assert "error" in G.guide(2024, workers=[{"disabled_kind": "기타"}]) and "error" in G.guide(2025, founded="2025/01/01")


def test_available_credit_by_year():
    assert G.available(2022)[0] == ["고용증대"] and G.available(2023)[0] == ["고용증대", "통합고용"] and G.available(2025)[0] == ["통합고용"]
    assert G.guide(2021)["제도"] == "고용증대" and G.guide(2024)["제도"] == "통합고용"
    assert J(G.guide(2024))["제도 선택"]["판정"] == "확인 필요"
    assert J(G.guide(2025, credit="고용증대"))["새로 늘어난 인원"]["판정"] == "대상 아님"
    assert "부칙 제34조" in G.available(2026)[1]


def test_youth_age_29_vs_34_and_military_service():
    w = [{"name": "서른", "age": 30}, {"name": "병역", "age": 31, "military_years": 2}, {"name": "기간제", "age": 25, "fixed_term": True, "contract_months": 24}]
    a, b = J(G.guide(2022, workers=w)), J(G.guide(2024, credit="통합고용", workers=w))
    assert a["직원 — 서른"]["판정"] == "상시근로자 — 청년등 외" and b["직원 — 서른"]["판정"] == "상시근로자 — 청년등"
    assert a["직원 — 병역"]["판정"] == "상시근로자 — 청년등" and "29세" in a["직원 — 병역"]["사유"]
    assert a["직원 — 기간제"]["판정"] == "상시근로자 — 청년등 외" and "기간제근로자" in a["직원 — 기간제"]["사유"]      # 1년 이상 계약이면 상시근로자이지만 청년은 아님


def test_youth_group_widened_by_year():
    old = [{"name": "고령", "age": 61, "age_at_contract": 60}, {"name": "오일팔", "age": 50, "disabled_kind": "5·18민주화운동부상자"}, {"name": "장애", "age": 50, "disabled_kind": "장애인"}]
    assert [J(G.guide(y, workers=old))["직원 — 고령"]["판정"] for y in (2020, 2021)] == ["상시근로자 — 청년등 외", "상시근로자 — 청년등"]
    assert [J(G.guide(y, workers=old))["직원 — 오일팔"]["판정"] for y in (2018, 2019)] == ["상시근로자 — 청년등 외", "상시근로자 — 청년등"]
    assert J(G.guide(2018, workers=old))["직원 — 장애"]["판정"] == "상시근로자 — 청년등"
    d = [{"name": "탈북", "age": 40, "defector": True}, {"name": "경단", "age": 40, "career_break": True}]
    assert J(G.guide(2024, workers=d))["직원 — 탈북"]["판정"].endswith("청년등 외") and J(G.guide(2025, workers=d))["직원 — 탈북"]["판정"].endswith("— 청년등")
    assert "제29조의3" in J(G.guide(2024, workers=d))["직원 — 경단"]["사유"] and "제29조의8제2항" in J(G.guide(2025, workers=d))["직원 — 경단"]["사유"]
    assert J(G.guide(2022, workers=d))["직원 — 경단"]["판정"].endswith("청년등 외")
    assert len(R(G.guide(2018))["청년등상시근로자 범위"]["해당"]) == 2 and len(R(G.guide(2025))["청년등상시근로자 범위"]["해당"]) == 5


def test_regular_employee_exclusions():
    w = [{"name": "단기", "age": 25, "contract_months": 6}, {"name": "임원", "executive": True}, {"name": "배우자", "owner_or_family": True},
         {"name": "미신고", "withholding": False, "social_insurance": False}, {"name": "보험만", "age": 40, "withholding": False, "social_insurance": True},
         {"name": "알바", "age": 22, "part_time": True, "monthly_hours": 40}, {"name": "반일", "age": 40, "part_time": True, "monthly_hours": 80}, {"name": "미상", "part_time": True}]
    r = J(G.guide(2023, workers=w))
    assert all(r[f"직원 — {n}"]["판정"] == "상시근로자 아님" for n in ("단기", "임원", "배우자", "미신고", "알바"))
    assert r["직원 — 보험만"]["판정"] == "상시근로자 — 청년등 외" and r["직원 — 반일"]["인원_환산"] == 0.5 and r["직원 — 미상"]["판정"] == "확인 필요"
    half = J(G.guide(2023, workers=[{"name": "보험없음", "age": 30, "social_insurance": False}, {"name": "원천없음", "age": 30, "withholding": False}, {"name": "원천만", "age": 30, "withholding": True, "social_insurance": False}]))
    assert half["직원 — 보험없음"]["판정"] == "확인 필요" and half["직원 — 원천없음"]["판정"] == "확인 필요" and half["직원 — 원천만"]["판정"] == "상시근로자 — 청년등"      # 둘 다 확인되지 않아야 제외
    assert "제40조제1항" in R(G.guide(2019))["상시근로자 범위"]["제외"][2] and "제42조제1항" in R(G.guide(2018))["상시근로자 범위"]["제외"][2]
    assert "제23조제10항" in R(G.guide(2025))["상시근로자 범위"]["근거"]


def test_startup_reduction_overlap_by_year():
    k = "창업감면과의 관계"
    assert J(G.guide(2022, startup_reduction=True, extra_reduction_for_employment=False))[k]["판정"] == "함께 적용"
    assert J(G.guide(2022, startup_reduction=True, extra_reduction_for_employment=True))[k]["판정"] == "함께 적용하지 않음"
    assert J(G.guide(2024, startup_reduction=True))[k]["판정"] == "확인 필요"
    assert J(G.guide(2025, startup_reduction=True, founded="2025-01-01"))[k]["판정"] == "함께 적용하지 않음"
    assert J(G.guide(2025, startup_reduction=True, founded="2024-12-31", extra_reduction_for_employment=False))[k]["판정"] == "함께 적용"
    assert J(G.guide(2025, startup_reduction=True))[k]["판정"] == "확인 필요" and J(G.guide(2025, startup_reduction=False))[k]["판정"] == "해당 없음"
    assert "제29조의8제1항" in R(G.guide(2023))["다른 감면·공제와의 관계"]["내용"] and "제29조의8" not in R(G.guide(2022))["다른 감면·공제와의 관계"]["내용"]
    assert J(G.guide(2023, took_employment_increase=True))["고용증대와의 관계"]["판정"] == "대상 아님"


def test_carryforward_and_follow_up_text():
    assert "5년" in R(G.guide(2019))["이월공제"]["내용"] and "10년" in R(G.guide(2020))["이월공제"]["내용"] and "부칙 제35조" in R(G.guide(2020))["이월공제"]["근거"]
    assert "부칙 제13조" in R(G.guide(2018))["공제 기간과 사후관리"]["근거"] and "공제받은 직전 과세연도" in R(G.guide(2018))["공제 기간과 사후관리"]["내용"]
    assert "유예 특례" in R(G.guide(2020))["공제 기간과 사후관리"]["내용"] and "유예 특례" not in R(G.guide(2023, credit="고용증대"))["공제 기간과 사후관리"]["내용"]
    assert "제3항" in R(G.guide(2025))["공제 기간과 사후관리"]["근거"] and "제2항" in R(G.guide(2024))["공제 기간과 사후관리"]["근거"]
    assert "상시근로자 명세서" in R(G.guide(2025))["신청"]["내용"] and "상시근로자 명세서" not in R(G.guide(2024))["신청"]["내용"]
    assert J(G.guide(2024, consumer_service=True))["업종"]["판정"] == "대상 아님"


def test_2026_integrated_credit_rules():
    r = G.guide(2026)
    q = R(r)
    assert "직전 3개 과세연도" in q["상시근로자 수 증가"]["내용"] and "제26조의8제2항" in q["상시근로자 범위"]["근거"] and "근무개월 수" in q["인원 계산"]["내용"]
    assert "삭제" in q["공제 기간과 사후관리"]["내용"] and "부칙 제34조" in q["공제 기간과 사후관리"]["근거"]
    k = "최소고용증가인원수"
    assert J(G.guide(2026, size="중견기업", increase=5))[k]["판정"] == "대상 아님" and J(G.guide(2026, size="중견기업", increase=5.5))[k]["판정"] == "충족"
    assert J(G.guide(2026, size="일반", increase=10))[k]["판정"] == "대상 아님" and J(G.guide(2026, size="중소기업", increase=1))[k]["판정"] == "해당 없음"
    assert J(G.guide(2026, increase=3))[k]["판정"] == "확인 필요" and k not in J(G.guide(2025, size="일반", increase=3, consumer_service=False))
    w = [{"name": "신규", "age": 30}, {"name": "일년", "age": 30, "service_months": 14}, {"name": "단기", "age": 30, "service_months": 8}]
    j = J(G.guide(2026, workers=w))
    assert j["직원 — 신규"]["판정"] == "확인 필요" and j["직원 — 일년"]["판정"] == "상시근로자 — 청년등" and j["직원 — 단기"]["판정"] == "상시근로자 아님"
    q25 = R(G.guide(2025))
    assert "근무개월 수" in q25["인원 계산"]["내용"] and "부칙 제11조제1항" in q25["인원 계산"]["근거"] and "제23조제10항" in q25["상시근로자 범위"]["근거"]
    assert "매월 말" in R(G.guide(2024))["인원 계산"]["내용"] and "근무개월" not in R(G.guide(2024))["인원 계산"]["내용"]
    assert any("부칙 제11조" in x for x in G.guide(2025)["한계"]) and not any("부칙 제11조" in x for x in G.guide(2024)["한계"])


def test_2026_youth_kept_after_34():
    base = {"age": 36, "age_at_contract": 34, "service_months": 20}
    f = lambda size, cd: J(G.guide(2026, size=size, workers=[dict(base, name="A", contract_date=cd)]))["직원 — A"]
    a = f("중소기업", "2025-03-01")
    assert a["판정"] == "상시근로자 — 청년등" and "3년간(2028-03-01" in a["사유"] and "부칙 제11조제2항" in a["사유"]
    assert "2년간(2027-03-01" in f("일반", "2025-03-01")["사유"] and "4년간(2030-02-01" in f("중견기업", "2026-02-01")["사유"]
    assert f(None, "2025-03-01")["판정"].endswith("확인 필요") and f("중소기업", "2024-03-01")["판정"].endswith("청년등 외")
    assert "사전-2026-법규법인-0729" in f("중소기업", "2024-03-01")["사유"]
    # 2025년 최초 공제분에도 청년 유지 규정 적용(부칙 제11조제1항·제2항) — 2025년 계약 3년
    b = J(G.guide(2025, size="중소기업", workers=[{"name": "A", "age": 35, "age_at_contract": 34, "contract_date": "2025-02-01"}]))["직원 — A"]
    assert b["판정"] == "상시근로자 — 청년등" and "3년간(2028-02-01" in b["사유"]
    assert J(G.guide(2024, size="중소기업", workers=[{"name": "A", "age": 35, "age_at_contract": 34, "contract_date": "2024-02-01"}]))["직원 — A"]["판정"].endswith("청년등 외")


def test_age_is_checked_before_other_groups_and_inputs_are_validated():
    # 청년 나이면 다른 표시가 있어도 청년등(북한이탈주민 2024, 경력단절·5·18 부상자 2018)
    j = J(G.guide(2024, workers=[{"name": "A", "age": 25, "defector": True}, {"name": "B", "age": 30, "career_break": True}, {"name": "C", "age": 45, "career_break": True}]))
    assert j["직원 — A"]["판정"] == "상시근로자 — 청년등" and j["직원 — B"]["판정"] == "상시근로자 — 청년등" and j["직원 — C"]["판정"].endswith("확인 필요")
    j = J(G.guide(2018, workers=[{"name": "D", "age": 25, "disabled_kind": "5·18민주화운동부상자"}, {"name": "E", "age": 28, "career_break": True}, {"name": "F", "defector": True}]))
    assert j["직원 — D"]["판정"] == "상시근로자 — 청년등" and j["직원 — E"]["판정"] == "상시근로자 — 청년등" and j["직원 — F"]["판정"].endswith("확인 필요")
    assert J(G.guide(2023, workers=[{"name": "G", "age": 25, "fixed_term": True}]))["직원 — G"]["판정"] == "확인 필요"      # 기간제인데 계약기간을 주지 않음
    bad = G.guide(2026, increase="5", consumer_service="예", workers=[{"age": "30"}, {"monthly_hours": -1}, {"contract_date": "2025.3.1"}, {"age": True}])
    assert "error" in bad and len(bad["문제"]) == 6


def test_foreign_workers_and_related_rulings():
    w = [{"name": "거주", "age": 30, "foreigner": True, "resident": True}, {"name": "비거주", "age": 30, "foreigner": True, "resident": False}, {"name": "미상", "age": 30, "foreigner": True}]
    j = J(G.guide(2024, workers=w))
    assert j["직원 — 거주"]["판정"] == "상시근로자 — 청년등" and j["직원 — 비거주"]["판정"] == "상시근로자 아님" and j["직원 — 미상"]["판정"] == "확인 필요"
    assert "서면-2024-소득-0033" in j["직원 — 비거주"]["사유"] and "서면-2024-소득-0033" in R(G.guide(2020))["상시근로자 범위"]["내용"]
    ids = lambda r: [x["문서번호"] for x in r["관련 해석"]]
    assert "서면-2024-소득-0033" in ids(G.guide(2020)) and "사전-2026-법규법인-0729" not in ids(G.guide(2020)) and "사전-2026-법규법인-0729" in ids(G.guide(2026))


def test_youth_retention_from_leap_day_contract():
    f = lambda size: J(G.guide(2026, size=size, workers=[{"name": "A", "age": 36, "age_at_contract": 34, "contract_date": "2028-02-29", "service_months": 12}]))["직원 — A"]["사유"]
    assert "4년간(2032-02-29" in f("중소기업") and "3년간(2031-02-28" in f("일반")


def test_2025_part_time_standard_and_truncation_from_forms():
    q = R(G.guide(2025))["인원 계산"]
    assert "1개월간의 소정근로시간이 60시간 이상" in q["내용"] and "사람별로 버린 뒤 합함" in q["내용"] and "별지 제10호의9서식(1)" in q["근거"] and "286쪽" in q["근거"]
    assert "제36342호 부칙 제2조제2항" in q["근거"] and "2025 과세연도에는 적용되지 않음" in q["내용"]
    q26 = R(G.guide(2026))["인원 계산"]
    assert "월 평균 근로시간 60시간 이상" in q26["내용"] and "합계에서 버림" in q26["내용"] and "서식(2)" in q26["근거"] and "제36342호" in q26["근거"]
    assert any("소정근로시간 60시간" in x and "종전 규정" in x for x in G.guide(2025)["한계"]) and not any("찾지 못함" in x for x in G.guide(2025)["한계"])
    assert any("별지 제10호의9서식" in x["문서번호"] for x in G.guide(2025)["관련 해석"]) and "국적 무관" in R(G.guide(2025))["상시근로자 범위"]["내용"]
    # 2025년 단시간근로자 판정은 종전 문언(1개월 소정근로시간), 2026년은 월 평균 근로시간
    w = [{"name": "A", "age": 40, "part_time": True, "monthly_hours": 50, "service_months": 24}]
    assert "1개월 소정근로시간 50" in J(G.guide(2025, workers=w))["직원 — A"]["사유"] and "월 평균 근로시간 50" in J(G.guide(2026, workers=w))["직원 — A"]["사유"]
