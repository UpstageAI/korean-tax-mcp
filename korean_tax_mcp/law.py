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
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache, wraps

from . import _mask_oc

DRF = "https://www.law.go.kr/DRF"
CTX = ssl.create_default_context(); CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


class NoKey(RuntimeError):
    pass


def _oc():
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc: raise NoKey("법제처 OC 키가 없습니다 — https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC로 설정")
    return oc


def _get(path, query):
    """법제처 DRF API 호출. 재시도 2회(지수 백오프), 타임아웃 20초."""
    u = f"{DRF}/{path}?OC={_oc()}&type=JSON&{query}"
    last_exc = None
    for attempt in range(3):  # 최대 2회 재시도 (총 3회 시도)
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "korean-tax-mcp"}), context=CTX, timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            last_exc = e
            if attempt < 2:
                time.sleep(2 ** attempt)  # 지수 백오프: 1초, 2초
    raise last_exc


# 메모리 캐시용 TTL (기본 24시간)
_CACHE_TTL = int(os.environ.get("KTM_CACHE_TTL", 86400))


def _ttl_cache(maxsize=128, ttl=_CACHE_TTL):
    """TTL 기반 메모리 캐시 데코레이터. 날짜가 바뀌면 시행본 재조회."""

    def decorator(func):
        cache = {}
        order = []

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, frozenset(kwargs.items()))
            now = time.time()
            if key in cache:
                val, expiry = cache[key]
                if now < expiry:
                    return val
                del cache[key]
                order.remove(key)
            result = func(*args, **kwargs)
            cache[key] = (result, now + ttl)
            order.append(key)
            if len(order) > maxsize:
                old = order.pop(0)
                cache.pop(old, None)
            return result

        def clear():
            cache.clear()
            order.clear()

        wrapper.clear = clear
        return wrapper

    return decorator


def _list(x): return x if isinstance(x, list) else ([x] if x else [])


_ARTICLE_RE = re.compile(
    r"(?:제\s*)?\d+\s*조\s*(?:의\s*\d+)?"
    r"|"
    r"(?:제\s*)?\d+\s*의\s*\d+"
    r"|"
    r"\d+\s*-\s*\d+"
    r"|"
    r"\d+"
)


def normalize_article(raw):
    """'26의2', '26조의2', '제26조의2', '26-2', '26_2', '§26의2', 'Art. 26-2' → '제26조의2'.
    '10', '10조', '제10조' → '제10조'.
    항·호가 붙은 입력('제26조의2 제1항', '26의2①')은 조 부분만 정규화하고 항 정보는 분리.
    '의정서'처럼 숫자가 아닌 값은 그대로 반환.
    정규화 실패 시 ValueError."""

    if raw is None:
        return None, None
    s = raw.strip()
    if not s:
        return None, None

    # 조약 '의정서' 등 숫자 아닌 값은 그대로 통과
    if not _ARTICLE_RE.search(s):
        return s, None

    # §/Art./영문 접두사 제거 (공백 포함)
    s2 = re.sub(r"^\s*(?:§|Art\.|Article)\s*", "", s)

    # circled number(①~⑩) → 숫자. 항·호 감지와 base 분리 전에 처리
    _CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(10)}  # ①→'1', …, ⑩→'10'

    def _circled_replace(m):
        return _CIRCLED.get(m.group(0), m.group(0))

    # 조 번호는 맨 앞 '제N조(의M)'·'N의M'·'N-M'만 읽고, 뒤에 오는 항·호 숫자는 조 번호에 섞지 않는다
    # ('제17조 제2항 제2호'가 제172조로 읽히던 문제)
    m = re.match(r"\s*(?:제\s*)?(\d+)\s*(?:조)?\s*(?:(?:의|-|_)\s*(\d+))?", s2)
    if not m:
        raise ValueError("조문은 '제52조' 형식 — 예: '제52조', '26의2', '26-2'")
    main_no = int(m.group(1))
    branch_no = int(m.group(2)) if m.group(2) else 0

    # 나머지에서 항(①~⑳ 또는 'N항') 우선, 항이 없으면 호('N호')
    rest = s2[m.end():]
    hang_info = None
    c = re.search(r"[①-⑳]", rest)
    h = re.search(r"(?:제\s*)?(\d+)\s*항", rest)
    if c:
        hang_info = f"제{_CIRCLED.get(c.group(0), ord(c.group(0)) - 0x2460 + 1)}항"
    elif h:
        hang_info = f"제{h.group(1)}항"
    else:
        ho = re.search(r"(?:제\s*)?(\d+)\s*호", rest)
        if ho:
            hang_info = f"제{ho.group(1)}호"

    norm = f"제{main_no}조" + (f"의{branch_no}" if branch_no else "")
    return norm, hang_info


def requested_ho(raw):
    """'제17조 제2항 제2호' → '제2호'. 항과 호가 함께 왔을 때 호만 돌려줌(없으면 None)."""
    if not raw: return None
    s = re.sub(r"^\s*(?:§|Art\.|Article)\s*", "", str(raw))
    m = re.match(r"\s*(?:제\s*)?\d+\s*(?:조)?\s*(?:(?:의|-|_)\s*\d+)?", s)
    rest = s[m.end():] if m else s
    if not (re.search(r"[①-⑳]", rest) or re.search(r"\d+\s*항", rest)): return None
    ho = re.search(r"(?:제\s*)?(\d+)\s*호", rest)
    if ho: return f"제{ho.group(1)}호"
    c = re.search(r"[①-⑳]\s*(\d+)\s*$", rest)    # '제17조②2'
    return f"제{c.group(1)}호" if c else None


def ho_text(body, hang, ho):
    """본문에서 hang(예: '제2항') 안의 ho(예: '제2호') 줄과 그 아래 목(가.·나.)까지 잘라 돌려줌. 못 찾으면 ''."""
    try:
        hn = int(re.sub(r"\D", "", hang)); hon = int(re.sub(r"\D", "", ho))
    except ValueError:
        return ""
    lines = body.split("\n")
    mark = chr(0x2460 + hn - 1) if 1 <= hn <= 20 else None
    start = next((i for i, ln in enumerate(lines) if mark and ln.lstrip().startswith(mark)), None)
    if start is None: return ""
    out = []
    for ln in lines[start + 1:]:
        t = ln.lstrip()
        if re.match(r"^[①-⑳]", t): break                       # 다음 항
        m = re.match(r"^(\d+)\.", t)
        if m:
            if out: break                                           # 다음 호
            if int(m.group(1)) == hon: out.append(ln)
            continue
        if out: out.append(ln)                                      # 목·이어지는 줄
    return "\n".join(out)


def jo6(article):
    """'제52조' → '005200', '제28조의2' → '002802'."""
    norm, _ = normalize_article(article)
    m = re.fullmatch(r"제(\d+)조(?:의(\d+))?", norm)
    if not m: raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}"


@_ttl_cache(maxsize=128)
def _versions(law):
    # 연혁은 한 페이지 100건까지라 끝까지 넘겨 읽는다 — 첫 페이지만 읽으면 개정이 잦은 시행령은
    # 몇 년 전 시행본이 통째로 빠짐(소득세법 시행령은 2018-02 이전이 안 보였음)
    out, page = [], 1
    while True:
        d = _get("lawSearch.do", f"target=eflaw&display=100&page={page}&query=" + urllib.parse.quote(law))
        ls = d.get("LawSearch", {})
        rows = _list(ls.get("law"))
        out += [v for v in rows if v.get("법령명한글") == law]
        try: total = int(ls.get("totalCnt") or 0)
        except ValueError: total = 0
        if len(rows) < 100 or page * 100 >= total or page >= 20: break
        page += 1
    return out


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
    norm, _ = normalize_article(article_no)
    mst, ef = version(law, as_of)
    if not mst: return {"error": f"'{law}'를 찾지 못했거나 {as_of or '오늘'} 이전 시행본이 없음 — 정식 법령명 확인"}
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={ef}&JO={jo6(norm)}")
    lines = [t.strip() for t in _texts(d.get("법령", d)) if t.strip()]
    # DRF 응답 구조상 "항"→"호" 순회가 "조문내용"보다 먼저 yield될 수 있으므로
    # 조 제목 라인(제N조(...) 형태)과 편·장·절·관 제목을 명시적으로 분리한다.
    HEAD_RE = re.compile(r'^제\d+조(?:의\d+)?\s*\(')
    GUAN_RE = re.compile(r'^제\d+(관|장|절|관)\b')
    head = None
    body_lines = []
    for ln in lines:
        if GUAN_RE.match(ln):
            continue  # 편·장·절·관 제목 제거
        if HEAD_RE.match(ln) and head is None:
            head = ln  # 조 제목 라인 저장 (맨 앞에 배치)
            continue
        body_lines.append(ln)
    if head is not None:
        # 머리말 라인에서 개정/신설 표시 제거 (완전 태그 + 잘린 꺾쇠)
        head = re.sub(r'<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b', '', head).strip()
        body_lines.insert(0, head)
    body = "\n".join(body_lines)
    return {"법령": law, "조": norm, "적용 시행일": ef, "본문": body or "조문 없음 — 조번호 확인",
            "링크": f"https://www.law.go.kr/법령/{urllib.parse.quote(law)}/{norm}"}


