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

    # 항·호 정보 분리: '제26조의2 제1항', '26의2①', '제10조 ②'

    # ①~⑩ (circled number): 끝에 붙은 경우 항 정보로 추출, base에서는 제거
    _hang_circled = re.search(r"([①-⑳])\s*$", s2)
    hang_digit = None
    if _hang_circled:
        hang_digit = _CIRCLED.get(_hang_circled.group(1))
        s2_clean = s2[:_hang_circled.start()].rstrip()
    else:
        s2_clean = s2

    # 텍스트 항·호: '제26조의2 제1항', '제10조 ②' 등 (이미 치환된 s3와 원래 s2_clean 모두 사용)
    s3 = re.sub(r"[①-⑳]", _circled_replace, s2_clean)
    m_etc = re.match(r"^(.*?)(?:\s+(?:제)?(\d+)(?:항|호))?\s*$", s3)
    if not m_etc:
        m_etc = re.match(r"^(.*?)(?:\s+(?:제)?(\d+)(?:항|호))?\s*$", s2_clean)
    base_part = m_etc.group(1).strip() if m_etc else s2_clean
    hang_info = None
    if m_etc and m_etc.group(2):
        grp0 = m_etc.group(0) or ""
        hang_info = f"제{m_etc.group(2)}항" if "항" in grp0 else f"제{m_etc.group(2)}호"
    elif hang_digit:
        hang_info = f"제{hang_digit}항"   # circled number: 항으로 간주

    # 한글·기호 제거 → 숫자/의/-(구분자)만 남김
    cleaned = re.sub(r"[^\d\-_의]", "", base_part.replace(" ", ""))
    cleaned = cleaned.replace("_", "-")

    m2 = re.search(r"(\d+)\s*-\s*(\d+)", cleaned)
    if m2:
        main_no, branch_no = int(m2.group(1)), int(m2.group(2))
    elif "-" not in cleaned and "의" not in cleaned:
        main_no = int(cleaned)
        branch_no = 0
    else:
        # '28의2'처럼 '의'가 구분자인 경우
        parts = re.findall(r"\d+", cleaned)
        if not parts:
            raise ValueError("조문은 '제52조' 형식 — 예: '제52조', '26의2', '26-2'")
        main_no = int(parts[0])
        branch_no = int(parts[1]) if len(parts) > 1 else 0

    norm = f"제{main_no}조" + (f"의{branch_no}" if branch_no else "")
    return norm, hang_info


def jo6(article):
    """'제52조' → '005200', '제28조의2' → '002802'."""
    norm, _ = normalize_article(article)
    m = re.fullmatch(r"제(\d+)조(?:의(\d+))?", norm)
    if not m: raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}"


@_ttl_cache(maxsize=128)
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


def tiers(law, article_no, as_of=""):
    """법률 조문 → [법률, 위임 시행령 조문들, 위임 시행규칙 조문들] 원문(기준일 시행본)."""
    norm, _ = normalize_article(article_no)
    j = jo6(norm); no, br = j[:4], j[4:]
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
    jobs = [("법률", law, norm)] + [("시행령", law + " 시행령", a) for a in dict.fromkeys(dec)] + \
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
    """한 법령의 조문 전부(제목+본문)를 조회해 캐시. 조문 번호 1~50을 병렬 조회."""
    key = _find_cache_key(law, ef)
    if (cached := _FIND_CACHE.get(key)) and time.time() < cached[1]:
        return cached[0]
    mst, actual_ef = version(law, ef)
    if not mst:
        _FIND_CACHE[key] = ([], time.time() + _FIND_CACHE_TTL)
        return []
    articles = {}
    with ThreadPoolExecutor(8) as ex:
        futures = [ex.submit(_article_once, mst, actual_ef, i) for i in range(1, 51)]
        for fut in as_completed(futures, timeout=30):
            try:
                res = fut.result(timeout=15)
                if res:
                    articles[res["조"]] = res
            except Exception:
                pass
    result = list(articles.values())
    _FIND_CACHE[key] = (result, time.time() + _FIND_CACHE_TTL)
    return result


def _article_once(mst, ef, no):
    jo = f"{no:04d}00"
    try:
        d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={ef}&JO={jo}")
        body = "\n".join(t.strip() for t in _texts(d.get("법령", d)) if t.strip())
        if not body:
            return None
        first_line = body.split("\n")[0].strip()
        m = re.match(r"^(제\d+조(?:의\d+)?)\s*\((.+?)\)\s*$", first_line)
        title = m.group(2) if m else ""
        return {"조": f"제{no}조", "제목": title, "본문": body, "적용 시행일": ef}
    except Exception:
        return None


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


def _title_score(keyword, title, kw_words):
    if not title:
        return 0
    tl = title.lower()
    if all(w.lower() in tl for w in kw_words):
        return 100 + sum(title.count(w) for w in kw_words)
    return sum(1 for w in kw_words if w.lower() in tl)


def _body_score(keyword, body, kw_words):
    bl = body.lower()
    return sum(1 for w in kw_words if w.lower() in bl)


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
    all_articles = []
    for law in target_laws:
        try:
            arts = _fetch_law_articles(law, ef)
            for a in arts:
                a["_law"] = law
            all_articles.extend(arts)
        except Exception:
            continue

    if not all_articles:
        return {"error": "조문을 찾지 못함 — law_name 확인 또는 LAW_OC 키 설정",
                "다음 단계": "law_article(law_name, 조, keyword=...)로 해당 항만 조회"}

    scored = []
    for a in all_articles:
        title_s = _title_score(keyword, a.get("제목", ""), kw_words)
        body_s = _body_score(keyword, a.get("본문", ""), kw_words)
        if title_s == 0 and body_s == 0:
            continue
        all_in_title = all(w.lower() in a.get("제목", "").lower() for w in kw_words)
        all_in_body = all(w.lower() in a.get("본문", "").lower() for w in kw_words)
        total = title_s * 5 + body_s + (20 if all_in_title else 0) + (10 if all_in_body else 0)
        scored.append((total, a))

    scored.sort(key=lambda x: -x[0])
    top = scored[:n]

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

    out = {"결과": results,
           "다음 단계": "law_article(law_name, 조, keyword=...)로 해당 항만 조회"}
    return out


