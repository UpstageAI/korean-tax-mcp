"""interest_withholding_guide — 원문 대조 테스트(2026-11-16, Claude 작성). 외부 호출 없음.

기대값은 아래 원문에서 손으로 정했다(조회일 2026-11-16, 조문 MCP 배포본 law_article·article_addenda·basic_rules·get_tax_ruling):
  · 법인세법 제98조제1항 2018.1.1. 시행본 — 제3호 본문 100분의 20, 단서 국가·지방자치단체·내국법인 발행 채권 이자 100분의 14.
    2019.1.1.·2026.1.2. 시행본 — 제1호 가목(채권 이자) 100분의 14, 나목(그 밖의 이자) 100분의 20. "그 지급을 할 때 … 다음 달 10일까지".
  · 소득세법 제156조제1항 2018.4.1. 시행본 제3호(단서 14), 2019.1.1.·2026.4.21. 시행본 제1호 가목·나목. 제156조의6(2026.4.21.).
  · 법인세법 제93조제1호(2016.1.25.·2026.1.2. 같은 문언) — 가목·나목, 단서(국외사업장이 직접 차용한 차입금 이자 제외).
  · 법인세법 제98조의6 2025.3.14. 시행본(제4항 경정청구) / 2026.1.2. 시행본(제4항 세무서 제출 — 다음 연도 2월 말일, 제5항 경정청구), 부칙 <제21217호> 제13조(시행 이후 신청분부터).
  · 법인세법 시행령 제138조의7 — 제1항 '지급받기 전까지', 제6항 '제출된 날부터 3년 이내 … 변동 시 다시 제출'(2016.6.23.·2026.10.1. 같음). 제137조(2026.10.1.) — 지급시기 특례는 제4항 나목 이자만.
  · 법인세법 제98조의7(2026.1.2.) — 대상조세에 지방소득세가 없으면 제1호(제한세율과 국내 세율 중 낮은 것), 있으면 제2호(국내 세율에 지방소득세 100분의 10 반영).
  · 법인세법 기본통칙 98-0…2 — 약정액 ÷ (1 − 원천징수세율) = 과세표준.
  · 국제조세조정에 관한 법률 구 제14조(2018.1.1.), 구 제15조의2(2019.1.1.), 제22조·제24조·제26조(2026.1.2.), 부칙 <제17651호> 제6조(구 제15조의2는 2019.1.1. 이후 개시 과세연도분부터).
  · 서면인터넷방문상담2팀-1656(비거주자 이자 원천징수 시기 = 실제 지급하는 때), 조심 2014광4612(면제받아 지급하지 않은 이자 — 원천징수 의무 없음),
    국업46017-135(국내원천소득 아님)·서이46017-10386(기타소득)·서면인터넷방문상담2팀-1549(사업소득) — 지급보증수수료.
조세조약은 royalty 테스트와 같은 fixtures(royalty_treaties.json — 미국 제1조·제13조, b_law_treaties.json — 일본·싱가포르)를 되돌려 준다.
  미국 제13조(2) 12%, 제1조 대상조세 '소득세 및 법인세'(지방소득세 없음) / 싱가포르 제11조(2) 10%, 제11조(8) 특수관계, 제2조 '지방소득세' 포함.
예시 숫자는 모두 지어낸 둥근 값이다.
"""
import asyncio
import json
import os

import pytest

from korean_tax_mcp import ntis
from korean_tax_mcp import interest_withholding as G
from korean_tax_mcp.server import mcp

FX = os.path.join(os.path.dirname(__file__), "fixtures")
TREATY = {"목록": [], "조문": {}}
for _f in ("royalty_treaties.json", "b_law_treaties.json"):
    _d = json.load(open(os.path.join(FX, _f), encoding="utf-8"))
    TREATY["목록"] += _d["목록"]; TREATY["조문"].update(_d["조문"])


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