@lru_cache(maxsize=64)
def _three_tier(law):
    mst, _ = version(law)
    if not mst: return []
    d = _get("lawService.do", f"target=thdCmp&MST={mst}&knd=2")
    return _list(d.get("LspttnThdCmpLawXService", {}).get("위임조문삼단비교", {}).get("법률조문"))


def _jo_str(no, br): return f"제{int(no)}조" + (f"의{int(br)}" if br and br != "00" else "")


@lru_cache(maxsize=32)
def _raw_units(law, ef):
    """법령 전체 조문단위 원본 목록(전문=장·절 머리 포함) — 목차용 (Claude 10-15)"""
    mst, vef = version(law, ef)
    if not mst: return []
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={vef}")
    return [u for u in _list(d.get("법령", d).get("조문", {}).get("조문단위")) if isinstance(u, dict)]


@lru_cache(maxsize=32)
def _full_units(law, ef):
    """법령 전체(1회 요청) → [(조, 항, 호, 단위 원문)] 문서 순서. 50조 제한 없음 (Claude 10-12)"""
    mst, vef = version(law, ef)
    if not mst: return []
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={vef}")
    out = []
    for u in _list(d.get("법령", d).get("조문", {}).get("조문단위")):
        if u.get("조문여부") != "조문": continue
        jo = _jo_str(u.get("조문번호", "0"), u.get("조문가지번호") or "00")
        for t in _texts({"조문내용": u.get("조문내용")}): out.append((jo, "", "", t))
        for h in _list(u.get("항")):
            if not isinstance(h, dict): continue
            hn = (h.get("항번호") or "").strip()
            for t in _texts({"항내용": h.get("항내용")}): out.append((jo, hn, "", t))
            for ho in _list(h.get("호")):
                if not isinstance(ho, dict): continue
                hon = (ho.get("호번호") or "").strip()
                for t in _texts({"호내용": ho.get("호내용")}): out.append((jo, hn, hon, t))
                for mk in _list(ho.get("목")):
                    if isinstance(mk, dict):
                        for t in _texts({"목내용": mk.get("목내용")}): out.append((jo, hn, hon, t))
    return out


_DEF_RE = re.compile(r"(?:법|영)\s*(제\d+조(?:의\d+)?)((?:제\d+항)?)(?:제\d+호(?:의\d+)?)?(?:[가-하]목)?[^\"\u201c]{0,40}?에서\s*[\"\u201c]([^\"\u201d]{2,40})[\"\u201d]\s*(?:이)?란")


@lru_cache(maxsize=32)
def _phrase_defs(lower_law, ef):
    """하위 법령(시행령→'법', 시행규칙→'영' 인용)에서 상위 조의 위임 구절을 정의한 곳 목록"""
    cite = "법" if lower_law.endswith("시행령") else "영"
    out = []
    for jo, hn, hon, t in _full_units(lower_law, ef):
        for m in _DEF_RE.finditer(t):
            if not t[m.start():].startswith(cite): continue
            out.append({"상위조": m.group(1), "상위항": m.group(2), "구절": m.group(3), "하위조": jo, "하위항": hn, "하위호": hon})
    return out


def links(law_name, article_no, as_of=""):
    """법령·조의 상위·하위 위임 연결.

    반환: {"상위": [{"법령","조","항"?,"구절"?,"출처"?}...], "하위": [...]}
    출처①: 법제처 3단비교 공식표(_three_tier). 법률·시행령·시행규칙 어느 쪽 입력이든 양방향 조회.
    출처②: 하위 법령 원문에서 '법 제N조…에서 "…으로 정하는 X"란'(시행규칙은 '영 제N조…') 위임 구절 정의로 상위 조문 특정.
    ①∪② 합집합, (법령, 조) 중복 제거(구절 정보 보존). 법령명 비교는 공백만 무시, 급(시행령·시행규칙) 유지.
    """
    norm, _ = normalize_article(article_no)
    j = jo6(norm); no, br = int(j[:4]), int(j[4:]) if j[4:] else 0
    N = lambda s: re.sub(r"\s+", "", s or "")

    # 입력이 법률/시행령/시행규칙인지에 따라 계열 법률과 유형 결정
    tier_type = "법률"
    base_law = law_name
    if law_name.endswith(" 시행령"):
        base_law = law_name[:-4]
        tier_type = "시행령"
    elif law_name.endswith(" 시행규칙"):
        base_law = law_name[:-5]
        tier_type = "시행규칙"

    ef = re.sub(r"\D", "", as_of or "") or time.strftime("%Y%m%d")
    if len(ef) != 8: ef = time.strftime("%Y%m%d")

    up, down = [], []

    # ── 출처①: 3단비교 공식표 ──
    tier_rows = _three_tier(base_law)
    for r in tier_rows:
        if tier_type == "법률":
            if not r.get("조번호") or int(r.get("조번호")) != no or int(r.get("조가지번호", "00")) != br: continue
        elif tier_type == "시행령":
            d = r.get("시행령조문") or {}
            if not d.get("조번호") or int(d.get("조번호")) != no or int(d.get("조가지번호", "00")) != br: continue
        elif tier_type == "시행규칙":
            s = r.get("시행규칙조문") or {}
            if not s.get("조번호") or int(s.get("조번호")) != no or int(s.get("조가지번호", "00")) != br: continue
        d = r.get("시행령조문") or {}
        s = r.get("시행규칙조문") or {}

        if tier_type == "법률":
            if d.get("조번호"):
                down.append({"법령": base_law + " 시행령", "조": _jo_str(d["조번호"], d.get("조가지번호")), "출처": "공식표"})
            if s.get("조번호"):
                down.append({"법령": base_law + " 시행규칙", "조": _jo_str(s["조번호"], s.get("조가지번호")), "출처": "공식표"})
        elif tier_type == "시행령":
            if r.get("조번호"):
                up.append({"법령": base_law, "조": _jo_str(r["조번호"], r.get("조가지번호")), "출처": "공식표"})
            if s.get("조번호"):
                down.append({"법령": base_law + " 시행규칙", "조": _jo_str(s["조번호"], s.get("조가지번호")), "출처": "공식표"})
        elif tier_type == "시행규칙":
            if r.get("조번호"):
                up.append({"법령": base_law, "조": _jo_str(r["조번호"], r.get("조가지번호")), "출처": "공식표"})
            if d.get("조번호"):
                up.append({"법령": base_law + " 시행령", "조": _jo_str(d["조번호"], d.get("조가지번호")), "출처": "공식표"})

    # ── 출처②: 하위 법령 원문의 구절 정의 '법(영) 제N조…에서 "…으로 정하는 X"란' (Claude 10-12, 정밀 일치만) ──
    lower_of = {"법률": base_law + " 시행령", "시행령": base_law + " 시행규칙"}
    if tier_type in lower_of:   # 이 조를 인용해 구절을 정의한 하위 조문 → 하위
        for dfn in _phrase_defs(lower_of[tier_type], ef):
            if dfn["상위조"] == norm:
                down.append({"법령": lower_of[tier_type], "조": dfn["하위조"], "항": dfn["하위항"],
                             "구절": dfn["구절"], "상위항": dfn["상위항"], "출처": "원문정의"})
    if tier_type in ("시행령", "시행규칙"):   # 이 조 원문이 인용한 상위 조 → 상위
        upper = base_law if tier_type == "시행령" else base_law + " 시행령"
        for dfn in _phrase_defs(law_name, ef):
            if dfn["하위조"] == norm:
                up.append({"법령": upper, "조": dfn["상위조"], "항": dfn["상위항"], "구절": dfn["구절"], "출처": "원문정의"})

    # ── ①∪② 합집합, (법령, 조) 중복 제거(구절 정보 보존) ──
    def dedup(items):
        # (법령, 조, 구절) 단위로 보존 — 한 조에 여러 위임 구절이 있으면 모두 남김. 구절 있는 항목이 있으면 같은 조의 구절 없는 중복은 제거
        out, seen = [], set()
        with_phrase = {(N(x["법령"]), x["조"]) for x in items if x.get("구절")}
        for x in items:
            k = (N(x["법령"]), x["조"], x.get("구절") or "")
            if k in seen: continue
            if not x.get("구절") and (k[0], k[1]) in with_phrase: continue
            seen.add(k); out.append(x)
        return out

    # 확인 수준 표시 (Claude 10-12): 하위 조문 원문이 상위 조를 직접 인용하면 "원문인용", 공식표에만 있으면 "공식표만"(포괄 위임·간접 연결 가능)
    def _cited(lower, lower_jo, upper_jo):
        w = "법" if lower.endswith("시행령") else "영"
        txt = "\n".join(t for jo, _, _, t in _full_units(lower, ef) if jo == lower_jo)
        return bool(re.search(w + r"\s*" + re.escape(upper_jo) + r"(?![0-9]|의\d)", txt))
    def mark(items, direction):
        for x in items:
            if x.get("출처") == "원문정의":
                x["확인"] = "원문인용"; continue
            try:
                if direction == "하위":
                    ok = _cited(x["법령"], x["조"], norm) if (tier_type == "법률" and x["법령"].endswith("시행령")) or (tier_type == "시행령" and x["법령"].endswith("시행규칙")) else False
                else:
                    ok = _cited(law_name, norm, x["조"]) if (tier_type == "시행령" and not x["법령"].endswith("시행령")) or (tier_type == "시행규칙" and x["법령"].endswith("시행령")) else False
            except Exception:
                ok = False
            x["확인"] = "원문인용" if ok else "공식표만"
        return sorted(items, key=lambda x: x["확인"] != "원문인용")
    return {"상위": mark(dedup(up), "상위"), "하위": mark(dedup(down), "하위")}


