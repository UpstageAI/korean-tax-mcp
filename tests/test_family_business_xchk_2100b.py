"""family_business_succession_guide — 상증령 2020년 이후 시행본 원문 대조 후 고친 판정(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(법제처 DRF 연혁본):
- 상속세 및 증여세법 시행령 2022.2.15. 시행본(대통령령 제32414호) 제15조제3항제1호가목: 100분의 50(상장 100분의 30) 이상 10년 이상 계속 보유
- 2023.2.28. 시행본(대통령령 제33278호) 같은 목: 100분의 40(상장 100분의 20) — 부칙 제2조제1항 "2023년 1월 1일 이후 상속이 개시되는 경우부터 적용"
- 2023.2.28. 개정 제15조제15항: 법 제18조의2제5항의 "대통령령으로 정하는 율" = 100분의 100 (현행 2026.2.27. 시행본 같음)
정답은 위 문언에서 손으로 셈한 값(지분율 '이상')."""
from korean_tax_mcp import family_business_succession as G


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def share(d, pct, listed=None):
    return J(G.guide(d, decedent_share_pct=pct, share_holding_years=10, listed=listed))["피상속인 지분"]


def test_shareholding_boundary_2023():
    assert share("2022-12-31", 45, listed=False)["판정"] == "미충족"      # 50%
    r = share("2023-01-01", 45, listed=False)
    assert r["판정"] == "충족" and "제33278호" in r["근거"] and "부칙 제2조제1항" in r["근거"]   # 40%
    assert share("2023-01-01", 39.9, listed=False)["판정"] == "미충족"
    assert share("2023-01-01", 40, listed=False)["판정"] == "충족"         # '이상'
    assert share("2022-12-31", 25, listed=True)["판정"] == "미충족"       # 상장 30%
    assert share("2023-02-01", 25, listed=True)["판정"] == "충족"          # 시행령 공포 전이라도 부칙 제2조제1항으로 20%
    assert share("2023-02-01", 19.9, listed=True)["판정"] == "미충족"
    assert share("2022-12-31", 50, listed=False)["판정"] == "충족"
    assert G.shareholding_rule(G._d("2026-11-14"))[:3] == (40, 20, 10)


def test_unverified_marks_removed_2023():
    r = G.guide("2023-01-01", decedent_share_pct=45, share_holding_years=10, ceo_ratio=0.3, ceo_years_in_last10=4,
                heir_age=17, heir_years_in_business=3, heir_officer_by_deadline=True, heir_ceo_within_2y=True)
    txt = str(r["요건"]) + str(r["판정"])
    assert "미확인" not in txt
    j = J(r)
    # 대표이사·상속인 요건은 현행 문언과 같으므로(2023.2.28.·2026.2.27. 시행본) 미충족은 미충족으로 돌려줌
    assert j["피상속인 대표이사 재직"]["판정"] == "미충족" and j["상속인 요건"]["판정"] == "미충족"
    # 2020~2022 구간 문구: 2022.2.15. 시행본으로 대조
    assert "2022.2.15. 시행본으로 대조" in G.decree_note(G._d("2021-06-01"))
    assert "대분류" in G.decree_note(G._d("2022-03-01")) and G.decree_note(G._d("2023-01-01")) == ""


def test_post_management_rate_100():
    r = G.guide("2024-01-01", post_events=[{"event": "가업 미종사", "date": "2025-01-01"}])
    p = J(r)["사후관리 — 가업 미종사(2025-01-01)"]
    assert p["판정"] == "추징 사유" and "100%" in p["사유"] and "제15조제15항" in p["근거"]
    assert "100%" in [x for x in r["요건"] if x["구분"] == "사후관리"][0]["내용"]
    # 2019년 상속개시, 2023.1.1. 전 추징 → 종전(10년) 구간은 기간별 추징률
    r = G.guide("2019-01-01", assessed_before_2023=True, post_events=[{"event": "가업 미종사", "date": "2020-01-01"}])
    assert "기간별 추징률" in J(r)["사후관리 — 가업 미종사(2020-01-01)"]["사유"]
    # 2023.1.1.~2.27. 사유 발생분은 100% 적용 시점 확인 필요 문구
    r = G.guide("2021-01-01", post_events=[{"event": "가업 미종사", "date": "2023-02-01"}])
    assert "적용례가 없어 확인 필요" in J(r)["사후관리 — 가업 미종사(2023-02-01)"]["사유"]
    r = G.guide("2021-01-01", post_events=[{"event": "가업 미종사", "date": "2023-02-28"}])
    assert "적용례가 없어" not in J(r)["사후관리 — 가업 미종사(2023-02-28)"]["사유"]