@pytest.fixture
def look(monkeypatch):
    ntis.treaties.cache_clear()
    by_id = {x["txaAgrmBscId"]: x["txaAgrmNtnNm"] for x in TREATY["목록"]}

    def fake_act(action, param, timeout=40):
        if action == "ASISTC001MR01":
            return {"txaTraDVOList": TREATY["목록"]}
        if action == "ASISTC002MR01":
            return {"txaTraDVOList": TREATY["조문"][by_id[param["txaAgrmBscId"]]]}
        raise AssertionError(f"예상 못 한 호출 {action}")
    monkeypatch.setattr(ntis, "_act", fake_act)
    yield lambda c: ntis.withholding_rates(c, "이자")
    ntis.treaties.cache_clear()


def J(r):
    return {p["항목"]: p for p in r["판정"]}


BASE = dict(payment_date="2026-06-30", recipient_country="싱가포르", payment_kind="차입금 이자", payer_type="내국법인·거주자·국가 등",
            for_overseas_branch=False, attributable_to_korean_pe=False, beneficial_owner_confirmed=True, application_date="2025-01-10", related_party=False)


def g(look, **kw):
    return G.guide(**{**BASE, "treaty_lookup": look, **kw})


# ── 안내 · 입력 오류 ───────────────────────────────────────────────────────

def test_overview_and_bad_values_are_refused():
    r = G.guide()
    assert len(r["요소"]) == 11 and len(r["결정 트리"]) == 8 and len(r["지급일별로 달라지는 것"]) == 5
    assert r["입력"]["payment_kind"] == ["차입금 이자", "채권 이자", "지급보증수수료"]
    for bad in (dict(payment_date="2015-12-31"), dict(payment_date="2027-01-01"), dict(payment_date="2026/01/01"),
                dict(payment_date="2026-01-01", payment_kind="배당"), dict(payment_date="2026-01-01", payer_type="본점"),
                dict(payment_date="2026-01-01", recipient_type="조합"), dict(payment_date="2026-01-01", net_of_tax="전부"),
                dict(payment_date="2026-01-01", application_date="어제")):
        assert "error" in G.guide(**bad), bad


def test_unknown_facts_are_not_guessed():
    r = G.guide(payment_date="2026-06-30")
    assert r["결정"]["구분"] == "확인 필요" and r["지급 대상"] == "확인 필요"
    j = J(r)
    for k in ("소득 구분", "국내원천", "조약 제한세율", "지방소득세", "절차 — 실질귀속자", "절차 — 제한세율 적용신청서", "세금부담 약정", "과소자본·정상이자율·과다이자"):
        assert j[k]["판정"].startswith("확인 필요"), (k, j[k]["판정"])
    # 지급 대상만 알면: 막힌 사실(지급자·거주지국·신청서·실질귀속자)을 적고 세율을 정하지 않는다
    r = G.guide(payment_date="2026-06-30", payment_kind="차입금 이자")
    d = r["결정"]
    assert d["구분"] == "확인 필요" and len(d["막힌 사실"]) == 4 and any("20%" in x for x in d["가능한 결과"])


# ── 시행본 경계: 국내 세율의 호 ─────────────────────────────────────────────

def test_domestic_rate_item_by_payment_date():
    """2018.12.31.까지 제98조제1항제3호(본문 20%·단서 채권 14%), 2019.1.1.부터 제1호 가목(14%)·나목(20%) — 세율 같음."""
    k = "국내 세율"
    for day, loan, bond in (("2018-12-31", "법인세법 제98조제1항제3호 본문", "법인세법 제98조제1항제3호 단서"),
                            ("2019-01-01", "법인세법 제98조제1항제1호나목", "법인세법 제98조제1항제1호가목")):
        a = J(G.guide(payment_date=day, payment_kind="차입금 이자"))[k]
        b = J(G.guide(payment_date=day, payment_kind="채권 이자"))[k]
        assert (a["판정"], a["근거"]) == ("20%", loan) and (b["판정"], b["근거"]) == ("14%", bond)
    assert "2018.12.31.까지 시행본은 제3호" in J(G.guide(payment_date="2018-12-31", payment_kind="차입금 이자"))[k]["사유"]
    # 개인(비거주자): 소득세법 제156조제1항 제3호 → 제1호
    i18 = J(G.guide(payment_date="2018-12-31", payment_kind="차입금 이자", recipient_type="개인"))[k]
    i19 = J(G.guide(payment_date="2019-01-01", payment_kind="채권 이자", recipient_type="individual"))[k]
    assert i18["근거"] == "소득세법 제156조제1항제3호 본문" and i19["근거"] == "소득세법 제156조제1항제1호가목" and i19["판정"] == "14%"


