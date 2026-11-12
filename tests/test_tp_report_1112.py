"""transfer_pricing_report·transfer_pricing_far(2026-11-12, Claude).
근거: 국조칙 별지 제13호서식(2026.3.20. 시행본 PDF 12쪽), 시행규칙 제6조·제7조·제10조, 시행령 제33조(2026.11.1. 시행본)."""
from korean_tax_mcp import server as S
from korean_tax_mcp import tp_report as R
from korean_tax_mcp import oecd_tpg as O


def test_outline_matches_form_table_of_contents():
    r = R.outline()
    nums = [x["번호"] for x in r["항목"]]
    assert r["전체건수"] == 24
    assert nums[:5] == [f"Ⅰ-{i}" for i in range(1, 6)] and nums[5:20] == [f"Ⅱ-{i}" for i in range(1, 16)] and nums[20:] == [f"Ⅲ-{i}" for i in range(1, 5)]
    by = {x["번호"]: x for x in r["항목"]}
    assert by["Ⅱ-7"]["제목"] == "특수관계 거래와 관련한 납세의무자와 국외특수관계인의 비교가능성 및 기능 분석"
    assert by["Ⅱ-9"]["제목"] == "분석대상으로 선정된 기업 및 선정 이유에 대한 설명" and by["Ⅱ-15"]["제목"] == "검토 결과"
    assert "transfer_pricing_far" in by["Ⅱ-7"]["도구"] and by["Ⅱ-11"]["OECD 지침 문단"] == "3.75-3.79"
    assert len(r["분석절차"]["순서"]) == 9 and r["분석절차"]["순서"][0] == "분석대상 연도의 선정"
    assert all(x["작성방법"] and x["준비할 사실·자료"] and x["근거"] for x in r["항목"])


def test_outline_guideline_pointers_exist_in_index():
    for x in R.outline()["항목"]:
        for part in (x.get("OECD 지침 문단") or "").split(","):
            if part.strip():
                res = O.lookup(part.strip(), limit=500)
                assert "error" not in res and not res.get("없는 문단"), x["번호"]


def test_outline_filters():
    assert R.outline("Ⅱ")["전체건수"] == 15 and R.outline("2")["전체건수"] == 15 and R.outline("II")["전체건수"] == 15
    assert [x["번호"] for x in R.outline("2-9")["항목"]] == ["Ⅱ-9"]
    assert [x["번호"] for x in R.outline(keyword="다년도")["항목"]] == ["Ⅱ-11"]
    assert "error" in R.outline("Ⅳ")


def test_far_without_input_returns_questionnaire():
    r = R.far()
    assert len(r["질문지"]) == 7 and len(r["위험 분석 순서"]) == 4 and "입력 형식" in r


PARTIES = {"본사": {"기능": ["설계", "제조", "연구·개발", "마케팅", "재무", "관리"], "자산": ["공장", "상표권"], "고유무형자산": True},
           "미국법인": {"기능": ["유통", "광고"], "자산": ["창고 임차"], "고유무형자산": False}}


def test_risk_allocation_follows_rule_article_10():
    r = R.far(parties=PARTIES, risks=[
        {"위험": "시장위험", "계약상": "미국법인", "손익귀속": "미국법인", "관리통제": ["본사"], "재정능력": ["본사"]},      # 관리·통제·재정 능력 없음 → 본사로 재배분
        {"위험": "재고위험", "계약상": "미국법인", "손익귀속": "본사", "관리통제": ["본사"], "재정능력": ["본사"]},          # 계약과 실제 귀속이 다름 → 실제 귀속자
        {"위험": "신용위험", "계약상": "미국법인", "손익귀속": "미국법인", "관리통제": ["미국법인"], "재정능력": ["미국법인"]},  # 그대로
        {"위험": "환위험", "계약상": "미국법인", "손익귀속": "미국법인", "관리통제": ["본사"], "재정능력": ["미국법인"]},      # 둘을 갖춘 쪽이 없음
        {"위험": "투자위험", "계약상": "본사", "손익귀속": "본사"}])                                                        # 관리·통제 미입력
    a = {x["위험"]: x for x in r["위험 분석"]}
    assert a["시장위험"]["부담자"] == "본사" and a["시장위험"]["재배분"] is True and "4호 나목" in a["시장위험"]["근거"]
    assert a["재고위험"]["부담자"] == "본사" and a["재고위험"]["재배분"] is True
    assert a["신용위험"]["부담자"] == "미국법인" and "재배분" not in a["신용위험"]
    assert a["환위험"]["부담자"] is None and a["환위험"]["결론"] == "확인 필요"
    assert a["투자위험"]["부담자"] == "본사" and "확인 필요" in a["투자위험"]["결론"]
    t = r["당사자별 기능·자산·위험"]
    assert t["본사"]["부담 위험"] == ["시장위험", "재고위험", "투자위험"] and t["미국법인"]["부담 위험"] == ["신용위험"]
    assert len([s for s in r["쟁점"] if "계약상 부담자와 다른" in s]) == 2 and any("환위험" in s for s in r["쟁점"])


