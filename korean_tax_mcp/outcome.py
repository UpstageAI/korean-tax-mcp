"""쟁점별 승패 비교 — 조세심판·심사·이의·법원 판결을 납세자 승/패로 나누고, 양쪽 주장과 결정 이유를 나란히.

이긴 사례만 보면 '어떻게 이겼는지'를, 진 사례만 보면 '무엇이 부족했는지'를 모른다. 같은 쟁점의 양쪽을 한 화면에 둔다.
결과 판정은 본문의 주문(主文)을 규칙으로 읽는다(모델 추정 아님).
"""
import re
from concurrent.futures import ThreadPoolExecutor

from . import ntis

WIN, PART, LOSE, OTHER = "납세자 승(인용·취소)", "일부 인용", "납세자 패(기각)", "각하·기타"


def _conclusion(s):
    """결론 문장(공백 제거) → 결과. 국세기본법 제65조①: 1호 각하, 2호 기각, 3호 인용."""
    if re.search(r"일부이유(가)?있", s) or (re.search(r"이유(가)?있", s) and "기각" in s): return PART
    if re.search(r"이유(가)?없(으므로|다)", s) or "제65조제1항제2호" in s: return LOSE
    if re.search(r"이유(가)?있(으므로|다|어|음)", s) or "제65조제1항제3호" in s: return WIN
    if "제65조제1항제1호" in s: return OTHER
    return None


def verdict(body):
    """본문 → (결과, 주문 원문). 주문(主文)을 규칙으로 읽고, 주문이 없거나 '주문과 같다'면 결론 문장으로."""
    f = re.search(r"결정유형\s*\n\s*([^\n]{1,20})", body[:600])   # 최근 결정문 머리의 결정유형 필드가 가장 정확
    if f:
        v = re.sub(r"\s", "", f.group(1))
        k = OTHER if "각하" in v else PART if "일부" in v else LOSE if "기각" in v else WIN if re.search("인용|취소|경정|재조사", v) else None
        if k: return k, f"결정유형: {f.group(1).strip()}"
    m = re.search(r"\[?\s*주\s*문\s*\]?\s*\n(?!\s*과)(.{0,400}?)(?:\n\s*\[?\s*(?:이\s*유|청\s*구\s*취\s*지|신\s*청\s*취\s*지)|$)", body, re.S)
    t = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    s = re.sub(r"\s", "", t)
    c = re.search(r"결\s*론\s*\n?(.{0,400})", body[-1500:], re.S)
    cs = re.sub(r"\s", "", c.group(1)) if c else ""
    if not s or s.startswith("주문과"):
        r = _conclusion(cs)
        return (r or OTHER), re.sub(r"\s+", " ", c.group(1)).strip()[:300] if c else ""
    if "파기" in s: return OTHER, t[:300]   # 파기환송 — 다시 판단
    if "각하" in s and not re.search("취소|경정", s): return OTHER, t[:300]
    taxpayer_lost = re.search(r"(원고|청구인|청구법인|심판청구|심사청구|이의신청|청구)(들)?의?(항소|상고|청구|심판청구|심사청구|이의신청)?(를|을)?(모두)?기각", s)
    gov_lost = re.search(r"피고(들)?의?(항소|상고)(를|을)?(모두)?기각", s)
    won = re.search(r"(취소한다|취소하고|취소합니다|경정한다|경정하고|경정합니다|인용하고|인용하며|재조사|인용한다|과세하지아니|감액)", s)
    if not gov_lost and not re.search(r"(원고|청구)", s) and re.search(r"(항소|상고)(를|을)?(모두)?기각", s):
        head = re.sub(r"\s", "", body[:300])   # 주체 없는 "상고를 기각" — 누가 상고(항소)인인지로 판단
        if re.search(r"피고(들)?,?(상고인|항소인)", head) and not re.search(r"원고(들)?,?(상고인|항소인)", head): gov_lost = True
    if gov_lost: return WIN, t[:300]
    if won and taxpayer_lost: return PART, t[:300]
    if won: return (PART if "나머지" in s or "일부" in s else WIN), t[:300]
    if taxpayer_lost or "기각" in s: return LOSE, t[:300]
    return (_conclusion(cs) or _conclusion(s) or OTHER), t[:300]