def test_local_tax_special_rule_article_by_date():
    """지방소득세 세율 특례: 2020.12.31.까지 구 국제조세조정에 관한 법률 제29조, 2021.1.1.부터 법인세법 제98조의7."""
    assert "구 국제조세조정에 관한 법률 제29조" in J(G.guide(payment_date="2020-12-31", payment_kind="차입금 이자"))["지방소득세"]["근거"]
    assert J(G.guide(payment_date="2021-01-01", payment_kind="차입금 이자"))["지방소득세"]["근거"].startswith("법인세법 제98조의7제1항")


# ── 시행본 경계: 신청서 세무서 제출 의무(2026.1.1. 이후 신청분) · 경정청구 항 ──────────

def test_filing_duty_before_and_after_2026(look):
    k = "절차 — 신청서 세무서 제출"
    before = J(g(look, payment_date="2025-12-31", application_date="2025-12-01"))
    assert before[k]["판정"] == "해당 없음" and "제98조의6제4항" in before[k]["근거"] and "제21217호" in before[k]["근거"]
    assert before["절차 — 경정청구"]["근거"] == "법인세법 제98조의6제4항"            # 2025.3.14. 시행본: 경정청구가 제4항
    new = J(g(look, payment_date="2026-03-31", application_date="2026-02-01"))
    assert new[k]["판정"] == "제출 의무" and "2027년 2월 말일" in new[k]["사유"] and new[k]["확신도"] == "확인함"
    assert new["절차 — 경정청구"]["근거"] == "법인세법 제98조의6제5항"                # 2026.1.2. 시행본: 제5항
    old_app = J(g(look, payment_date="2026-03-31", application_date="2025-11-01"))   # 2025년에 받아 둔 신청서(3년 이내)
    assert old_app[k]["판정"] == "의무 없음으로 읽힘" and old_app[k]["확신도"] == "유추"
    ind = J(g(look, payment_date="2026-03-31", application_date="2026-02-01", recipient_type="개인"))[k]
    assert "소득세법 제156조의6제4항" in ind["근거"] and "제21221호" in ind["근거"]


# ── 신청서 유무·시기 → 결정 ───────────────────────────────────────────────

def test_treaty_rate_with_valid_application_local_tax_inside_cap(look):
    """싱가포르 제11조(2) 10%, 대상조세에 지방소득세 포함 → 제98조의7제1항제2호: min(10, 20×1.1) = 10%가 합계 상한, 법인세 10/11·지방 1/11."""
    d = g(look)["결정"]
    assert d["구분"] == "10%" and d["합계(%)"] == 10.0 and d["법인세율(%)"] == 9.0909 and d["지방소득세율(%)"] == 0.9091
    assert "제98조의7제1항제2호" in d["지방소득세"] and d["세율 확신도"] == "자동 추출(조문 확인 필요)"
    j = J(g(look))
    assert j["절차 — 제한세율 적용신청서"]["판정"] == "충족" and j["지방소득세"]["판정"] == "제한세율 안에 포함"


