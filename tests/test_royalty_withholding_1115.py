"""royalty_withholding_guide · treaty_withholding_rates 세율별 근거 · 변경된 판례 표시 — 원문 대조 테스트(2026-11-15, Claude 작성). 외부 호출 없음.

대조한 원문(조회일 2026-11-15): 법인세법 제93조 2019.12.31.·2020.1.1.·2026.7.1. 시행본과 부칙 <제16833호> 제8조, 제98조·제98조의6·제98조의7·제120조의2(2026.7.1.),
부칙 <제21217호, 2025.12.23.> 제13조, 법인세법 시행령 제137조·제138조의7(2026.10.1.), 기본통칙 98-0…2(2024년 고시본), 지방세법 제103조의52(2026.7.1.),
국제조세조정에 관한 법률 시행령 제36조(2026.2.27.), 한미 조세조약 제1조·제6조·제14조·제17조, 대법원 2025. 9. 18. 선고 2021두59908 전원합의체 판결.
조세조약은 같은 날 국세법령정보시스템 응답에서 필요한 조문만 남긴 fixtures/royalty_treaties.json(미국·베트남)과 fixtures/b_law_treaties.json(일본·싱가포르)을 되돌려 준다.
베트남은 개정 의정서(2021.1.20.)를 뺀 본문만 넣었다 — 한 항 안의 두 세율이 각자 목 문장을 근거로 갖는지만 본다.
"""
import asyncio
import json
import os
import re

import pytest

from korean_tax_mcp import ntis, overruled
from korean_tax_mcp import royalty_withholding as G
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
def treaties(monkeypatch):
    ntis.treaties.cache_clear()
    by_id = {x["txaAgrmBscId"]: x["txaAgrmNtnNm"] for x in TREATY["목록"]}

    def fake_act(action, param, timeout=40):
        if action == "ASISTC001MR01":
            return {"txaTraDVOList": TREATY["목록"]}
        if action == "ASISTC002MR01":
            return {"txaTraDVOList": TREATY["조문"][by_id[param["txaAgrmBscId"]]]}
        raise AssertionError(f"예상 못 한 호출 {action}")
    monkeypatch.setattr(ntis, "_act", fake_act)
    yield lambda c: ntis.withholding_rates(c, "사용료")
    ntis.treaties.cache_clear()


def J(r):
    return {p["항목"]: p for p in r["판정"]}


# 미국 모회사에 특허 사용료, 요건을 모두 확인한 기본 사실
US = dict(payment_date="2026-06-30", recipient_country="미국", licensed=["특허"], used_in_korea=True, attributable_to_korean_pe=False,
          application_before_payment=True, beneficial_owner_confirmed=True, related_party=True)


def g(**kw):
    return G.guide(**{**US, **kw})


# ── 안내 · 입력 오류 ───────────────────────────────────────────────────────

def test_overview_and_errors():
    r = G.guide()
    assert len(r["요소"]) == 9 and len(r["결정 트리"]) == 7 and len(r["지급일별로 달라지는 것"]) == 4
    assert len(r["미등록 특허 판례"]["전원합의체 판결"]["변경된 판례"]) == 8
    for bad in (dict(payment_date="2015-12-31"), dict(payment_date="2027-01-01"), dict(payment_date="2026/01/01"),
                dict(payment_date="2026-01-01", licensed=["영업권"]), dict(payment_date="2026-01-01", recipient_type="조합"),
                dict(payment_date="2026-01-01", net_of_tax="전부"), dict(payment_date="2026-01-01", licensed=["특허"], allocation={"용역": 1}),
                dict(payment_date="2026-01-01", application_date="어제"), dict(payment_date="2026-01-01", amount_krw=-1)):
        assert "error" in G.guide(**bad), bad


def test_unknown_facts_are_not_guessed():
    """사실을 하나도 안 주면 세율을 내지 않는다."""
    r = G.guide(payment_date="2026-06-30")
    assert r["결정"]["구분"] == "확인 필요"
    j = J(r)
    for k in ("소득 구분", "국내원천", "조약 제한세율", "절차 — 실질귀속자", "절차 — 제한세율 적용신청서", "세금부담 약정", "이전가격", "부가가치세 대리납부", "관세 과세가격"):
        assert j[k]["판정"].startswith("확인 필요"), (k, j[k]["판정"])
    r = G.guide(payment_date="2026-06-30", recipient_country="미국", licensed=["특허"])
    assert r["결정"]["구분"] == "확인 필요" and len(r["결정"]["막힌 사실"]) == 3
    assert any("15%" in x for x in r["결정"]["가능한 결과"]) and any("20%" in x for x in r["결정"]["가능한 결과"])