# ── law_article용 항(paragraph) 파싱 헬퍼 ─────────────────────────────────────

_HANG_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(10)}  # ①→1, ②→2, …


def _normalize_paragraph_spec(spec):
    """'①'·'1'·'제1항'·'2' 등을 '제1항' 형태로 정규화."""
    if spec is None:
        return None
    s = str(spec).strip()
    if not s:
        return None
    if s in _HANG_CIRCLED:
        return f"제{_HANG_CIRCLED[s]}항"
    m = re.match(r"^제(\d+)항$", s)
    if m:
        return f"제{m.group(1)}항"
    m = re.match(r"^(\d+)$", s)
    if m:
        return f"제{m.group(1)}항"
    m = re.match(r"^(\d+)항$", s)
    if m:
        return f"제{m.group(1)}항"
    return None


def _parse_paragraphs(body):
    """본문을 항 단위로 분할. 각 항: {항 번호, 첫 문장(80자)}."""
    if not body:
        return []
    parts = re.split(r"(?<=\S)[①-⑩](?=\s)", body)
    out = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not p:
            continue
        m = re.match(r"^(\S+)\s*(.*)", p)
        head, rest = (m.group(1), m.group(2)) if m else ("", p)
        circled = re.match(r"^[①-⑩]$", head)
        hang_no = _HANG_CIRCLED.get(head) if circled else None
        if not circled:
            hm = re.match(r"^(제\d+항)$", head)
            if hm:
                hang_no = hm.group(1)
        if hang_no is None:
            hang_no = str(i + 1)
        first_line = rest.strip().split("\n")[0].strip()
        highlight = first_line[:80] if first_line else ""
        out.append({"항 번호": f"제{hang_no}항" if str(hang_no).isdigit() else str(hang_no),
                    "첫 문장": highlight})
    return out


def _pick_paragraph(body, paragraph_spec):
    """paragraph_spec에 해당하는 항 본문만 반환. 없으면 None."""
    if not body or not paragraph_spec:
        return None
    markers = list(re.finditer(r"[①-⑩]|(제\d+항)", body))
    if not markers:
        return None
    spec_norm = _normalize_paragraph_spec(paragraph_spec)
    if spec_norm is None:
        return None
    for idx, m in enumerate(markers):
        mk_norm = _normalize_paragraph_spec(m.group(0))
        if mk_norm == spec_norm:
            end = markers[idx + 1].start() if idx + 1 < len(markers) else len(body)
            return body[m.start():end].strip()
    return None


def _paragraphs_matching_keyword(body, kw):
    """키워드가 들어간 항 번호 목록(제N항 형태). 항 구분이 없으면 빈 리스트."""
    if not body or not kw:
        return []
    markers = list(re.finditer(r"[①-⑩]|(제\d+항)", body))
    if not markers:
        return []
    kw_lower = kw.lower()
    matched = []
    for idx, m in enumerate(markers):
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(body)
        chunk = body[m.start():end]
        if kw_lower in chunk.lower():
            norm = _normalize_paragraph_spec(m.group(0))
            if norm:
                matched.append(norm)
    # 중복 제거 + 항 번호 순 정렬
    seen = set()
    result = []
    for m in matched:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return sorted(result, key=lambda x: int(re.search(r"\d+", x).group()))


def _article_body_with_scope(law_name, norm, hang_from_input, ef, paragraph, keyword):
    """law_article 본문 반환 — paragraph/keyword 제한, 긴 본문 항 목록 처리.

    keyword 지정 시 항 → 호 → 목 순으로 필터링. 일치한 호 단위만 반환하되
    조 제목·해당 항 머리말 문장(상위 문맥)을 한 줄로 함께 붙인다.
    일치 위치("일치_위치")와, 일치 없을 때 "일치 없음" + 항·호 목록을 반환.
    """
    a = article(law_name, norm, ef)
    body = a.get("본문", "")
    scope = "전체"

    if paragraph:
        picked = _pick_paragraph(body, paragraph)
        if picked is not None:
            body = picked
            spec_norm = _normalize_paragraph_spec(paragraph)
            scope = f"제{int(re.search(r'\d+', spec_norm).group())}항" if spec_norm else "제○항"
        else:
            a["안내"] = f"'{paragraph}'항은 이 조문 본문에서 확인되지 않음 — 항 번호 확인"
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
            body = jo_head + "\n" + "\n".join(chunks)
            a["일치_위치"] = match_locs
            scope = f"keyword 일치(호): {', '.join(match_locs)}"
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
            body = body[:2000]
            scope = "일치 없음"
    elif not paragraph and len(body) > 4000:
        a["항 목록"] = _parse_paragraphs(body)
        a["안내"] = "keyword 또는 paragraph로 필요한 항만 조회하세요"
        body = body[:2000]
        scope = "항 목록"

    a["본문"] = body
    a["반환 범위"] = scope
    if hang_from_input:
        a["요청 항"] = hang_from_input
    return a


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
            norm = _normalize_paragraph_spec(m.group(0))
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
