"""0.13.0 tax_crime_guide — 조문 문언 대조 테스트(2026-11-13, Claude 작성). 외부 호출 없음.
근거: 조세범 처벌법 제3조~제22조(2015.12.29.·2019.1.1.·2021.1.1. 시행본), 2018.12.31. 법률 제16108호 부칙,
특정범죄 가중처벌 등에 관한 법률 제8조·제8조의2·제16조."""
from korean_tax_mcp import tax_crime as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert len(r["범칙행위"]) == 17 and len(r["행위일에 따라 달라지는 것"]) == 5
    assert "error" in G.guide(offense="조세포탈") and "error" in G.guide("2015-12-31", "조세포탈") and "error" in G.guide("2024-13-01", "조세포탈")
    assert "error" in G.guide("2024-05-31", "탈세") and "error" in G.guide("2024-05-31", "조세포탈", evaded_tax=-1)
    assert "error" in G.guide("2024-05-31", "세금계산서 미발급·거짓기재", document="영수증")


def test_evasion_thresholds():
    # 제3조① 단서: 3억 이상이면서 30% 이상(1호) 또는 5억 이상(2호)
    assert J(G.guide("2024-03-31", "조세포탈", evaded_tax=299_999_999))["제3조제1항 단서"]["판정"] == "해당 아님"
    assert J(G.guide("2024-03-31", "조세포탈", evaded_tax=300_000_000))["제3조제1항 단서"]["판정"] == "확인 필요"
    assert J(G.guide("2024-03-31", "조세포탈", evaded_tax=300_000_000, tax_due=1_000_000_000))["제3조제1항 단서"]["판정"] == "해당"            # 정확히 30%
    assert J(G.guide("2024-03-31", "조세포탈", evaded_tax=300_000_000, tax_due=1_000_000_001))["제3조제1항 단서"]["판정"] == "해당 아님"
    r = J(G.guide("2024-03-31", "조세포탈", evaded_tax=500_000_000, tax_due=9_000_000_000))["제3조제1항 단서"]
    assert r["판정"] == "해당" and "제2호" in r["근거"] and "3배" in r["법정형"]


def test_evasion_aggravated_and_common():
    r = G.guide("2024-03-31", "조세포탈", evaded_tax=600_000_000, annual_evaded_tax=600_000_000)
    a = J(r)["특정범죄 가중처벌"]
    assert a["판정"] == "해당" and "3년 이상" in a["법정형"] and "제16조" in a["고발"]
    assert "무기" in J(G.guide("2024-03-31", "조세포탈", annual_evaded_tax=1_000_000_000))["특정범죄 가중처벌"]["법정형"]
    assert J(G.guide("2024-03-31", "조세포탈", annual_evaded_tax=499_999_999))["특정범죄 가중처벌"]["판정"] == "해당 아님"
    assert J(G.guide("2024-03-31", "조세포탈"))["특정범죄 가중처벌"]["판정"] == "확인 필요"
    c = {x["항목"]: x for x in r["공통 규정"]}
    assert "7년" in c["공소시효"]["내용"] and "10년" in c["공소시효"]["내용"] and "제21조" in c["고발"]["근거"] and "벌금 경합" in c
    assert len(r["부정한 행위"]["유형"]) == 7 and "제3조제5항" in r["기수 시기"]["근거"]
    assert "article='제3조'" in r["다음 단계"][0] and "as_of='20240331'" in r["다음 단계"][0]


def test_invoice_by_act_date():
    # 제10조①②: 2018년까지 세금계산서만, 2019.1.1.부터 계산서 추가. 제2항 벌금 기준 매입금액 → 공급가액
    old = G.guide("2018-12-31", "세금계산서 미발급·거짓기재", document="계산서")
    assert J(old)["계산서"]["판정"] == "대상 아님" and "계산서" not in old["구성요건"].replace("세금계산서", "")
    new = G.guide("2019-01-01", "세금계산서 미발급·거짓기재", document="계산서")
    assert J(new)["계산서"]["판정"] == "대상" and new["적용 시행본"].startswith("2019.1.1.")
    assert "매입금액" in G.guide("2018-06-30", "세금계산서 미수취·거짓수취")["법정형"] and "공급가액" in G.guide("2019-06-30", "세금계산서 미수취·거짓수취")["법정형"]
    assert J(G.guide("2018-12-31", "세금계산서 미발급·거짓기재", document="세금계산서"))["세금계산서"]["판정"] == "대상"