# ── 한미: 세율 결정 ────────────────────────────────────────────────────────

def test_us_patent_15_percent():
    """한미 제14조(1) 15% + 지방소득세(법인세의 10%, 조약 제1조에 지방세 없음) = 16.5%. 조약 조회 없이도 확인값으로 답한다."""
    d = g()["결정"]
    assert d["구분"] == "15%" and d["법인세율(%)"] == 15.0 and d["지방소득세율(%)"] == 1.5 and d["합계(%)"] == 16.5
    assert "제14조(1)" in d["결론"] and d["세율 확신도"] == "확인함"
    assert any("제17조" in p for p in d["전제"]) and any("제14조(5)" in p for p in d["전제"])
    j = J(g())
    assert j["국내 세율"]["판정"] == "20%" and j["국내 세율"]["근거"] == "법인세법 제98조제1항제6호"
    assert "제98조의7제1항제1호" in j["지방소득세"]["근거"] and "지방세법 제103조의52" in j["지방소득세"]["근거"]
    assert "제103조의29제1항은 내국법인" in j["지방소득세"]["사유"]


def test_copyright_vs_patent():
    d = g(licensed=["저작권"])["결정"]
    assert d["구분"] == "10%" and d["합계(%)"] == 11.0 and "제14조(2)" in d["결론"]
    for k in ("노하우", "상표", "know-how", "trademark"):
        assert g(licensed=[k])["결정"]["구분"] == "15%", k


def test_software_rate_stays_unconfirmed():
    """소프트웨어의 한미 10% 적용 여부는 미확인 — 세율을 정하지 않는다."""
    r = g(licensed=["소프트웨어"])
    assert r["결정"]["구분"] == "확인 필요" and len(r["결정"]["가능한 결과"]) == 2
    assert J(r)["조약 제한세율(소프트웨어)"]["확신도"] == "미확인"
    assert J(r)["소득 구분(소프트웨어)"]["판정"] == "확인 필요"


def test_registered_vs_unregistered_patent():
    """국내 등록 여부는 결론을 바꾸지 않는다(대법원 2025. 9. 18. 2021두59908 전원합의체)."""
    reg, unreg = g(patent_registered_in_korea=True), g(patent_registered_in_korea=False)
    assert reg["결정"]["구분"] == unreg["결정"]["구분"] == "15%"
    ju = J(unreg)["국내원천"]
    assert ju["판정"] == "국내원천소득" and "2021두59908" in ju["근거"] and "미등록" in ju["사유"] and ju["확신도"] == "확인함"
    assert "다목 문언을 직접 해석한 대법원 판결은 찾지 못했고(미확인)" in ju["사유"]
    assert "2021두59908" in " ".join(unreg["결정"]["경로"])
    assert "등록 여부는 결론을 바꾸지 않음" in J(reg)["국내원천"]["사유"]


def test_item_c_applies_to_payments_from_2020():
    """제93조제8호 다목은 2020.1.1. 이후 지급하는 소득분부터(부칙 <제16833호> 제8조) — 그 전은 단서 후문."""
    before, after = g(payment_date="2019-12-31", patent_registered_in_korea=False), g(payment_date="2020-01-01", patent_registered_in_korea=False)
    jb, ja = J(before)["국내원천"], J(after)["국내원천"]
    assert "단서 후문" in jb["근거"] and "다목" not in jb["근거"] and "전원합의체 판결이 바로 이 단서 후문을 해석" in jb["사유"]
    assert "다목" in ja["근거"] and "제16833호" in ja["근거"] and "단서 후문" not in ja["근거"]
    assert before["결정"]["구분"] == after["결정"]["구분"] == "15%"
    assert "기준일 주의" in before and "기준일 주의" in after and "기준일 주의" not in g()