def tiers(law, article_no, as_of=""):
    """법령 조문 → [상위·해당·하위 단계] 원문(기준일 시행본). 법률·시행령·시행규칙 모두 지원."""
    norm, _ = normalize_article(article_no)
    j = jo6(norm); no, br = j[:4], j[4:]

    # 입력이 시행령·시행규칙이면 계열 법률 찾기
    base_law = law
    if law.endswith(" 시행령"):
        base_law = law[:-4]
    elif law.endswith(" 시행규칙"):
        base_law = law[:-5]

    with ThreadPoolExecutor(4) as ex:
        tier = ex.submit(_three_tier, base_law)
        for name in (base_law, base_law + " 시행령", base_law + " 시행규칙"): ex.submit(_versions, name)
        tier = tier.result()

    # 입력이 법률이면: 법률 조문 번호(no, br)로 행 찾기
    # 입력이 시행령이면: 시행령 조문 번호(no, br)로 행 찾기
    # 입력이 시행규칙이면: 시행규칙 조문 번호(no, br)로 행 찾기
    matched_rows = []
    for r in tier:
        if law == base_law:
            if r.get("조번호") != no or r.get("조가지번호", "00") != br: continue
        elif law.endswith(" 시행령"):
            d = r.get("시행령조문") or {}
            if d.get("조번호") != no or d.get("조가지번호", "00") != br: continue
        elif law.endswith(" 시행규칙"):
            s = r.get("시행규칙조문") or {}
            if s.get("조번호") != no or s.get("조가지번호", "00") != br: continue
        matched_rows.append(r)

    dec, rul = [], []
    law_no, law_br = None, None
    for r in matched_rows:
        d = r.get("시행령조문") or {}; s = r.get("시행규칙조문") or {}
        if d.get("조번호"): dec.append(_jo_str(d["조번호"], d.get("조가지번호")))
        if s.get("조번호") and "서식" not in (s.get("조제목") or ""): rul.append(_jo_str(s["조번호"], s.get("조가지번호")))
        if law_no is None:
            law_no = r.get("조번호"); law_br = r.get("조가지번호", "00")

    # 단계 구성
    steps = []
    tier_type = "법률"
    if law.endswith(" 시행령"): tier_type = "시행령"
    elif law.endswith(" 시행규칙"): tier_type = "시행규칙"

    if tier_type == "법률":
        steps = [("법률", law, norm)]
        steps += [("시행령", base_law + " 시행령", a) for a in dict.fromkeys(dec)]
        steps += [("시행규칙", base_law + " 시행규칙", a) for a in dict.fromkeys(rul)]
    elif tier_type == "시행령":
        # 상위: 법률 (3단비교 행의 법률 조문)
        if law_no:
            steps = [("법률", base_law, _jo_str(law_no, law_br))]
        else:
            steps = [("법률", base_law, norm)]  # fallback: 동일한 조 번호
        steps += [("시행령", law, norm)]
        steps += [("시행규칙", base_law + " 시행규칙", a) for a in dict.fromkeys(rul)]
    elif tier_type == "시행규칙":
        # 상위: 법률, 시행령
        if law_no:
            steps = [("법률", base_law, _jo_str(law_no, law_br))]
        else:
            steps = [("법률", base_law, norm)]
        steps += [("시행령", base_law + " 시행령", norm)]  # 동일한 조 번호 (fallback)
        steps += [("시행규칙", law, norm)]

    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda x: {"단계": x[0], **article(x[1], x[2], as_of)}, steps))
    return rows


# ── 영문 법령(법제처 공식 번역본, 법적 효력 없음) — OC 키에 「영문법령」 사용 신청 필요 ──
@lru_cache(maxsize=128)
def _en_versions(law):
    try: d = _get("lawSearch.do", "target=elaw&display=20&query=" + urllib.parse.quote(law))
    except Exception: return []
    return [v for v in _list(d.get("LawSearch", {}).get("law")) if v.get("법령명한글") == law]


def article_en(law, article_no):
    norm, _ = normalize_article(article_no)
    vs = _en_versions(law)
    if not vs:
        return {"error": "No official English translation found, or the LAW_OC key is not approved for English laws "
                         "(open.law.go.kr → OPEN API 신청 → 영문법령 체크)."}
    v = max(vs, key=lambda x: x.get("시행일자", ""))
    d = _get("lawService.do", f"target=elaw&MST={v['법령일련번호']}&JO={jo6(norm)}")
    body = "\n".join(t.strip() for t in _texts(d) if t.strip())
    return {"법령": v.get("법령명영문") or law, "조": norm, "적용 시행일": v.get("시행일자"), "본문": body or "article not found",
            "주의": "Official English translation by the Korea Legislation Research Institute — not legally binding and may lag behind amendments; "
                   "the Korean text prevails. Translation edition may differ from the as_of date."}


def history(law, article_no, last=8):
    """조문의 연혁: 최근 시행본들(시행예정 포함)에서 이 조 본문이 바뀐 시점."""
    norm, _ = normalize_article(article_no)
    vs = sorted({v["시행일자"]: v for v in _versions(law)}.values(), key=lambda x: x["시행일자"])[-last:]
    if not vs: return {"error": f"'{law}' 연혁을 찾지 못함 — 정식 법령명 확인"}
    jo = jo6(norm)
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
    return {"법령": law, "조": norm, "연혁": rows,
            "요약": ("시행 예정 개정에서 이 조가 바뀜: " + ", ".join(r["시행일"] for r in upcoming)) if upcoming else "시행 예정 개정 중 이 조 변경 없음",
            "주의": f"최근 {len(rows)}개 시행본만 비교(법률 조문 본문 기준). 더 이전은 law_article(as_of)로 확인"}
# ── 조문 위치 찾기 (find_article) ────────────────────────────────────────────

_DEFAULT_LAWS = (
    "국세기본법", "국세징수법", "소득세법", "법인세법", "부가가치세법",
    "상속세 및 증여세법", "조세특례제한법", "국제조세조정에 관한 법률",
    "국세기본법 시행령", "국세징수법 시행령", "소득세법 시행령", "법인세법 시행령",
    "부가가치세법 시행령", "상속세 및 증여세법 시행령", "조세특례제한법 시행령",
)

_FIND_CACHE = {}
_FIND_CACHE_TTL = int(os.environ.get("KTM_CACHE_TTL", 86400))


def _find_cache_key(law, ef):
    return (law, ef)


def _fetch_law_articles(law, ef):
    """한 법령의 조문 전부(제목+본문)를 조문단위 기반으로 조회해 캐시.

    lawService.do 한 번으로 받은 '법령.조문.조문단위'를 순회하며
    조문여부=='조문'인 단위만 쓴다. '전문'(장·절·관 머리)과 삭제 조문은 버린다.
    같은 응답의 '법령.부칙.부칙단위'도 함께 파싱해 캐시에 저장한다.
    캐시 항목은 {"articles": [...], "addenda": [...], "expiry": ...} 형태.
    """
    key = _find_cache_key(law, ef)
    if (cached := _FIND_CACHE.get(key)) and time.time() < cached["expiry"]:
        return cached["articles"]
    mst, actual_ef = version(law, ef)
    if not mst:
        _FIND_CACHE[key] = {"articles": [], "addenda": [], "expiry": time.time() + _FIND_CACHE_TTL}
        return []
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={actual_ef}")
    law_obj = d.get("법령", d)
    units = [u for u in _list(law_obj.get("조문", {}).get("조문단위")) if isinstance(u, dict)]
    addenda_units = [u for u in _list(law_obj.get("부칙", {}).get("부칙단위")) if isinstance(u, dict)]

    articles = []
    for u in units:
        # "전문"(장·절 머리)은 버리고 "조문"만 쓴다
        if u.get("조문여부") != "조문":
            continue
        jo = _jo_str(u.get("조문번호", "0"), u.get("조문가지번호") or "00")
        title = (u.get("조문제목") or "").strip()
        content = u.get("조문내용") or ""
        # 삭제 조문: 제목이 비어 있고 내용이 '제N조(의M)? 삭제'로 시작하면 버린다
        if not title and re.match(r"^제\d+조(?:의\d+)?\s*삭제\b", content.strip()):
            continue
        # 본문: 조문내용 + 항→호→목 내용을 _full_units와 같은 순서로 이어붙인다
        body_parts = []
        for t in _texts({"조문내용": content}):
            body_parts.append(t)
        for h in _list(u.get("항")):
            if not isinstance(h, dict):
                continue
            for t in _texts({"항내용": h.get("항내용")}):
                body_parts.append(t)
            for ho in _list(h.get("호")):
                if not isinstance(ho, dict):
                    continue
                for t in _texts({"호내용": ho.get("호내용")}):
                    body_parts.append(t)
                for mk in _list(ho.get("목")):
                    if isinstance(mk, dict):
                        for t in _texts({"목내용": mk.get("목내용")}):
                            body_parts.append(t)
        body = "\n".join(body_parts).strip()
        # 제목 정규화: <개정…>, <신설…> 태그 제거
        title_clean = re.sub(r"<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b", "", title).strip()
        articles.append({"조": jo, "제목": title_clean, "본문": body, "적용 시행일": actual_ef})

    # 부칙 단위 파싱: 각 부칙마다 '줄 목록'과 '부칙공포일자'를 둔다 (줄바꿈 기준, 문장 부호 분할 없음)
    addenda = []
    for au in addenda_units:
        add_text = au.get("부칙내용") or ""
        raw = "\n".join(t.strip() for t in _texts({"부칙내용": add_text}) if t.strip())
        add_lines = [ln for ln in raw.split("\n") if ln.strip()] if raw else []
        if add_lines:
            head_line = add_lines[0]
        else:
            br_no = au.get("부칙공포번호") or ""
            br_date = au.get("부칙공포일자") or ""
            head_line = f"부칙 <제{br_no},{br_date}>"
        addenda.append({"lines": add_lines, "head": head_line, "date": au.get("부칙공포일자", "")})

    _FIND_CACHE[key] = {"articles": articles, "addenda": addenda, "expiry": time.time() + _FIND_CACHE_TTL}
    return articles