_HEAD = {
    "납세자 주장": r"(?:청구(?:인|법인)들?\s*주\s*장|원고(?:들)?(?:의)?\s*주\s*장|신청인\s*주\s*장)",
    "과세관청 의견": r"(?:처분청\s*의\s*견|피고(?:들)?(?:의)?\s*주\s*장|과세관청\s*의\s*견)",
    "판단": r"(?:심리\s*및\s*판단|[가-하다]\.\s*판\s*단\s*\n|\d\.\s*판\s*단\s*\n|당\s*원의\s*판단|법원의\s*판단)",
}
_END = r"\n\s*(?:\d\.|[가-하]\.|\(\d\)|<|【)?\s*(?:처분청\s*의\s*견|피고(?:들)?(?:의)?\s*주\s*장|관계\s*법령|심리\s*및\s*판단|판\s*단|결\s*론|사실관계\s*및\s*판단)"


def _sec(body, name, limit):
    hs = [m for m in re.finditer(_HEAD[name], body)]
    if not hs: return ""
    if name == "판단":   # 판단은 끝부분(결론 직전)이 승패를 가른 이유
        start = hs[0].end()
        end = re.search(r"\n\s*\d\.\s*결\s*론|주문과\s*같이", body[start:])
        seg = body[start: start + end.start()] if end else body[start:]
        return _tidy(seg[-limit:])
    h = None
    for x in hs:   # "청구인 주장 및 처분청 의견" 같은 묶음 제목은 건너뜀
        nxt = body[x.end():x.end() + 25]
        if not re.match(r"\s*및", nxt) and not re.match(r"\s*\n?\s*가\.\s*청구", nxt): h = x; break
    if h is None: return ""
    rest = body[h.end():]
    e = re.search(_END, rest)
    seg = rest[: e.start()] if e and e.start() > 20 else rest[:limit * 2]
    return _tidy(seg[:limit])


def _tidy(t):
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    return t if len(t) < 20 else t.lstrip(".·:) ")


def analyze(row, limit=600):
    try: d = ntis.document(row["id"], 40000)
    except Exception as e: return {**_base(row), "결과": OTHER, "주문": "", "오류": f"본문 조회 실패: {str(e)[:60]}"}
    b = d.get("본문", "")
    res, order = verdict(b)
    return {**_base(row), "결과": res, "주문": order, "납세자 주장": _sec(b, "납세자 주장", limit),
            "과세관청 의견": _sec(b, "과세관청 의견", limit), "결정 이유(판단 끝부분)": _sec(b, "판단", limit),
            "관련조문": d.get("관련조문", []), **({"주의": "본문 일부만 제공됨 — 링크에서 전문 확인"} if len(b) < 2500 else {})}


def _base(r): return {"문서번호": r["문서번호"], "구분": r["구분"], "일자": r["일자"], "제목": r["제목"], "링크": r["링크"]}


def compare(issue, tax=None, n=16, limit=600):
    """쟁점 → {납세자 승: [...], 일부 인용: [...], 납세자 패: [...], 각하·기타: [...], 집계}"""
    rows = ntis.search(issue, ("판례",), tax, "정확도", 30)
    rows = rows[:n]
    with ThreadPoolExecutor(4) as ex: done = list(ex.map(lambda r: analyze(r, limit), rows))
    out = {WIN: [], PART: [], LOSE: [], OTHER: []}
    for x in done: out[x["결과"]].append(x)
    return {"쟁점": issue, "집계": {k: len(v) for k, v in out.items()}, **out}