def test_tested_party_methods_and_indicators_for_a_distributor():
    r = R.far(parties=PARTIES, risks=[{"위험": "신용위험", "계약상": "미국법인", "손익귀속": "미국법인", "관리통제": ["미국법인"], "재정능력": ["미국법인"]}],
              facts={"tested_resells_to_third_parties": True, "tested_processing_or_manufacturing": False, "tested_bears_inventory": False, "internal_comparable": False})
    assert r["분석대상 당사자"]["후보"] == "미국법인" and r["분석대상 당사자"]["OECD 지침 문단"] == "3.18-3.19" and "국조법령에 없음" in r["분석대상 당사자"]["근거"]
    fit = {x["방법"]: x for x in r["산출방법 적합성"]}
    assert fit["재판매가격방법"]["적합성"] == "문언상 맞음" and fit["비교가능 제3자 가격방법"]["적합성"] == "문언상 맞지 않음"
    assert fit["원가가산방법"]["적합성"] == "확인 필요" and fit["거래순이익률방법"]["적합성"] == "지표로 판단"
    assert [x["지표"] for x in r["거래순이익률 지표"]] == ["매출액에 대한 거래순이익의 비율", "영업비용에 대한 매출 총이익의 비율"]
    assert r["보고서 항목"].keys() == {"Ⅱ-7", "Ⅱ-8", "Ⅱ-9"} and any("판정하지 않는다" in s for s in r["한계"])


def test_distributor_with_processing_or_own_intangibles():
    r = R.far(parties=PARTIES, facts={"tested_resells_to_third_parties": True, "tested_processing_or_manufacturing": True})
    assert {x["방법"]: x for x in r["산출방법 적합성"]}["재판매가격방법"]["적합성"] == "문언상 맞지 않음"
    p2 = {"본사": PARTIES["본사"], "미국법인": {**PARTIES["미국법인"], "고유무형자산": True, "기능": ["유통"]}}
    r = R.far(parties=p2, facts={"tested_resells_to_third_parties": True, "tested_processing_or_manufacturing": False}, tested_party="미국법인")
    assert "고유한 무형자산" in {x["방법"]: x for x in r["산출방법 적합성"]}["재판매가격방법"]["주의"]
    r = R.far(parties=PARTIES, tested_party="본사")
    assert "주의" in r["분석대상 당사자"] and r["분석대상 당사자"]["입력한 분석대상"] == "본사"


def test_inventory_contradiction_and_manufacturing_indicators():
    r = R.far(parties=PARTIES, risks=[{"위험": "재고위험", "계약상": "미국법인", "손익귀속": "미국법인", "관리통제": ["미국법인"], "재정능력": ["미국법인"]}],
              facts={"tested_resells_to_third_parties": True, "tested_processing_or_manufacturing": False, "tested_bears_inventory": False})
    assert any("재고 관련 위험" in s for s in r["쟁점"])
    r = R.far(parties=PARTIES, facts={"intermediate_goods_or_services": True, "asset_intensive": True})
    assert [x["근거"] for x in r["거래순이익률 지표"]] == ["시행규칙 제6조③3호", "시행규칙 제6조③2호"]


def test_far_input_errors():
    assert "error" in R.far(parties={"본사": {}})
    assert "error" in R.far(parties=PARTIES, facts={"x": True})
    assert "error" in R.far(parties=PARTIES, risks=[{"위험": "시장위험", "계약상": "일본법인"}])
    assert "error" in R.far(parties=PARTIES, tested_party="일본법인")


def test_tools_registered():
    f = getattr(S.transfer_pricing_report, "fn", S.transfer_pricing_report)
    assert f(section="Ⅱ-8")["항목"][0]["번호"] == "Ⅱ-8"
    g = getattr(S.transfer_pricing_far, "fn", S.transfer_pricing_far)
    assert "질문지" in g() and g(parties=PARTIES)["분석대상 당사자"]["후보"] == "미국법인"
    assert isinstance(g(lang="en"), dict)


def test_cases_by_issue():
    r = R.cases()
    assert len(r["쟁점"]) == 9 and r["쟁점 목록"][0] == "입증책임"
    total = sum(len(v["사례"]) for v in r["쟁점"].values())
    assert total == 20
    for v in r["쟁점"].values():
        assert v["보고서에 반영할 점"]
        for c in v["사례"]:
            assert c["결과"] in ("납세자 승", "과세관청 승", "해석", "(제목만 확인)") and c["요지"] and c["읽은 범위"] in ("요지", "요지와 판단 부분", "제목")
    d = R.cases("다년도")["쟁점"]
    assert list(d) == ["다년도 자료"] and d["다년도 자료"]["과세관청 승"] == 3 and any("제9조" in s for s in d["다년도 자료"]["보고서에 반영할 점"])
    w = R.cases("차이 조정", "납세자 승")["쟁점"]["차이 조정"]["사례"]
    assert [c["문서번호"] for c in w] == ["서울고등법원-2009-누-39126"]
    assert "error" in R.cases("없는쟁점") and "error" in R.cases("", "무승부")


def test_cases_tool():
    f = getattr(S.transfer_pricing_cases, "fn", S.transfer_pricing_cases)
    r = f(issue="비교대상")
    assert r["쟁점"]["비교대상 선정"]["납세자 승"] == 1 and r["쟁점"]["비교대상 선정"]["과세관청 승"] == 2
    assert any("본문" in s for s in r["주의"])
