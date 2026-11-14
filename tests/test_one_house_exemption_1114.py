"""one_house_exemption_guide — 조문·부칙 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본: 소득세법 시행령 2026.10.1. 시행본(대통령령 제36737호 반영) 제152조의3·제154조·제155조·제156조와 같은 시행본에 실린 개정 부칙
(제28293호 2017.9.19. 제2조, 제29242호 2018.10.23. 제2조, 제29523호 2019.2.12. 제1조제3호, 제30395호 2020.2.11., 제32420호 2022.2.15., 제32654호 2022.5.31.,
제33267호 2023.2.28., 제34990호 2024.11.12., 제36737호 2026.9.30.) — 국세법령정보시스템 조회."""
from korean_tax_mcp import one_house_exemption as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["양도일별 변화"]) >= 6 and r["특례 구분"] == ["상속주택", "동거봉양", "혼인", "농어촌주택"]
    assert "error" in G.guide("2015-12-31")
    assert "error" in G.guide("2024/01/01")
    assert "error" in G.guide("2024-01-01", acquisition_date="2024-02-01")
    assert "error" in G.guide("2024-01-01", special="이혼")
    assert "error" in G.guide("2024-01-01", transfer_price=-1)
    assert "error" in G.guide("2024-01-01", residence_periods=[{"from": "2020-01-01", "to": "2019-01-01"}])


def test_holding_two_years_boundary():
    # 초일불산입 — 2020-03-01 취득이면 2022-03-01 양도부터 2년
    assert J(G.guide("2022-03-01", acquisition_date="2020-03-01"))["보유기간 2년"]["판정"] == "충족"
    assert J(G.guide("2022-02-28", acquisition_date="2020-03-01"))["보유기간 2년"]["판정"] == "미충족"


def test_residence_requirement_2017_08_03_acquisition():
    # 제154조제1항(2017.9.19. 개정) — 2017.8.2. 이전 취득은 종전 규정(부칙 제2조제2항제1호)
    before = J(G.guide("2020-01-10", acquisition_date="2017-08-02", adjusted_area_at_acquisition=True))
    after = J(G.guide("2020-01-10", acquisition_date="2017-08-03", adjusted_area_at_acquisition=True))
    assert before["거주기간 2년"]["판정"] == "해당 없음"
    assert after["거주기간 2년"]["판정"] == "확인 필요"
    lived = J(G.guide("2020-01-10", acquisition_date="2017-08-03", adjusted_area_at_acquisition=True, residence_periods=[{"from": "2017-08-03", "to": "2019-08-03"}]))
    short = J(G.guide("2020-01-10", acquisition_date="2017-08-03", adjusted_area_at_acquisition=True, residence_periods=[{"from": "2017-08-03", "to": "2019-08-02"}]))
    assert lived["거주기간 2년"]["판정"] == "충족" and short["거주기간 2년"]["판정"] == "미충족"


def test_residence_transfer_before_2017_09_19_and_contract_exceptions():
    # 부칙 제2조제2항제3호 — 2017.8.3. 이후 취득해 2017.9.19. 전에 양도하면 종전 규정
    assert J(G.guide("2017-09-18", acquisition_date="2017-08-10", adjusted_area_at_acquisition=True))["거주기간 2년"]["판정"] == "해당 없음"
    # 부칙 제2조제2항제2호 — 2017.8.2. 이전 계약금 지급 + 무주택
    r = J(G.guide("2020-01-10", acquisition_date="2017-10-01", adjusted_area_at_acquisition=True, contract_date="2017-08-02", homeless_at_contract=True))
    assert r["거주기간 2년"]["판정"] == "해당 없음"
    r = J(G.guide("2020-01-10", acquisition_date="2017-10-01", adjusted_area_at_acquisition=True, contract_date="2017-08-03", homeless_at_contract=True))
    assert r["거주기간 2년"]["판정"] == "확인 필요"
    # 제154조제1항제5호 — 공고일 이전 계약 + 무주택
    r = J(G.guide("2024-01-10", acquisition_date="2021-10-01", adjusted_area_at_acquisition=True, contract_before_designation=True, homeless_at_contract=True))
    assert r["거주기간 2년"]["판정"] == "해당 없음"
    assert J(G.guide("2024-01-10", acquisition_date="2021-10-01", adjusted_area_at_acquisition=False))["거주기간 2년"]["판정"] == "해당 없음"


