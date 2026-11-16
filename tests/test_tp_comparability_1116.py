"""이전가격 비교대상 선정·기능 유사성·거래의 독립성 보강(2026-11-16).

사건은 국세법령정보시스템·법제처 본문 판단 부분과 대조한 것만 실었다. 통칙 8-0…1·8-15…1은 basic_rules(2024년 고시본),
시행령 제2조②·제15조⑦은 law_article(2026.2.27. 시행본)로 대조.
"""
from korean_tax_mcp import server as S
from korean_tax_mcp import tp_report as R
from korean_tax_mcp import transfer_pricing as T

# 계산 MCP(korean-tax-calc-mcp) engine/kr_comparables/compare.py DEFAULT_RULES, engine/calc_tp_screen.py DEFAULT_SCREENS의 키(2026-11-16)
CALC_RULES = {"mix_max_diff", "ratio_low", "ratio_high", "ppe_abs_tol", "rnd_abs_tol", "advert_abs_tol", "coverage_min", "coverage_max",
              "independence_legal_pct", "related_sales_review", "unknown_review_count", "mix_unverified_review"}
CALC_SCREENS = {"independence_pct", "independence_bvd_reject", "industry_codes", "size_min", "size_max", "loss_years", "crisis_exception",
                "rnd_max", "adv_max", "wc_band", "related_max", "segment_min", "special_flags", "outlier_k", "op_tolerance"}


def _rows():
    return {c["문서번호"]: (n, c) for n, v in R.cases()["쟁점"].items() for c in v["사례"]}


def test_case_numbers_and_outcomes_not_mixed():
    rows = _rows()
    n, c = rows["대법원-2024-두-64901"]
    assert n == "비교대상 선정" and c["결과"] == "납세자 승" and "심리불속행" in c["요지"] and c["판단 위치"].startswith("원심")
    assert [r["문서번호"] for r in c["관련 문서"]] == ["수원고등법원-2023-누-16871", "수원지방법원-2022-구합-75045"]
    assert c["관련 문서"][0]["링크"].endswith("200000000000014827")
    n, c = rows["대법원-2024-두-54065"]
    assert c["결과"] == "일부" and "파기환송" in c["요지"] and "소형가전" in c["요지"] and "의료장비" in c["요지"]
    assert c["관련 문서"][0]["문서번호"] == "서울고등법원-2022-누-55844"
    n, c = rows["대법원-2012-두-23341"]
    assert c["결과"] == "납세자 승" and c["일자"] == "2014.08.20."
    n, c = rows["조심 2023서9158"]
    assert n == "다년도 자료" and c["결과"] == "일부" and c["id"] == "tt:2058951" and "사업연도별" in c["요지"]
    assert c["링크"] == "https://www.law.go.kr/LSW/specialDeccInfoP.do?spDeccSeq=2058951"


def test_independence_issue():
    v = R.cases("비교대상 독립성")["쟁점"]["비교대상 독립성"]
    by = {c["문서번호"]: c for c in v["사례"]}
    c = by["대법원-2009-두-24122"]
    assert c["결과"] == "과세관청 승" and "53%" in c["요지"] and "특수관계가 아님" in c["요지"]
    assert c["관련 문서"][0]["문서번호"] == "서울고등법원-2007-누-29392" and "납세자 승" in c["관련 문서"][0]["비고"]
    assert by["조심 2018서4584"]["결과"] == "납세자 승"
    assert any("8-0…1" in s for s in v["보고서에 반영할 점"]) and any("제2조②" in s for s in v["보고서에 반영할 점"])


def test_outcome_partial_filter_and_tool():
    r = R.cases("", "일부")
    docs = sorted(c["문서번호"] for v in r["쟁점"].values() for c in v["사례"])
    assert docs == ["대법원-2024-두-54065", "조심 2021서3863", "조심 2023서9158"]
    f = getattr(S.transfer_pricing_cases, "fn", S.transfer_pricing_cases)
    out = f(issue="비교대상", outcome="일부")
    assert {"비교대상 선정", "비교대상 독립성"} <= set(out["쟁점"])
    assert [x["도구"] for x in out["계산 다음 단계"]][-1] == "계산 MCP arm_length_range"


def test_guide_independence_quartile_control():
    items = {x["항목"]: x for x in T.guide("재화")["비교가능 거래"]["내용"]}
    ind = items["거래의 독립성"]
    assert "8-0…1" in ind["근거"] and "비교대상거래로 사용될 수는 없으나" in ind["내용"] and ind["OECD 지침 문단"].startswith("3.24-3.26")
    ctl = items["실질 지배 기준(특수관계)"]
    assert "시행령 제2조②" in ctl["근거"] and any("절반" in x and "3년" in x for x in ctl["내용"])
    assert any("50%" in x and "거래에 의존" in x for x in ctl["내용"]) and "2009두24122" in ctl["주의"] and "준용" in ctl["주의"]
    q = items["정상가격 범위 — 사분위"]
    assert "(n+2)/4" in q["내용"] and "(3n+2)/4" in q["내용"] and "평균" in q["내용"] and "8-15…1" in q["근거"] and "272" in q["근거"]