def test_us_cap_with_local_tax_outside(look):
    """미국 제13조(2) 12%, 제1조 대상조세에 지방소득세 없음 → 제98조의7제1항제1호: 법인세 12% + 지방 1.2% = 13.2%."""
    d = g(look, recipient_country="미국")["결정"]
    assert (d["구분"], d["법인세율(%)"], d["지방소득세율(%)"], d["합계(%)"]) == ("12%", 12.0, 1.2, 13.2)
    assert any("제17조" in p for p in d["전제"])                  # 혜택 배제 조항
    bond = g(look, recipient_country="미국", payment_kind="채권 이자")["결정"]
    assert bond["법인세율(%)"] == 12.0                               # min(12, 14)


@pytest.mark.parametrize("app_date,cat", [
    ("2026-07-01", "20%"),        # 지급(2026-06-30) 뒤 수령 — 시행령 제138조의7제1항 '지급받기 전까지'
    ("2023-06-29", "20%"),        # 제출일부터 3년이 지난 뒤의 지급 — 같은 조 제6항
    ("2023-07-01", "10%"),        # 3년 이내
])
def test_application_timing(look, app_date, cat):
    r = g(look, application_date=app_date)
    assert r["결정"]["구분"] == cat
    if cat == "20%":
        assert r["결정"]["합계(%)"] == 22.0 and r["결정"]["법인세율(%)"] == 20 and r["결정"]["지방소득세율(%)"] == 2.0
        j = J(r)["절차 — 제한세율 적용신청서"]
        assert j["판정"].startswith("제한세율 적용 불가") and "제98조의6제3항" in j["근거"]
        assert J(r)["절차 — 경정청구"]["판정"] == "5년 이내 가능"


def test_application_boundary_day_and_change_stay_open(look):
    """3년이 되는 같은 날짜의 지급은 기간 계산(초일 산입)을 확인하지 못해 '확인 필요', 내용 변동은 다시 받았는지 확인."""
    edge = g(look, application_date="2023-06-30")
    assert edge["결정"]["구분"] == "확인 필요" and J(edge)["절차 — 제한세율 적용신청서"]["확신도"] == "미확인"
    assert any("3년 이내" in x and "초일" in x for x in edge["미확인"])
    ch = g(look, application_changed=True)
    assert ch["결정"]["구분"] == "확인 필요" and J(ch)["절차 — 제한세율 적용신청서"]["확신도"] == "유추"
    none = g(look, application_date=None, application_before_payment=False)
    assert none["결정"]["구분"] == "20%"


# ── 세금부담 약정(순액) ───────────────────────────────────────────────────

def test_net_of_tax_gross_up(look):
    """통칙 98-0…2: 약정액 ÷ (1 − 원천징수세율). 신청서가 없어 20%: ÷ 0.8(순액 기준 실효 25%). 지방소득세까지 부담하면 ÷ 0.78(유추, 실효 28.21%)."""
    r = g(look, application_date=None, application_before_payment=False, net_of_tax="법인세")
    n = r["결정"]["순액 약정 반영"]
    assert n["과세표준"] == "약정액 ÷ (1 − 0.2)" and n["순액 기준 실효 세율(%)"] == 25.0 and n["확신도"] == "확인함"
    assert "62,500,000원" in J(r)["세금부담 약정"]["사유"]                       # 지어낸 값: 5천만 원 ÷ 0.8
    r2 = g(look, application_date=None, application_before_payment=False, net_of_tax="corporate_and_local_tax")
    n2 = r2["결정"]["순액 약정 반영"]
    assert n2["과세표준"] == "약정액 ÷ (1 − 0.22)" and n2["순액 기준 실효 세율(%)"] == 28.21 and n2["확신도"] == "유추"
    assert J(r2)["세금부담 약정"]["확신도"] == "유추" and "64,102,564원" in J(r2)["세금부담 약정"]["사유"]   # 5천만 원 ÷ 0.78, 원 미만 버림
    args = next(s for s in r2["계산 다음 단계"] if s["도구"] == "계산 MCP nonresident_withholding")["인자"]
    assert args["net_of_tax"] is True and args["payer_bears_local_tax"] is True and args["income_kind"] == "이자" and "treaty_rate" not in args