def test_fictitious_invoice_aggravated():
    f = lambda amt, fp=True: J(G.guide("2023-07-25", "실물거래 없는 세금계산서", supply_amount_total=amt, for_profit=fp))["특정범죄 가중처벌"]
    assert f(2_999_999_999)["판정"] == "해당 아님" and "1년 이상" in f(3_000_000_000)["법정형"] and "3년 이상" in f(5_000_000_000)["법정형"]
    assert f(9_000_000_000, False)["판정"] == "해당 아님"
    r = G.guide("2023-07-25", "실물거래 없는 세금계산서")
    assert J(r)["특정범죄 가중처벌"]["판정"] == "확인 필요" and "3배" in r["법정형"] and any("2분의 1" in x for x in r["병과·가중·감경"])


def test_foreign_account_by_act_date():
    r = G.guide("2018-06-30", "해외금융계좌 신고의무 불이행", unreported_amount=9_000_000_000)
    assert r["판정"][0]["판정"] == "이 법에 벌칙 없음" and "조문" not in r
    assert "제34조제1항" in G.guide("2020-06-30", "해외금융계좌 신고의무 불이행")["구성요건"] and "제53조제1항" in G.guide("2021-06-30", "해외금융계좌 신고의무 불이행")["구성요건"]
    g = lambda amt: J(G.guide("2024-06-30", "해외금융계좌 신고의무 불이행", unreported_amount=amt))["금액 기준"]["판정"]
    assert g(5_000_000_000) == "해당 아님" and g(5_000_000_001) == "해당"
    c = {x["항목"]: x for x in G.guide("2024-06-30", "해외금융계좌 신고의무 불이행")["공통 규정"]}
    assert "확인하지 않음" in c["공소시효"]["내용"] and "벌금 경합" not in c


def test_wording_by_period():
    assert "근로장려금" not in G.guide("2018-12-31", "거짓 근로소득 원천징수영수증")["구성요건"] and "근로장려금" in G.guide("2019-01-01", "거짓 근로소득 원천징수영수증")["구성요건"]
    assert "주세법" in G.guide("2020-12-31", "무면허 주류")["구성요건"] and "주류 면허 등에 관한 법률" in G.guide("2021-01-01", "무면허 주류")["구성요건"]
    assert "제3항" in G.guide("2018-12-31", "면세유 부정유통")["조문"] and "제2항" in G.guide("2019-01-01", "면세유 부정유통")["조문"]
    assert "소인된 인지" in G.guide("2018-12-31", "납세증명표지 불법사용")["구성요건"] and "전자수입인지" in G.guide("2019-01-01", "납세증명표지 불법사용")["구성요건"]
    r = G.guide("2024-05-10", "원천징수 불이행")
    assert "1천만원 이하 벌금" in r["법정형"] and "2년 이하의 징역" in r["법정형"] and "판정" not in r


def test_every_offense_returns():
    for o in G.OFFENSES:
        r = G.guide("2024-05-31", o)
        assert r["조문"].startswith("조세범 처벌법 제") and r["법정형"] and r["한계"] and "article='제" in r["다음 단계"][0], o


def test_joint_penalty_exclusion_1114():
    """제18조 괄호(2019.1.1. 시행본부터): 국조법 제36조(2019~2020)·제57조(2021~) 위반행위는 양벌규정 제외 — 2026-11-14 추가."""
    def joint(r):
        return {p["항목"]: p for p in r["공통 규정"]}["양벌규정"]["내용"]
    a = joint(G.guide("2024-03-31", "해외금융계좌 비밀유지 위반"))
    assert "제57조를 위반한 행위는 양벌규정에서 제외" in a and "제38조제2항부터 제4항까지 위반이면 양벌규정 적용" in a
    b = joint(G.guide("2020-03-31", "해외금융계좌 비밀유지 위반"))
    assert "제36조를 위반한 행위는 양벌규정에서 제외" in b and "제31조제6항부터 제8항까지" in b
    assert "제외(제18조 괄호" not in joint(G.guide("2024-03-31", "조세포탈")) and "양벌규정에서 제외" not in joint(G.guide("2024-03-31", "조세포탈"))
    assert "제57조" not in joint(G.guide("2017-03-31", "조세포탈"))
    assert "제36조" in joint(G.guide("2020-03-31")) and "제57조" in joint(G.guide("2024-03-31"))
