"""family_business_succession_guide — 조문 문언 대조 테스트(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(국세법령정보시스템 연혁본): 상속세 및 증여세법 2016.1.1.(법률 제13557호)·2017.1.1.(제14388호)·2018.1.1.(제15224호)·2019.1.1.(제16102호)·
2020.1.1.(제16846호)·2021.1.1.·2022.1.1.(제18591호)·2023.1.1.(제19195호)·2024.1.1.·2025.3.14.·2026.1.1. 시행본 제18조·제18조의2·제72조의2와 부칙,
시행령 2016.2.5.·2017.2.7.(대통령령 제27835호)·2018.2.13.·2019.2.12. 시행본 제15조와 부칙.
기대값은 위 문언에서 손으로 옮긴 것: 매출액 기준 3천억(2016은 직전 사업연도)·4천억(2022)·5천억(2023~), 한도 200/300/500억(2017까지 15·20년 구간, 2018~ 20·30년 구간)·300/400/600억(2023~),
사후관리 10년(~2019 상속)·7년(2020~2022)·5년(2023~, 법률 제19195호 부칙 제7조제2항으로 2023.1.1. 당시 사후관리 중인 상속인 포함)."""
from korean_tax_mcp import family_business_succession as G

EOK = 100_000_000


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_input_errors():
    r = G.guide()
    assert any("5천억원" in x for x in r["상속개시일별 변화"]) and "고용 미달" in r["사후관리 사유"]
    assert G.guide("2015-12-31")["error"] and G.guide("2023-13-01")["error"]
    assert G.guide("2023-01-01", company_size="대기업")["error"]
    assert G.guide("2023-01-01", post_events=[{"event": "폐업"}])["error"]


def test_article_location_boundary():
    assert G.guide("2022-12-31")["조문"] == "상속세 및 증여세법 제18조제2항제1호"
    assert G.guide("2023-01-01")["조문"] == "상속세 및 증여세법 제18조의2제1항"


def test_revenue_thresholds_by_date():
    v = lambda d, rev: J(G.guide(d, company_size="중견기업", avg_revenue=rev * EOK))["기업 규모·매출액"]["판정"]
    assert v("2021-12-31", 2999) == "충족" and v("2021-12-31", 3000) == "미충족" and v("2021-12-31", 3500) == "미충족"
    assert v("2022-01-01", 3500) == "충족" and v("2022-12-31", 3999) == "충족" and v("2022-12-31", 4000) == "미충족" and v("2022-12-31", 4500) == "미충족"
    assert v("2023-01-01", 4500) == "충족" and v("2023-01-01", 4999) == "충족" and v("2023-01-01", 5000) == "미충족"
    assert v("2017-01-01", 2999) == "충족"
    # 2016년: 직전 사업연도 매출액 3천억원, 상호출자제한기업집단 제외
    w = lambda **k: J(G.guide("2016-06-30", company_size="중견기업", **k))["기업 규모·매출액"]["판정"]
    assert w(prior_year_revenue=2999 * EOK, cross_shareholding_group=False) == "충족" and w(prior_year_revenue=3000 * EOK) == "미충족"
    assert w(prior_year_revenue=2000 * EOK, cross_shareholding_group=True) == "미충족"
    assert J(G.guide("2023-01-01", company_size="일반"))["기업 규모"]["판정"] == "미충족"
    assert J(G.guide("2023-01-01", company_size="중견기업"))["기업 규모·매출액"]["판정"] == "확인 필요"


def test_limits_by_years_managed():
    lim = lambda d, y: G.deduction_limit(G._d(d), y)
    assert lim("2017-12-31", 9) is None and lim("2017-12-31", 10) == 200 * EOK and lim("2017-12-31", 15) == 300 * EOK and lim("2017-12-31", 20) == 500 * EOK
    assert lim("2018-01-01", 15) == 200 * EOK and lim("2018-01-01", 20) == 300 * EOK and lim("2018-01-01", 29) == 300 * EOK and lim("2018-01-01", 30) == 500 * EOK
    assert lim("2022-12-31", 10) == 200 * EOK and lim("2022-12-31", 25) == 300 * EOK and lim("2022-12-31", 35) == 500 * EOK
    assert lim("2023-01-01", 10) == 300 * EOK and lim("2023-01-01", 25) == 400 * EOK and lim("2023-01-01", 35) == 600 * EOK
    assert lim("2026-11-14", 19.9) == 300 * EOK
    r = G.guide("2023-01-01", years_managed=25, business_property_value=450 * EOK)
    assert r["공제액(한도 적용)"]["공제액"] == 400 * EOK
    r = G.guide("2022-12-31", years_managed=25, business_property_value=250 * EOK)
    assert r["공제액(한도 적용)"]["공제액"] == 250 * EOK
    assert J(G.guide("2023-01-01", years_managed=9))["피상속인 계속 경영기간"]["판정"] == "미충족"


def test_post_management_regime_boundary():
    assert G.regime_for(G._d("2023-01-01"))[0] == "5년"
    assert G.regime_for(G._d("2022-12-31"))[0] == "5년"                       # 부칙 제7조제2항 — 2023.1.1. 당시 사후관리 중
    assert G.regime_for(G._d("2022-12-31"), assessed_before_2023=True)[0] == "7년"
    assert G.regime_for(G._d("2020-01-01"), assessed_before_2023=True)[0] == "7년"
    assert G.regime_for(G._d("2019-12-31"), assessed_before_2023=True)[0] == "10년"
    assert G.guide("2022-12-31")["사후관리 적용"]["기간 종료"] == "2027-12-31"
    assert G.guide("2019-12-31", assessed_before_2023=True)["사후관리 적용"]["기간 종료"] == "2029-12-31"