def test_calc_arguments_carry_treaty_rate(look):
    args = next(s for s in g(look)["계산 다음 단계"] if s["도구"] == "계산 MCP nonresident_withholding")["인자"]
    assert args["treaty_rate"] == 0.1 and args["treaty_includes_local_tax"] is True and args["recipient_type"] == "법인" and args["year"] == 2026
    names = [s["도구"] for s in g(look, related_party=True)["계산 다음 단계"]]
    assert names == ["계산 MCP nonresident_withholding", "계산 MCP withholding_late_payment_penalty", "계산 MCP thin_capitalization", "계산 MCP arm_length_range"]
    assert "계산 MCP thin_capitalization" not in [s["도구"] for s in g(look)["계산 다음 단계"]]     # related_party=False


# ── 지급 시점: 미지급 · 원본 전입 · 면제 ──────────────────────────────────

def test_accrued_unpaid_interest(look):
    r = g(look, accrued_unpaid=True)
    j = J(r)["절차 — 원천징수 시기"]
    assert j["판정"] == "아직 원천징수 의무 없음(실제 지급 때)" and j["확신도"] == "확인함"
    assert "서면인터넷방문상담2팀-1656" in j["근거"] and "시행령 제137조" in j["근거"] and r["결정"]["원천징수 시점"] == "실제 지급일"
    # 국외 지급자가 국내사업장 손금에 넣는 나목 이자는 지급시기 의제(시행령 제137조제4항)
    n = J(g(look, accrued_unpaid=True, payer_type="foreign_payer_pe_deductible"))["절차 — 원천징수 시기"]
    assert n["판정"] == "지급시기 의제(나목 이자)" and n["근거"] == "법인세법 시행령 제137조제4항"


def test_capitalized_interest_is_closed_as_no_basis(look):
    r = g(look, capitalized_to_principal=True)
    j = J(r)["절차 — 원천징수 시기"]
    assert j["판정"] == "근거 없음 — 두 결과" and j["확신도"] == "근거 없음"
    assert "2026-11-16" in j["사유"] and "서면질의 필요" in j["사유"] and "원본 전입" in j["사유"]
    assert "전입일에 지급한 것으로 보아 원천징수" in j["사유"] and "실제 현금 지급" in j["사유"]
    assert "소득세법 시행령 제45조제4호·제9호의2" in j["근거"]
    assert r["결정"]["원천징수 시점"].startswith("근거 없음") and any(x.startswith("원본 전입") for x in r["근거 없음"])


def test_waived_interest(look):
    j = J(g(look, interest_waived=True))["절차 — 원천징수 시기"]
    assert j["판정"].startswith("원천징수 의무 성립 안 함") and "조심 2014광4612" in j["근거"] and j["확신도"] == "확인함"


# ── 지급보증수수료: 이자 아님 ─────────────────────────────────────────────

def test_guarantee_fee_is_not_interest(look):
    r = g(look, payment_kind="지급보증수수료")
    d = r["결정"]
    assert d["구분"] == "기타(이자 아님)" and len(d["가능한 결과"]) == 3
    j = J(r)
    assert j["소득 구분"]["판정"].startswith("이자 아님")
    for doc in ("국업46017-135", "서이46017-10386", "서면인터넷방문상담2팀-1549"):
        assert doc in j["소득 구분"]["사유"] and doc in j["소득 구분"]["근거"]
    assert "국내 세율" not in j and "조약 제한세율" not in j and "세금부담 약정" not in j
    assert [x["문서"].split("(")[0] for x in r["지급보증수수료 회신"]][:3] == ["국업46017-135", "서이46017-10386", "서면인터넷방문상담2팀-1549"]
    assert all(s["인자"].get("income_kind") != "이자" for s in r["계산 다음 단계"])