def _fetch_law_articles_with_addenda(law, ef):
    """_fetch_law_articles와 같지만, 캐시에서 (articles, addenda) 둘 다 반환.

    _fetch_law_articles가 이미 조문·부칙을 함께 캐시하므로 lawService.do 재호출 없이
    캐시에서 부칙만 함께 반환한다.
    """
    _fetch_law_articles(law, ef)  # 캐시 확보 (없으면 조회 후 저장)
    key = _find_cache_key(law, ef)
    cached = _FIND_CACHE.get(key)
    if cached:
        return cached["articles"], cached["addenda"]
    return [], []


def _kw_split(kw):
    return [w for w in re.split(r"\s+", kw.strip()) if w]


def _sentences_with_keywords(text, kw_words, max_chars=200):
    """키워드 단어가 모두 들어간 문장 1~2개(각 200자 이내)."""
    if not text or not kw_words:
        return []
    parts = re.split(r"([。\。\n]+)", text)
    sents = []
    buf = ""
    for p in parts:
        if p in ("。", "。", "\n", ""):
            if buf.strip():
                sents.append(buf.strip())
            buf = ""
        else:
            buf += p
    if buf.strip():
        sents.append(buf.strip())
    if len(sents) <= 1 and len(text) > 200:
        sents = [s.strip() for s in text.split("\n") if s.strip()]
    # 키워드 단어가 하나라도 포함된 문장 중, 많이 포함된 순서로 상위 2개
    scored_sents = []
    for s in sents:
        if len(s) > max_chars:
            s = s[:max_chars]
        cnt = sum(1 for w in kw_words if w in s)
        if cnt > 0:
            scored_sents.append((cnt, s))
    scored_sents.sort(key=lambda x: -x[0])
    return [s for _, s in scored_sents[:2]]


def _title_compress(s):
    """제목 정규화: 가운뎃점(ㆍ·)과 공백을 단어 구분자로 쓴 뒤,
    낱말 중 '등'·'등의'만 제거하고 이어 붙인다.

    예: '경정 등의 청구' → '경정청구', '가산세 감면 등' → '가산세감면',
         '사업자등록' → '사업자등록', '등기ㆍ등록 등' → '등기등록'
    """
    if not s:
        return ""
    # 가운뎃점을 공백으로 바꿔 단어 경계를 만든 뒤 분할
    s = s.replace("ㆍ", " ").replace("·", " ")
    words = s.split()
    words = [w for w in words if w not in ("등", "등의")]
    return "".join(words)


def _title_score(keyword, title, kw_words):
    if not title:
        return 0
    comp_kw = _title_compress(keyword)
    comp_title = _title_compress(title)
    tl = title.lower()
    if comp_kw and comp_title and comp_kw == comp_title:
        # 제목 압축형과 키워드 압축형이 완전히 같음 → 맨 위로 올리는 큰 가산점
        return 1000 + sum(title.count(w) for w in kw_words)
    if comp_kw and comp_title and comp_kw in comp_title:
        # 제목 압축형에 키워드 압축형이 들어 있음 → '모든 단어 있음'과 같게 취급
        return 100 + sum(title.count(w) for w in kw_words)
    if all(w.lower() in tl for w in kw_words):
        return 100 + sum(title.count(w) for w in kw_words)
    return sum(1 for w in kw_words if w.lower() in tl)


def _body_score(keyword, body, kw_words):
    bl = body.lower()
    return sum(min(bl.count(w.lower()), 10) for w in kw_words)


def find_article(keyword, law_name=None, as_of="", n=5):
    """키워드로 조문 위치를 찾는다. 조문 번호를 모를 때 first step.

    law_name 생략 시 주요 세법(국세기본법·징수법·소득세법·법인세법·부가가치세법·
    상속세및증여세법·조세특례제한법·국제조세조정에관한법률 + 각 시행령)을 모두 조회.
    """
    kw_words = _kw_split(keyword)
    if not kw_words:
        return {"error": "keyword 필요"}
    if n < 1:
        n = 1
    ef = re.sub(r"\D", "", as_of or "") or time.strftime("%Y%m%d")
    if len(ef) != 8:
        return {"error": "as_of는 YYYYMMDD 또는 YYYY-MM-DD"}

    target_laws = list(_DEFAULT_LAWS) if law_name is None else ([law_name] if isinstance(law_name, str) else list(law_name))

    # 2. 조문 수집
    #    - NoKey: law_article과 같은 문구로 즉시 반환 (version()→_oc()에서 발생)
    #    - 그 외 예외 또는 빈 결과: 건너뛰기
    all_articles = []
    no_key_raised = False
    mst_found_any = False
    for law in target_laws:
        # version()을 안전하게 호출해 MST 존재 여부 확인 (NoKey 발생 가능)
        try:
            mst, _ = version(law, ef)
        except NoKey:
            no_key_raised = True
            continue
        except Exception:
            continue
        if mst:
            mst_found_any = True
        try:
            arts = _fetch_law_articles(law, ef)
            for a in arts:
                all_articles.append({**a, "_law": law})
        except NoKey:
            no_key_raised = True
            continue
        except Exception:
            continue

    if no_key_raised:
        return {"error": "법제처 OC 키가 없습니다 — 'LAW_OC' 환경변수 설정 필요 (https://open.law.go.kr). "
                         "OC 키 없이는 law_article/find_article 모두 사용할 수 없습니다.",
                "다음 단계": "https://open.law.go.kr 에서 무료 OC 키 신청 후 환경변수 LAW_OC로 설정"}

    if not mst_found_any:
        return {"error": "법령을 찾지 못함 — law_name 확인",
                "다음 단계": "법령 정식 명칭 확인 (예: '소득세법')."}

    if not all_articles:
        return {"error": "일치하는 조문 없음 — 키워드를 줄이거나 다른 말로",
                "다음 단계": "law_article(law_name, 조, keyword=...)로 해당 항만 조회"}

    # 3. 점수 매기기
    # 제목 전부 일치(모든 키워드 단어가 제목에 있거나, 키워드 압축형이 제목 압축형에 포함)를
    # 한 묶음으로 두고 총점순 정렬, 그 뒤에 나머지를 총점순으로 둔다.
    title_full = []
    others = []
    for a in all_articles:
        title_s = _title_score(keyword, a.get("제목", ""), kw_words)
        body_s = _body_score(keyword, a.get("본문", ""), kw_words)
        if title_s == 0 and body_s == 0:
            continue
        title_text = a.get("제목", "")
        all_in_title = all(w.lower() in title_text.lower() for w in kw_words)
        comp_match = _title_compress(keyword) and _title_compress(keyword) in _title_compress(title_text)
        all_in_body = all(w.lower() in a.get("본문", "").lower() for w in kw_words)
        total = title_s * 5 + body_s + (20 if all_in_title else 0) + (10 if all_in_body else 0)
        entry = (total, a)
        if all_in_title or comp_match:
            title_full.append(entry)
        else:
            others.append(entry)

    title_full.sort(key=lambda x: -x[0])
    others.sort(key=lambda x: -x[0])
    ranked = title_full + others
    top = ranked[:n]

    # 4. 관련 부칙 (1위 결과의 법령 부칙에서만, 조문단위 구조에서 파싱한 부칙 중 대상만)
    addenda_for_top = []
    if top:
        top_law = top[0][1].get("_law", "")
        top_jo = top[0][1].get("조", "")
        if top_law and top_jo:
            jo_num = re.match(r"^제(\d+)조(?:의\d+)?$", top_jo)
            if jo_num:
                jo_num_str = jo_num.group(1)
                pat = re.compile(
                    r"제" + re.escape(jo_num_str) + r"조(?!의)(?:\b|[^조])"
                )
                matched_adds = []
                try:
                    _, adds = _fetch_law_articles_with_addenda(top_law, ef)
                except Exception:
                    adds = []
                for ad in adds:
                    for ln in ad["lines"]:
                        if "적용" not in ln:
                            continue
                        if pat.search(ln):
                            matched_adds.append((ad["date"], ad["head"], ln))
                matched_adds.sort(key=lambda x: x[0], reverse=True)
                for _, head, ln in matched_adds[:2]:
                    m = pat.search(ln)
                    if m:
                        jo_pos = m.start()
                        ctx_start = max(0, jo_pos - 150)
                        ctx_end = min(len(ln), jo_pos + 150)
                        snippet = ln[ctx_start:ctx_end]
                        s = f"{head} — …{snippet}…"
                    else:
                        s = f"{head} — {ln}"
                    if len(s) > 300:
                        s = s[:297] + "..."
                    addenda_for_top.append(s)

    # 5. 결과 구성 (top이 비었으면 "일치하는 조문 없음" 오류)
    if not top:
        return {"error": "일치하는 조문 없음 — 키워드를 줄이거나 다른 말로",
                "다음 단계": "law_article(law_name, 조, keyword=...)로 해당 항만 조회"}

    results = []
    for _, a in top:
        matched = _sentences_with_keywords(a.get("본문", ""), kw_words)
        if not matched and a.get("제목"):
            tl = a["제목"].lower()
            if all(w.lower() in tl for w in kw_words):
                matched = [a["제목"][:200]]
        results.append({
            "법령": a.get("_law", law_name or ""),
            "조": a.get("조", ""),
            "제목": a.get("제목", ""),
            "적용 시행일": a.get("적용 시행일", ef),
            "일치 문장": matched[:2] if matched else [],
        })

    out = {"결과": results}
    if addenda_for_top:
        out["관련 부칙"] = addenda_for_top
    out["다음 단계"] = "law_article(law_name, 조, keyword=...)로 해당 항만 조회"

    # 6. 크기 제한: 4000자 초과 시 일치 문장 축소 → 결과 수 축소
    raw = json.dumps(out, ensure_ascii=False)
    if len(raw) > 4000:
        # 일치 문장을 1개로 줄임
        for r in results:
            r["일치 문장"] = r["일치 문장"][:1]
        out2 = {"결과": results}
        if addenda_for_top:
            out2["관련 부칙"] = addenda_for_top
        out2["다음 단계"] = out["다음 단계"]
        raw = json.dumps(out2, ensure_ascii=False)
        if len(raw) > 4000:
            # 결과 수 줄이기
            while len(results) > 1 and len(json.dumps({"결과": results,
                                                          "다음 단계": out["다음 단계"],
                                                          **({"관련 부칙": addenda_for_top} if addenda_for_top else {})},
                                                       ensure_ascii=False)) > 4000:
                results.pop()
            out3 = {"결과": results}
            if addenda_for_top:
                out3["관련 부칙"] = addenda_for_top
            out3["다음 단계"] = out["다음 단계"]
            raw = json.dumps(out3, ensure_ascii=False)
        out = out2 if len(json.dumps(out2, ensure_ascii=False)) <= 4000 else out3

    return out