def test_residence_multiple_periods_summed():
    p = [{"from": "2018-01-01", "to": "2019-01-01"}, {"from": "2020-01-01", "to": "2021-01-02"}]   # 365 + 367 = 732일
    assert J(G.guide("2022-01-10", acquisition_date="2018-01-01", adjusted_area_at_acquisition=True, residence_periods=p))["거주기간 2년"]["판정"] == "충족"
    p = [{"from": "2018-01-01", "to": "2019-01-01"}, {"from": "2020-01-01", "to": "2020-12-01"}]
    assert J(G.guide("2022-01-10", acquisition_date="2018-01-01", adjusted_area_at_acquisition=True, residence_periods=p))["거주기간 2년"]["판정"] == "미충족"


def test_final_one_house_holding_start_2021_to_2022_05_09():
    # 제154조제5항(2019.2.12. 개정, 2021.1.1. 시행) — 2022.5.31. 개정 부칙: 2022.5.10. 이후 양도분 폐지
    kw = dict(acquisition_date="2015-01-01", other_houses_disposed_date="2021-06-01")
    assert J(G.guide("2022-05-09", **kw))["보유기간 2년"]["판정"] == "미충족"
    assert J(G.guide("2022-05-10", **kw))["보유기간 2년"]["판정"] == "충족"
    assert J(G.guide("2020-12-31", **kw))["보유기간 2년"]["판정"] == "충족"
    assert J(G.guide("2023-06-02", **kw))["보유기간 기산일"]["판정"] == "해당 없음"


def test_temporary_two_house_deadline_by_period():
    f = G.deadline_years
    # 조정대상지역 간이 아니면 3년
    assert f(G.D(2021, 6, 1), G.D(2020, 3, 1), False)[0] == 3
    # 2018.10.23. 전 양도 — 3년
    assert f(G.D(2018, 10, 22), G.D(2018, 9, 20), True)[0] == 3
    # 2018.10.23. 이후 양도: 2018.9.14. 이후 취득 2년, 2018.9.13. 이전 취득·계약 3년
    assert f(G.D(2018, 10, 23), G.D(2018, 9, 14), True)[0] == 2
    assert f(G.D(2018, 10, 23), G.D(2018, 9, 13), True)[0] == 3
    assert f(G.D(2019, 6, 1), G.D(2018, 12, 1), True, new_contract=G.D(2018, 9, 13))[0] == 3   # 기준-2020-법령해석재산-0102
    # 2020.2.11. 이후 양도: 2019.12.17. 이후 취득 1년 + 전입, 2019.12.16. 이전 취득 2년
    assert f(G.D(2020, 2, 11), G.D(2019, 12, 17), True)[:2] == (1, True)
    assert f(G.D(2020, 2, 11), G.D(2019, 12, 16), True)[:2] == (2, False)
    assert f(G.D(2020, 2, 10), G.D(2019, 12, 17), True)[:2] == (2, False)
    # 2022.5.10. 이후 양도 — 제155조제1항제2호 개정
    assert f(G.D(2022, 5, 9), G.D(2021, 6, 1), True)[0] == 1
    assert f(G.D(2022, 5, 10), G.D(2021, 6, 1), True)[:2] == (2, False)
    # 2023.1.12. 이후 양도 — 3년
    assert f(G.D(2023, 1, 11), G.D(2021, 6, 1), True)[0] == 2
    assert f(G.D(2023, 1, 12), G.D(2021, 6, 1), True)[0] == 3
    # 2026.10.1. 이후 양도: 2026.8.4. 이후 취득 2년, 2026.8.3. 이전 취득·계약 3년
    assert f(G.D(2026, 10, 1), G.D(2026, 8, 4), True)[0] == 2
    assert f(G.D(2026, 10, 1), G.D(2026, 8, 3), True)[0] == 3
    assert f(G.D(2026, 10, 1), G.D(2026, 9, 1), True, new_contract=G.D(2026, 8, 3))[0] == 3
    assert f(G.D(2026, 9, 30), G.D(2026, 8, 4), True)[0] == 3