# ── 국내원천 · 국내사업장 ─────────────────────────────────────────────────

def test_source_and_pe(look):
    assert g(look, for_overseas_branch=True)["결정"]["구분"] == "0%"                  # 제93조제1호 단서
    assert g(look, payer_type="foreign")["결정"]["구분"] == "0%"                      # 가목·나목 어디에도 없음
    assert g(look, payer_type="foreign_payer_pe_deductible")["결정"]["경로"][1] == "Q2 국내원천(법인세법 제93조제1호 나목)"
    pe = g(look, attributable_to_korean_pe=True)
    assert pe["결정"]["구분"] == "기타" and J(pe)["국내원천(국내사업장 귀속)"]["판정"] == "원천징수 대상 아님"
    assert "제11조(6)" in pe["결정"]["경로"][-1]                                      # 조약 고정사업장 항


# ── 개인 수취인 ───────────────────────────────────────────────────────────

def test_individual_recipient_uses_income_tax_act(look):
    r = g(look, recipient_type="개인")
    d = r["결정"]
    assert "소득세율(%)" in d and "법인세율(%)" not in d and d["합계(%)"] == 10.0 and d["소득세율(%)"] == 9.0909
    assert r["수취인"]["구분"] == "비거주자(개인)"
    assert J(r)["국내원천"]["근거"] == "소득세법 제119조제1호" and J(r)["절차 — 신청서 세무서 제출"]["근거"].startswith("소득세법 제156조의6제4항")
    assert any("소득세법 제156조의6제1항" in p for p in d["경로"])
    assert next(s for s in r["계산 다음 단계"] if s["도구"].endswith("nonresident_withholding"))["인자"]["recipient_type"] == "개인"


# ── 조약 미체결국 · 조회 실패 ─────────────────────────────────────────────

def test_no_treaty_country(look):
    r = g(look, recipient_country="파나마")                 # fixtures 목록에 없음 → '체결국 아님'
    assert J(r)["조약 제한세율"]["판정"] == "조약 없음"
    d = r["결정"]
    assert (d["구분"], d["법인세율(%)"], d["지방소득세율(%)"], d["합계(%)"]) == ("20%", 20.0, 2.0, 22.0)
    assert "조세조약 없음" in d["결론"]


def test_lookup_failure_leaves_treaty_open():
    def boom(c): raise RuntimeError("blocked")
    r = G.guide(**{**BASE, "treaty_lookup": boom})
    assert r["결정"]["구분"] == "확인 필요" and r["조약 조회"].startswith("조회 실패") and J(r)["조약 제한세율"]["확신도"] == "미확인"


# ── 특수관계 · 과소자본 · 과다이자 (과세연도 경계) ──────────────────────────

def test_related_party_and_interest_limits_by_year(look):
    r = g(look, related_party=True)
    assert any("싱가포르 조세조약 제11조(8)" in p for p in r["결정"]["전제"])
    k = "과소자본·정상이자율·과다이자"
    y18 = J(g(look, payment_date="2018-06-30", related_party=True))[k]
    assert y18["근거"].startswith("구 국제조세조정에 관한 법률 제14조,") and "2019.1.1. 이후 개시하는 과세연도부터라" in y18["사유"]
    y19 = J(g(look, payment_date="2019-06-30", related_party=True))[k]
    assert y19["근거"].startswith("구 국제조세조정에 관한 법률 제14조·제15조의2") and "100분의 30" in y19["사유"]
    y21 = J(g(look, payment_date="2021-06-30", related_party=True))[k]
    assert y21["근거"].startswith("국제조세조정에 관한 법률 제22조·제24조·제26조") and "2배" in y21["사유"] and "30%" in y21["사유"] and "큰 쪽 하나만" in y21["사유"]
    no = J(g(look))[k]
    assert no["판정"].startswith("해당 없음") and "제22조제2항제3호" in no["사유"]           # 지급보증 차입도 대상


