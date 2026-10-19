"""시기 규칙표(timing_rules.json) 조회 — 납세의무 성립·손익 귀속·소득별 수입시기·부가 공급시기."""
import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "timing_rules.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)

_SUPPORTED = ("법인", "소득", "부가", "양도", "상증", "국기", "종부")

_WARNING = "현행 조문 기준 표 — 지난 해 사안은 law_article(as_of=그 해 말일)로 그 해 조문을 확인. 사실관계를 어느 규칙에 맞출지는 판단 몫"


def lookup(tax=None, kind=None, keyword=""):
    """시기 규칙표에서 필터 조건에 맞는 규칙을 반환.

    반환: {규칙: [...원문 dict...], 확인 시행본: {...}, 주의: "..."}
    tax가 있으면 "세목" 키도 포함. tax가 없으면 "세목별 건수"와 "안내" 포함.
    """
    rules = _DATA["규칙"]
    confirmed = _DATA["확인 시행본"]

    if tax:
        tax = tax.strip()
        if tax in ("법인", "소득", "부가"):
            selected = [r for r in rules if r["세목"] == tax or
                        (r["세목"] == "공통" and tax in (r.get("관련 세목") or []))]
        elif tax in ("양도", "상증", "국기", "종부"):
            selected = [r for r in rules if r["세목"] == "공통" and tax in (r.get("관련 세목") or [])]
        else:
            return {"error": f"지원 세목: 법인·소득·부가·양도·상증·국기·종부"}
    else:
        selected = [r for r in rules if r["세목"] == "공통"]
        counts = {}
        for r in rules:
            t = r["세목"]
            counts[t] = counts.get(t, 0) + 1
        result = {
            "규칙": selected,
            "확인 시행본": confirmed,
            "세목별 건수": {"공통": counts.get("공통", 0),
                           "법인": counts.get("법인", 0),
                           "소득": counts.get("소득", 0),
                           "부가": counts.get("부가", 0)},
            "안내": "세목(tax)을 주면 그 세목 규칙 전부",
            "주의": _WARNING,
        }
        # kind/keyword 필터
        if kind:
            result["규칙"] = [r for r in result["규칙"] if r.get("구분") == kind]
        if keyword:
            k = keyword.strip()
            result["규칙"] = [r for r in result["규칙"]
                            if k in (r.get("항목", "") + r.get("시기", "") + r.get("예외", ""))]
        return result

    if kind:
        selected = [r for r in selected if r.get("구분") == kind]
    if keyword:
        k = keyword.strip()
        selected = [r for r in selected
                    if k in (r.get("항목", "") + r.get("시기", "") + r.get("예외", ""))]

    return {
        "규칙": selected,
        "확인 시행본": confirmed,
        "세목": tax,
        "주의": _WARNING,
    }