def test_foreign_use_under_use_based_treaty():
    r = g(used_in_korea=False)
    assert r["결정"]["구분"] == "0%" and r["결정"]["합계(%)"] == 0.0 and "제6조(3)" in " ".join(r["결정"]["경로"])
    assert J(r)["국내원천"]["확신도"] == "유추"            # 2020.1.1. 이후: 국외분 제외 근거가 조약뿐이라는 것은 유추
    assert J(g(used_in_korea=False, payment_date="2019-06-30"))["국내원천"]["확신도"] == "확인함"   # 구법 단서 본문
    r = g(used_in_korea=None)
    assert r["결정"]["구분"] == "확인 필요" and r["결정"]["막힌 사실"] == ["국내 사용 여부(used_in_korea)"]


def test_application_before_or_after_payment():
    """신청서를 지급 전에 못 받으면 20%(제98조의6제3항), 5년 내 경정청구(2026년부터 제5항)."""
    d = g(application_before_payment=False)["결정"]
    assert d["구분"] == "20%" and d["법인세율(%)"] == 20.0 and d["합계(%)"] == 22.0
    path = " ".join(d["경로"])
    assert "제98조의6제3항" in path and "제98조의6제5항" in path
    assert g(application_date="2026-06-30")["결정"]["구분"] == "15%"       # 지급일 당일까지 수령
    assert g(application_before_payment=None, application_date="2026-07-01")["결정"]["구분"] == "20%"   # 지급 뒤 수령
    assert g(beneficial_owner_confirmed=False)["결정"]["구분"] == "20%"
    r = g(application_before_payment=None)
    assert r["결정"]["구분"] == "확인 필요" and "application_before_payment" in r["결정"]["막힌 사실"][0]


def test_refund_claim_paragraph_moved_in_2026():
    j26, j25 = J(g(application_before_payment=False))["절차 — 경정청구"], J(g(payment_date="2025-12-31", application_before_payment=False))["절차 — 경정청구"]
    assert j26["근거"].startswith("법인세법 제98조의6제5항") and "제4항은 신청서 세무서 제출의무" in j26["사유"]
    assert "제4항(2025.12.31. 이전 시행본)" in j25["근거"] and "제5항" in j25["근거"]
    assert "제4항 — 2026.1.1.부터 제5항" in " ".join(g(payment_date="2025-12-31", application_before_payment=False)["결정"]["경로"])


def test_filing_duty_from_2026_applications():
    """제98조의6제4항(2025.12.23. 신설)은 2026.1.1. 이후 제한세율 적용을 신청하는 경우부터(부칙 <제21217호> 제13조)."""
    k = "절차 — 신청서 세무서 제출"
    a = J(g(application_date="2026-02-01"))[k]
    assert a["판정"] == "제출 의무" and "2027년 2월 말일" in a["사유"] and a["확신도"] == "확인함" and "제21217호" in a["근거"]
    b = J(g(application_date="2025-11-01"))[k]
    assert b["판정"] == "의무 없음으로 읽힘" and b["확신도"] == "유추"
    assert J(g())[k]["판정"] == "확인 필요"                                   # 수령일을 모르면 정하지 않음
    assert J(g(payment_date="2025-12-31"))[k]["판정"] == "해당 없음"
    assert J(g())["절차 — 지급명세서"]["판정"] == "2027년 2월 말일까지 제출"


def test_services_in_or_out_of_korea():
    kw = dict(payment_date="2026-03-01", recipient_country="미국", licensed=["용역"])
    out = G.guide(services_performed_in_korea=False, **kw)
    assert out["결정"]["구분"] == "0%" and "제6조(6)" in " ".join(out["결정"]["경로"])
    assert any("노하우" in p for p in out["결정"]["전제"])
    inn = G.guide(services_performed_in_korea=True, **kw)
    assert inn["결정"]["구분"] == "20%" and inn["결정"]["합계(%)"] == 22.0 and "제98조제1항제4호" in " ".join(inn["결정"]["경로"])
    assert any("유추" in p and "제98조의4" in p for p in inn["결정"]["전제"])
    assert J(inn)["국내원천(용역)"]["확신도"] == "유추"
    assert G.guide(**kw)["결정"]["구분"] == "확인 필요"
    assert "미등록 특허 판례" in out and "안내" in out["미등록 특허 판례"]


