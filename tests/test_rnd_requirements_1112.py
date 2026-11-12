"""0.12.24 rnd_credit_requirements_guide — 조문 문언 대조 테스트(2026-11-12, Claude 작성). 외부 호출 없음.
근거: 조세특례제한법 시행령 별표 6, 시행규칙 제7조①③, 시행령 제9조·제8조·제1조의2(2016~2025 각 연말·2026.11.12. 시행본)."""
from korean_tax_mcp import rnd_requirements as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_without_year():
    r = G.guide()
    assert len(r["연도별 변화"]) >= 6 and "연구전담요원" in r["직원 구분"] and "그 밖의 기업" in r["위탁 기관 구분"]


def test_excluded_activities_by_year():
    n = lambda y: len(G.excluded_activities(y)[0])
    assert [n(y) for y in (2016, 2018, 2019, 2020, 2024, 2025, 2026)] == [7, 7, 8, 9, 9, 10, 10]
    assert "제8조제2항" in G.excluded_activities(2018)[1] and "제1조의2" in G.excluded_activities(2020)[1]
    assert any("동일성을 유지" in a for a in G.excluded_activities(2025)[0]) and not any("동일성을 유지" in a for a in G.excluded_activities(2024)[0])
    r = G.guide(2025, activities=["기존 제품 디자인 개선", "신규 유효성분 안정화 기술 개발"])
    assert J(r)["활동 — 기존 제품 디자인 개선"]["판정"] == "확인 필요" and J(r)["활동 — 신규 유효성분 안정화 기술 개발"]["판정"].startswith("제외 활동 문언에")
    assert J(G.guide(2024, activities=["기존 제품 디자인 개선"]))["활동 — 기존 제품 디자인 개선"]["판정"].startswith("제외 활동 문언에")      # 10호는 2025년부터


def test_staff_rules():
    staff = [{"name": "대표", "role": "연구전담요원", "shareholder_executive": True}, {"name": "연구원", "role": "연구전담요원"}, {"name": "보조", "role": "연구보조원"},
             {"name": "총무", "role": "행정사무"}, {"name": "지원", "role": "연구지원"}]
    r = J(G.guide(2025, lab=True, staff=staff))
    assert r["인건비 — 대표"]["판정"] == "대상 아님" and r["인건비 — 연구원"]["판정"] == "대상" and r["인건비 — 보조"]["판정"] == "대상"
    assert r["인건비 — 총무"]["판정"] == "대상 아님" and r["인건비 — 지원"]["판정"] == "확인 필요"
    # 2020년까지는 연구요원과 직접 지원 인력
    r = J(G.guide(2020, lab=True, staff=staff))
    assert r["인건비 — 지원"]["판정"] == "대상" and r["인건비 — 대표"]["판정"] == "대상 아님"
    # 전담부서등이 없으면 인건비는 대상이 아님
    assert J(G.guide(2025, lab=False, staff=[{"name": "연구원", "role": "연구전담요원"}]))["인건비 — 연구원"]["판정"] == "대상 아님"


def test_cost_items_by_year():
    c = lambda y, item, **k: J(G.guide(y, costs=[item], **k))[f"비용 — {item}"]["판정"]
    assert [c(y, "사회보험료") for y in (2023, 2024, 2025)] == ["대상 아님", "대상", "대상"]
    assert [c(y, "클라우드 이용료") for y in (2024, 2025)] == ["대상 아님", "대상"]
    assert [c(y, "인공지능 학습용 데이터") for y in (2025, 2026)] == ["대상 아님", "대상"]
    assert [c(y, "연구용 소프트웨어") for y in (2019, 2022, 2025)] == ["대상 아님", "조건부", "대상"]
    assert [c(y, "특허 조사·분석비") for y in (2020, 2021)] == ["대상 아님", "대상"] and c(2021, "특허 조사·분석비", sme=False) == "대상 아님"
    assert c(2025, "퇴직급여") == "대상 아님" and c(2019, "성과급") == "대상 아님" and c(2020, "성과급") == "조건부"
    assert c(2025, "직무발명 보상금") == "대상" and c(2025, "연구용 재료·시약", lab=False) == "대상 아님"
    assert "4대" in J(G.guide(2024, costs=["사회보험료"]))["비용 — 사회보험료"]["사유"] and "5대" in J(G.guide(2025, costs=["사회보험료"]))["비용 — 사회보험료"]["사유"]


def test_outsourcing():
    r = J(G.guide(2025, outsourced_to=[{"name": "대학 연구실", "org": "대학"}, {"name": "개발사", "org": "다른 기업의 전담부서등", "performed_by_lab": True},
                                       {"name": "개발사 하청", "org": "다른 기업의 전담부서등", "performed_by_lab": False}, {"name": "미확인", "org": "다른 기업의 전담부서등"},
                                       {"name": "생산 위탁", "org": "그 밖의 기업"}, {"name": "ERP 개발", "org": "연구산업 영위 기업", "system_development": True}]))
    assert r["위탁 — 대학 연구실"]["판정"] == "대상" and r["위탁 — 개발사"]["판정"] == "대상" and r["위탁 — 개발사 하청"]["판정"] == "대상 아님"
    assert r["위탁 — 미확인"]["판정"] == "확인 필요" and r["위탁 — 생산 위탁"]["판정"] == "대상 아님" and r["위탁 — ERP 개발"]["판정"] == "대상 아님"


def test_requirements_text_by_year():
    req = lambda y: {x["요건"]: x for x in G.guide(y)["요건"]}
    assert "산업디자인전문회사" in req(2020)["전담부서등(자체연구개발 인건비·재료비 등)"]["내용"] and "산업디자인전문회사" not in req(2019)["전담부서등(자체연구개발 인건비·재료비 등)"]["내용"]
    assert "연구전담요원" in req(2021)["인건비 대상자"]["내용"] and "직접적으로 지원" in req(2020)["인건비 대상자"]["내용"]
    assert "연구노트" in req(2020)["증거서류"]["내용"] and "연구노트" not in req(2019)["증거서류"]["내용"]
    assert "제8조제1항" in req(2019)["정부 출연금 등으로 쓴 금액 제외"]["근거"] and "제9조제1항" in req(2020)["정부 출연금 등으로 쓴 금액 제외"]["근거"]
    assert "인력개발비" in req(2019)["정부 출연금 등으로 쓴 금액 제외"]["내용"] and "인력개발비" not in req(2018)["정부 출연금 등으로 쓴 금액 제외"]["내용"]


def test_grant_and_lab_flags():
    r = J(G.guide(2025, lab=False, grant_funded=True))
    assert r["전담부서등"]["판정"] == "미충족" and "위탁" in r["전담부서등"]["사유"] and r["정부 출연금 등"]["판정"] == "제외할 금액 있음"


def test_input_errors():
    assert "error" in G.guide(2015) and "error" in G.guide(2025, staff=[{"role": "사장"}])
    assert "error" in G.guide(2025, costs=["접대비"]) and "error" in G.guide(2025, outsourced_to=[{"org": "친구"}])
