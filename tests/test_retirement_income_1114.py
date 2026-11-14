"""retirement_income_guide — 조문·부칙 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(국세법령정보시스템 응답):
  소득세법 2019.1.1.(법률 제16104호)·2020.1.1.(제16834호)·2022.1.1.(제18578호)·2023.1.1.(제19196호)·2026.4.21.(제21548호) 시행본 제22조제3항·제4항(계산식 그림), 제48조제1항(표 그림), 제146조제2항
  부칙 제12852호(2014.12.23.) 제25조 표, 제16834호(2019.12.31.) 제1조·제3조·제14조, 제19196호(2022.12.31.) 제1조·제13조
  소득세법 시행령 2016.2.17.(제26982호)·2017.2.3.·2026.10.1.(제36737호) 시행본 제42조의2제4항~제7항, 제43조, 제50조제2항, 제202조의2제1항
  부칙 제26982호 제1조(제42조의2제4항제4호 2018.1.1. 시행), 제30395호(2020.2.11.) 제1조·제5조·제6조·제32조·제33조"""
import datetime as dt

from korean_tax_mcp import retirement_income as G

D = dt.date


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["퇴직일별 변화"]) == 5 and r["퇴직일별 변화"][0].startswith("임원 퇴직소득 한도")
    assert "error" in G.guide("2015-12-31")
    assert "error" in G.guide("2027-01-01")
    assert "error" in G.guide("2024/01/01")
    assert "error" in G.guide("2024-01-01", event="해고")
    assert "error" in G.guide("2024-01-01", service_start_date="2024-02-01")
    assert "error" in G.guide("2024-01-01", retirement_income=-1)
    assert "error" in G.guide("2024-01-01", years_of_service=0)
    assert "error" in G.guide("2024-01-01", deferral="지급 후 연금계좌 입금", paid_date="2024-02-01", pension_deposit_date="2024-01-31")


def test_months_rule_one_month_minimum():
    # 법 제22조제4항제1호 — 개월 수, 1개월 미만은 1개월
    assert G.months(D(2012, 1, 1), D(2019, 12, 31)) == 96
    assert G.months(D(2020, 1, 1), D(2020, 1, 1)) == 1
    assert G.months(D(2020, 1, 15), D(2020, 2, 14)) == 1
    assert G.months(D(2020, 1, 15), D(2020, 2, 15)) == 2


def test_executive_multipliers_boundary_2020_01_01():
    # 법률 제16834호 부칙 제3조(시행 이후 퇴직분)·제14조(시행 전 퇴직분은 종전 규정)
    before = G.executive_multipliers(D(2019, 12, 31), D(2014, 1, 1))
    after = G.executive_multipliers(D(2020, 1, 1), D(2014, 1, 1))
    assert [m["배수"] for m in before] == [3]
    assert [m["배수"] for m in after] == [3, 2]
    with_2011 = G.executive_multipliers(D(2024, 6, 30), D(2010, 1, 1))
    assert [m["배수"] for m in with_2011] == [None, 3, 2]


def test_executive_limit_before_and_after_2020():
    # 2019.12.31. 퇴직: 연평균 3.6억/36×12=1.2억 × 1/10 × 72/12 × 3 = 2억1,600만원
    r = J(G.guide("2019-12-31", executive=True, service_start_date="2014-01-01", salary_3y_before_retirement=360_000_000, retirement_income=300_000_000))
    e = r["임원 퇴직소득 한도"]
    assert e["한도액"] == 216_000_000 and e["근로소득으로 보는 금액"] == 84_000_000 and e["판정"] == "한도 초과"
    # 2020.1.1. 퇴직: 3배 구간 2억1,600만원 + 2배 구간 (1,000만원/1개월×12=1.2억 × 1/10 × 1/12 × 2 = 200만원)
    r = J(G.guide("2020-01-01", executive=True, service_start_date="2014-01-01", salary_3y_to_2019=360_000_000, salary_3y_before_retirement=10_000_000,
                  retirement_income=200_000_000))
    e = r["임원 퇴직소득 한도"]
    assert e["한도액"] == 218_000_000 and e["근로소득으로 보는 금액"] == 0 and e["판정"] == "한도 이내"


def test_executive_pre2012_exclusion():
    # 시행령 제42조의2제6항 — 5.4억 × 12/108 = 6,000만원을 빼고 한도 적용. 한도 1.2억/10 × 96/12 × 3 = 2.88억
    r = J(G.guide("2019-12-31", executive=True, service_start_date="2011-01-01", salary_3y_before_retirement=360_000_000, retirement_income=540_000_000))
    e = r["임원 퇴직소득 한도"]
    assert e["2011.12.31. 퇴직 가정 금액"] == 60_000_000 and e["한도액"] == 288_000_000 and e["근로소득으로 보는 금액"] == 192_000_000
    r = J(G.guide("2019-12-31", executive=True, service_start_date="2011-01-01", salary_3y_before_retirement=360_000_000, retirement_income=540_000_000,
                  pre2012_retirement_income=100_000_000))
    assert r["임원 퇴직소득 한도"]["근로소득으로 보는 금액"] == 152_000_000