def test_net_of_tax_gross_up():
    """기본통칙 98-0…2: 과세표준 = 약정액 ÷ (1 − 세율). 15% → 0.15/0.85 = 17.65%. 지방소득세 포함 0.165/0.835 = 19.76%(유추)."""
    a = g(net_of_tax="법인세")
    assert a["결정"]["순액 약정 반영"] == {"과세표준": "약정액 ÷ (1 − 0.15)", "순액 기준 실효 법인세율(%)": 17.65, "확신도": "확인함"}
    assert J(a)["세금부담 약정"]["확신도"] == "확인함" and "117,647,058" in J(a)["세금부담 약정"]["사유"]
    b = g(net_of_tax="corporate_and_local_tax")
    assert b["결정"]["순액 약정 반영"] == {"과세표준": "약정액 ÷ (1 − 0.165)", "순액 기준 실효 세율(법인세+지방소득세, %)": 19.76, "확신도": "유추"}
    assert J(b)["세금부담 약정"]["확신도"] == "유추" and "119,760,479" in J(b)["세금부담 약정"]["사유"]
    assert "net_of_tax" in b["다음에 부를 도구"][0] and "treaty_rate=0.15" in b["다음에 부를 도구"][0]
    assert J(g(net_of_tax="없음"))["세금부담 약정"]["판정"] == "해당 없음" and "순액 약정 반영" not in g(net_of_tax="없음")["결정"]
    assert J(g())["세금부담 약정"]["판정"] == "확인 필요"


def test_pe_sale_and_mixed_contract():
    assert g(attributable_to_korean_pe=True)["결정"]["구분"] == "기타"
    s = G.guide(payment_date="2026-05-01", recipient_country="미국", licensed=["권리 양도"], sale_price_contingent=False)
    assert s["결정"]["구분"] == "기타" and "2022두66002" in " ".join(s["결정"]["경로"])
    assert J(s)["소득 구분(권리 양도)"]["판정"] == "조약상 사용료 아님"
    assert G.guide(payment_date="2026-05-01", recipient_country="미국", licensed=["권리 양도"])["결정"]["구분"] == "확인 필요"
    m = g(licensed=["patent", "services"], services_performed_in_korea=False, allocation={"patent": 0.7, "services": 0.3})
    assert m["결정"]["구분"] == "혼합" and [c["구분"] for c in m["결정"]["구성요소"]] == ["15%", "0%"] and m["결정"]["안분(입력값)"] == {"특허": 0.7, "용역": 0.3}
    assert J(m)["소득 구분(혼합계약)"]["판정"] == "구성요소별 안분"
    assert J(g(licensed=["특허", "용역"], services_performed_in_korea=False))["소득 구분(혼합계약)"]["판정"] == "확인 필요"


def test_procedure_other_taxes_and_thresholds():
    j = J(g(accrued_unpaid=True))["절차 — 원천징수 시기"]
    assert j["확신도"] == "유추" and "시행령 제137조" in j["근거"] and "미확인" in j["사유"]
    assert "다음 달 10일" in J(g())["절차 — 원천징수·납부"]["판정"]
    # 국제거래명세서 면제: 무형자산거래 1억원 이하(국조령 제36조) — 1억원은 충족, 1원 넘으면 제출 대상
    assert "1억원 이하 기준은 충족" in J(g(amount_krw=100_000_000))["이전가격"]["사유"]
    assert "초과 → 국제거래명세서 제출 대상" in J(g(amount_krw=100_000_001))["이전가격"]["사유"]
    assert "1,000,000원(500,000원)" in J(g(amount_krw=100_000_000))["절차 — 지급명세서"]["사유"]   # 1%·0.5%
    assert J(g(related_party=False))["이전가격"]["판정"] == "해당 없음" and J(g(related_party=None))["이전가격"]["판정"] == "확인 필요"
    assert J(g(payer_vat_exempt_business=True))["부가가치세 대리납부"]["판정"].startswith("대리납부 대상")
    assert J(g(payer_vat_exempt_business=False))["부가가치세 대리납부"]["판정"].startswith("대리납부 의무 없음")
    assert J(g(related_to_imported_goods=True))["관세 과세가격"]["판정"].startswith("확인 필요")
    assert J(g(related_to_imported_goods=False))["관세 과세가격"]["판정"].startswith("해당 없음")