# ── law_article용 항(paragraph) 파싱 헬퍼 ─────────────────────────────────────

_HANG_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}  # ①→1, ②→2, …, ⑳→20


def _항_번호_파싱(s):
    """'①'·'1'·'제1항'·'2항' → '제N항'. N=1~20만 유효, 아니면 None."""
    if s in _HANG_CIRCLED:
        return f"제{_HANG_CIRCLED[s]}항"
    m = re.match(r"^제(\d+)항", s)
    if m and 1 <= int(m.group(1)) <= 20:
        return f"제{m.group(1)}항"
    m = re.match(r"^(\d+)항", s)
    if m and 1 <= int(m.group(1)) <= 20:
        return f"제{m.group(1)}항"
    m = re.match(r"^(\d+)$", s)
    if m and 1 <= int(m.group(1)) <= 20:
        return f"제{m.group(1)}항"
    return None


def _호_문자열_파싱(s):
    """'2호'·'제2호' → '제2호'. 숫자+호, 없으면 None."""
    if not s:
        return None
    m = re.match(r"^제(\d+)호$", s)
    if m:
        return f"제{m.group(1)}호"
    m = re.match(r"^(\d+)호$", s)
    if m:
        return f"제{m.group(1)}호"
    return None


def _normalize_paragraph_spec(spec):
    """'①'·'1'·'제1항'·'②2호'·'제2항 제2호'·'제2항제2호'·'2,3' 등을 파싱.

    반환: (항번호_또는_None, 호번호_또는_None, 여러항목록_또는_None)
    - 항+호(P1): ("제2항", "제2호", None)
    - 단일 항(기존): ("제2항", None, None)
    - 여러 항(P3): (None, None, ["제2항", "제3항"])
    - 해석 불가(P5): (None, None, None)
    """
    if spec is None:
        return None, None, None
    s = str(spec).strip()
    if not s:
        return None, None, None

    # 쉼표로 여러 항 구분 (P3)
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        parsed = []
        for p in parts:
            hn = _항_번호_파싱(p)
            if hn is None:
                return None, None, None
            parsed.append(hn)
        return None, None, parsed

    # P1 우선: 원문자 + 호 패턴 ("②2호", "②제2호")
    m = re.match(r"^([①-⑳])(.*)$", s)
    if m:
        circled = m.group(1)
        hang = f"제{_HANG_CIRCLED[circled]}항"
        ho = _호_문자열_파싱(m.group(2).strip())
        if ho:
            return hang, ho, None
        return hang, None, None

    # 단일 항 파싱 (원문자 단독, "제N항", "N항", "N")
    hang = _항_번호_파싱(s)
    if hang is None:
        return None, None, None

    # 항 뒤의 호 파싱 ("제N항 제M호", "제N항제M호", "N항 M호")
    ho = _호_뒤_파싱(s, hang)
    if ho:
        return hang, ho, None

    return hang, None, None


def _호_뒤_파싱(전체_입력, 항_번호):
    """항 번호 뒤의 호 부분을 추출. '②2호'·'제2항 제2호' 등에서 '제N호' 반환."""
    # 1. 입력이 원문자(①~⑳)로 시작하면 그 원문자 뒤 추출
    if 전체_입력 and 전체_입력[0] in _HANG_CIRCLED:
        m = re.match(rf"^{re.escape(전체_입력[0])}(.*)$", 전체_입력)
        if m:
            return _호_문자열_파싱(m.group(1).strip())
    # 2. '제N항'·'N항' 형태 뒤 추출
    항_숫자 = re.sub(r"\D", "", 항_번호)  # "제2항" → "2"
    m = re.match(rf"^(?:제\s*)?{항_숫자}항\s*(.*)$", 전체_입력)
    if m:
        return _호_문자열_파싱(m.group(1).strip())
    return None


_ARTICLE_TITLE_RE = re.compile(r"^(제\d+조(?:의\d+)?)\s*\(")

# 줄 맨 앞 원문자(①~⑳)로 항 경계를 찾는 공용 정규식
_PARA_START = re.compile(r"^[ \t]*([①-⑳])")


def _split_paragraphs(body):
    """본문(항 부분만)에서 조 제목 분리 후 항 경계 원문자 기준으로 항 텍스트를 추출.

    반환: (조_제목_줄, [(항_번호, 항_텍스트_strip), ...])
    항 마커가 하나도 없으면 빈 리스트.
    조 제목 줄이 없으면 빈 문자열.
    """
    jo_head, para_body = _split_article_title(body)
    if not para_body:
        return jo_head, []
    lines = para_body.split("\n")
    paragraphs = []  # [(hang_no, start_line_idx), ...]
    current_no = None
    current_start = None
    for i, ln in enumerate(lines):
        m = _PARA_START.match(ln)
        if m:
            circled = m.group(1)
            no = _HANG_CIRCLED.get(circled)
            if no:
                if current_no is not None:
                    paragraphs.append((current_no, current_start))
                current_no = f"제{no}항"
                current_start = i
    if current_no is not None:
        paragraphs.append((current_no, current_start))

    out = []
    for idx, (hang_no, start) in enumerate(paragraphs):
        end = paragraphs[idx + 1][1] if idx + 1 < len(paragraphs) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        out.append((hang_no, chunk))
    return jo_head, out


def _split_article_title(body):
    """본문에서 조 제목 줄과 항 텍스트를 분리.

    반환: (조_제목_줄, 항_텍스트)
    조 제목이 없으면 ("", body)를 반환.
    """
    if not body:
        return "", ""
    lines = body.split("\n")
    if not lines:
        return "", ""
    first = lines[0].strip()
    if _ARTICLE_TITLE_RE.match(first):
        jo_line = lines[0]
        body_lines = lines[1:]
        # DRF 응답에서 조 제목 라인에 붙는 개정/신설 태그 제거
        jo_clean = re.sub(r"<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b", "", jo_line).strip()
        return jo_clean, "\n".join(body_lines)
    return "", body


def _parse_paragraphs(body):
    """본문을 줄 맨 앞 원문자(①~⑳) 기준 항으로 분할.

    반환: [{"항 번호": "제N항", "첫 문장": <항 기호 뒤 첫 줄, 최대 80자>, "길이": <항 텍스트 길이>}, ...]
    줄 맨 앞 항 기호가 하나도 없으면 빈 리스트.
    조 제목 줄은 어느 항에도 속하지 않으며, 항 텍스트 길이에도 포함되지 않는다.
    """
    if not body:
        return []
    _, paragraphs = _split_paragraphs(body)
    if not paragraphs:
        return []

    out = []
    for hang_no, para_text in paragraphs:
        first_line = para_text.split("\n")[0].lstrip()
        fm = re.match(r"^[ \t]*[①-⑳]\s*", first_line)
        text_after = first_line[fm.end():] if fm else first_line
        first_sentence = text_after.strip()[:80]
        out.append({"항 번호": hang_no, "첫 문장": first_sentence, "길이": len(para_text)})
    return out


