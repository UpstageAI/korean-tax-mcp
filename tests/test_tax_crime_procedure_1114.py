"""0.14.0 tax_crime_procedure_guide — 조세범 처벌절차법·시행령 연혁본 대조(국세법령정보시스템, 2026-11-14). Claude 작성. 외부 호출 없음."""
from korean_tax_mcp import tax_crime_procedure as P


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_errors():
    assert len(P.guide()["날짜에 따라 달라지는 것"]) == 6   # 2026.10.2. 법률 제21857호 추가
    assert "error" in P.guide("2015-12-31") and "error" in P.guide("2024-13-01") and "error" in P.guide("2024-01-01", offense_article=17)


def test_rules_by_date():
    r = P.guide("2016-06-01")["날짜별 규정"]
    assert "20명" in r["위원회 정원"] and r["위촉위원"] == "8명 이내" and "제14조" in r["범칙행위 범위"]
    assert "15명" in P.guide("2016-01-10")["날짜별 규정"]["위원회 정원"]
    r = P.guide("2023-02-01")["날짜별 규정"]
    assert "5명" in r["회의 구성(제3조 사건 등)"] and "정지" in r["통고처분과 공소시효"] and "제16조" in r["범칙행위 범위"]
    assert "6명" in P.guide("2023-03-01")["날짜별 규정"]["회의 구성(제3조 사건 등)"]


def test_scope_and_committee():
    assert J(P.guide("2018-06-01", offense_article=15))["조세범칙행위 범위"]["판정"] == "대상 아님"
    assert J(P.guide("2019-06-01", offense_article=15))["조세범칙행위 범위"]["판정"] == "대상"
    assert J(P.guide("2024-06-01", offense_article=3))["선정 심의"]["판정"] == "위원회 심의 필요"
    assert J(P.guide("2024-06-01", offense_article=10))["선정 심의"]["판정"] == "위원회 선정 심의 대상 아님"


def test_warrantless_2023():
    assert J(P.guide("2024-06-01", offense_article=8, flight_or_destroy_risk=True))["영장 없는 압수·수색(2호)"]["판정"].startswith("불가")
    assert J(P.guide("2024-06-01", offense_article=5, flight_or_destroy_risk=True))["영장 없는 압수·수색(2호)"]["판정"] == "가능"
    assert J(P.guide("2024-06-01", offense_article=3, evasion_proviso=True, flight_or_destroy_risk=True))["영장 없는 압수·수색(2호)"]["판정"] == "가능"
    assert "영장 없는 압수·수색(2호)" not in J(P.guide("2022-06-01", offense_article=8, flight_or_destroy_risk=True))


def test_mandatory_threshold():
    j = J(P.guide("2024-06-01", annual_reported_revenue=12_000_000_000, annual_suspected_evasion=1_900_000_000))
    assert j["연간 조세포탈 혐의금액 기준"]["판정"] == "해당"              # 15.8% ≥ 15%
    j = J(P.guide("2024-06-01", annual_reported_revenue=30_000_000_000, annual_suspected_evasion=1_900_000_000))
    assert j["연간 조세포탈 혐의금액 기준"]["판정"] == "해당 아님" and j["의무 조세범칙조사"]["판정"].startswith("금액 기준으로는")
    j = J(P.guide("2024-06-01", annual_reported_revenue=30_000_000_000, annual_suspected_evasion=600_000_000, filed_return=False))
    assert j["신고수입금액 간주"]["판정"] == "20억원 미만으로 봄" and j["연간 조세포탈 혐의금액 기준"]["판정"] == "해당"
    assert J(P.guide("2024-06-01", expected_evaded_tax=500_000_000))["의무 조세범칙조사"]["판정"] == "대상"


def test_disposition_deadlines():
    j = J(P.guide("2024-06-01", committee_resolution_date="2024-05-02", notice_date="2024-05-20"))
    assert j["통고 기한"]["판정"] == "2024-05-12까지" and j["통고 기한 경과"]["판정"] == "확인 필요"
    j = J(P.guide("2024-06-01", notice_served_date="2024-05-01", paid_date="2024-05-20"))
    assert j["통고 불이행 고발"]["판정"] == "고발하지 않음" and "고발 전 이행" in j["통고 불이행 고발"]["사유"]
    assert J(P.guide("2024-06-01", notice_served_date="2024-05-01", accused_date="2024-05-25"))["통고 불이행 고발"]["판정"] == "고발 의무"
    assert J(P.guide("2024-06-01", prison_likely=True))["즉시 고발"]["판정"].startswith("통고처분을 거치지 않고")


def test_limitation_suspension():
    j = J(P.guide("2023-06-01", notice_date="2023-01-17", accused_date="2023-03-01"))
    assert j["공소시효"]["판정"] == "정지" and "43일" in j["공소시효"]["사유"]
    assert J(P.guide("2023-06-01", notice_date="2023-01-16"))["공소시효"]["판정"] == "중단"
    j = J(P.guide("2023-06-01", notice_date="2023-01-16"))
    assert "납부 방법" not in j and j["통고처분 불복"]["근거"] == "국세기본법 제55조①1호"
