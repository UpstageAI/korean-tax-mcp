"""정상가격 산출방법 안내표(transfer_pricing.json) 조회 — 국외특수관계인 거래에 적용할 규정, 산출방법, 선택 기준, 거래 유형별 특칙. Claude 작성(2026-11-12).

정상가격을 산출하거나 거래가격이 정상가격인지 판정하지 않는다. 조문은 표의 '확인 시행본'으로 대조했고, 원문은 law_article로 확인한다."""
import json
import os

from . import oecd_tpg as _tpg
from .tp_report import _COMPARABLE_CALC

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "transfer_pricing.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)

_TPG_TOPICS = {
    "공통": ["가장 합리적인 방법 선택", "비교가능성 분석요소", "기능 분석", "위험 분석", "비교가능성 분석 절차", "정상가격 범위", "다년도 자료", "차이 조정", "문서화"],
    "재화": ["사업전략", "손실이 계속", "통합평가"], "용역": ["용역이 실제 제공", "저부가가치"], "금전대차": ["금전대차"], "지급보증": ["지급보증"],
    "무형자산": ["무형자산", "원가분담"],
}
TRANSACTIONS = ("재화", "용역", "금전대차", "지급보증", "무형자산")
EXCEPTIONS = ("무상이전·채무면제", "무수익자산", "출연금대납", "자본거래")
_FACT_KEYS = ("internal_comparable", "buyer_resells", "seller_cost_known", "joint_profit")
_LAW = "국제조세조정에 관한 법률"
# 금액 계산은 계산 MCP(korean-tax-calc-mcp) — 거래 유형별로 부를 도구
# 비교대상 기업을 찾아야 하면 kr_comparable_candidates → kr_comparable_profile_compare → tp_comparable_screen → arm_length_range(tp_report._COMPARABLE_CALC)
_SEARCH = [(x["도구"].removeprefix("계산 MCP "), f"비교대상 탐색 {i}/3 — " + x["용도"].split(" ", 1)[1]) for i, x in enumerate(_COMPARABLE_CALC[:3], 1)]
_SEARCH[1] = (_SEARCH[1][0], _SEARCH[1][1] + " — rules는 '비교대상 선정 기준'의 넘길 값")
_SEARCH[2] = (_SEARCH[2][0], _SEARCH[2][1] + " — screens·quartile_method는 '비교대상 선정 기준'의 넘길 값, 남은 비교대상은 arm_length_range로")
_CALC = {
    "재화": [("arm_length_range", "비교대상 이익률·가격이 있으면 정상가격 범위(사분위)와 조정액")] + _SEARCH,
    "용역": [("arm_length_range", "원가가산율 등 비교대상이 있으면 정상가격 범위와 조정액")] + _SEARCH + [("expat_cost_recharge", "해외 파견 인건비 청구액·가산율")],
    "금전대차": [("deemed_interest", "국외특수관계인 대여 이자의 정상이자율 적용·세무조정")],
    "지급보증": [("arm_length_range", "보증수수료율 비교대상으로 정상가격 범위와 조정액")],
    "무형자산": [("arm_length_range", "사용료율 비교대상이 있으면 정상가격 범위와 조정액")] + _SEARCH,
}
_USES_COMPANIES = ("재화", "용역", "무형자산")     # 비교대상 '기업' 선정 기준을 보여 줄 거래 유형


ROLES = ("판매", "제조", "용역")
_CMP_KEYS = ("role", "limited_risk", "tested_loss", "economic_crisis")
_DEFAULT_ROLE = {"용역": "용역"}