def test_asset_disposal_thresholds():
    ev = lambda d, when, ratio, **k: J(G.guide(d, post_events=[{"event": "가업용 자산 처분", "date": when, "ratio": ratio}], **k))
    assert ev("2023-01-01", "2025-01-01", 39)["사후관리 — 가업용 자산 처분(2025-01-01)"]["판정"] == "해당 없음"
    assert ev("2023-01-01", "2025-01-01", 40)["사후관리 — 가업용 자산 처분(2025-01-01)"]["판정"] == "추징 사유"
    assert ev("2023-01-01", "2028-01-01", 90)["사후관리 — 가업용 자산 처분(2028-01-01)"]["판정"] == "해당 없음"      # 5년 경과
    # 종전 규정(2023.1.1. 전 추징): 5년 이내 10%, 이후 20%
    assert ev("2020-03-01", "2022-03-01", 15, assessed_before_2023=True)["사후관리 — 가업용 자산 처분(2022-03-01)"]["판정"] == "추징 사유"
    assert ev("2020-03-01", "2025-06-01", 15, assessed_before_2023=True)["사후관리 — 가업용 자산 처분(2025-06-01)"]["판정"] == "해당 없음"
    # 같은 2022년 상속이라도 2023.1.1. 당시 사후관리 중이면 40% 기준
    assert ev("2022-03-01", "2024-03-01", 15)["사후관리 — 가업용 자산 처분(2024-03-01)"]["판정"] == "해당 없음"
    j = ev("2023-01-01", "2024-01-01", 50)
    assert j["사후관리 — 가업용 자산 처분(2024-01-01)"]["근거"].startswith("상속세 및 증여세법 제18조의2제5항")


def test_employment_and_other_events():
    r = J(G.guide("2023-05-01", post_events=[{"event": "고용 미달", "employment_ratio": 85, "payroll_ratio": 95},
                                            {"event": "고용 미달", "date": "2024-01-01", "employment_ratio": 85, "payroll_ratio": 80},
                                            {"event": "가업 미종사", "date": "2025-01-01", "justified": True}]))
    assert r["사후관리 — 고용 미달"]["판정"] == "해당 없음"
    assert r["사후관리 — 고용 미달(2024-01-01)"]["판정"] == "추징 사유"
    assert r["사후관리 — 가업 미종사(2025-01-01)"]["판정"].startswith("해당 없음")
    r = J(G.guide("2019-06-01", post_events=[{"event": "조세포탈·회계부정 형 확정"}]))
    assert r["사후관리 — 조세포탈·회계부정 형 확정"]["판정"] == "해당 없음"                 # 2020.1.1. 이후 행위·상속개시분부터


def test_shareholding_and_heir():
    hold = lambda d: G.shareholding_rule(G._d(d))[2]
    assert hold("2017-02-06") is None and hold("2017-02-07") == 10
    r = J(G.guide("2019-05-01", decedent_share_pct=45, share_holding_years=12))
    assert r["피상속인 지분"]["판정"] == "미충족"
    r = J(G.guide("2019-05-01", decedent_share_pct=35, share_holding_years=12, listed=True))
    assert r["피상속인 지분"]["판정"] == "충족"
    # 2023.1.1. 이후 상속개시분 40%(대통령령 제33278호 부칙 제2조제1항 — test_family_business_xchk_2100b.py)
    assert J(G.guide("2023-05-01", decedent_share_pct=45, share_holding_years=12))["피상속인 지분"]["판정"] == "충족"
    r = J(G.guide("2019-05-01", heir_age=17, heir_years_in_business=3, heir_officer_by_deadline=True, heir_ceo_within_2y=True))
    assert r["상속인 요건"]["판정"] == "미충족"
    r = J(G.guide("2019-05-01", heir_age=17, heir_years_in_business=3, heir_officer_by_deadline=True, heir_ceo_within_2y=True, spouse_qualifies=True))
    assert r["상속인 요건"]["판정"] == "충족"
    r = J(G.guide("2019-05-01", heir_age=30, heir_years_in_business=1, decedent_age_at_death=60, heir_officer_by_deadline=True, heir_ceo_within_2y=True))
    assert r["상속인 요건"]["판정"] == "충족"
    r = J(G.guide("2019-05-01", ceo_years=12))
    assert r["피상속인 대표이사 재직"]["판정"] == "확인 필요"
    assert J(G.guide("2019-05-01", ceo_years=12, heir_succeeded_ceo=True))["피상속인 대표이사 재직"]["판정"] == "충족"
    assert J(G.guide("2019-05-01", ceo_ratio=0.3, ceo_years_in_last10=4))["피상속인 대표이사 재직"]["판정"] == "미충족"


def test_deferral_and_capacity_only_when_in_force():
    has = lambda d, word: any(word in x["요건"] for x in G.guide(d)["요건"])
    assert not has("2022-12-31", "납부유예") and has("2023-01-01", "납부유예")
    assert not has("2018-12-31", "납부능력") and has("2019-01-01", "납부능력")
    assert not has("2019-12-31", "조세포탈") and has("2020-01-01", "조세포탈")
    assert G.guide("2023-01-01")["관련 해석"] and "미확인" in " ".join(G.guide("2023-01-01")["한계"])
