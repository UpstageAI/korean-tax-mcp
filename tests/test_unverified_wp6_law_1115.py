"""미확인 꼬리표 정리(2026-11-15, Claude 작성) — 국내사업장 시행령·부칙, 거주자 판례 4건, 이전가격 결정례 본문 대조. 외부 호출 없음.
대조 원문(법제처 DRF 연혁본·국세법령정보시스템, 원자료는 저장소 밖 raw_wp6):
  · 법인세법 시행령 제133조 — 2016(20161129)·2017(20170726)·2018(20181101)·2019(20190916)·2020(20201210)·2021(20211230)·2022(20221027)·2023(20231221)·
    2024(20241112)·2025(20251128) 연말 시행본, 20260227·20261001 시행본. 제1항제2호는 2025년까지 '주로 특정 외국법인만을 위하여',
    2026.2.27.(대통령령 제36130호)부터 '전적으로 또는 거의 전적으로 … 특수관계가 있는 외국법인을 위하여'. 제3항은 2019.2.12.(대통령령 제29529호) 신설.
  · 소득세법 시행령 제180조 — 2016(20161205)~2025(20251128)·2026(20261001) 시행본. 제2항은 2019.2.12.(대통령령 제29523호) 신설, 제1항제2호는 2026.2.27.(대통령령 제36129호) 개정.
  · 소득세법 제120조 2020.1.1. 시행본(법률 제16834호) — 제4항·제5항 '예비적 또는 보조적'.
  · 부칙: 법인세법 제16008호·제16833호 제2조(시행 이후 개시하는 사업연도분부터), 소득세법 제16104호·제16834호 제2조제1항(시행 이후 발생하는 소득분부터),
    법인세법 시행령 제36130호·소득세법 시행령 제36129호(공포한 날부터 시행, 제133조·제180조 적용례 없음).
  · 판례: 대법원 2017두59352·2014두6869·2010두28946·2010두22719 판결문과 하급심 판결문(국세법령정보시스템).
  · 대법원 2015. 2. 26. 선고 2014두13959 판결문과 원심 서울고등법원 2014. 10. 10. 선고 2013누27786 판결문(국세법령정보시스템, 2026-11-15)."""
import json
import os

from korean_tax_mcp import permanent_establishment as G
from korean_tax_mcp import tp_report as R
from korean_tax_mcp.residency import judgment as RJ

SPECIFIC, RELATED = "주로 특정 외국법인만을 위한 독립대리인", "특수관계 외국법인을 위한 독립대리인"


def J(r):
    return {p["항목"]: p for p in r["판정"]}


def test_decree_wording_boundary_2025_2026():
    # 2019~2025: 제2호 문언은 2018년까지와 같음(개정 전 도구는 2019년부터 2026 문언을 보여 줬음)
    for y in (2016, 2019, 2022, 2025):
        t = G.guide(y)["요소"]["대통령령으로 정하는 자"]
        assert "주로 특정 외국법인만을 위하여" in t and "전적으로 또는 거의 전적으로" not in t and "확인 필요" not in t
    t = G.guide(2026)["요소"]["대통령령으로 정하는 자"]
    assert "전적으로 또는 거의 전적으로" in t and "2026.2.27." in t and "제36130호" in t and "2026.2.26.까지는 종전 문언" in t
    # 비거주자: 소득세법 시행령 제180조(2018년까지 항 없음, 2019.2.12. 개정으로 제1항·제2항)
    assert G.guide(2018, taxpayer="비거주자")["요소"]["대통령령으로 정하는 자"].startswith("소득세법 시행령 제180조:")
    t = G.guide(2025, taxpayer="비거주자")["요소"]["대통령령으로 정하는 자"]
    assert t.startswith("소득세법 시행령 제180조제1항:") and "주로 특정비거주자만을 위하여" in t
    t = G.guide(2026, taxpayer="비거주자")["요소"]["대통령령으로 정하는 자"]
    assert "특수관계가 있는 비거주자를 위하여" in t and "제36129호" in t