def _추출_호_본문(para_text, ho):
    """항 텍스트 내에서 ho(예: '제2호')에 해당하는 호 본문(호 줄 + 목·가·나 포함) 추출.
    호 줄은 줄 맨 앞 'N.' (숫자+점). 다음 호(N. 다른 숫자) 직전까지."""
    try:
        ho_no = int(re.sub(r"\D", "", ho))
    except ValueError:
        return None
    lines = para_text.split("\n")
    out = []
    found = False
    for ln in lines:
        t = ln.lstrip()
        # 첫 줄의 항 마커(원문자)는 건너뛰고, 그 이후 원문자는 다음 항 경계로 처리
        if not found and re.match(r"^[①-⑳]\s*", t):
            continue
        if re.match(r"^[①-⑳]", t):            # 다음 항 경계
            break
        m = re.match(r"^(\d+)\.", t)
        if m:
            if found:
                break                         # 다음 호 → 종료
            if int(m.group(1)) == ho_no:
                found = True
                out.append(ln)
            continue
        if found:
            out.append(ln)                    # 목·이어지는 줄
    return "\n".join(out) if out else None


def _항_내_호_목록(para_text):
    """항 텍스트에서 호 번호 목록(줄 맨 앞 'N.' 형태) 추출."""
    lines = para_text.split("\n")
    hos = []
    for ln in lines:
        t = ln.lstrip()
        # 첫 줄의 항 마커(원문자)는 건너뛰기
        if not hos and re.match(r"^[①-⑳]\s*", t):
            continue
        if re.match(r"^[①-⑳]", t):
            break
        m = re.match(r"^(\d+)\.", t)
        if m:
            hos.append(m.group(1))
    return hos


def _pick_paragraph(body, paragraph_spec):
    """paragraph_spec에 해당하는 항 본문 반환(줄 맨 앞 원문자 기준, 길이 제한 없음).

    P1(항+호): 해당 항 내 특정 호부터 다음 호 직전까지(가·나·다 목 포함).
    P3(여러 항): 지정한 항들을 원래 순서대로 이어 붙임.
    단일 항(기존): 해당 항 전체.
    없으면 None."""
    if not body or not paragraph_spec:
        return None
    hang, ho, multi = _normalize_paragraph_spec(paragraph_spec)
    if hang is None and ho is None and multi is None:
        return None
    _, paragraphs = _split_paragraphs(body)
    if not paragraphs:
        return None

    # P3: 여러 항 — 지정한 항들을 순서대로 이어서 반환
    if multi is not None:
        chunks = []
        for h in multi:
            for hn, pt in paragraphs:
                if hn == h:
                    if pt:
                        chunks.append(pt)
                    break
        if chunks:
            return "\n".join(chunks)
        return None

    # P1: 항+호 — 항 머리말(개정 태그 제거) + 해당 호 본문 추출
    if ho is not None:
        for hn, para_text in paragraphs:
            if hn == hang:
                ho_body = _추출_호_본문(para_text, ho)
                if ho_body:
                    lines = para_text.split("\n")
                    head_line = lines[0].strip() if lines else ""
                    head_clean = re.sub(r"<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b", "", head_line).strip()
                    if head_clean:
                        return head_clean + "\n" + ho_body
                    return ho_body
                return None  # 호를 못 찾았으면 None → _article_body_with_scope에서 P4 처리
        return None

    # 단일 항(기존)
    for hang_no, para_text in paragraphs:
        if hang_no == hang:
            return para_text if para_text else None
    return None


def _paragraphs_matching_keyword(body, kw):
    """키워드가 들어간 항 번호 목록(제N항 형태). 줄 맨 앞 원문자 기준 항 분할.
    항 구분이 없으면 빈 리스트."""
    if not body or not kw:
        return []
    _, paragraphs = _split_paragraphs(body)
    if not paragraphs:
        return []
    kw_lower = kw.lower()
    matched = []
    for hang_no, para_text in paragraphs:
        if kw_lower in para_text.lower():
            matched.append(hang_no)
    return sorted(set(matched), key=lambda x: int(re.search(r"\d+", x).group()))


def _apply_long_article_logic(a, body, limit, prefix=""):
    """조문이 limit자 초과일 때 항 단위 절단, 생략된 항 표시, 반환 범위 '항 목록'을 a에 반영한다.

    짧은 조문은 아무 역할도 하지 않는다.
    prefix: paragraph를 못 찾은 경우 안내 앞에 붙일 문구.
    """
    if len(body) <= limit:
        return
    jo_head, raw_paragraphs = _split_paragraphs(body)
    paragraphs = _parse_paragraphs(body)
    truncated, cut_hang, omitted = _build_truncated_body(jo_head, body, raw_paragraphs, limit)
    a["본문"] = truncated
    a["항 목록"] = paragraphs
    if cut_hang:
        a["잘린 항"] = cut_hang
    if omitted:
        a["생략된 항"] = omitted
    base = "keyword 또는 paragraph로 필요한 항만 조회하세요."
    if omitted:
        omitted_str = f"{omitted[0]}~{omitted[-1]}"
        a["안내"] = prefix + base + f" 생략된 항: {omitted_str}"
    else:
        a["안내"] = prefix + base
    a["반환 범위"] = "항 목록"


def _article_body_with_scope(law_name, norm, hang_from_input, ef, paragraph, keyword):
    """law_article 본문 반환 — paragraph/keyword 제한, 긴 본문 항 목록 처리.

    keyword 지정 시 항 → 호 → 목 순으로 필터링. 일치한 호 단위만 반환하되
    조 제목·해당 항 머리말 문장(상위 문맥)을 한 줄로 함께 붙인다.
    일치 위치("일치_위치")와, 일치 없을 때 "일치 없음" + 항·호 목록을 반환.
    """
    a = article(law_name, norm, ef)
    body = a.get("본문", "")

    if paragraph:
        hang, ho, multi = _normalize_paragraph_spec(paragraph)

        if hang is None and ho is None and multi is None:
            # P5: 해석 불가 → 형식 예시 안내
            a["항 목록"] = _parse_paragraphs(body)
            if len(body) > 4000:
                _apply_long_article_logic(a, body, 4000, prefix="")
            else:
                a["본문"] = body
                a["반환 범위"] = "전체"
            a["안내"] = (
                f"'{paragraph}'은 항·호 지정으로 인식할 수 없음 — "
                "받을 수 있는 형식: ②, 제2항, ②2호, 제2항 제2호, 2,3"
            )
        else:
            picked = _pick_paragraph(body, paragraph)
            if picked is not None:
                # P1(항+호), P3(여러 항), 단일 항(기존)
                a["본문"] = picked
                if multi is not None:
                    a["반환 범위"] = ", ".join(multi)              # "제2항, 제3항"
                elif ho is not None:
                    a["반환 범위"] = f"{hang} {ho}"               # "제2항 제2호"
                else:
                    a["반환 범위"] = hang                          # "제2항"
            else:
                # P2 / P4 / 일반 not-found
                handled = False

                # P4: 항+호 지정인데 해당 호 없음 → 항 전체 + 호 목록 안내
                if hang is not None and ho is not None and multi is None:
                    para_text = _pick_paragraph(body, hang)
                    if para_text:
                        a["본문"] = para_text
                        a["반환 범위"] = hang
                        hos = _항_내_호_목록(para_text)
                        a["안내"] = f"제{re.sub(r'\D', '', ho)}호가 없음. 호 목록: {', '.join(hos)}"
                        handled = True

                # P2: 숫자 하나(항 번호)인데 제N항 없고 제1항 제N호 있음 → 폴백
                if not handled and hang is not None and ho is None and multi is None:
                    s = str(paragraph).strip()
                    num_m = re.match(r"^(\d+)$", s)
                    if num_m:
                        ho_no = num_m.group(1)
                        first_para = _pick_paragraph(body, "제1항")
                        if first_para:
                            ho_result = _추출_호_본문(first_para, f"제{ho_no}호")
                            if ho_result:
                                a["본문"] = ho_result
                                a["반환 범위"] = f"제1항 제{ho_no}호"
                                a["안내"] = f"제{ho_no}항이 없어 제1항 제{ho_no}호로 봄"
                                handled = True

                # 일반 not-found (P2/P4 실패 시)
                if not handled:
                    was_long = len(body) > 4000
                    prefix = f"'{paragraph}'항은 이 조문 본문에서 확인되지 않음 — 항 번호 확인. "
                    _apply_long_article_logic(a, body, 4000, prefix=prefix)
                    if "항 목록" not in a:
                        a["항 목록"] = _parse_paragraphs(body)
                    if not was_long:
                        a["항 목록"] = _parse_paragraphs(body)
                        a["안내"] = f"'{paragraph}'항은 이 조문 본문에서 확인되지 않음 — 항 번호 확인"
                        a["반환 범위"] = "전체"
    elif keyword:
        km = _호_목_매칭(body, keyword)
        if km:
            # 조 머리말: 본문 첫 줄에서 개정 표시(<개정 …>, 미완결 "<개정") 제거.
            first_line = body.split("\n")[0].strip() if body else ""
            jo_head = re.sub(r"<개정[^>]*>|<개정\b", "", first_line).strip()
            match_locs = []
            jo_label = a.get("조", "")  # "전체" 대체용 실제 조 번호
            # 항별로 그룹화: 각 항마다 항_머리말 1줄 + 매칭된 호 문장들
            항_groups = {}
            for hit in km:
                항_l = hit["항"]; 호_l = hit["호"]
                disp_항 = jo_label if 항_l == "전체" else 항_l
                loc = f"{disp_항} {호_l}" if 호_l else disp_항
                match_locs.append(loc)
                if disp_항 not in 항_groups:
                    항_groups[disp_항] = {"항_머리말": hit.get("항_머리말", ""), "호들": []}
                # 호 본문: 호 번호가 있으면 호 번호 접두사 유지(t5c #4), 없으면 그대로
                body_hit = hit["호_본문"]
                if 호_l:
                    ho_no = re.search(r"\d+", 호_l).group()  # "제18호" → "18"
                    body_hit = f"{ho_no}. {body_hit}"
                항_groups[disp_항]["호들"].append(body_hit)
            chunks = []
            for 항_l in sorted(항_groups.keys(), key=lambda x: int(re.search(r"\d+", x).group()) if re.search(r"\d+", x) else 0):
                group = 항_groups[항_l]
                # 항 머리말: 개정 표시 제거 후 추가. 조 머리말과 동일하면 중복이므로 생략.
                항_head = re.sub(r"<개정[^>]*>|<개정\b", "", group["항_머리말"]).strip()
                if 항_head and 항_head != jo_head:
                    chunks.append(항_head)
                chunks.extend(group["호들"])
            a["본문"] = jo_head + "\n" + "\n".join(chunks)
            a["일치_위치"] = match_locs
            a["반환 범위"] = f"keyword 일치(호): {', '.join(match_locs)}"
        else:
            # 항·호·목 어디에도 keyword 없음 → "일치 없음" + 항·호 목록(번호+앞30자)
            ctx_all = _호_목_맥락_분할(body)
            jo_label = a.get("조", "")
            ho_list = []
            for c in ctx_all:
                disp_항 = jo_label if c['항'] == "전체" else c['항']
                label = f"{disp_항} {c['호']}" if c['호'] else disp_항
                snippet = c['호_머리말'] or c['항_머리말'] or c['본문'][:30]
                ho_list.append({"위치": label, "앞30자": snippet[:30]})
            # 항 단위 보기 추가 (항 정보만, 호 없으면 호 목록)
            if not ho_list:
                # 항 마커조차 없는 짧은 본문 → 본문 앞 30자
                ho_list.append({"위치": "전체", "앞30자": body[:30]})
            a["일치 없음"] = f"'{keyword}'가 포함된 항·호·목이 확인되지 않음"
            a["항_호_목록"] = ho_list
            a["본문"] = body[:2000]
            a["반환 범위"] = "일치 없음"
    elif not paragraph and len(body) > 4000:
        _apply_long_article_logic(a, body, 4000)
    else:
        a["반환 범위"] = "전체"

    if hang_from_input:
        a["요청 항"] = hang_from_input

    # 읽기 주의: 돌려준 본문의 단서·우선·제외 구절 원문(최대 3개)
    if "error" not in a and a.get("본문"):
        from . import reading
        notes_list, more = reading.extract_reading_notes(a["본문"])
        if notes_list:
            a["읽기 주의"] = notes_list
            if more:
                a["읽기 주의 더 있음"] = more

    return a


