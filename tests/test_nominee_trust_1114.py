"""nominee_trust_guide — 상속세 및 증여세법 제45조의2 연혁본 대조(국세법령정보시스템, 2026-11-14). Claude 작성. 외부 호출 없음.

대조한 시행본: 상증법 2016.1.1.(제13557호)·2018.9.21.(제15522호, 2018.12.31. 현재)·2019.1.1.(제16102호)·2020.1.1.(제16846호)·2021.1.1.(제17654호)·
2026.1.1.(제21219호)의 제4조의2·제6조·제45조의2·제47조·제55조, 부칙 제13557호 제3조, 제16102호 제3조·제6조, 제16846호 제2조.
보고서 골든 케이스 중 고친 것: G2(종전 의제분도 증여재산공제 없음 — 제55조①1호), G4·G6(2018.12.31. 이전 취득 해태분은 부칙 제6조로 종전 규정).
"""
from korean_tax_mcp import nominee_trust as N


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_overview_and_errors():
    o = N.guide()
    assert len(o["날짜에 따라 달라지는 것"]) == 4
    assert "error" in N.guide("타인명의", "비상장주식", "2015-12-31")                      # G19
    assert "error" in N.guide("타인명의", "비상장주식", "2024-13-01")
    assert "error" in N.guide("명의개서해태", "비상장주식")
    assert "error" in N.guide("타인명의", "주식")
    assert "error" in N.guide("명의개서해태", "비상장주식", acquisition_date="2025-03-01")   # 의제일 2027-01-01


def test_boundary_2018_12_31_vs_2019_03_01():
    a = N.guide("타인명의", "비상장주식", "2019-03-01")                                    # G1
    assert a["적용 규정"]["구분"] == "2019.1.1. 이후 체계" and a["납세의무"]["납세의무자"].startswith("실제소유자")
    assert a["납세의무"]["물적납세의무"].startswith("명의자") and "제6조②3호" in a["납세의무"]["과세 관할"]
    assert "합산배제" in a["납세의무"]["합산"] and "체납처분" in a["납세의무"]["물적납세의무"]
    b = N.guide("타인명의", "비상장주식", "2018-12-31")                                    # G2
    assert b["적용 규정"]["구분"] == "종전 체계" and b["납세의무"]["납세의무자"] == "명의자(수증자)"
    assert b["납세의무"]["연대납세의무"].startswith("실제소유자") and b["납세의무"]["물적납세의무"].startswith("없음")
    assert "증여재산공제" in b["세액 계산 요소"]["과세표준"] and "적용 안 됨" in b["세액 계산 요소"]["과세표준"]
    assert "강제징수" in N.guide("타인명의", "비상장주식", "2021-03-01")["납세의무"]["물적납세의무"]
    c = N.guide("타인명의", "비상장주식", "2018-03-01", nominee_kind="영리법인")
    assert c["납세의무"]["납세의무자"].startswith("실제소유자(영리법인 제외)") and c["납세의무"]["연대납세의무"].startswith("해당 없음")


def test_lapse_dates_and_transition():
    g4 = N.guide("명의개서해태", "비상장주식", acquisition_date="2017-05-10")
    assert g4["증여의제일"] == "2019-01-01" and g4["적용 규정"]["구분"] == "종전 체계" and "부칙 제6조" in g4["적용 규정"]["사유"]
    assert g4["증여시기"]["평가기준일"] == "2017-05-10" and "경과조치 주의" in g4
    g5 = N.guide("명의개서해태", "비상장주식", acquisition_date="2016-12-31")
    assert g5["증여의제일"] == "2018-01-01" and g5["적용 규정"]["구분"] == "종전 체계"
    g6 = N.guide("명의개서해태", "비상장주식", acquisition_date="2018-06-01")
    assert g6["증여의제일"] == "2020-01-01" and g6["적용 규정"]["구분"] == "종전 체계" and g6["증여시기"]["평가기준일"] == "2018-06-01"
    g6b = N.guide("명의개서해태", "비상장주식", acquisition_date="2019-01-02")
    assert g6b["증여의제일"] == "2021-01-01" and g6b["적용 규정"]["구분"] == "2019.1.1. 이후 체계"


def test_limitation():
    a = N.guide("타인명의", "비상장주식", "2019-03-01", filed=False)                       # G3
    assert a["부과제척기간"]["부과제척기간"].startswith("15년") and a["부과제척기간"]["법정신고기한"].startswith("2019-06-30")
    assert N.guide("타인명의", "비상장주식", "2019-03-01", filed=True)["부과제척기간"]["부과제척기간"].startswith("10년")
    assert N.due_date(__import__("datetime").date(2019, 11, 5)).isoformat() == "2020-02-29"


