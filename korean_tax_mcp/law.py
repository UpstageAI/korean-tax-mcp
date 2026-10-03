"""법제처 국가법령정보 공동활용(DRF) — 시점별 조문 원문과 법률→시행령→시행규칙 위임 체계.

인증키(OC)는 사용자 본인 것: https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC.
"""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

DRF = "https://www.law.go.kr/DRF"
CTX = ssl.create_default_context(); CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


class NoKey(RuntimeError):
    pass


def _oc():
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc: raise NoKey("법제처 OC 키가 없습니다 — https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC로 설정")
    return oc


@lru_cache(maxsize=512)
def _get(path, query):
    u = f"{DRF}/{path}?OC={_oc()}&type=JSON&{query}"
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "korean-tax-mcp"}), context=CTX, timeout=40) as r:
        return json.loads(r.read())


def _list(x): return x if isinstance(x, list) else ([x] if x else [])


def jo6(article):
    """'제52조' → '005200', '제28조의2' → '002802'."""
    m = re.fullmatch(r"제?(\d+)조(?:의(\d+))?", (article or "").strip())
    if not m: raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}"


@lru_cache(maxsize=128)
def _versions(law):
    d = _get("lawSearch.do", "target=eflaw&display=100&query=" + urllib.parse.quote(law))
    return [v for v in _list(d.get("LawSearch", {}).get("law")) if v.get("법령명한글") == law]


def version(law, as_of=""):
    """기준일(YYYYMMDD, 없으면 오늘)에 시행 중이던 연혁본 → (MST, 시행일자)."""
    day = as_of or time.strftime("%Y%m%d")
    vs = [v for v in _versions(law) if v.get("시행일자", "99999999") <= day]
    if not vs: return None, None
    v = max(vs, key=lambda x: x["시행일자"])
    return v["법령일련번호"], v["시행일자"]


def _texts(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k.endswith("내용") and k != "개정문내용" and isinstance(v, str): yield v
            elif k.endswith("내용") and k != "개정문내용" and isinstance(v, list) and all(isinstance(x, str) for x in v):
                yield "\n".join(v)   # 여러 줄짜리 목(가·나·다)은 문자열 목록으로 온다 — 빠뜨리면 공제율 등 핵심 문언이 사라짐
            elif isinstance(v, list) and v and all(isinstance(x, list) for x in v):
                for row in v: yield "\n".join(x for x in row if isinstance(x, str))
            else: yield from _texts(v)
    elif isinstance(o, list):
        for v in o: yield from _texts(v)


def article(law, article_no, as_of=""):
    mst, ef = version(law, as_of)
    if not mst: return {"error": f"'{law}'를 찾지 못했거나 {as_of or '오늘'} 이전 시행본이 없음 — 정식 법령명 확인"}
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={ef}&JO={jo6(article_no)}")
    body = "\n".join(t.strip() for t in _texts(d.get("법령", d)) if t.strip())
    return {"법령": law, "조": article_no, "적용 시행일": ef, "본문": body or "조문 없음 — 조번호 확인",
            "링크": f"https://www.law.go.kr/법령/{urllib.parse.quote(law)}/{article_no}"}


@lru_cache(maxsize=64)
def _three_tier(law):
    mst, _ = version(law)
    if not mst: return []
    d = _get("lawService.do", f"target=thdCmp&MST={mst}&knd=2")
    return _list(d.get("LspttnThdCmpLawXService", {}).get("위임조문삼단비교", {}).get("법률조문"))


def _jo_str(no, br): return f"제{int(no)}조" + (f"의{int(br)}" if br and br != "00" else "")


def tiers(law, article_no, as_of=""):
    """법률 조문 → [법률, 위임 시행령 조문들, 위임 시행규칙 조문들] 원문(기준일 시행본)."""
    j = jo6(article_no); no, br = j[:4], j[4:]
    with ThreadPoolExecutor(4) as ex:   # 위임 목록과 법·령·규칙 연혁 목록을 동시에
        tier = ex.submit(_three_tier, law)
        for name in (law, law + " 시행령", law + " 시행규칙"): ex.submit(_versions, name)
        tier = tier.result()
    dec, rul = [], []
    for r in tier:
        if r.get("조번호") != no or r.get("조가지번호", "00") != br: continue
        d = r.get("시행령조문") or {}; s = r.get("시행규칙조문") or {}
        if d.get("조번호"): dec.append(_jo_str(d["조번호"], d.get("조가지번호")))
        if s.get("조번호") and "서식" not in (s.get("조제목") or ""): rul.append(_jo_str(s["조번호"], s.get("조가지번호")))
    jobs = [("법률", law, article_no)] + [("시행령", law + " 시행령", a) for a in dict.fromkeys(dec)] + \
           [("시행규칙", law + " 시행규칙", a) for a in dict.fromkeys(rul)]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda x: {"단계": x[0], **article(x[1], x[2], as_of)}, jobs))
    return rows


