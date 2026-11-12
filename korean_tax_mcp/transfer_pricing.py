"""정상가격 산출방법 안내표(transfer_pricing.json) 조회 — 국외특수관계인 거래에 적용할 규정, 산출방법, 선택 기준, 거래 유형별 특칙. Claude 작성(2026-11-12).

정상가격을 산출하거나 거래가격이 정상가격인지 판정하지 않는다. 조문은 표의 '확인 시행본'으로 대조했고, 원문은 law_article로 확인한다."""
import json
import os

from . import oecd_tpg as _tpg

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
_NEXT = {
    "재화": [("법 제8조", f"law_article(law_name='{_LAW}', article='제8조')"), ("시행령 제14조", f"law_article(law_name='{_LAW} 시행령', article='제14조')")],
    "용역": [("시행령 제12조", f"law_article(law_name='{_LAW} 시행령', article='제12조')")],
    "금전대차": [("시행령 제11조", f"law_article(law_name='{_LAW} 시행령', article='제11조')"), ("시행규칙 제3조", f"law_article(law_name='{_LAW} 시행규칙', article='제3조')")],
    "지급보증": [("시행령 제12조", f"law_article(law_name='{_LAW} 시행령', article='제12조')")],
    "무형자산": [("시행령 제13조", f"law_article(law_name='{_LAW} 시행령', article='제13조')")],
}


def guide(transaction, foreign_related=True, exception=None, facts=None, as_of=""):
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
    out["선택 기준"] = _DATA["선택 기준"]
    out["적용 절차"] = _DATA["적용 절차"]
    out["거래 유형 특칙"] = _DATA["거래 유형"][transaction]
    out["조정·처분"] = _DATA["조정·처분"]
    out["OECD 지침"] = {"관련 문단": _tpg.pointers(_TPG_TOPICS["공통"] + _TPG_TOPICS[transaction]), "지위": _tpg.STATUS,
                      "조회": "oecd_tp_guidelines(paragraph='문단 번호 또는 범위') — 국조법령에 규정이 없거나 해석이 갈리는 대목의 논거 자료"}
    out["한계"] = _DATA["한계"]
    out["다음 단계"] = ([{"확인할 조문": t, "호출": c} for t, c in _NEXT[transaction]]
                    + [{"확인할 것": "관련 해석·결정례", "호출": f"search_tax_rulings(query='정상가격 {transaction} 국외특수관계인', tax='국조')"}])
    a = "".join(ch for ch in str(as_of or "") if ch.isdigit())
    if a and a < "20210101":
        out["기준일 주의"] = (f"기준일 {a} — 2020.12.31.까지는 구 국제조세조정에 관한 법률(정상가격 제4조·산출방법 제5조, 구 시행령)이 적용되어 조문 번호와 일부 내용이 다르다. "
                          "이 표는 2021.1.1. 이후 시행본 기준이므로 law_article(as_of=기준일)로 당시 조문을 확인")
    elif a and "20210101" <= a < "20220215" and transaction == "금전대차":
        out["기준일 주의"] = f"기준일 {a} — 2022.2.15. 개정 전 시행령 제11조②는 시행규칙으로 정하는 이자율을 정상이자율로 본다고만 규정(신용부도스왑·이자율 산정 모형 방법은 그 뒤 신설)"
    return out