def test_independent_agent_judgment_by_year():
    key = "대통령령으로 정하는 자(독립대리인)"
    # 2025년까지: '주로 특정 외국법인만을 위한' 독립대리인이 요건
    r = J(G.guide(2025, agent_types=[SPECIFIC]))[key]
    assert r["판정"] == "국내사업장 있음" and r["근거"] == "법인세법 제94조제3항, 법인세법 시행령 제133조제1항제2호·제2항"
    r = J(G.guide(2025, agent_types=[RELATED]))[key]
    assert r["판정"] == "확인 필요" and "주로 특정 외국법인만을 위하여" in r["사유"]
    # 2026년: 2026.2.27.부터 '전적으로 또는 거의 전적으로 특수관계 외국법인을 위한' 독립대리인
    r = J(G.guide(2026, agent_types=[RELATED]))[key]
    assert r["판정"] == "국내사업장 있음" and "2026.2.27." in r["사유"] and "2026.2.26.까지는 종전 문언" in r["사유"]
    g = G.guide(2026, agent_types=[SPECIFIC])
    assert J(g)[key]["판정"] == "확인 필요" and any("2026.2.27. 이후분" in c for c in g["확인 필요"])
    # 제1호·제3호는 전 연도 문언이 같아 그대로 판정
    assert J(G.guide(2021, agent_types=["보험료 징수·보험 인수"]))["대통령령으로 정하는 자"]["판정"] == "국내사업장 있음"
    assert "error" in G.guide(2024, agent_types=["독립대리인"])


def test_individual_decree_agent_now_decided():
    # 개정 전: 비거주자는 '시행령 조문을 대조하지 못함'으로 확인 필요 → 소득세법 시행령 제180조 대조 후 판정
    r = J(G.guide(2018, taxpayer="비거주자", agent_types=["자산 상시 보관·배달"]))["대통령령으로 정하는 자"]
    assert r["판정"] == "국내사업장 있음" and r["근거"] == "소득세법 제120조제3항, 소득세법 시행령 제180조"
    r = J(G.guide(2023, taxpayer="비거주자", agent_types=[SPECIFIC]))["대통령령으로 정하는 자(독립대리인)"]
    assert r["판정"] == "국내사업장 있음" and r["근거"] == "소득세법 제120조제3항, 소득세법 시행령 제180조제1항제2호" and "특정비거주자" in r["사유"]
    assert J(G.guide(2026, taxpayer="비거주자", agent_types=[SPECIFIC]))["대통령령으로 정하는 자(독립대리인)"]["판정"] == "확인 필요"


def test_anti_fragmentation_related_party_reference():
    assert "제133조제3항 → 제131조제2항" in G.guide(2019)["요소"]["세분화 방지"]
    assert "제180조제2항 → 제183조의2제2항" in G.guide(2024, taxpayer="비거주자")["요소"]["세분화 방지"]
    assert "제133조제3항" not in G.guide(2018)["요소"]["세분화 방지"]


def test_application_basis_and_labels_removed():
    c = G.guide(2019)["적용 기준"]
    assert "사업연도 개시일" in c["연도 기준"] and any("제16008호" in x and "개시하는 사업연도분부터" in x for x in c["근거"])
    assert any("제16833호" in x and "2020.1.1. 시행" in x for x in c["근거"])
    p = G.guide(2020, taxpayer="비거주자")["적용 기준"]
    assert "소득이 발생한 연도" in p["연도 기준"] and any("제16834호" in x and "2020.1.1. 시행" in x and "발생하는 소득분부터" in x for x in p["근거"])
    assert set(G.guide()["적용 기준"]) == {"외국법인", "비거주자"}
    txt = json.dumps(G.guide(2022, taxpayer="비거주자", agent_types=[RELATED]), ensure_ascii=False) + json.dumps(G.guide(), ensure_ascii=False) + G.__doc__
    for label in ("대조하지 못함", "대조하지 않음", "찾지 못함", "미대조", "미확인"):
        assert label not in txt, label
    assert "20200101" in G.VERIFIED and "제180조" in G.VERIFIED


def test_pe_rulings_listed():
    r = G.guide(2024)
    assert len(r["해석·판례"]) == 5 and all(x["id"].isdigit() and x["요지"] and x["읽은 범위"] for x in r["해석·판례"])
    assert any(x["문서번호"] == "대법원-2014-두-13812" for x in r["해석·판례"]) and "get_tax_ruling" in r["해석·판례 안내"]