def test_deleted_article_not_cited_and_labels_kept():
    """국조법 제28조(2018.12.31. 삭제)는 근거로 쓰지 않는다. 확신도는 조사 표기 그대로."""
    r = g(patent_registered_in_korea=False, net_of_tax="법인세+지방소득세", accrued_unpaid=True, amount_krw=100_000_000)
    assert not [p for p in r["판정"] if "제28조" in p["근거"]]
    assert any("제28조는 2018.12.31. 삭제" in x for x in r["한계"])
    assert {p["확신도"] for p in r["판정"]} <= {"확인함", "유추", "미확인", "자동 추출(조문 확인 필요)"}
    u = r["미등록 특허 판례"]
    assert [x["확신도"] for x in u["남은 불확실성"]] == ["미확인", "미확인", "유추"]
    assert u["전원합의체 판결"]["확신도"] == "확인함" and u["후속"][3]["확신도"] == "확인함(요지만)"
    assert len(r["미확인"]) == 12
    names = " ".join(r["다음에 부를 도구"])
    for t in ("nonresident_withholding", "treaty_withholding_rates", "tax_treaty", "tax_memo_guide"):
        assert t in names, t


def test_individual_recipient_is_not_decided_under_corporate_tax_act():
    r = g(recipient_type="individual")
    j = J(r)
    assert j["국내 세율"]["판정"] == "확인 필요" and j["지방소득세"]["판정"] == "확인 필요" and j["절차"]["확신도"] == "미확인"
    assert r["결정"]["지방소득세율(%)"] == "확인 필요"
    assert g(recipient_type="개인", application_before_payment=False)["결정"]["구분"] == "확인 필요"


# ── 다른 나라: 조약 조회 결과로 ─────────────────────────────────────────────

def test_other_countries_use_treaty_lookup(treaties):
    jp = g(recipient_country="일본", treaty_lookup=treaties)
    d = jp["결정"]            # 한일: 10%, 대상조세에 주민세 포함 → 법인세 10/11, 지방소득세 1/11(제98조의7제1항제2호)
    assert d["구분"] == "10%" and d["합계(%)"] == 10.0 and d["법인세율(%)"] == 9.0909 and d["지방소득세율(%)"] == 0.9091
    assert d["세율 확신도"] == "자동 추출(조문 확인 필요)" and "tax_treaty(country='일본', article='제12조')" in " ".join(d["경로"])
    assert J(jp)["지방소득세"]["판정"] == "제한세율 안에 포함" and "제98조의7제1항제2호" in J(jp)["지방소득세"]["근거"]
    assert "treaty_rate=0.1," in jp["다음에 부를 도구"][0]
    # 지급자 기준 원천 규칙(싱가포르 제12조(5)): 국외 사용이어도 0%로 끝나지 않는다
    sg = g(recipient_country="싱가포르", used_in_korea=False, treaty_lookup=treaties)
    assert sg["결정"]["구분"] == "5%" and J(sg)["국내원천"]["확신도"] == "유추"
    # 한 조문에 세율이 둘(베트남 5%·15%)이면 고르지 않는다
    vn = g(recipient_country="베트남", treaty_lookup=treaties)
    assert vn["결정"]["구분"] == "확인 필요" and "5%, 15%" in vn["결정"]["결론"]
    # 조약 체결국이 아니면 국내 세율
    none = g(recipient_country="가나다국", treaty_lookup=treaties)
    assert none["결정"]["구분"] == "20%" and J(none)["조약 제한세율"]["판정"] == "조약 없음"
    # 한미는 조회해도 같은 답
    us = g(treaty_lookup=treaties)
    assert us["결정"]["구분"] == "15%" and us["조약 조회"].startswith("미국 조세조약 원문 조회함")


def test_treaty_lookup_failure_is_not_guessed():
    def boom(c): raise RuntimeError("연결 실패")
    r = g(recipient_country="일본", treaty_lookup=boom)
    assert r["결정"]["구분"] == "확인 필요" and J(r)["조약 제한세율"]["판정"] == "확인 필요" and r["조약 조회"].startswith("조회 실패")
    us = g(treaty_lookup=boom)      # 한미는 조사에서 확인한 값으로 답하고 조회 실패를 알림
    assert us["결정"]["구분"] == "15%" and "조사 시점" in us["조약 조회"]


# ── treaty_withholding_rates: 세율별 근거·요건·지방소득세 ────────────────────