def selection_criteria(transaction="재화", comparable=None):
    """비교대상 선정 기준 묶음 — 값마다 성격·출처·기준일·근거 강도, 판례 신호는 확인 질문, 계산 MCP 입력 그대로의 '넘길 값'.

    comparable: {role: 판매|제조|용역, limited_risk, tested_loss, economic_crisis}(값은 true/false, 모두 선택)."""
    cmp_ = dict(comparable or {})
    bad = [k for k in cmp_ if k not in _CMP_KEYS]
    if bad:
        return {"error": f"comparable의 키 {bad} — 허용 키: {list(_CMP_KEYS)}"}
    role = cmp_.get("role") or _DEFAULT_ROLE.get(transaction)
    if role is not None and role not in ROLES:
        return {"error": f"comparable.role={role!r} — 허용값: {list(ROLES)}"}
    c = json.loads(json.dumps(_DATA["비교대상 선정 기준"], ensure_ascii=False))
    note = []
    if cmp_.get("economic_crisis"):
        row = next(x for x in c["tp_comparable_screen"] if x["키"] == "crisis_exception")
        row["값"] = True
        row["출처"] += " — 입력: 특수한 경제위기 상황을 고려할 필요가 있음"
    if cmp_.get("tested_loss"):
        note.append("분석대상도 손실 연도가 있음 — 손실 후보를 일괄로 빼지 말고 손실 원인을 사람이 확인(OECD 지침 3.64-3.65). loss_years로 걸러진 후보는 탈락 사유를 남김")
    if cmp_.get("limited_risk"):
        note.append("분석대상이 제한위험 기능 — 자체 마케팅·재고위험을 지는 후보와는 기능 차이를 조정하지 않으면 비교가능성이 부정된 사례가 있음(대법원 2024두54065 소형가전 부문). 광고·연구개발 비율이 높은 후보는 확인 질문으로 대조")
    if role == "용역":
        note.append("용역 제공자 — 재고·원재료 비교 항목은 의미가 적을 수 있어 kr_comparable_profile_compare 결과의 재고 판정은 사람이 확인. 지표는 총원가가산율 등(시행령 제8조①3호)")
    qs = [q for q in c["확인 질문"] if role is None or role in q["역할"]]
    prof = {x["키"]: x["값"] for x in c["kr_comparable_profile_compare"]}
    scr = {x["키"]: x["값"] for x in c["tp_comparable_screen"] if x["키"] != "quartile_method"}
    qm = next(x["값"] for x in c["tp_comparable_screen"] if x["키"] == "quartile_method")
    out = {**c, "확인 질문": qs, "입력": {"거래 유형": transaction, "역할": role or "판매·제조(지정 안 함)", **{k: v for k, v in cmp_.items() if k != "role"}},
           "넘길 값": {"kr_comparable_profile_compare": {"rules": prof}, "tp_comparable_screen": {"screens": scr, "quartile_method": qm}}}
    if note:
        out["주의"] = note
    return out

_NEXT = {
    "재화": [("법 제8조", f"law_article(law_name='{_LAW}', article='제8조')"), ("시행령 제14조", f"law_article(law_name='{_LAW} 시행령', article='제14조')")],
    "용역": [("시행령 제12조", f"law_article(law_name='{_LAW} 시행령', article='제12조')")],
    "금전대차": [("시행령 제11조", f"law_article(law_name='{_LAW} 시행령', article='제11조')"), ("시행규칙 제3조", f"law_article(law_name='{_LAW} 시행규칙', article='제3조')")],
    "지급보증": [("시행령 제12조", f"law_article(law_name='{_LAW} 시행령', article='제12조')")],
    "무형자산": [("시행령 제13조", f"law_article(law_name='{_LAW} 시행령', article='제13조')")],
}


