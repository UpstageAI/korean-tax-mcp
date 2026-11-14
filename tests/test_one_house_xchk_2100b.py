"""one_house_exemption_guide — 2016~2024 시행본 원문 대조 후 고친 판정(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(법제처 DRF 연혁본):
- 소득세법 시행령 2017.9.19. 시행본(대통령령 제28293호) 제154조제1항제4호·제5호, 제155조제4항·제5항
- 2018.2.13. 시행본(제28637호) 부칙 제2조제2항, 2018.10.23. 시행본 제155조제4항(10년)
- 2019.2.12. 시행본(제29523호) 제154조제1항제4호 단서(연 증가율 5%)와 부칙 제6조, 2019.9.16. 시행본 제154조
- 2020.2.11. 시행본(제30395호) 부칙 제38조제2항(2019.12.16. 이전 등록 신청분 종전 규정)
- 2022.5.31. 시행본 제155조제1항제2호(2년, 전입요건 문언 없음), 2024.9.15. 시행본 제155조제5항(혼인 5년)
정답은 위 문언에서 손으로 셈한 값(초일불산입 — n년이 되는 날까지 양도하면 충족)."""
from korean_tax_mcp import one_house_exemption as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


BASE = dict(acquisition_date="2018-01-10", adjusted_area_at_acquisition=True, residence_periods=[])


def test_rental_registration_exempts_residence_154_1_4():
    # 양도 2020-02-10(삭제 전날) — 구 제154조제1항제4호, 등록 2018-03-01, 임대의무 준수
    r = J(G.guide("2020-02-10", rental_registered_date="2018-03-01", rental_rule_kept=True, **BASE))
    assert r["거주기간 2년"]["판정"] == "해당 없음" and "제154조제1항제4호" in r["거주기간 2년"]["근거"]
    # 양도 2020-03-01 — 삭제 뒤지만 등록 신청 ≤ 2019-12-16 → 종전 규정(제30395호 부칙 제38조제2항)
    r = J(G.guide("2020-03-01", rental_registered_date="2018-03-01", rental_rule_kept=True, **BASE))
    assert r["거주기간 2년"]["판정"] == "해당 없음" and "제38조제2항" in r["거주기간 2년"]["근거"]
    # 등록 신청 2019-12-16(경계) → 종전 규정 / 2019-12-17 → 거주 2년 필요, 거주 0일이라 미충족
    assert J(G.guide("2020-03-01", rental_registered_date="2019-12-16", rental_rule_kept=True, **BASE))["거주기간 2년"]["판정"] == "해당 없음"
    r = J(G.guide("2020-03-01", rental_registered_date="2019-12-17", rental_rule_kept=True, **BASE))
    assert r["거주기간 2년"]["판정"] == "미충족" and "제38조제2항" in r["거주기간 2년"]["사유"]
    # 단서 위반(임대의무기간 중 양도·5% 초과) → 거주요건 적용
    assert J(G.guide("2020-02-10", rental_registered_date="2018-03-01", rental_rule_kept=False, **BASE))["거주기간 2년"]["판정"] == "미충족"
    # 준수 여부를 안 주면 확인 필요, 2019.2.12. 이후 양도면 5% 단서 안내
    r = J(G.guide("2019-03-01", rental_registered_date="2018-03-01", **BASE))
    assert r["거주기간 2년"]["판정"] == "확인 필요" and "5%" in r["거주기간 2년"]["사유"]
    r = J(G.guide("2019-02-11", rental_registered_date="2018-03-01", **BASE))
    assert "5%" not in r["거주기간 2년"]["사유"]
    # 양도일 뒤 등록은 해당 없음 → 거주 0일 미충족
    assert J(G.guide("2019-03-01", rental_registered_date="2019-04-01", rental_rule_kept=True, **BASE))["거주기간 2년"]["판정"] == "미충족"


def test_residence_empty_list_vs_missing():
    # 빈 목록 = 거주 0일(미충족), 생략 = 확인 필요
    assert J(G.guide("2020-03-01", **BASE))["거주기간 2년"]["판정"] == "미충족"
    b = dict(BASE)
    b.pop("residence_periods")
    assert J(G.guide("2020-03-01", **b))["거주기간 2년"]["판정"] == "확인 필요"


def test_parent_cohabitation_period_155_4():
    # 2018.2.12. 이전 양도분 5년(2017.9.19. 시행본)
    assert J(G.guide("2017-03-01", special="동거봉양", special_date="2012-03-01"))["동거봉양 합가 특례"]["판정"] == "충족"   # 5년이 되는 날
    assert J(G.guide("2017-03-02", special="동거봉양", special_date="2012-03-01"))["동거봉양 합가 특례"]["판정"] == "미충족"
    assert J(G.guide("2018-02-12", special="동거봉양", special_date="2010-05-01"))["동거봉양 합가 특례"]["판정"] == "미충족"
    # 2018.2.13. 이후 양도분 10년(제28637호 부칙 제2조제2항) — 2020-05-01까지
    r = J(G.guide("2018-02-13", special="동거봉양", special_date="2010-05-01"))["동거봉양 합가 특례"]
    assert r["판정"] == "충족" and "2020-05-01" in r["사유"]
    assert J(G.guide("2019-02-12", special="동거봉양", special_date="2009-02-12"))["동거봉양 합가 특례"]["판정"] == "충족"
    assert J(G.guide("2019-02-13", special="동거봉양", special_date="2009-02-12"))["동거봉양 합가 특례"]["판정"] == "미충족"


def test_marriage_period_155_5():
    # 2024.11.11. 이전 양도분 5년(2024.9.15. 시행본), 2024.11.12. 이후 10년
    assert J(G.guide("2024-11-11", special="혼인", special_date="2019-11-11"))["혼인 합가 특례"]["판정"] == "충족"
    assert J(G.guide("2024-11-11", special="혼인", special_date="2019-06-01"))["혼인 합가 특례"]["판정"] == "미충족"
    assert J(G.guide("2024-11-12", special="혼인", special_date="2019-06-01"))["혼인 합가 특례"]["판정"] == "충족"
    assert J(G.guide("2017-01-01", special="혼인", special_date="2012-01-01"))["혼인 합가 특례"]["판정"] == "충족"


def test_temporary_2022_no_unverified_mark():
    r = J(G.guide("2022-06-01", acquisition_date="2016-01-01", new_house_acquisition_date="2021-01-01", both_adjusted_at_new_acquisition=True))
    t = r["일시적 2주택 — 처분기한"]
    assert t["처분기한(년)"] == 2 and "미확인" not in t["근거"] and "전입 요건 문언 없음" in t["근거"]
    assert t["판정"] == "충족"   # 2023-01-01까지
    assert not any(x["항목"] == "일시적 2주택 — 신규 주택 전입" for x in r.values())


def test_limits_cleaned():
    r = G.guide("2020-03-01", acquisition_date="2018-01-10", adjusted_area_at_acquisition=True, residence_periods=[], contract_before_designation=True, homeless_at_contract=True)
    assert "신설 시기 미확인" not in J(r)["거주기간 2년"]["근거"] and "2017.9.19." in J(r)["거주기간 2년"]["근거"]
    lim = " ".join(r["한계"])
    assert "동거봉양" not in lim and "혼인 합가 기간" not in lim and "제154조제5항의 정확한 문언" not in lim
    assert "error" in G.guide("2020-03-01", rental_rule_kept="yes")
    assert "error" in G.guide("2020-03-01", rental_registered_date="2019/12/16")