# ── 영문 법령(법제처 공식 번역본, 법적 효력 없음) — OC 키에 「영문법령」 사용 신청 필요 ──
@lru_cache(maxsize=128)
def _en_versions(law):
    try: d = _get("lawSearch.do", "target=elaw&display=20&query=" + urllib.parse.quote(law))
    except Exception: return []
    return [v for v in _list(d.get("LawSearch", {}).get("law")) if v.get("법령명한글") == law]


def article_en(law, article_no):
    vs = _en_versions(law)
    if not vs:
        return {"error": "No official English translation found, or the LAW_OC key is not approved for English laws "
                         "(open.law.go.kr → OPEN API 신청 → 영문법령 체크)."}
    v = max(vs, key=lambda x: x.get("시행일자", ""))
    d = _get("lawService.do", f"target=elaw&MST={v['법령일련번호']}&JO={jo6(article_no)}")
    body = "\n".join(t.strip() for t in _texts(d) if t.strip())
    return {"법령": v.get("법령명영문") or law, "조": article_no, "적용 시행일": v.get("시행일자"), "본문": body or "article not found",
            "주의": "Official English translation by the Korea Legislation Research Institute — not legally binding and may lag behind amendments; "
                   "the Korean text prevails. Translation edition may differ from the as_of date."}


def history(law, article_no, last=8):
    """조문의 연혁: 최근 시행본들(시행예정 포함)에서 이 조 본문이 바뀐 시점."""
    vs = sorted({v["시행일자"]: v for v in _versions(law)}.values(), key=lambda x: x["시행일자"])[-last:]
    if not vs: return {"error": f"'{law}' 연혁을 찾지 못함 — 정식 법령명 확인"}
    jo = jo6(article_no)
    def body(v):
        try:
            d = _get("lawService.do", f"target=eflaw&MST={v['법령일련번호']}&efYd={v['시행일자']}&JO={jo}")
            return re.sub(r"\s+", "", "".join(_texts(d.get("법령", d))))
        except Exception:
            return None
    with ThreadPoolExecutor(6) as ex: bodies = list(ex.map(body, vs))
    rows, prev = [], None
    for v, b in zip(vs, bodies):
        changed = None if b is None or prev is None else (b != prev)
        rows.append({"시행일": v["시행일자"], "공포일": v.get("공포일자", ""), "제개정": v.get("제개정구분명", ""),
                     "상태": v.get("현행연혁코드", ""), "이 조 변경": "확인 불가" if b is None else ("기준" if prev is None else ("바뀜" if changed else "그대로"))})
        if b is not None: prev = b
    upcoming = [r for r in rows if r["상태"] == "시행예정" and r["이 조 변경"] == "바뀜"]
    return {"법령": law, "조": article_no, "연혁": rows,
            "요약": ("시행 예정 개정에서 이 조가 바뀜: " + ", ".join(r["시행일"] for r in upcoming)) if upcoming else "시행 예정 개정 중 이 조 변경 없음",
            "주의": f"최근 {len(rows)}개 시행본만 비교(법률 조문 본문 기준). 더 이전은 law_article(as_of)로 확인"}