def test_residency_case_names_filled():
    by = {p.case_no: p for p in RJ.CASES}
    assert by["2017두59352"].case_name == "종합소득세부과처분취소" and "인도네시아" in by["2017두59352"].conclusion
    assert "서울고등법원 2017누34331" in by["2017두59352"].holding and "심리불속행" in by["2017두59352"].holding and "법리 설시가 없음" in by["2017두59352"].misc
    assert by["2014두6869"].case_name == "경정청구거부처분취소" and "540일" in by["2014두6869"].facts
    assert by["2010두28946"].case_name == "경정청구거부처분취소청구" and "뉴질랜드" in by["2010두28946"].facts
    assert by["2010두22719"].case_name.startswith("종합소득세 부과처분 취소") and "주식매수선택권" in by["2010두22719"].facts
    for no in ("2017두59352", "2014두6869", "2010두28946", "2010두22719"):
        p = by[no]
        assert "미확인" not in p.case_name and "확인 안 됨" not in p.facts and "미확정" not in p.conclusion + p.facts + p.misc and "유렉스" not in p.misc
    # 사실 요약으로 찾을 때 2017두59352가 잡힘(인도네시아 법인 대표이사)
    hit = RJ.find_similar_cases("인도네시아 해외 법인 대표이사, 중대한 이해관계 중심지 다툼", top=3)
    assert "2017두59352" in [p.case_no for p in hit]


def test_2014du13959_facts_from_judgment_text():
    """대법원 2014두13959 — 판결문에 적힌 원심 인정 사실(체류일수 270·287·232일, 평균 255일, 호텔 약 20일, 6,125만 원)과 증명책임 판시."""
    c = {p.case_no: p for p in RJ.CASES}["2014두13959"]
    assert c.date == "2015.02.26." and c.case_name == "양도소득세등부과처분취소"
    assert "확인 안 됨" not in c.facts and "미확인" not in c.facts + c.holding + c.misc
    for w in ("2006년 270일", "2007년 287일", "2008년 232일", "평균 255일", "연간 약 20일", "6,125만 원", "미국 또는 중국", "2006년 귀속 종합소득세", "2008년 귀속 양도소득세"):
        assert w in c.facts, w
    assert "이를 주장하는 납세의무자에게 증명책임" in c.holding and "2006두3964" in c.holding and "과세요건" in c.holding
    assert "항구적 주거" in c.holding and "일상적 거소" in c.holding
    assert c.conclusion.startswith("거주자") and "2013구합11628" in c.misc and "2013누27786" in c.misc
    rules = open(os.path.join(os.path.dirname(RJ.__file__), "..", "data", "residency", "rules.md"), encoding="utf-8").read()
    sec = rules[rules.index("#### 6-1-3."):rules.index("### 6-2.")]
    assert "공개 자료로는 확인하지 못함" not in sec and "평균 255일" in sec and "2013구합11628" in sec


def test_tp_cases_all_read_against_body():
    path = os.path.join(os.path.dirname(R.__file__), "data", "tp_cases.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    rows = [c for v in d["쟁점"].values() for c in v["사례"]]
    assert len(rows) == 20 and all(c["id"] for c in rows)
    assert sum(c["읽은 범위"] == "요지와 판단 부분" for c in rows) == 17 and sum(c["읽은 범위"] == "요지와 본문" for c in rows) == 3
    tt = next(c for c in rows if c["id"] == "tt:121314")
    assert tt["결과"] == "과세관청 승" and "거래순이익률방법" in tt["요지"]
    assert next(c for c in rows if c["문서번호"] == "대법원-2012-두-1969")["id"] == "000000000000151810"
    assert next(c for c in rows if c["문서번호"] == "조심-2012-중-3014")["id"] == "000000000000163309"
    r = R.cases("차이 조정")
    assert r["쟁점"]["차이 조정"]["과세관청 승"] == 2 and r["확인일"] == "2026-11-15" and not any("대조하지 않음" in x for x in r["주의"])
