"""시기 규칙표(timing_rules.json) 조회 — 납세의무 성립·손익 귀속·소득별 수입시기·부가 공급시기."""
import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "timing_rules.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)

_SUPPORTED = ("법인", "소득", "부가", "양도", "상증", "국기", "종부")

_WARNING = "현행 조문 기준 표 — 지난 해 사안은 law_article(as_of=그 해 말일)로 그 해 조문을 확인. 사실관계를 어느 규칙에 맞출지는 판단 몫"

# 표에 세목 고유 규칙이 없는 세목 — 공통(납세의무 성립) 규칙만 있다. 어디를 보면 되는지 안내 (모의 2차 #37)
_NO_OWN = {
    "양도": "양도·취득시기는 소득세법 제98조·같은 법 시행령 제162조",
    "상증": "상속개시일·증여재산 취득시기는 상속세 및 증여세법 제2조·같은 법 시행령 제24조",
    "국기": "납세의무 성립·확정은 국세기본법 제21조·제22조",
    "종부": "과세기준일(매년 6월 1일)은 종합부동산세법 제3조",
}
# 표에 없는 시기를 keyword로 찾을 때 볼 조문 (모의 2차 #71: '대손' 0건)
_HINTS = {
    "대손": "대손금 손금 귀속 사업연도는 법인세법 시행령 제19조의2 제3항(소득세는 소득세법 시행령 제55조 제2항)",
    "취득시기": "양도·취득시기는 소득세법 제98조·같은 법 시행령 제162조",
    "양도시기": "양도·취득시기는 소득세법 제98조·같은 법 시행령 제162조",
    "증여": "증여재산 취득시기는 상속세 및 증여세법 시행령 제24조",
    "감가상각": "감가상각비 손금산입은 결산조정 — 법인세법 제23조",
}


# 평소 쓰는 말 → 표의 문구 (Claude 2026-10-28: '선발급'이 표의 '공급시기 전 … 발급'과 안 맞던 문제)
_SYNONYMS = {
    "선발급": ["공급시기 전"], "먼저발급": ["공급시기 전"], "사전발급": ["공급시기 전"],
    "중간지급": ["중간지급조건부"], "할부": ["할부"], "장기할부": ["장기할부"], "완성도": ["완성도기준"],
    "간주임대료": ["간주임대료", "임대보증금"], "선수금": ["선불"], "선불": ["선불"], "수출": ["수출재화", "선(기)적"],
    "폐업": ["폐업"], "상품권": ["상품권"], "임대료": ["임대"], "성립": ["납세의무 성립"], "확정": ["확정"],
}


def _norm(s):
    return "".join((s or "").split())


def _matches(r, keyword):
    """keyword의 낱말이 모두(띄어쓰기 무시) 규칙의 항목·시기·예외·정의·구분·근거 어딘가에 있으면 일치. 동의어도 봄."""
    hay = _norm(" ".join(str(r.get(f) or "") for f in ("구분", "항목", "시기", "예외", "정의", "근거")))
    for w in keyword.split():
        cands = [w] + _SYNONYMS.get(_norm(w), [])
        if not any(_norm(c) in hay for c in cands):
            return False
    return True


def _filter(selected, kind, keyword):
    if kind:   # 띄어쓰기 무시('손익귀속' = '손익 귀속')
        selected = [r for r in selected if _norm(r.get("구분")) == _norm(kind)]
    if keyword:
        k = keyword.strip()
        selected = [r for r in selected if _matches(r, k)]
    return selected


def _empty_notice(tax, kind, keyword, pool):
    cond = ", ".join(x for x in (f"세목 {tax}" if tax else "", f"구분 '{kind}'" if kind else "", f"keyword '{keyword}'" if keyword else "") if x)
    msg = f"해당 규칙 없음 — 이 표({cond})에 맞는 규칙이 없음. 표 밖의 시기는 find_article로 조문을 찾고 law_article로 확인"
    hint = next((v for k, v in _HINTS.items() if k in _norm(keyword or "")), None)
    if hint: msg += f". 참고: {hint}"
    kinds = list(dict.fromkeys(r.get("구분") for r in pool))
    return msg, kinds


def _as_of_note(as_of, confirmed):
    """기준일이 표의 확인 시행본보다 앞이면 — 이 표는 현행 조문만 정리했다고 알림."""
    later = {k: v for k, v in confirmed.items() if v > as_of}
    if not later: return None
    lst = ", ".join(f"{k}({v})" for k, v in later.items())
    return (f"이 표는 현행 조문만 정리(지난 해 규칙 없음). 기준일 {as_of}보다 뒤에 시행된 조문 기준: {lst}. "
            f"그 해 규칙은 law_article(law_name, 조, as_of='{as_of}')로 확인")


def lookup(tax=None, kind=None, keyword="", as_of=""):
    """시기 규칙표에서 필터 조건에 맞는 규칙을 반환.

    반환: {규칙: [...원문 dict...], 확인 시행본: {...}, 주의: "..."}
    tax가 있으면 "세목" 키도 포함. tax가 없으면 "세목별 건수"와 "안내" 포함.
    규칙이 0건이거나 세목 고유 규칙이 없으면 "안내", as_of가 표의 확인 시행본보다 앞이면 "기준일 주의".
    """
    rules = _DATA["규칙"]
    confirmed = _DATA["확인 시행본"]
    as_of = "".join(ch for ch in (as_of or "") if ch.isdigit())
    if as_of and len(as_of) != 8:
        return {"error": "as_of는 YYYYMMDD"}

    if tax:
        tax = tax.strip()
        if tax in ("법인", "소득", "부가"):
            pool = [r for r in rules if r["세목"] == tax or
                    (r["세목"] == "공통" and tax in (r.get("관련 세목") or []))]
        elif tax in ("양도", "상증", "국기", "종부"):
            pool = [r for r in rules if r["세목"] == "공통" and tax in (r.get("관련 세목") or [])]
        else:
            return {"error": f"지원 세목: 법인·소득·부가·양도·상증·국기·종부"}
        result = {"규칙": _filter(pool, kind, keyword), "확인 시행본": confirmed, "세목": tax, "주의": _WARNING}
        if tax in _NO_OWN and result["규칙"]:
            result["안내"] = (f"이 표에 '{tax}' 세목 고유 규칙 없음 — 공통(납세의무 성립) 규칙만. "
                            f"{_NO_OWN[tax]} — law_article로 확인")
    else:
        pool = [r for r in rules if r["세목"] == "공통"]
        counts = {}
        for r in rules:
            counts[r["세목"]] = counts.get(r["세목"], 0) + 1
        result = {
            "규칙": _filter(pool, kind, keyword),
            "확인 시행본": confirmed,
            "세목별 건수": {t: counts.get(t, 0) for t in ("공통", "법인", "소득", "부가")},
            "안내": "세목(tax)을 주면 그 세목 규칙 전부",
            "주의": _WARNING,
        }

    if not result["규칙"]:
        msg, kinds = _empty_notice(tax, kind, keyword, pool)
        if tax in _NO_OWN: msg += f". {_NO_OWN[tax]}"
        result["안내"] = msg
        result["구분 목록"] = kinds
    if as_of:
        note = _as_of_note(as_of, confirmed)
        if note: result["기준일 주의"] = note
    return result
