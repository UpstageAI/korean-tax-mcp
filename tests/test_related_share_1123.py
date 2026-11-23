"""특수관계 거래 비중 — 근거 없는 관행값(20%·25%)을 빼고 법령으로 거슬러 올라가는 신호로(2026-11-23).

- 숫자는 data/related_share.json 한 곳: 의존 신호 50%(국조법 시행령 제2조②3호 다목 준용, 사람 확인), 참고선 30%·중견 40%·중소 50%(상증법 제45조의3 — 목적이 다른 규정, 표시만).
- transfer_pricing_guide(계산 MCP로 넘기는 control_dependence)와 tp_comparability_review(R5)가 같은 값을 읽는다.
- 모델 호출 없음(숫자만 주는 후보 — 문장 신호는 judgments=[]로 비움).
"""
import json
import os

from korean_tax_mcp import related_share as RS
from korean_tax_mcp import tp_review as TR
from korean_tax_mcp import transfer_pricing as T

TESTED = {"role": "판매", "products": "화학 기초제품", "channel": "국내 수요처에 1차 도매"}


def _review(cands, rules=None):
    return TR.review(TESTED, cands, judgments={"판정": []}, rules=rules)


def _by(out):
    return {r["후보"]: r for r in out["후보별 권고"]}


def _r5(r):
    return next((s for s in r["신호"] if s["신호"] == "R5"), None)


def test_one_place_two_tools_same_value():
    h = T.selection_criteria("재화")["넘길 값"]["kr_comparable_profile_compare"]["rules"]
    assert h["control_dependence"] == RS.DEPENDENCE == 0.5
    raw = json.load(open(os.path.join(os.path.dirname(RS.__file__), "data", "related_share.json"), encoding="utf-8"))
    assert raw["의존 신호"]["값"] == RS.DEPENDENCE and raw["참고선"]["값"] == {"일반": 0.3, "중견": 0.4, "중소": 0.5}
    out = _review([{"name": "가", "related_sales": 0.5}])
    assert _r5(_by(out)["가"])["특수관계 거래 비중"]["의존 신호"]["기준"] == h["control_dependence"]
    assert out["기준값"]["특수관계 거래 비중"]["의존 신호"]["값"] == h["control_dependence"]


def test_no_practice_default_left():
    assert TR.DEFAULT_RULES["related_review"] is None
    for rows in (T.selection_criteria("재화")["kr_comparable_profile_compare"], T.selection_criteria("재화")["tp_comparable_screen"]):
        assert not any(isinstance(r["값"], float) and r["값"] in (0.2, 0.25) and "related" in r["키"] for r in rows)
    sig = json.load(open(os.path.join(os.path.dirname(RS.__file__), "data", "tp_review_signals.json"), encoding="utf-8"))
    txt = json.dumps(sig["숫자 기준"]["related_review"], ensure_ascii=False)
    assert "2007누29392" not in txt and "2019-0179" not in txt and "숫자 기준 없음" in txt


def test_flag_at_50_percent_sales_or_purchase():
    out = _by(_review([{"name": "매출49", "related_sales": 0.49}, {"name": "매출50", "related_sales": 0.5},
                       {"name": "매입60", "related_sales": 0.05, "related_purchase": 0.6}, {"name": "매입30", "related_purchase": 0.3}]))
    assert _r5(out["매출49"])["판정"] == "가까움" and _r5(out["매출50"])["판정"] == "다름"
    assert _r5(out["매입60"])["판정"] == "다름" and _r5(out["매입30"])["판정"] == "가까움"
    for n in ("매출50", "매입60"):
        assert out[n]["권고"] == "사람 확인" and "특수관계 거래 비중" in out[n]["이유"]   # 사람 확인 — 자동 제외 아님
        assert "다목" in _r5(out[n])["기준"]
    assert out["매출49"]["권고"] != "제외 후보" and out["매입30"]["권고"] != "제외 후보"


def test_shares_always_shown_as_numbers():
    out = _by(_review([{"name": "낮음", "related_sales": 0.05, "related_purchase": 0.1}, {"name": "없음"}]))
    rel = out["낮음"]["특수관계 거래 비중"]
    assert rel["특수관계 매출 비중"] == 0.05 and rel["특수관계 매입 비중"] == 0.1 and rel["의존 신호"]["해당"] is False
    assert "5.0%" in _r5(out["낮음"])["이유"] and "10.0%" in _r5(out["낮음"])["이유"]
    none = out["없음"]["특수관계 거래 비중"]
    assert none["특수관계 매출 비중"] == "자료 없음" and none["의존 신호"]["해당"] is None and none["참고선"]["초과"] is None


def test_reference_line_by_size():
    def ref(size, x=0.35):
        c = {"name": "가", "related_sales": x, **({"company_size": size} if size else {})}
        return _by(_review([c]))["가"]["특수관계 거래 비중"]["참고선"]
    r = ref(None)
    assert r["선"] == 0.3 and r["초과"] is True and "규모 모름" in r["규모"]
    assert "목적이 다른 증여의제 규정(상증법 제45조의3, 시행령 제34조의3 제7항) — 참고선, 비교대상 독립성 기준 아님" in r["출처"]
    assert ref("중견")["선"] == 0.4 and ref("중견")["초과"] is False
    assert ref("중소", 0.5)["선"] == 0.5 and ref("중소", 0.5)["초과"] is False      # '넘는' 경우만(초과)
    assert ref("중소", 0.51)["초과"] is True
    big = ref("대")
    assert big["선"] == 0.3 and "3분의 2" in big["규모"] and "1천억원" in big["규모"]
    assert ref("일반", 0.3)["초과"] is False
    # 참고선은 판정·권고에 쓰지 않음 — 35%는 의존 신호 아래라 R5 가까움
    assert _r5(_by(_review([{"name": "가", "related_sales": 0.35}]))["가"])["판정"] == "가까움"
    assert "error" in _review([{"name": "가", "company_size": "소기업"}])


def test_user_threshold_optional():
    out = _by(_review([{"name": "가", "related_sales": 0.3}], rules={"related_review": 0.25}))
    r5 = _r5(out["가"])
    assert r5["판정"] == "다름" and "사용자 입력" in r5["기준"]
    dep = out["가"]["특수관계 거래 비중"]["의존 신호"]
    assert dep["성격"] == "사용자 입력" and dep["법정 준용 기준(참고)"] == 0.5
    assert "error" in _review([{"name": "가"}], rules={"related_review": 25})


def test_remand_case_number_filled():
    from korean_tax_mcp import tp_report as R
    v = R.cases("비교대상 독립성")["쟁점"]["비교대상 독립성"]
    c = next(x for x in v["사례"] if x["문서번호"] == "대법원-2009-두-24122")
    note = c["관련 문서"][0]["비고"]
    assert "2008두14364" in note and "2008.12.11." in note and "미확인" not in note