def test_beneficial_owner_facts_are_not_judged(look):
    r = g(look, remitted_to_third_party=True, pass_through_obligation=True)
    j = J(r)["절차 — 실질귀속자"]
    assert j["판정"] == "확인 필요" and "판정은 하지 않음" in j["사유"] and "서이46017-11059" in j["사유"]
    assert r["결정"]["구분"] == "확인 필요" and len(r["실질귀속자 해석"]) == 6
    assert any("백투백" in p for p in r["결정"]["전제"])


# ── 서버 등록 · 영문 키 · 조약 도구 안내 ───────────────────────────────────

def test_server_tool_and_english_keys(look):
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    names = list(tools)
    assert len(names) == 54 and names.index("interest_withholding_guide") == names.index("royalty_withholding_guide") + 1
    t = tools["interest_withholding_guide"]
    assert t.annotations.read_only_hint and t.description.startswith("Requirement guide for withholding on interest paid from Korea")
    assert "interest_withholding_guide" in tools["royalty_withholding_guide"].description
    assert "interest_withholding_guide" in tools["treaty_withholding_rates"].description and "interest_withholding_guide" in mcp.instructions
    args = {k: v for k, v in BASE.items()}
    r = _call("interest_withholding_guide", args)
    assert r["결정"]["구분"] == "10%" and r["다음에 부를 도구"][-1].startswith("서면 결과물")
    en = _call("interest_withholding_guide", {**args, "payment_kind": "loan_interest", "payer_type": "domestic", "lang": "en"})
    assert en["decision"]["type"] == "10%" and en["decision"]["total_rate_pct"] == 10.0
    assert {"judgments", "facts_to_check", "next_calculation", "no_basis", "verified_versions"} <= set(en)
    assert en["judgments"][0]["confidence"] == "verified" and en["next_calculation"][0]["tool"] == "계산 MCP nonresident_withholding"
    assert "error" in _call("interest_withholding_guide", {"payment_date": "2030-01-01"})


def test_treaty_rates_point_interest_to_this_tool(look):
    r = _call("treaty_withholding_rates", {"country": "싱가포르"})
    by = {x["소득"]: x for x in r["제한세율"]}
    assert "interest_withholding_guide" in by["이자"]["다음 단계"] and "royalty_withholding_guide" in by["사용료"]["다음 단계"]
    assert "다음 단계" not in by["배당"]


def test_treaty_rate_passed_even_when_equal_to_domestic_rate():
    """조약 제한세율이 국내 세율과 같은 20%여도 대상조세에 지방소득세가 있으면 합계 20%(법인세 20/1.1) — 계산 인자에 treaty_rate·treaty_includes_local_tax를 넘겨야 22%로 계산되지 않음."""
    fake = lambda c: {"국가": "가상국", "제한세율": [{"소득": "이자", "조문": "제11조", "세율": [{"세율(%)": 20.0, "항": "(2)", "근거": "made-up"}], "요건·기타": []}],
                      "지방소득세": {"대상조세 포함": True, "근거": "made-up"}}
    r = G.guide(**{**BASE, "recipient_country": "가상국", "treaty_lookup": fake})
    assert r["결정"]["구분"] == "20%" and r["결정"]["합계(%)"] == 20.0 and r["결정"]["법인세율(%)"] == 18.1818
    args = next(s for s in r["계산 다음 단계"] if s["도구"].endswith("nonresident_withholding"))["인자"]
    assert args["treaty_rate"] == 0.2 and args["treaty_includes_local_tax"] is True
    # 신청서가 없어 국내 세율로 결정되면 treaty_rate를 넘기지 않음
    r2 = G.guide(**{**BASE, "recipient_country": "가상국", "treaty_lookup": fake, "application_date": None, "application_before_payment": False})
    assert "treaty_rate" not in next(s for s in r2["계산 다음 단계"] if s["도구"].endswith("nonresident_withholding"))["인자"]