def test_us_royalty_rates_carry_their_own_basis(treaties):
    r = _call("treaty_withholding_rates", {"country": "미국", "income": "사용료"})
    roy = r["제한세율"][0]
    r15, r10 = roy["세율"]
    assert (r15["세율(%)"], r15["항"], r10["세율(%)"], r10["항"]) == (15.0, "(1)", 10.0, "(2)")
    assert r15["근거"] != r10["근거"]
    assert "shall not exceed 15 percent" in r15["근거"] and "10 percent" not in r15["근거"] and r15["근거"].endswith("paragraphs (2) and (3).")
    assert r10["근거"].startswith("Royalties derived from copyrights") and "10 percent of the gross amount of such royalties" in r10["근거"] and "15 percent" not in r10["근거"]
    assert "15퍼센트" in r15["근거(국문)"] and "10퍼센트" in r10["근거(국문)"] and "저작권" in r10["근거(국문)"]
    conds = {c["조항"]: c for c in roy["요건·기타"] if "조항" in c}
    assert set(conds) == {"제14조(3)", "제14조(5)", "제6조(3)", "제17조"}, set(conds)
    assert conds["제14조(3)"]["구분"].startswith("고정사업장") and conds["제14조(5)"]["구분"].startswith("특수관계")
    assert conds["제6조(3)"]["구분"] == "원천 규칙" and "only if paid for the use of" in conds["제6조(3)"]["근거"]
    assert conds["제17조"]["구분"].startswith("혜택 배제") and "25퍼센트" in conds["제17조"]["근거(국문)"]
    assert "royalty_withholding_guide" in roy["다음 단계"] and "세율 안내" in roy
    lt = r["지방소득세"]
    assert lt["대상조세 포함"] is False and "제98조의7" in lt["안내"] and "지방세법 제103조의52제1항" in lt["안내"]


def test_us_dividend_and_interest_still_extracted(treaties):
    r = _call("treaty_withholding_rates", {"country": "미국"})
    by = {x["소득"]: x for x in r["제한세율"]}
    assert [x["세율(%)"] for x in by["배당"]["세율"]] == [15.0, 10.0]      # (b)(ii)의 25·50퍼센트는 세율이 아님
    assert [x["세율(%)"] for x in by["이자"]["세율"]] == [12.0]
    assert {c["조항"] for c in by["배당"]["요건·기타"] if "조항" in c} >= {"제12조(3)", "제6조(1)", "제17조"}
    assert "다음 단계" not in by["배당"]


def test_other_countries_keep_working(treaties):
    jp = _call("treaty_withholding_rates", {"country": "일본", "income": "사용료"})["제한세율"][0]
    assert [x["세율(%)"] for x in jp["세율"]] == [10.0] and jp["세율"][0]["항"] == "(2)"
    assert {c["조항"]: c["구분"] for c in jp["요건·기타"]}["제12조(4)"] == "원천 규칙"
    sg = _call("treaty_withholding_rates", {"country": "싱가포르", "income": "사용료"})
    assert [x["세율(%)"] for x in sg["제한세율"][0]["세율"]] == [5.0] and sg["지방소득세"]["대상조세 포함"] is True
    assert {c["조항"] for c in sg["제한세율"][0]["요건·기타"]} == {"제12조(4)", "제12조(5)", "제12조(6)"}   # 이 fixture는 제26조 본문을 비워 둠
    vn = _call("treaty_withholding_rates", {"country": "베트남", "income": "사용료"})["제한세율"][0]["세율"]
    assert [x["세율(%)"] for x in vn] == [5.0, 15.0]
    assert vn[0]["근거"].startswith("a) 5 per cent") and "15 per cent" not in vn[0]["근거"] and vn[1]["근거"] == "b) 15 per cent of the gross amount of the royalties in all other cases."


def test_treaty_english_keys_us(treaties):
    r = _call("treaty_withholding_rates", {"country": "미국", "income": "royalties", "lang": "en"})

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k; yield from keys(v)
        elif isinstance(o, list):
            for v in o: yield from keys(v)
    assert not [k for k in keys(r) if re.search(r"[가-힣]", k)], r
    assert r["withholding_caps"][0]["rates"][1]["basis_ko"] and r["withholding_caps"][0]["conditions"][0]["clause"] == "제14조(3)"