def _cut_at_line_break(text, limit):
    """text를 limit자 안에서 마지막 줄바꿈 앞까지 자름. 줄바꿈이 없으면 limit자에서 자름."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    last_nl = head.rfind("\n")
    if last_nl >= 0:
        return text[:last_nl]
    return text[:limit]


def _build_truncated_body(jo_head, body, paragraphs, limit):
    """조 제목 + 항들을 순서대로 이어붙이되 limit자 이하가 되는 데까지 포함.

    반환: (본문, 잘린_항_or_None, 생략된_항_목록)
    - 항 기호 없는 긴 본문: limit자 안에서 마지막 줄바꿈 앞까지 자름
    - 첫 항만으로도 limit 초과: 조 제목 + 첫 항을 limit 안에서 마지막 줄바꿈 앞까지, 잘린_항="제1항"
    paragraphs: _split_paragraphs가 반환한 [(항_번호, 항_텍스트), ...] 리스트.
    """
    if not paragraphs:
        # 항 기호 없는 본문: 조 제목 + 본문 전체를 limit 안에서 마지막 줄바꿈 앞까지
        _, para_text = _split_article_title(body)
        full = jo_head + ("\n" + para_text if para_text else "")
        return _cut_at_line_break(full, limit), None, []

    # 조 제목 + 항 순서대로 이어붙이기 (항 텍스트는 이미 _split_paragraphs에서 추출됨)
    accumulated = jo_head if jo_head else ""
    for idx, (hang_label, para_text) in enumerate(paragraphs):
        if not para_text:
            para_text = ""
        sep = "\n" if accumulated else ""
        candidate = accumulated + sep + para_text
        if len(candidate) <= limit:
            accumulated = candidate
        else:
            # 이 항에서 초과
            if idx == 0:
                # 첫 항만으로도 초과: 조 제목 + 첫 항을 limit 안에서 마지막 줄바꿈 앞까지
                truncated = _cut_at_line_break(candidate, limit)
                omitted = [paragraphs[i][0] for i in range(1, len(paragraphs))]
                return truncated, hang_label, omitted
            else:
                # 이미 포함된 항들까지만. 생략된 항 시작점 = idx
                omitted = [paragraphs[i][0] for i in range(idx, len(paragraphs))]
                return accumulated, None, omitted

    return accumulated, None, []


# ── law_article 키워드 필터: 호·목 단위 (SPEC t5b) ──────────────────────────────

_HO_HOL = re.compile(r"제(\d+)호")          # 제1호, 제2호 …
_HO_NUM = re.compile(r"^\s*(\d{1,2})[\.\)]")   # 1. …, 2) … (chunk 시작 위치의 숫자+닷/괄호, 호 번호는 1~2자리)
_MOK = re.compile(r"(?:^|\s)[가-힣]\.|\([가-힣]+\)")  # (가), (나) …, 가. 나. … (문장 말미 "다." 오인 방지)

# 항 블록 내 호 마커 탐색용: 줄 시작(\n 뒤) 위치의 호 마커만 인식.
# 항 머리말 내 "제1호에 해당하는" 같은 문장 내 제N호를 호 마커로 오인하지 않도록,
# 호 마커는 반드시 \n 뒤에 있는 것으로 제한 (블록 시작 위치 제외).
_HO_MARKER_IN_BLOCK = re.compile(r"\n\s*(?:제\d+호|\d{1,2}[\.\)])")


def _호_목_분할(body):
    """본문을 항 → 호 → 목 트리 리스트로 분할.

    반환: [{"항": "제1항", "항_머리말": "…", "호": [{"호": "제1호", "목": ["가.", "나."], "본문": "…"}]}]
    항 표시가 없으면 전체를 하나의 항으로, 호 표시만 있으면 그 호들로 분할.
    항 마커는 동그라미 숫자(①~⑩)만 사용한다. 텍스트 "제1항"은 문장 내 참조일 수 있어
    항 마커로 사용하지 않는다(중복 필터링 불필요).
    """
    if not body:
        return []
    ant = list(re.finditer(r"[①-⑩]", body))
    if not ant:
        return [_항_블록(body, None)]
    out = []
    for idx, m in enumerate(ant):
        start = m.start()
        end = ant[idx + 1].start() if idx + 1 < len(ant) else len(body)
        block = body[start:end].strip()
        if block:
            norm = _항_번호_파싱(m.group(0))
            out.append(_항_블록(block, norm))
    return out


def _항_블록(block, 항_norm):
    """하나의 항 블록을 호·목으로 분할.

    반환: {"항": …, "항_머리말": …, "호": […]}
    항_머리말은 항 마커 뒤 첫 호 마커 앞까지의 텍스트(항의 도입부).
    개정 태그(<개정 …>) 내 날짜 숫자(예: 2019.12.31)가 호 마커로 오인되지 않도록
    호 마커 탐색 전에 개정 태그를 제거한다.
    호 마커는 \n 뒤에만 있는 것으로 제한하여 항 머리말 내 제N호를 오인하지 않는다.
    """
    # 개정 태그 제거 (호 마커 탐색용 별도 문자열)
    block_for_ho = re.sub(r"<개정[^>]*>|<개정\b[^>]*>", "", block)
    hos = list(re.finditer(_HO_MARKER_IN_BLOCK, block_for_ho))
    if not hos:
        return {"항": 항_norm or "전체", "항_머리말": block.strip(), "호": [{"호": None, "목": [], "본문": block.strip()}]}
    # 첫 호 마커 앞의 텍스트를 항_머리말로 보존 (원문 기준).
    first_ho_match = hos[0]
    항_머리말 = block[:first_ho_match.start()].strip()
    out = []
    for idx, m in enumerate(hos):
        # 호 마커 매치: \n\s*(제\d+호|\d{1,2}[\.\)])
        # 매치 그룹에서 호 번호 추출
        full_match = m.group(0)
        # 호 마커 부분 추출 (첫 줄바꿈 제외)
        ho_marker = full_match.strip()  # "\n1." → "1."
        # 호 라벨 파싱
        gm = _HO_HOL.match(ho_marker)
        gn = _HO_NUM.match(ho_marker)
        if gm:
            ho_label = f"제{gm.group(1)}호"
        elif gn:
            ho_label = f"제{gn.group(1)}호"
        else:
            ho_label = None
        # 호 내용 시작 위치: 매치 끝 위치 (호 마커 직후)
        body_start = m.end()
        # 다음 호 마커까지의 텍스트
        end = hos[idx + 1].start() if idx + 1 < len(hos) else len(block_for_ho)
        chunk = block_for_ho[body_start:end].strip()
        mok_seq = [m2.group() for m2 in _MOK.finditer(chunk)]
        out.append({"호": ho_label, "목": mok_seq, "본문": chunk})
    merged = []
    for b in out:
        if b["호"] is None and not merged:
            merged.append({"호": None, "목": b["목"], "본문": b["본문"]})
        else:
            merged.append(b)
    return {"항": 항_norm or "전체", "항_머리말": 항_머리말, "호": merged}

def _호_목_매칭(body, kw):
    """keyword가 포함된 호·목 단위 위치 목록.

    각 항목: {항, 호, 항_머리말, 호_본문, 목_일치}
    """
    if not body or not kw:
        return []
    kw_lower = kw.lower()
    tree = _호_목_분할(body)
    matched = []
    for ant in tree:
        항_머리말 = ant.get("항_머리말", "")
        for ho in ant["호"]:
            hb = ho["본문"]
            if not hb:
                continue
            if kw_lower in hb.lower():
                mok_hits = []
                for mk in ho["목"]:
                    mk_pos = hb.find(mk)
                    if mk_pos != -1:
                        mk_text = hb[mk_pos + len(mk):]
                        nxt = _MOK.search(mk_text)
                        mk_text = mk_text[:nxt.start()] if nxt else mk_text
                        if kw_lower in mk_text.lower():
                            mok_hits.append(mk)
                matched.append({"항": ant["항"], "호": ho["호"], "항_머리말": 항_머리말, "호_본문": hb, "목_일치": mok_hits})
    return matched


def _호_목_맥락_분할(body):
    """호 본문 + 항/호 머리말(한 줄 요약) 정보를 함께 반환.

    반환: [{"항": …, "항_머리말": …, "호": …, "호_머리말": …, "본문": …}]
    - 항 마커가 없는 호-only 구조에서는 항_머리말을 비운다(호 간 중복 방지).
    - 각 항의 항_머리말은 `_호_목_분할`이 보존한 실제 항 머리말(항 마커 뒤 첫 호 앞 텍스트)을 사용한다.
      호-only 구조에서는 항 마커 없이 호들만 있으므로 항_머리말을 ""로 둔다.
    """
    tree = _호_목_분할(body)
    # 항 마커가 하나도 없는 호-only 구조 → 항_머리말 사용 안 함
    no_ant_markers = bool(tree) and tree[0]["항"] == "전체"
    out = []
    for ant in tree:
        항_label = ant["항"]
        if no_ant_markers:
            head = ""
        else:
            # `_호_목_분할` → `_항_블록`이 보존한 실제 항 머리말 사용
            head = ant.get("항_머리말", "")
        for ho in ant["호"]:
            hb = ho["본문"]
            hfirst = hb.split("\n")[0].strip()[:80] if hb else ""
            out.append({"항": 항_label, "항_머리말": head, "호": ho["호"],
                        "호_머리말": hfirst, "본문": hb})
    return out


# ── law_article 목차 (SPEC t1) ────────────────────────────────────────────────────

_HEAD_KIND_RE = re.compile(r"^제\d+(관|장|절|편)(?:의\d+)?(?=\s|$)")  # Claude 10-15: 제2장의2 같은 가지 머리 포함


def _heading_kind(content):
    """조문내용에서 머리 종류(관·장·절·편) 판별. 아니면 None."""
    m = _HEAD_KIND_RE.match(content.strip())
    return m.group(1) if m else None


def _heading_level(kind):
    return {"편": 0, "장": 1, "절": 2, "관": 3}.get(kind, 99)


def _clean_heading_name(content):
    """머리 원문에서 개정·신설 태그와 '삭제' 접미 제거 후 trim."""
    s = content.strip()
    s = re.sub(r"<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b", "", s).strip()
    if s.endswith(" 삭제"):
        s = s[:-3].rstrip()
    return s


def _is_deleted_article(content, norm):
    """조문내용이 '제N조 삭제'로 시작하면 True."""
    return content.strip().startswith(norm + " 삭제")


def toc_outline(units, article_no, max_chars=1500):
    """법령 조문단위 목록에서 목차 정보를 반환.

    units: lawService.do '법령.조문.조문단위' 목록.
    article_no: 정규화된 조 번호('제34조').
    반환: {'전체': '…'} (small) 또는 {'개요': '…', '이 조가 속한 곳': '…', '같은 곳 조문': '…'} (large).
    """
    norm, _ = normalize_article(article_no)

    # 1. 머리(편·장·절·관)와 조문을 분리
    heads = []       # [{"i", "level", "name", "start", "end", "articles"}]
    article_map = {} # norm → {"번호", "제목", "쪽"}
    for i, u in enumerate(units):
        if u.get("조문여부") == "전문":
            content = u.get("조문내용") or ""
            kind = _heading_kind(content)
            if kind is None:
                continue
            name = _clean_heading_name(content)
            level = _heading_level(kind)
            jo_str = _jo_str(u.get("조문번호", "0"), u.get("조문가지번호") or "00")
            try:
                no = int(re.search(r"\d+", jo_str).group())
            except Exception:
                continue
            heads.append({"i": i, "level": level, "name": name,
                          "jo_no": no, "articles": []})
        elif u.get("조문여부") == "조문":
            jo_str = _jo_str(u.get("조문번호", "0"), u.get("조문가지번호") or "00")
            try:
                no = int(re.search(r"\d+", jo_str).group())
            except Exception:
                continue
            content = u.get("조문내용") or ""
            if _is_deleted_article(content, jo_str):
                continue
            title = u.get("조문제목") or ""
            article_map[jo_str] = {"번호": no, "쪽": jo_str, "제목": title,
                                   "content": content}

    if not article_map:
        return {}

    # 2. 각 머리의 범위(구간) 결정: 다음 같은수준 이상 머리 직전까지의 조문(삭제 제외)
    for idx, h in enumerate(heads):
        end_idx = len(units)
        for j in range(idx + 1, len(heads)):
            if heads[j]["level"] <= h["level"]:
                end_idx = heads[j]["i"]
                break
        lo = h["i"] + 1
        articles = []
        first_no = None
        last_no = None
        for k in range(lo, end_idx):
            u = units[k]
            if u.get("조문여부") != "조문":
                continue
            js = _jo_str(u.get("조문번호", "0"), u.get("조문가지번호") or "00")
            if js not in article_map:
                continue
            a = article_map[js]
            articles.append(a)
            if first_no is None:
                first_no = a["번호"]
            last_no = a["번호"]
        h["articles"] = articles
        h["first_no"] = first_no
        h["last_no"] = last_no

    # 3. 전체 목차(모든 조)
    items = []
    for a in sorted(article_map.values(), key=lambda x: (x["번호"], x["쪽"])):
        item = f"{a['쪽']} {a['제목']}" if a["제목"] else a["쪽"]
        items.append(item)
    전체 = " · ".join(items)

    # 머리가 아예 없는 법령(조세범 처벌법 등): 전체 목차가 max_chars 이하면 그대로 반환
    if not heads:
        if len(전체) <= max_chars:
            return {"전체": 전체}
        return {"전체": 전체[:max_chars - 1] + "…"}

    # 4. 조가 있는 머리만 유지
    hits = [h for h in heads if h["articles"]]
    if not hits:
        if len(전체) <= max_chars:
            return {"전체": 전체}
        return {"전체": 전체[:max_chars - 1] + "…"}

    if len(전체) <= max_chars:
        return {"전체": 전체}

    # 5. 개요: "이름(첫조~끝조)", 가지번호 포함. 길면 관→절 순으로 빼고, 그래도 넘으면 자름 (Claude 10-15: 범위에 가지번호 빠지던 것 수정)
    def _join(maxlev):
        return " · ".join(f"{h['name']}({h['articles'][0]['쪽']}~{h['articles'][-1]['쪽']})"
                          for h in hits if h["level"] <= maxlev)
    개요 = _join(99)
    for lev in (2, 1):
        if len(개요) <= max_chars:
            break
        개요 = _join(lev)
    if len(개요) > max_chars:
        개요 = 개요[:max_chars - 1] + "…"

    # 6. 요청 조가 목록에 있으면 가장 낮은 수준 머리 + 그 범위
    요청 = None
    for h in hits:
        for a in h["articles"]:
            if a["쪽"] == norm:
                if 요청 is None or h["level"] > 요청["level"]:
                    요청 = {"level": h["level"], "name": h["name"], "articles": h["articles"]}
                break

    if 요청:
        same_items = []
        for a in sorted(요청["articles"], key=lambda x: (x["번호"], x["쪽"])):
            item = f"{a['쪽']} {a['제목']}" if a["제목"] else a["쪽"]
            same_items.append(item)
        same_str = " · ".join(same_items)
        if len(same_str) > max_chars:
            same_str = same_str[:max_chars - 1] + "…"
        return {"개요": 개요, "이 조가 속한 곳": 요청["name"], "같은 곳 조문": same_str}

    return {"개요": 개요}


def toc(law, article_no, as_of=""):
    """version 조회(이미 캐시 활용) → 법 전체 조문단위 조회 → toc_outline."""
    norm, _ = normalize_article(article_no)
    mst, ef = version(law, as_of)
    if not mst:
        return {"error": f"'{law}'를 찾지 못했거나 {as_of or '오늘'} 이전 시행본이 없음"}
    try:
        units = _raw_units(law, ef)
        return toc_outline(units, norm)
    except Exception as e:
        return {"error": str(e)}