def guide(transaction, foreign_related=True, exception=None, facts=None, as_of="", comparable=None):
    if transaction not in TRANSACTIONS:
        return {"error": f"transaction={transaction!r} — 허용값: {list(TRANSACTIONS)}"}
    if exception is not None and exception not in EXCEPTIONS:
        return {"error": f"exception={exception!r} — 허용값: {list(EXCEPTIONS)} 또는 생략"}
    facts = facts or {}
    bad = [k for k in facts if k not in _FACT_KEYS]
    if bad:
        return {"error": f"facts의 키 {bad} — 허용 키: {list(_FACT_KEYS)}(값은 true/false)"}
    rule = _DATA["적용 규정"]
    out = {"거래 유형": transaction, "확인 시행본": _DATA["확인 시행본"]}
    if not foreign_related:
        out["적용 규정"] = {"적용": "법인세법 제52조", **rule["국내"]}
        out["한계"] = _DATA["한계"][:1]
        return out
    if exception:
        i = EXCEPTIONS.index(exception)
        out["적용 규정"] = {"적용": "법인세법 제52조", "결론": f"국제거래지만 '{rule['예외']['유형'][i]}'에 해당 — 법인세법 제52조를 적용한다(시가와 차액 3억원 이상 또는 시가의 5% 이상).",
                        "근거": rule["예외"]["근거"] + ", 법인세법 제52조"}
        out["소득처분"] = {"내용": "법인세법 시행령 제106조①에 따라 귀속자별로 처분 — 주주는 배당, 임직원은 상여, 법인은 그 이익이 내국법인이나 외국법인 국내사업장의 소득을 구성하는 경우에만 기타사외유출, 그 밖의 자는 기타소득",
                        "근거": "법인세법 시행령 제106조①1호"}
        out["한계"] = ["정상가격 산출방법 안내는 국조법이 적용되는 거래에만 해당 — 이 거래는 법인세법의 시가 규정(시행령 제89조)으로 본다"]
        return out
    out["적용 규정"] = {"적용": "국조법 정상가격 조정", **rule["원칙"], "예외 유형": rule["예외"]["유형"], "예외 근거": rule["예외"]["근거"]}
    methods = []
    first = []
    for m in _DATA["산출방법"]:
        row = {k: v for k, v in m.items() if k != "facts"}
        tp = _tpg.pointers([m["방법"]])
        if tp:
            row["OECD 지침 문단"] = tp[0]["문단"]
        if m["facts"] and m["facts"] in facts:
            row["입력 사실"] = "해당" if facts[m["facts"]] else "해당 없음"
            if facts[m["facts"]]:
                first.append(m["방법"])
        methods.append(row)
    out["산출방법"] = methods
    if first:
        out["먼저 볼 방법"] = {"방법": first, "이유": "입력한 사실이 그 방법의 정의 문언(법 제8조① 각 호)에 맞음 — 가장 합리적인 방법인지는 시행령 제14조 기준으로 판단"}
    elif transaction in ("금전대차", "지급보증"):
        out["먼저 볼 방법"] = {"방법": [], "이유": f"{transaction}은 아래 '거래 유형 특칙'을 먼저 본다"}
    out["순서"] = "제1호~제5호 가운데 가장 합리적인 방법을 고르고, 제6호(그 밖의 방법)는 제1호~제5호로 산출할 수 없는 경우에만 적용(법 제8조① 단서)"
    out["비교가능 거래"] = _DATA["비교가능 거래"]
    if transaction in _USES_COMPANIES:
        sel = selection_criteria(transaction, comparable)
        if "error" in sel:
            return sel
        out["비교대상 선정 기준"] = sel
    out["선택 기준"] = _DATA["선택 기준"]
    out["적용 절차"] = _DATA["적용 절차"]
    out["거래 유형 특칙"] = _DATA["거래 유형"][transaction]
    out["조정·처분"] = _DATA["조정·처분"]
    out["OECD 지침"] = {"관련 문단": _tpg.pointers(_TPG_TOPICS["공통"] + _TPG_TOPICS[transaction]), "지위": _tpg.STATUS,
                      "조회": "oecd_tp_guidelines(paragraph='문단 번호 또는 범위') — 국조법령에 규정이 없거나 해석이 갈리는 대목의 논거 자료"}
    out["한계"] = _DATA["한계"]
    out["다음 단계"] = ([{"확인할 조문": t, "호출": c} for t, c in _NEXT[transaction]]
                    + [{"확인할 것": "관련 해석·결정례", "호출": f"search_tax_rulings(query='정상가격 {transaction} 국외특수관계인', tax='국조')"}]
                    + ([{"확인할 것": "비교대상 선정·독립성 결정례", "호출": "transfer_pricing_cases(issue='비교대상')"},
                        {"확인할 것": "통칙 원문(사분위 8-15…1, 거래의 독립성 8-0…1)", "호출": f"basic_rules(law_name='{_LAW}', keyword='사분위')"},
                        {"확인할 조문": "시행령 제2조②(실질 지배 기준)", "호출": f"law_article(law_name='{_LAW} 시행령', article='제2조')"}]
                       if transaction in _USES_COMPANIES else []))
    out["계산 다음 단계"] = [{"도구": f"계산 MCP {n}", "용도": u} for n, u in _CALC[transaction]]
    a = "".join(ch for ch in str(as_of or "") if ch.isdigit())
    if a and a < "20210101":
        out["기준일 주의"] = (f"기준일 {a} — 2020.12.31.까지는 구 국제조세조정에 관한 법률(정상가격 제4조·산출방법 제5조, 구 시행령)이 적용되어 조문 번호와 일부 내용이 다르다. "
                          "이 표는 2021.1.1. 이후 시행본 기준이므로 law_article(as_of=기준일)로 당시 조문을 확인")
    elif a and "20210101" <= a < "20220215" and transaction == "금전대차":
        out["기준일 주의"] = f"기준일 {a} — 2022.2.15. 개정 전 시행령 제11조②는 시행규칙으로 정하는 이자율을 정상이자율로 본다고만 규정(신용부도스왑·이자율 산정 모형 방법은 그 뒤 신설)"
    return out
