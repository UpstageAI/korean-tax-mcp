"""그 해 기준 묶음 조회 — 사실 발생 시점의 조문·3단 위임·기본통칙·집행기준·당시 해석을 한 번에.

AI에 맡기면 자주 틀리는 시점 판단을 코드로 고정한다.
- 기준일: 법인·소득은 사업연도(과세기간) 종료일, 부가는 과세기간(1기 6/30, 2기 12/31) 종료일, 날짜를 주면 그 날
  양도=양도일(잔금일·등기접수일 중 빠른 날), 상속=상속개시일, 증여=증여일, 원천=지급일
- 조문 변경: 기준일 조문과 현행 조문을 비교
- 해석 시점: 해석·판례 등록일에 시행되던 조문이 기준일 조문과 같은지 표시(같은 시행본이면 '같음', 본문이 바뀌었으면 '개정 후')
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import law, ntis


EVENTS = {   # 세목별 기준일 — 납세의무 성립·적용 법령을 가르는 날
    "양도": ("양도일", "양도시기: 원칙 대금청산일(잔금일), 그 전에 소유권이전등기를 접수했으면 등기접수일(소득세법 제98조, 영 제162조)"),
    "상속": ("상속개시일", "상속개시일(사망일)에 납세의무 성립 — 그날 시행 법 적용(국세기본법 제21조②, 상증법 제1조)"),
    "증여": ("증여일", "증여재산 취득시기에 납세의무 성립. 부동산 등 등기 대상은 소유권이전등기 접수일(상증법 제32조, 영 제24조)"),
    "원천": ("지급일", "원천징수 대상 소득을 지급하는 때 납세의무 성립(국세기본법 제21조③1호). 귀속시기와 다를 수 있음 — 배당·상여 처분은 지급 의제일 확인"),
}


def _ymd(p):
    m = re.fullmatch(r"\s*(\d{4})\s*[-./]?\s*(\d{1,2})\s*[-./]?\s*(\d{1,2})\.?\s*", p or "")
    if not m: return None
    y, mo, d = m.groups()
    return f"{y}{int(mo):02d}{int(d):02d}" if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 else None


def base_date(period, tax=None, event=None, registered=None):
    """'2023'·'2023-2'·'2023-12-31'·'20231231' → (YYYYMMDD, 설명).
    event(양도·상속·증여·원천)면 연도가 아니라 그 사건의 날짜가 기준 — 날짜 필수. 양도는 registered(등기접수일)가 잔금일보다 빠르면 그날."""
    p = (period or "").strip()
    event = event or ("양도" if tax == "양도" else None)
    if event:
        if event not in EVENTS: raise ValueError(f"event는 {tuple(EVENTS)} 중 하나")
        name, rule = EVENTS[event]
        d = _ymd(p)
        if not d: raise ValueError(f"{event}은(는) 연도가 아니라 {name}로 기준일을 정함 — period에 날짜(YYYY-MM-DD) 입력. {rule}")
        if event == "양도":
            r = _ymd(registered or "")
            if r and r < d: return r, f"양도일 {r[:4]}.{r[4:6]}.{r[6:]}. — 잔금일({d[:4]}.{d[4:6]}.{d[6:]}.)보다 등기접수일이 빨라 등기접수일. {rule}"
            return d, f"양도일 {d[:4]}.{d[4:6]}.{d[6:]}. (잔금일{'' if r else ' — 등기접수일이 더 빠르면 registered로 입력'}). {rule}"
        return d, f"{name} {d[:4]}.{d[4:6]}.{d[6:]}. {rule}"
    if _ymd(p):
        d = _ymd(p); return d, f"사실 발생일 {d[:4]}.{d[4:6]}.{d[6:]}."
    m = re.fullmatch(r"(\d{4})\s*-?\s*([12])\s*기?", p)
    if m:
        y, h = m.groups(); d = f"{y}0630" if h == "1" else f"{y}1231"
        return d, f"부가가치세 {y}년 제{h}기 과세기간 종료일"
    m = re.fullmatch(r"(\d{4})", p)
    if m:
        if tax == "상증": raise ValueError("상속·증여는 연도가 아니라 상속개시일·증여일 기준 — event='상속'|'증여'와 날짜 입력")
        what = {"부가": "부가가치세 과세기간(2기) 종료일"}.get(tax, "사업연도·과세기간 종료일(1.1.~12.31. 가정 — 사업연도가 다르면 날짜로 입력)")
        return f"{p}1231", f"{p} {what}"
    raise ValueError("period는 '2023'(사업연도), '2023-1'(부가 과세기간) 또는 '2023-12-31'(날짜)")


def _norm(t): return re.sub(r"\s+", "", t or "")


def research(law_name, article, period, tax=None, n=8, event=None, registered=None):
    day, why = base_date(period, tax, event, registered)
    today = time.strftime("%Y%m%d")
    out = {"기준일": day, "기준일 근거": why, "법령": law_name, "조": article}
    with ThreadPoolExecutor(4) as ex:
        f_rules = ex.submit(ntis.basic_rules, law_name, article)
        f_std = ex.submit(ntis.exec_standards, law_name, article)
        f_rul = ex.submit(ntis.search, law_name.split()[0], ("해석", "판례"), tax, "최신", n, "", "", article, law_name)
        try:
            tiers = law.tiers(law_name, article, day)
            now = law.article(law_name, article, today)
            out["그 해 조문(3단)"] = tiers
            then_body = tiers[0].get("본문", "")
            changed = _norm(then_body) != _norm(now.get("본문", ""))
            out["현행과 비교"] = {"기준일 시행본": tiers[0].get("적용 시행일"), "현행 시행본": now.get("적용 시행일"),
                              "조문 변경": "있음 — 현행 조문을 그대로 적용하면 안 됨" if changed else "없음(법률 조문 본문 동일)"}
        except law.NoKey as e:
            then_body = None; out["그 해 조문(3단)"] = {"error": str(e)}
        rulings = f_rul.result()
        out["기본통칙"] = f_rules.result().get("통칙", [])
        out["집행기준"] = f_std.result().get("항목", [])
    # 해석·판례마다 등록일 시행본의 조문이 기준일 조문과 같은지
    if then_body is not None:
        vers = {}
        for r in rulings:
            d = re.sub(r"\D", "", r.get("일자", ""))[:8]
            if not d: r["기준일 조문과"] = "등록일 미상"; continue
            if d not in vers:
                try: vers[d] = law.article(law_name, article, d)
                except Exception: vers[d] = {}
            v = vers[d]
            if not v.get("본문"): r["기준일 조문과"] = "확인 불가"
            elif v.get("적용 시행일") == out["그 해 조문(3단)"][0].get("적용 시행일"): r["기준일 조문과"] = "같은 시행본"
            elif _norm(v["본문"]) == _norm(then_body): r["기준일 조문과"] = f"다른 시행본({v.get('적용 시행일')})이나 이 조 본문 동일"
            else: r["기준일 조문과"] = f"조문 개정 후({v.get('적용 시행일')}) — 인용 전 차이 확인"
    out["해석·판례"] = rulings
    out["주의"] = "법률 조문 본문 기준 비교. 시행령·시행규칙 개정 여부는 3단 결과에서 확인. 판정은 사용자 몫"
    return out