# ── 변경된 판례 표시 ───────────────────────────────────────────────────────

CASES = ["대법원-91-누-6887", "대법원-2005-두-8641", "대법원-2012-두-18356", "대법원-2013-두-9670",
         "대법원-2016-두-42883", "대법원-2018-두-36592", "대법원-2019-두-50946", "대법원-2019-두-47100"]


def test_overruled_table_is_the_eight_cases_listed_in_the_judgment():
    assert len(overruled.OVERRULED) == 8
    for c in CASES:
        assert overruled.flag(c).startswith("변경됨 — 대법원 2025.9.18. 2021두59908 전원합의체"), c
    assert overruled.flag("대법원 2014. 11. 27. 선고 2012두18356 판결") and overruled.flag("대법원 1992. 5. 12. 선고 91누6887 판결")
    for c in ("대법원-2021-두-59908", "대법원-2022-두-30744", "대법원-2015-두-52418", "수원지방법원-2018-구합-66587", "수원고등법원-2012-누-18356",
              "조심-2012-두-18356", "서면-2018-국제세원-2267", ""):
        assert overruled.flag(c) is None, c


def test_search_and_document_flag_overruled_cases(monkeypatch):
    rows = [{"DOC_ID": f"20000000000000{i:04d}", "NTST_DCM_DSCM_CNTN": c, "TTL": "국내 미등록 특허권 사용료", "GIST_CNTN": "", "NTST_DCM_RGT_DT": "20141127"}
            for i, c in enumerate(CASES + ["대법원-2021-두-59908", "수원지방법원-2018-구합-66587"])]

    def fake_act(action, param, timeout=40):
        if action == "ASEISA001MR01":
            return {"searchResultVO": {"collectionList": [{"nameKr": "판례", "totalCount": len(rows), "resultList": rows}]}}
        if action == "ASIQTB002PR01":
            return {"dcmDVO": {"ntstDcmDscmCntn": "대법원-2012-두-18356", "ntstDcmTtl": "화해대가", "ntstDcmCntn": "본문"}}
        raise AssertionError(action)
    monkeypatch.setattr(ntis, "_act", fake_act)
    r = _call("search_tax_rulings", {"query": "미등록 특허", "kinds": ["판례"], "n": 30})["결과"]
    flagged = [x["문서번호"] for x in r if "판례 변경" in x]
    assert flagged == CASES
    assert all(x["판례 변경"].startswith("변경됨 — 대법원 2025.9.18. 2021두59908 전원합의체") for x in r if "판례 변경" in x)
    assert "판례 변경" in _call("get_tax_ruling", {"id": "200000000000000002"})
    en = _call("search_tax_rulings", {"query": "미등록 특허", "kinds": ["판례"], "n": 30, "lang": "en"})["results"]
    assert sum("overruled_by" in x for x in en) == 8


# ── 서버 등록 ──────────────────────────────────────────────────────────────

def test_server_tool(treaties):
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    assert names.index("royalty_withholding_guide") == names.index("permanent_establishment_guide") + 1
    r = _call("royalty_withholding_guide", {"payment_date": "2026-06-30", "recipient_country": "미국", "licensed": ["patent"], "patent_registered_in_korea": False,
                                             "used_in_korea": True, "attributable_to_korean_pe": False, "application_before_payment": True,
                                             "beneficial_owner_confirmed": True, "related_party": True})
    assert r["결정"]["구분"] == "15%" and r["결정"]["합계(%)"] == 16.5
    assert "error" in _call("royalty_withholding_guide", {"payment_date": "2030-01-01"})
    assert len(_call("royalty_withholding_guide", {})["결정 트리"]) == 7


def test_server_tool_without_network(monkeypatch):
    """조약 조회가 막혀도(오프라인) 한미는 확인값으로 답한다."""
    def boom(*a, **k): raise RuntimeError("blocked")
    monkeypatch.setattr(ntis, "withholding_rates", boom)
    r = _call("royalty_withholding_guide", {"payment_date": "2026-06-30", "recipient_country": "미국", "licensed": ["특허"], "used_in_korea": True,
                                             "application_before_payment": False, "beneficial_owner_confirmed": True})
    assert r["결정"]["구분"] == "20%" and r["조약 조회"].startswith("조회 실패")