def test_selection_criteria_sources_and_handoff_keys():
    c = T.guide("재화")["비교대상 선정 기준"]
    PR = "관행(근거 약함, 바꿀 수 있음)"
    assert set(c["출처 구분"]) == {"법정", "법정(준용)", "통칙", "판례", PR} and "2026" in c["기준일"]
    rules = c["넘길 값"]["kr_comparable_profile_compare"]["rules"]
    screens = c["넘길 값"]["tp_comparable_screen"]["screens"]
    assert set(rules) == CALC_RULES and set(screens) <= CALC_SCREENS
    assert c["넘길 값"]["tp_comparable_screen"]["quartile_method"] in ("inclusive", "exclusive")
    rows = c["kr_comparable_profile_compare"] + c["tp_comparable_screen"]
    assert all(r["성격"] in ("법정", "법정(준용)", "통칙", PR) and r["출처"] and r["기준일"] and r["근거 강도"] in ("강", "중", "약") for r in rows)
    kind = {r["키"]: r["성격"] for r in rows}
    for k in ("mix_max_diff", "ratio_low", "related_sales_review", "independence_pct", "loss_years", "rnd_max", "adv_max", "quartile_method"):
        assert kind[k] == PR, k
    assert {r["근거 강도"] for r in rows if r["성격"] == PR} == {"약"}
    assert kind["independence_legal_pct"] == "법정(준용)" and kind["crisis_exception"] == "법정"
    # 판례 신호는 숫자 기준이 아니라 확인 질문
    assert not any(r["성격"] == "판례" for r in rows)
    qs = c["확인 질문"]
    assert any("거래단계" in q["질문"] for q in qs) and any("마케팅" in q["질문"] for q in qs) and any("사업연도별" in q["질문"] for q in qs)
    assert "비교대상 선정 기준" in T.guide("용역") and "비교대상 선정 기준" not in T.guide("금전대차")


def test_selection_criteria_by_role_and_tested_party():
    sale = T.guide("재화", comparable={"role": "판매", "limited_risk": True, "tested_loss": True})["비교대상 선정 기준"]
    assert sale["입력"]["역할"] == "판매" and all("판매" in q["역할"] for q in sale["확인 질문"])
    assert any("2024두54065" in x for x in sale["주의"]) and any("3.64-3.65" in x for x in sale["주의"])
    mfg = T.guide("재화", comparable={"role": "제조"})["비교대상 선정 기준"]
    assert not any("마케팅·광고 기능" in q["질문"] for q in mfg["확인 질문"]) and any("수출 비중" in q["질문"] for q in mfg["확인 질문"])
    svc = T.guide("용역")["비교대상 선정 기준"]
    assert svc["입력"]["역할"] == "용역" and any("용역 제공자" in x for x in svc["주의"])
    crisis = T.guide("재화", comparable={"economic_crisis": True})["비교대상 선정 기준"]
    assert crisis["넘길 값"]["tp_comparable_screen"]["screens"]["crisis_exception"] is True
    assert T.guide("재화")["비교대상 선정 기준"]["넘길 값"]["tp_comparable_screen"]["screens"]["crisis_exception"] is False   # 원본 표는 그대로
    assert "error" in T.guide("재화", comparable={"role": "도매"}) and "error" in T.guide("재화", comparable={"x": 1})
    f = getattr(S.transfer_pricing_guide, "fn", S.transfer_pricing_guide)
    assert f(transaction="재화", comparable={"role": "판매"})["비교대상 선정 기준"]["입력"]["역할"] == "판매"


def test_calc_chain_order():
    names = [x["도구"].removeprefix("계산 MCP ") for x in T.guide("재화")["계산 다음 단계"]]
    assert names == ["arm_length_range", "kr_comparable_candidates", "kr_comparable_profile_compare", "tp_comparable_screen"]
    assert names[1:] == [x["도구"].removeprefix("계산 MCP ") for x in R._COMPARABLE_CALC[:3]]
    assert "expat_cost_recharge" in [x["도구"].removeprefix("계산 MCP ") for x in T.guide("용역")["계산 다음 단계"]]


def test_far_points_to_comparability_both_modes():
    parties = {"한국본사": {"기능": ["제조", "연구·개발"], "고유무형자산": True}, "미국법인": {"기능": ["유통"]}}
    for r in (R.far(), R.far(parties=parties)):
        cmp = r["비교대상 선정"]
        assert "8-0…1" in cmp["거래의 독립성"]["근거"] and "(n+2)/4" in cmp["정상가격 범위 — 사분위"]["내용"]
        assert [x["도구"] for x in r["계산 다음 단계"]] == [x["도구"] for x in R._COMPARABLE_CALC]


def test_english_still_works():
    f = getattr(S.transfer_pricing_guide, "fn", S.transfer_pricing_guide)
    assert isinstance(f(transaction="재화", lang="en"), dict)