def test_temporary_two_house_judgment():
    base = dict(acquisition_date="2019-01-01", new_house_acquisition_date="2023-03-01", both_adjusted_at_new_acquisition=True)
    assert J(G.guide("2026-03-01", **base))["일시적 2주택 — 처분기한"]["판정"] == "충족"
    assert J(G.guide("2026-03-02", **base))["일시적 2주택 — 처분기한"]["판정"] == "미충족"
    r = J(G.guide("2021-02-01", acquisition_date="2016-01-01", new_house_acquisition_date="2020-03-01", both_adjusted_at_new_acquisition=True))
    assert r["일시적 2주택 — 신규 주택 전입"]["판정"] == "확인 필요"
    r = J(G.guide("2021-02-01", acquisition_date="2016-01-01", new_house_acquisition_date="2020-03-01", both_adjusted_at_new_acquisition=True, moved_in_date="2021-03-02"))
    assert r["일시적 2주택 — 신규 주택 전입"]["판정"] == "미충족"
    # 종전 주택 취득 후 1년이 지나지 않고 신규 취득
    r = J(G.guide("2024-06-01", acquisition_date="2022-01-01", new_house_acquisition_date="2022-12-31", both_adjusted_at_new_acquisition=False))
    assert r["일시적 2주택 — 종전 주택 취득 후 1년"]["판정"] == "미충족"
    r = J(G.guide("2024-06-01", acquisition_date="2022-01-01", new_house_acquisition_date="2023-01-01", both_adjusted_at_new_acquisition=False))
    assert r["일시적 2주택 — 종전 주택 취득 후 1년"]["판정"] == "확인 필요"
    # 조정대상지역 여부를 안 주면 단축 기간이 걸리는 구간은 확인 필요
    assert J(G.guide("2021-02-01", acquisition_date="2016-01-01", new_house_acquisition_date="2020-03-01"))["일시적 2주택 — 처분기한"]["판정"] == "확인 필요"


def test_high_price_threshold_2021_12_08():
    # 제156조(2022.2.15. 개정 부칙 — 2021.12.8. 이후 양도분 12억원)
    assert J(G.guide("2021-12-07", transfer_price=1_000_000_000))["고가주택"]["판정"] == "고가주택"
    assert J(G.guide("2021-12-08", transfer_price=1_000_000_000))["고가주택"]["판정"] == "해당 없음"
    assert J(G.guide("2021-12-07", transfer_price=900_000_000))["고가주택"]["판정"] == "해당 없음"
    assert J(G.guide("2024-01-01", transfer_price=1_200_000_000))["고가주택"]["판정"] == "해당 없음"
    assert J(G.guide("2024-01-01", transfer_price=1_200_000_001))["고가주택"]["판정"] == "고가주택"
    assert "12억원" in {x["요건"]: x for x in G.guide("2021-12-08")["요건"]}["고가주택"]["내용"]


def test_specials():
    # 혼인 — 제155조제5항(2024.11.12. 개정 부칙: 시행 이후 양도분 10년)
    assert J(G.guide("2024-11-12", special="혼인", special_date="2016-01-01"))["혼인 합가 특례"]["판정"] == "충족"
    assert J(G.guide("2026-01-02", special="혼인", special_date="2016-01-01"))["혼인 합가 특례"]["판정"] == "미충족"
    assert J(G.guide("2024-11-11", special="혼인", special_date="2016-01-01"))["혼인 합가 특례"]["판정"] == "확인 필요"
    # 동거봉양 — 제155조제4항 10년
    assert J(G.guide("2025-01-01", special="동거봉양", special_date="2015-01-01"))["동거봉양 합가 특례"]["판정"] == "충족"
    assert J(G.guide("2025-01-02", special="동거봉양", special_date="2015-01-01"))["동거봉양 합가 특례"]["판정"] == "미충족"
    # 상속주택 — 제155조제2항: 일반주택은 상속개시 당시 보유
    assert J(G.guide("2025-01-01", acquisition_date="2019-01-01", special="상속주택", special_date="2020-01-01"))["상속주택 특례"]["판정"] == "충족"
    assert J(G.guide("2025-01-01", acquisition_date="2021-01-01", special="상속주택", special_date="2020-01-01"))["상속주택 특례"]["판정"] == "대상 아님"
    assert J(G.guide("2025-01-01", special="농어촌주택"))["농어촌주택 특례"]["판정"] == "확인 필요"


def test_output_shape():
    r = G.guide("2026-11-14", acquisition_date="2020-01-01")
    assert {"양도일", "요건", "판정", "한계", "관련 해석", "다음 단계", "확인 시행본"} <= set(r)
    assert any("capital_gains_tax" in x for x in r["한계"]) and all("문서번호" in x for x in r["관련 해석"])


def test_final_period_without_acquisition_date_codesolar_1114():
    from korean_tax_mcp import one_house_exemption as H
    r = H.guide("2021-06-01", other_houses_disposed_date="2020-01-10")
    p = {x["항목"]: x for x in r["판정"]}
    assert p["보유기간 2년"]["판정"] == "미충족" and "1주택이 된 날" in p["보유기간 2년"]["사유"]
    r = H.guide("2022-03-01", other_houses_disposed_date="2020-01-10")
    assert {x["항목"]: x for x in r["판정"]}["보유기간 2년"]["판정"] == "충족"
