"""비교대상 후보의 특수관계 거래 비중 신호 — 숫자는 data/related_share.json 한 곳. Claude 작성(2026-11-23).

transfer_pricing_guide(계산 MCP로 넘길 control_dependence)와 tp_comparability_review(R5)가 같은 값을 읽는다.
비중은 늘 숫자로 보여 주고, 의존 신호(국조법 시행령 제2조②3호 다목, 50% 이상 → 사람 확인)와
참고선(상증법 정상거래비율 — 목적이 다른 증여의제 규정)만 붙인다. 자동 제외 기준이 아니다.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "data", "related_share.json")
with open(_PATH, encoding="utf-8") as _f:
    DATA = json.load(_f)

DEPENDENCE = DATA["의존 신호"]["값"]
REFERENCE = DATA["참고선"]["값"]
SIZES = tuple(DATA["규모"])


def _pct(x):
    return f"{x:.1%}"


def reference_line(size=None):
    """규모 → (선, 규모 설명). 모르면 일반 30%."""
    key = DATA["규모"].get(size) if size else None
    if key is None:
        return REFERENCE["일반"], f"규모 모름 — 일반 {REFERENCE['일반']:.0%}로 표시(중견 {REFERENCE['중견']:.0%}, 중소 {REFERENCE['중소']:.0%})"
    note = f"{size} — {REFERENCE[key]:.0%}"
    if size == "대":
        note += " · " + DATA["참고선"]["대기업 보조선"]
    return REFERENCE[key], note


def assess(sales=None, purchase=None, size=None, review=None):
    """특수관계 매출·매입 비중(0~1, 없으면 None) → 숫자·의존 신호·참고선. review는 사용자 검토선(선택, 기본값 없음)."""
    shares = {"특수관계 매출 비중": sales, "특수관계 매입 비중": purchase}
    have = [x for x in (sales, purchase) if x is not None]
    hi = max(have) if have else None
    line = review if review is not None else DEPENDENCE
    dep = {"기준": line, "해당": None if hi is None else hi >= line}
    if review is None:
        dep.update({"성격": DATA["의존 신호"]["성격"], "출처": DATA["의존 신호"]["출처"]})
    else:
        dep.update({"성격": "사용자 입력", "출처": f"사용자 검토선 {review:g} — {DATA['숫자 기준 없음']}", "법정 준용 기준(참고)": DEPENDENCE})
    ref, size_note = reference_line(size)
    out = {**{k: (round(v, 4) if v is not None else "자료 없음") for k, v in shares.items()},
           "의존 신호": dep,
           "참고선": {"선": ref, "규모": size_note, "초과": None if sales is None else sales > ref,
                    "성격": DATA["참고선"]["성격"], "출처": DATA["참고선"]["출처"]},
           "안내": DATA["숫자 기준 없음"]}
    return out


def summary(sales=None, purchase=None):
    """사람이 읽을 한 줄 — 비중 숫자."""
    parts = [f"{n} {_pct(v)}" for n, v in (("특수관계 매출", sales), ("특수관계 매입", purchase)) if v is not None]
    return ", ".join(parts) if parts else "특수관계 매출·매입 비중 자료 없음"