def test_executive_missing_facts():
    assert J(G.guide("2024-06-30", executive=True))["임원 퇴직소득 한도"]["판정"] == "확인 필요"
    e = J(G.guide("2024-06-30", executive=True, service_start_date="2015-01-01", salary_3y_before_retirement=300_000_000))["임원 퇴직소득 한도"]
    assert e["판정"] == "확인 필요" and "salary_3y_to_2019" in e["사유"]
    # 2020.1.1. 이후 입사 임원은 2배 구간만
    e = J(G.guide("2024-12-31", executive=True, service_start_date="2022-01-01", salary_3y_before_retirement=360_000_000))["임원 퇴직소득 한도"]
    assert [m["배수"] for m in e["기간별 배수"]] == [2] and e["한도액"] == 72_000_000   # 1.2억/10 × 36/12 × 2


def test_service_deduction_boundary_2023_01_01():
    # 법 제48조제1항제1호, 법률 제19196호 부칙 제13조(시행 전 퇴직은 종전 규정)
    assert G.service_deduction(10, D(2022, 12, 31)) == 4_000_000
    assert G.service_deduction(10, D(2023, 1, 1)) == 15_000_000
    assert G.service_deduction(3, D(2022, 12, 31)) == 900_000 and G.service_deduction(3, D(2023, 1, 1)) == 3_000_000
    assert G.service_deduction(25, D(2022, 12, 31)) == 18_000_000 and G.service_deduction(25, D(2023, 1, 1)) == 55_000_000
    assert J(G.guide("2022-12-31", years_of_service=10))["근속연수공제"]["판정"] == "종전표"
    assert J(G.guide("2023-01-01", years_of_service=10))["근속연수공제"]["공제액"] == 15_000_000


def test_conversion_deduction_table():
    # 법 제48조제1항제2호 표의 구간 경계
    assert G.conversion_deduction(8_000_000) == 8_000_000
    assert G.conversion_deduction(70_000_000) == 45_200_000
    assert G.conversion_deduction(100_000_000) == 61_700_000
    assert G.conversion_deduction(300_000_000) == 151_700_000
    assert G.conversion_deduction(400_000_000) == 186_700_000


def test_blend_2016_2019_and_none_after():
    # 법률 제12852호 부칙 제25조 표
    def calc(d):
        return next(x for x in G.guide(d)["요건"] if x["항목"] == "세액계산 개요")["내용"]
    assert "80%" in calc("2016-12-31") and "20%" in calc("2016-12-31")
    assert "종전 규정 산출세액 × 20%" in calc("2019-12-31")
    assert "종전 규정" not in calc("2020-01-01")


def test_regular_conversion_boundary_2020_02_11():
    # 시행령 제43조제1항제4호, 대통령령 제30395호 부칙 제6조·제33조
    assert J(G.guide("2020-02-10", event="비정규직이 정규직", benefit_paid=False))["퇴직판정 특례"]["판정"] == "해당 없음"
    assert J(G.guide("2020-02-11", event="비정규직이 정규직", benefit_paid=False))["퇴직판정 특례"]["판정"] == "퇴직으로 보지 않을 수 있음"
    assert J(G.guide("2024-03-01", event="종업원이 임원", benefit_paid=True))["퇴직판정 특례"]["판정"] == "퇴직소득"
    assert J(G.guide("2024-03-01", event="상근임원이 비상근임원"))["퇴직판정 특례"]["판정"] == "확인 필요"


def test_interim_settlement():
    assert J(G.guide("2024-03-01", event="중간정산", interim_reason="퇴직연금제도 폐지"))["중간정산"]["판정"] == "퇴직소득"
    assert J(G.guide("2024-03-01", event="중간정산", interim_reason="그 밖의 사유"))["중간정산"]["판정"] == "퇴직으로 보지 않음"
    assert J(G.guide("2024-03-01", event="중간정산"))["중간정산"]["판정"] == "확인 필요"


def test_deferral_60_days():
    # 법 제146조제2항제2호 — 지급받은 날부터 60일 이내
    ok = J(G.guide("2024-06-30", deferral="지급 후 연금계좌 입금", paid_date="2024-07-10", pension_deposit_date="2024-09-08"))
    late = J(G.guide("2024-06-30", deferral="지급 후 연금계좌 입금", paid_date="2024-07-10", pension_deposit_date="2024-09-09"))
    assert ok["과세이연"]["판정"] == "대상" and late["과세이연"]["판정"] == "대상 아님"
    assert J(G.guide("2024-06-30", deferral="연금계좌로 지급"))["과세이연"]["판정"] == "대상"


def test_scope_religious_worker_2018():
    # 시행령 제42조의2제4항제4호 — 대통령령 제26982호 부칙 제1조 단서로 2018.1.1. 시행
    def scope(d):
        return next(x for x in G.guide(d)["요건"] if x["항목"] == "퇴직소득 범위")["내용"]
    assert "2018.1.1.부터" in scope("2017-12-31")
    assert "2018.1.1. 시행)" in scope("2018-01-01")


def test_server_tool_registered():
    from korean_tax_mcp import server
    doc = server.retirement_income_guide.__doc__ if hasattr(server.retirement_income_guide, "__doc__") else ""
    assert "언제:" in doc and "입력:" in doc and "①" not in doc