def test_purpose_presumption_and_rebuttal():
    r = N.guide("타인명의", "상장주식", "2024-03-01", non_tax_purposes=["대주주 공시요건 회피"])      # G10
    assert r["증여의제"]["판정"] == "반증 가능" and J(r)["조세회피목적"]["판정"].startswith("반증")
    assert any("적부-대구청" in c["사건"] for c in J(r)["조세회피목적"]["판례"])
    r = N.guide("타인명의", "비상장주식", "2024-03-01", non_tax_purposes=["발기인 수 충족"], avoided_taxes=["과점주주 간주취득세"])
    assert r["증여의제"]["판정"] == "해당" and J(r)["조세회피목적"]["판정"].startswith("조세회피목적 인정")
    r = N.guide("명의개서해태", "비상장주식", acquisition_date="2020-02-01", exception="양도세신고_변경신고")
    assert J(r)["조세회피목적 추정"]["판정"] == "추정하지 않음" and r["증여의제"]["판정"].startswith("해당(과세관청")
    r = N.guide("명의개서해태", "비상장주식", acquisition_date="2020-02-01", exception="상속세신고_포함", inheritance_return_date="2015-10-01")
    assert J(r)["조세회피목적 추정"]["판정"] == "추정함"                                    # 부칙 제13557호 제3조②
    r = N.guide("명의개서해태", "비상장주식", acquisition_date="2020-02-01", exception="상속세신고_포함", inheritance_return_type="기한후", foreknown=True)
    assert J(r)["조세회피목적 추정"]["판정"] == "추정함"


def test_not_deemed_cases():
    assert N.guide("타인명의", "비상장주식", "2022-01-10", agreement="명의도용")["증여의제"]["판정"] == "해당 없음"      # G11
    r = N.guide("타인명의", "비상장주식", "2022-01-10", origin="합병신주")                                            # G12
    assert r["증여의제"]["판정"].startswith("해당 없음") and any("2016두30644" in c["사건"] for p in r["판정"] for c in p.get("판례", []))
    r = N.guide("명의개서해태", "비상장주식", acquisition_date="2020-05-01", origin="신탁자사망_상속")                  # G13
    assert r["증여의제"]["판정"] == "해당 없음" and "계산 다음 단계" not in r
    assert N.guide("타인명의", "비상장주식", "2022-01-10", exception="양도담보")["증여의제"]["판정"] == "해당 없음"
    assert N.guide("타인명의", "차량", "2022-01-10", exception="신탁재산")["증여의제"]["판정"] == "해당 없음"
    assert N.guide("타인명의", "비상장주식", "2022-01-10", origin="유상증자신주")["증여의제"]["판정"] == "해당"
    assert N.guide(asset_type="예금·금전")["증여의제"]["판정"] == "해당 없음"


def test_real_estate_and_restore():
    r = N.guide("타인명의", "토지", "2020-05-01")                                          # G14
    assert r["증여의제"]["판정"] == "해당 없음" and "부동산 실권리자명의 등기에 관한 법률" in r["부동산"]
    assert any("미확인" in x for x in r["한계"])
    r = N.guide("타인명의", "비상장주식", "2020-05-01", restored_to="실제소유자")             # G18
    assert r["실명 환원"]["판정"] == "증여 아님"
    assert N.guide("타인명의", "비상장주식", "2020-05-01", restored_to="제3자", restored_date="2023-01-01")["실명 환원"]["판정"] == "새 증여"


def test_register_and_next_step():
    r = N.guide("타인명의", "비상장주식", "2020-05-01", no_shareholder_register=True, asset_value=300_000_000, filed=False)
    assert "대통령령" in r["증여시기"]["주주명부가 없을 때"]["증여일"]
    assert "해석" in N.guide("타인명의", "비상장주식", "2019-05-01", no_shareholder_register=True)["증여시기"]["주주명부가 없을 때"]["증여일"]
    nxt = r["계산 다음 단계"]
    assert nxt["도구"].endswith("nominee_gift_tax") and nxt["인자"] == {"deemed_gift_date": "2020-05-01", "trust_type": "타인명의", "asset_value": 300_000_000, "filed": False}
    assert any(x["항목"] == "과점주주 제2차 납세의무" for x in r["법인 연계"])
    assert "법인 연계" not in N.guide("타인명의", "차량", "2020-05-01")
