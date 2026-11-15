"""permanent_establishment_guide — 조문 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조 시행본(법제처 DRF 연혁본): 법인세법 제94조 2016(20160125)·2018(20181101)·2019(20190101)·2020(20200101)~2026(20260701) 연말 시행본,
소득세법 제120조 2016(20160901)·2018(20180921)·2019(20190101)·2020(20200828)~2026(20260701), 법인세법 시행령 제133조 2016(20161129)·2026(20261001),
법인세법 제94조의2 2022(20220218)~2026 시행본."""
from korean_tax_mcp import permanent_establishment as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_errors():
    r = G.guide()
    assert len(r["연도별로 달라지는 것"]) == 5 and "세분화 방지" in r["요소"]
    assert "error" in G.guide(2015) and "error" in G.guide(2027) and "error" in G.guide(2024, taxpayer="법인")
    assert "error" in G.guide(2024, place_types=["공장"]) and "error" in G.guide(2024, service_months_in_12=13)


def test_construction_boundary():
    assert J(G.guide(2024, construction_months=6))["건설현장"]["판정"] == "해당 없음"
    r = G.guide(2024, construction_months=6.5)
    assert J(r)["건설현장"]["판정"] == "국내사업장 있음" and r["결론"].startswith("국내법상 국내사업장 있음")
    assert J(G.guide(2024, place_types=["건설현장"]))["건설현장"]["판정"] == "확인 필요"


def test_service_pe():
    assert J(G.guide(2023, service_months_in_12=6.1))["용역 PE"]["판정"] == "국내사업장 있음"
    assert J(G.guide(2023, service_months_in_12=6, similar_service_years=2))["용역 PE"]["판정"] == "국내사업장 있음"
    assert J(G.guide(2023, service_months_in_12=6, similar_service_years=1.9))["용역 PE"]["판정"] == "해당 없음"
    assert J(G.guide(2023, service_months_in_12=6))["용역 PE"]["판정"] == "확인 필요"


def test_preparatory_exclusion_by_year():
    kw = dict(fixed_place=True, specific_activities=["판매 목적 아닌 저장·보관"])
    # 2018 시행본까지: 조건 없이 제외
    assert J(G.guide(2018, **kw))["고정된 장소"]["판정"] == "해당 없음"
    # 2019 시행본부터: 예비적·보조적일 때만 제외
    assert J(G.guide(2019, **kw))["고정된 장소"]["판정"] == "확인 필요"
    assert J(G.guide(2019, preparatory_or_auxiliary=False, **kw))["고정된 장소"]["판정"] == "국내사업장 있음"
    r = J(G.guide(2019, preparatory_or_auxiliary=True, **kw))["고정된 장소"]
    assert r["판정"] == "해당 없음" and "예비적이며 보조적" in r["사유"]
    assert "예비적 또는 보조적" in J(G.guide(2020, preparatory_or_auxiliary=True, **kw))["고정된 장소"]["사유"]


def test_anti_fragmentation_from_2019():
    kw = dict(fixed_place=True, specific_activities=["광고·선전·정보·시장조사"], preparatory_or_auxiliary=True, related_pe_complementary=True)
    assert J(G.guide(2019, **kw))["고정된 장소"]["판정"] == "국내사업장 있음"
    assert J(G.guide(2018, **kw))["고정된 장소"]["판정"] == "해당 없음"
    assert "없음" in G.guide(2018)["요소"]["세분화 방지"]


def test_dependent_agent_by_year():
    assert J(G.guide(2018, agent_principal_role=True))["종속대리인(중요한 역할)"]["판정"] == "확인 필요"
    r = J(G.guide(2019, agent_principal_role=True))["종속대리인(중요한 역할)"]
    assert r["판정"] == "국내사업장 있음" and r["근거"].endswith("제3항제2호")
    assert J(G.guide(2016, agent_contract_authority=True))["종속대리인"]["판정"] == "국내사업장 있음"
    r = G.guide(2024, fixed_place=False, agent_contract_authority=False, agent_principal_role=False)
    assert r["결론"].startswith("국내법상 국내사업장 없음")


def test_decree_agents_and_individual():
    # 시행령 제133조·제180조 연도별 문언과 판정은 tests/test_unverified_wp6_law_1115.py(2026-11-15 원문 대조)
    assert "주로 특정 외국법인만" in G.guide(2018)["요소"]["대통령령으로 정하는 자"]
    assert "전적으로 또는 거의 전적으로" in G.guide(2026)["요소"]["대통령령으로 정하는 자"]
    r = G.guide(2024, taxpayer="비거주자", agent_types=["자산 상시 보관·배달"])
    assert J(r)["대통령령으로 정하는 자"]["판정"] == "국내사업장 있음" and "소득세법 제120조" in r["요소"]["고정된 장소"]


def test_liaison_office_and_treaty():
    assert "연락사무소" not in G.guide(2021)["요소"] and "연락사무소" in G.guide(2022)["요소"]
    r = G.guide(2024, treaty_country="미국", construction_months=8)
    assert "tax_treaty(country='미국', keyword='고정사업장')" in r["다음 단계"]
