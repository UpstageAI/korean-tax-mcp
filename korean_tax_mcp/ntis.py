"""국세법령정보시스템(taxlaw.nts.go.kr) 조회 — 통합검색·문서 본문·기본통칙·세법집행기준.

사이트 화면이 쓰는 공개 조회(action.do)를 그대로 호출한다(로그인 불필요, 조회만).
국세청 서버 부담을 줄이려고 같은 요청은 디스크 캐시(기본 1일), 호출 간격은 최소 0.5초로 둔다.
- 검색: 질의회신·과세기준자문·사전답변 등(question), 판례·심판·이의·심사(precedent). 최신순/정확도순, 세목·기간·조문 필터.
- 본문: 문서 id(DOC_ID) → 질의·사실관계·회신(또는 판결 주문·이유) 전문과 관련 조문.
- 기본통칙: 법령별 최신 고시본에서 조문(법 제N조·영 제M조)별 통칙 전문.
- 세법집행기준: 책자(PDF 뷰어)라 본문 API가 없음 — 조문별 항목 제목·쪽·링크만.
"""
import hashlib
import html
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import _mask_oc

BASE = "https://taxlaw.nts.go.kr"
CTX = ssl.create_default_context(); CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT
TAX_CODES = {"국기": "301", "국징": "302", "법인": "303", "소득": "305", "부가": "306", "양도": "307", "상증": "308", "조특": "309", "국조": "310", "종부": "311"}
KINDS = {"해석": "question", "판례": "precedent"}


CACHE = Path(os.environ.get("KOREAN_TAX_MCP_CACHE", Path.home() / ".cache" / "korean-tax-mcp"))
TTL = int(os.environ.get("KOREAN_TAX_MCP_CACHE_TTL", 86400))
_lock = threading.Lock(); _last = [0.0]
UA = "korean-tax-mcp (+https://github.com/UpstageAI/korean-tax-mcp)"


def _act(action, param, timeout=40):
    key = hashlib.sha256(json.dumps([action, param], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    f = CACHE / f"{key}.json"
    try:
        if f.exists() and time.time() - f.stat().st_mtime < TTL: return json.loads(f.read_text())
    except Exception:
        pass
    with _lock:   # 호출 간격 0.5초 이상
        wait = 0.5 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
    out = _fetch(action, param, timeout)
    try:
        CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out, ensure_ascii=False))
    except Exception:
        pass
    return out


def _fetch(action, param, timeout):
    data = urllib.parse.urlencode({"actionId": action, "paramData": json.dumps(param, ensure_ascii=False)}).encode()
    req = urllib.request.Request(BASE + "/action.do", data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        d = json.loads(r.read())
    if d.get("status") != "SUCCESS": raise RuntimeError(f"NTIS 응답 {d.get('status')}: {d.get('message')}")
    return d["data"][action]


def _clean(s):
    s = re.sub(r"<!H[SE]>", "", s or "")
    s = re.sub(r"<br\s*/?>|</p>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t ]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def _date(s): return f"{s[:4]}.{s[4:6]}.{s[6:8]}." if s and len(s) >= 8 else ""


def jo_code(article):
    """'제52조' → '0052005', '제28조의2' → '0028025' (NTIS 조문 고유번호: 조 4자리 + 가지 2자리 + 5)."""
    m = re.fullmatch(r"제?(\d+)조(?:의(\d+))?", (article or "").strip())
    if not m: raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}5"


@lru_cache(maxsize=1)
def laws():
    """NTIS 조세법령 이름 → ntstBscId. 법률(01)·시행령(02)·시행규칙(03) 목록이 따로 있다."""
    out = {}
    for code in ("01", "02", "03"):
        out.update({x["ntstNm"]: x["ntstBscId"] for x in _act("ASISTZ001MR01", {"ntstSysClCd": code})})
    return out


def law_id(name):
    """정식 이름('법인세법 시행령')으로 찾는다. 띄어쓰기 없는 표기('법인세법시행령')도 허용.
    시행령·시행규칙을 법률 ID로 대체하지 않는다(대체하면 다른 조문의 해석이 섞임)."""
    m = laws()
    if name in m: return m[name]
    norm = re.sub(r"\s+", "", name)
    for k, v in m.items():
        if re.sub(r"\s+", "", k) == norm: return v
    return None


STOP = ("여부", "경우", "해당", "관련", "대한", "있는지", "되는지", "하는지", "적용", "따른", "위한", "그", "및", "등")


def _keywords(q, k):
    """긴 쟁점 문장 → 조사·어미를 떼고 앞쪽 핵심 명사 k개."""
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", q):
        w = re.sub(r"(으로|에서|에게|로서|로써|까지|부터|하는|되는|하여|으로서|의|가|이|은|는|을|를|에|와|과|로|도|만|인|한|된|할)$", "", w)
        if len(w) >= 2 and w not in STOP and w not in out: out.append(w)
    return " ".join(out[:k])


def search(query, kinds=("해석", "판례"), tax=None, sort="정확도", n=10, start="", end="", article=None, law=None):
    if sort == "정확도" and not article and len(_keywords(query, 9).split()) >= 3:
        return _pooled(query, kinds, tax, n, start, end)
    out = _search(query, kinds, tax, sort, n, start, end, article, law)
    if not out and not article:   # 긴 문장은 국세청 검색이 모든 단어를 요구해 0건 — 핵심어로 줄여 재시도
        for k in (5, 3):
            q2 = _keywords(query, k)
            if q2 and q2 != query:
                out = _search(q2, kinds, tax, sort, n, start, end, article, law)
                if out:
                    for r in out: r["검색어(축약)"] = q2
                    break
    return out


def search_issues(issues, kinds=("해석", "판례"), tax=None, n_per=5, recent_years=3):
    """쟁점마다 search(정확도)와 _search(최신·최근연도)를 따로 호출해 쟁점별로 묶는다.

    모델이 나눈 쟁점 여러 개를 각각 검색해 쟁점별 결과로 반환. 쟁점 하나면 search_tax_rulings 사용.
    반환: [{"쟁점": str, "결과": [{..., "선정": "정확도"|"최근"}]}, ...] 또는 {"쟁점": str, "결과": [], "오류": str}.
    """
    from datetime import date, timedelta

    out = []
    for issue in issues:
        try:
            acc = search(issue, kinds, tax, "정확도", n_per)
            acc = [{**r, "선정": "정확도"} for r in acc]
            item = {"쟁점": issue, "결과": acc}
            if recent_years > 0:
                try:   # 최근 문서 검색만 실패하면 정확도 결과는 살리고 따로 알린다
                    y, m, d = (date.today() - timedelta(days=recent_years * 365)).timetuple()[:3]
                    start = f"{y:04d}{m:02d}{d:02d}"
                    kw = _keywords(issue, 3) or issue
                    recent = _search(kw, kinds, tax, "최신", 2, start)
                    seen = {r.get("문서번호") or r.get("id") for r in acc}
                    rec = []
                    for r in recent:
                        key = r.get("문서번호") or r.get("id")
                        if key and key not in seen:
                            seen.add(key)
                            rec.append({**r, "선정": "최근"})
                            if len(rec) >= 2: break
                    acc += rec
                except Exception as e:
                    item["최근_오류"] = f"{type(e).__name__}: {str(e)}"
            out.append(item)
        except Exception as e:
            out.append({"쟁점": issue, "결과": [], "오류": f"{type(e).__name__}: {str(e)}"})
    return out


def _bigrams(t):
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _pooled(query, kinds, tax, n, start, end):
    """긴 쟁점 문장: 원문·핵심어 5·4·3·2개로 각각 정확도 검색해 후보를 모은 뒤, 제목·요지가 질문과 얼마나 겹치는지(글자 2-gram)로 다시 순위.
    국세청 정확도 순위가 오래된 유사 해석을 앞세우는 문제를 줄인다(사례집 96건 기준 Recall@10 90%→95%).

    검색어마다 _search를 호출하고 예외가 나면 다음 검색어로 넘어간다. 모든 검색어가 예외로 실패하면
    마지막 예외를 다시 던진다(서버 계층 search_tax_rulings가 이를 error 응답으로 바꾼다).
    일부만 실패하면 성공한 검색어 결과로 계속한다. 검색은 성공했지만 결과가 없으면 빈 목록을 반환한다."""
    pool = {}
    last_exc = None
    for v in dict.fromkeys(x for x in (query[:80], _keywords(query, 5), _keywords(query, 4), _keywords(query, 3), _keywords(query, 2)) if x):
        try: rs = _search(v, kinds, tax, "정확도", 30, start, end)
        except Exception as e:
            last_exc = e
            continue
        for i, r in enumerate(rs):
            k = r["문서번호"] or r["id"]
            if k not in pool: pool[k] = (r, i, v == query[:80])
    if not pool and last_exc is not None:
        raise last_exc
    qb = _bigrams(query)
    def score(k):
        r, i, full = pool[k]; tb = _bigrams(r["제목"] + r["요지"])
        return len(qb & tb) / ((len(qb) * max(1, len(tb))) ** 0.5 or 1) + (0.05 if full else 0) + 0.02 / (1 + i)
    out = [pool[k][0] for k in sorted(pool, key=score, reverse=True)[:n * max(1, len(kinds))]]
    for r in out: r["검색 방식"] = "원문·핵심어 검색 후보를 질문과의 겹침으로 재정렬"
    return out


def _search(query, kinds=("해석", "판례"), tax=None, sort="최신", n=10, start="", end="", article=None, law=None):
    """→ [{구분, 문서번호, 제목, 요지, 세목, 일자, id, 링크}]. sort: 최신 | 정확도. start/end: YYYYMMDD(등록일).
    article+law: 그 조문을 관련 법령으로 인용한 문서만."""
    p = {"schVcb": re.sub(r"[A-Z]+", lambda m: m.group().lower(), query),   # 국세청 검색은 영문 대문자(NFT 등)를 0건 처리
          "startCount": 1, "collection": ",".join(KINDS[k] for k in kinds), "sortField": "DATE/DESC" if sort == "최신" else "SCORE/DESC",
         "searchType": "", "viewCount": str(max(1, min(int(n), 30))), "useSynonymYn": "Y", "mainIdCtl": [], "icldVcbCtl": [], "exclVcbCtl": [],
         "rltnStttCtl": [], "ntstTlawClCdList": [TAX_CODES[tax]] if tax else []}
    if start: p["bltnStrtDtm"] = start + "000000"
    if end: p["bltnEndDtm"] = end + "999999"
    if article and law:
        lid = law_id(law)
        if not lid: raise ValueError(f"NTIS에 없는 법령명: {law}")
        p["rltnStttCtl"] = [f"{lid}_{jo_code(article)}"]
    d = _act("ASEISA001MR01", p)
    out = []
    for c in d["searchResultVO"]["collectionList"]:
        for r in c.get("resultList") or []:
            did = r.get("DOC_ID") or ""
            out.append({"구분": r.get("LBL1_TTL") or c.get("nameKr"), "문서번호": re.sub(r"\(\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.?\)$", "", _clean(r.get("NTST_DCM_DSCM_CNTN", ""))).strip(), "제목": _clean(r.get("TTL")),
                        "요지": _clean(r.get("GIST_CNTN"))[:400], "세목": r.get("NTST_TLAW_CL_NM", ""), "일자": _date(r.get("NTST_DCM_RGT_DT", "")),
                        "id": did, "링크": f"{BASE}/qt/USEQTA002P.do?ntstDcmId={did}", "전체건수": c.get("totalCount")})
    if sort == "최신": out.sort(key=lambda x: x["일자"], reverse=True)   # 종류(해석·판례)를 섞어 등록일 내림차순
    return out


def document(doc_id, limit=20000):
    """문서 본문(질의회신: 사실관계·질의·회신 / 판례·결정: 주문·이유) + 관련 조문."""
    if not re.fullmatch(r"\d{12,20}", str(doc_id)): raise ValueError("id는 숫자(검색 결과의 id)")
    d = _act("ASIQTB002PR01", {"dcmDVO": {"ntstDcmId": str(doc_id)}})
    v = d.get("dcmDVO") or {}
    body = next((x["dcmFleByte"] for x in d.get("dcmHwpEditorDVOList") or [] if x.get("dcmFleByte")), "") or v.get("ntstDcmCntn", "")
    rel = [x.get("ntstTextNm") for x in d.get("dcmRltnStttList") or [] if x.get("ntstTextNm")]
    return {"문서번호": v.get("ntstDcmDscmCntn", ""), "제목": _clean(v.get("ntstDcmTtl")), "요지": _clean(v.get("ntstDcmGistCntn")),
            "등록일": _date(v.get("ntstDcmRgtDt", "")), "관련조문": rel, "본문": _clean(body)[:limit],
            "링크": f"{BASE}/qt/USEQTA002P.do?ntstDcmId={doc_id}"}


def _latest(action, key, lid, years):
    for y in years:
        L = _act(action, {"ntstBscId": lid, "rgtYr": str(y)}).get(key) or []
        if L: return y, L
    return None, []


@lru_cache(maxsize=32)
def _rules(lid):
    years = [x["rgtYr"] for x in _act("ASISTD001MR03", {"ntstBscId": lid}).get("bscExrDVOList") or []]
    return _latest("ASISTD001MR02", "bscExrDVOList", lid, years)


def basic_rules(law, article="", keyword=""):
    """기본통칙(최신 고시본). article: 법 조문('제52조') — 그 조에 딸린 통칙. keyword: 제목·본문 검색."""
    lid = law_id(law)
    if not lid: raise ValueError(f"NTIS에 없는 법령명: {law}")
    year, L = _rules(lid)
    jo = jo_code(article) if article else None
    out = []
    for e in L:
        if e.get("lawClCd") != "5": continue   # 장·절 제목 제외
        t, c = e.get("ntstTextNm", ""), _clean(e.get("ntstTextCntn"))
        if jo and e.get("ntstTextUqno1") != jo: continue
        if keyword and keyword not in t + c: continue
        out.append({"통칙": re.sub(r"\s+", " ", t).strip(), "본문": c})
    return {"법령": law, "기준": f"{year}년 고시본" if year else "없음", "통칙": out,
            "링크": f"{BASE}/st/USESTD002M.do?ntstBscId={lid}"}


@lru_cache(maxsize=32)
def _standards(lid):
    return _latest("ASISTE001MR02", "exeBaseDVOList", lid, range(2026, 2014, -1))


def exec_standards(law, article="", keyword=""):
    """세법집행기준 항목 제목(최신 발간본). 번호 '52-88-1'의 앞 숫자가 법 조문. 본문은 NTIS 책자 뷰어(링크·쪽)에서."""
    m = {x["ntstNm"]: x["ntstBscId"] for x in _act("ASISTE001MR01", {}).get("exeBaseDVOList") or []}
    lid = m.get(law) or m.get({"소득세법": "종합소득세"}.get(law, ""))
    if not lid: return {"error": f"집행기준 없는 법령: {law} — 가능: {sorted(m)}"}
    year, L = _standards(lid)
    no = re.match(r"제?(\d+)조(?:의(\d+))?", article or "")
    pre = (f"{no.group(1)}의{no.group(2)}-" if no.group(2) else f"{no.group(1)}-") if no else ""
    out = [{"항목": re.sub(r"\s+", " ", e.get("ntstTextNm", "")).strip(), "쪽": e.get("srtOrdr")}
           for e in L if e.get("lawClCd") == "5" and (not pre or re.sub(r"\s+", "", e.get("ntstTextNm", "")).startswith(pre.replace(" ", "")))
           and (not keyword or keyword in e.get("ntstTextNm", ""))]
    return {"법령": law, "기준": f"{year}년 발간본" if year else "없음", "항목": out,
            "링크": f"{BASE}/st/USESTE001M.do?ntstBscId={lid}&rgtYr={year}", "주의": "집행기준 본문은 책자(PDF)라 링크에서 해당 쪽 확인"}


# ── 조세조약 (96개국, 조문별 국문·영문) ──
@lru_cache(maxsize=1)
def treaties():
    return {x["txaAgrmNtnNm"]: {"id": x["txaAgrmBscId"], "발효일": _date(x.get("valdOcrnDt", ""))}
            for x in _act("ASISTC001MR01", {"txaAgrmClCd": "01"}).get("txaTraDVOList") or []}


_KDATE_LINE = re.compile(r"^\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(?:[^\n]*?)(서명|발효)\s*$")
_DOC_DATE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")


def _ymd(y, m, d): return f"{int(y):04d}.{int(m):02d}.{int(d):02d}."


def treaty_meta(listed, rows):
    """현행 협정의 서명일·발효일과 부속 문서 구분(실사용 점검 #88·#108).

    국세청 조약 목록의 발효일(valdOcrnDt)은 최초 협정 기준이라, 신협정으로 바뀐 조약(일본 1999·싱가포르 2019 등)은
    조문 본문과 날짜가 어긋났다. 조약 '전문' 머리의 'YYYY년 M월 D일 … 발효' 줄을 현행 협정의 발효일로 쓴다.
    반환: (메타 dict, 종전 협정 문서 이름 set)
    """
    pre = next((r for r in rows if (r.get("txaAgrmTextNm") or "").strip() == "전문"), None)
    text = re.sub(r"<[^>]+>", "", (pre or {}).get("txaAgrmTextCntn") or "")
    cur = sign = None
    for ln in text.split("\n")[:12]:
        m = _KDATE_LINE.match(ln)
        if m and m.group(4) == "발효" and not cur: cur = _ymd(*m.group(1, 2, 3))
        if m and m.group(4) == "서명" and not sign: sign = _ymd(*m.group(1, 2, 3))
    meta = {"발효일": cur or listed}
    if sign: meta["서명일"] = sign
    if cur and cur != listed: meta["최초 협정 발효일"] = listed
    if not cur:
        meta["발효일 주의"] = "국세청 조약 목록의 발효일 — 개정 협정·의정서가 있으면 조약 전문·의정서에서 현행 문서의 발효일 확인"
    key = lambda s: tuple(int(x) for x in s.strip(".").split("."))
    related, old = [], []
    for r in rows:
        nm = (r.get("txaAgrmTextNm") or "").strip()
        if "의정서" not in (r.get("txaAgrmTextUqnm") or "") or nm in ("전문", "의정서", ""): continue
        d = _DOC_DATE.search(nm)
        superseded = nm.startswith("최초협정") or bool(cur and d and key(_ymd(*d.groups())) < key(cur))
        (old if superseded else related).append(nm)
    if related: meta["관련 문서"] = related
    if old: meta["종전 협정 문서"] = old   # 현행 협정 발효 전 문서 — 현행 조문을 고친 것이 아님
    return meta, set(old)


_KR_SIDE = re.compile(r"(?:대한민국|한국)\s*(?:의\s*경우|에\s*있어서는|에\s*대하여는|에서는|에\s*관하여는)")


def local_tax_coverage(rows):
    """대상조세 조문(보통 제2조)의 한국 측 조세에 지방소득세(주민세)가 있는지. 법인세법 제98조의7① 각 호 판단용(실사용 점검 #108)."""
    art = next((r for r in rows if "의정서" not in (r.get("txaAgrmTextUqnm") or "")
                and "대상조세" in re.sub(r"\s+", "", r.get("txaAgrmTextNm") or "")), None)
    text = re.sub(r"<[^>]+>", "", (art or {}).get("txaAgrmTextCntn") or "")
    m = _KR_SIDE.search(text)
    if not m:
        return {"대상조세 포함": None,
                "안내": "대상조세 조문에서 한국 측 조세 목록을 찾지 못함 — tax_treaty(country, keyword='대상조세')로 확인. "
                        "지방소득세(주민세)가 있으면 제한세율은 지방소득세 포함 상한(법인세법 제98조의7①2호), 없으면 지방소득세는 따로(같은 항 1호)"}
    rest = text[m.start():]
    end = re.search(r"[\"“”]\s*한국의\s*조세\s*[\"“”][^\n]*", rest)
    seg = rest[:end.end()] if end else rest[:400]
    seg = re.split(r"\n\s*(?:나\.|나\)|\(b\)|\(나\))", seg)[0]
    seg = re.sub(r"\s+", " ", seg).strip()
    no = (art.get("txaAgrmTextUqnm") or "").strip()
    if re.search(r"주민세|지방소득세", seg):
        return {"대상조세 포함": True, "근거": f"{no} {seg}".strip(),
                "안내": "대상조세에 한국 지방소득세(주민세)가 포함된 조약 — 제한세율은 원천징수 법인세(소득세)와 지방소득세를 합한 상한. "
                        "외국법인의 이자·배당·사용료는 제한세율과 '국내 세율에 지방소득세(법인세의 100분의 10)를 반영한 세율' 중 낮은 세율(법인세법 제98조의7①2호) — "
                        "예: 제한세율 10%면 법인세 10/11, 지방소득세 1/11로 나눠 합계 10%"}
    return {"대상조세 포함": False, "근거": f"{no} {seg}".strip(),
            "안내": "대상조세의 한국 측 조세에 지방소득세(주민세)가 없음 — 제한세율은 법인세(소득세)분이고, 지방소득세(원천징수세액의 100분의 10)는 따로(법인세법 제98조의7①1호)"}


TREATY_SYNONYMS = {
    "근로": ["근로", "급여", "종속적 인적용역", "고용", "dependent personal services", "employment"],
    "급여": ["근로", "급여", "종속적 인적용역", "고용", "dependent personal services", "employment"],
    "종속적 인적용역": ["종속적 인적용역", "근로", "급여", "고용", "dependent personal services", "employment"],
    "고용": ["근로", "급여", "종속적 인적용역", "고용", "dependent personal services", "employment"],
    "이사": ["이사", "이사회", "directors", "board"],
    "이사회": ["이사", "이사회", "directors", "board"],
    "directors": ["이사", "이사회", "directors", "board"],
    "인적용역": ["인적용역", "독립적 인적용역", "personal services", "independent personal services"],
    "독립적 인적용역": ["인적용역", "독립적 인적용역", "personal services", "independent personal services"],
    "고정사업장": ["고정사업장", "PE", "permanent establishment"],
    "PE": ["고정사업장", "PE", "permanent establishment"],
    "permanent establishment": ["고정사업장", "PE", "permanent establishment"],
}


def treaty(country, article="", keyword="", english=False):
    """country: 국가명(예: '미국', '중국'). article: '제10조'·'의정서' 등. keyword: 조문 제목·본문 검색."""
    t = treaties()
    name = country if country in t else next((n for n in t if country and (country in n or n in country)), None)
    if not name: return {"error": f"조약 체결국에서 '{country}'를 찾지 못함", "체결국": sorted(t)}
    rows = _act("ASISTC002MR01", {"txaAgrmBscId": t[name]["id"]}).get("txaTraDVOList") or []

    # keyword 동의어 확장
    search_terms = [keyword]
    if keyword and keyword in TREATY_SYNONYMS:
        search_terms = TREATY_SYNONYMS[keyword]

    out = []
    for r in rows:
        no, title = (r.get("txaAgrmTextUqnm") or "").strip(), (r.get("txaAgrmTextNm") or "").strip()
        body = (r.get("txaAgrmTextEnglCntn") if english else r.get("txaAgrmTextCntn")) or ""
        en_title = r.get("txaAgrmTextEnglNm") or ""
        if article and article.replace(" ", "") not in no.replace(" ", ""): continue
        if keyword:
            haystack = f"{title} {body} {en_title}"
            if not any(term and term in haystack for term in search_terms): continue
        out.append({"조": no, "제목": title, "영문 제목": en_title, "본문": body.strip()[:6000]})
    if keyword:   # 제목에 검색어가 있는 조문을 먼저 — '배당'이 본문에만 나오는 제5조가 제목이 '배당'인 조보다 앞서던 문제
        out.sort(key=lambda x: 0 if any(term and (term in x["제목"] or term in x["영문 제목"]) for term in search_terms) else 1)

    if not out and keyword and keyword in TREATY_SYNONYMS:
        # 동의어 확장으로도 결과가 없으면 안내 제공
        if keyword in ("이사", "이사회", "directors"):
            # 같은 조약에서 근로소득/인적용역 조문의 실제 조 번호를 찾아 안내
            labor_rows = [r for r in rows
                          if any(term in (r.get("txaAgrmTextNm") or "")
                                 for term in TREATY_SYNONYMS["근로"])
                          and "의정서" not in (r.get("txaAgrmTextUqnm") or "")]
            if labor_rows:
                labor_no = labor_rows[0].get("txaAgrmTextUqnm", "").strip()
                labor_title = labor_rows[0].get("txaAgrmTextNm", "").strip()
                안내 = f"이사 보수 조문 없음 → 근로소득 조항({labor_no} {labor_title}) 검토 권장"
            else:
                안내 = "이사 보수 조문 없음 → 근로소득 조항 검토 권장"
            return {"국가": name, **treaty_meta(t[name]["발효일"], rows)[0], "조문": [],
                    "안내": 안내,
                    "링크": f"{BASE}/st/USESTC002M.do?txaAgrmBscId={t[name]['id']}"}

    return {"국가": name, **treaty_meta(t[name]["발효일"], rows)[0], "조문": out,
            "링크": f"{BASE}/st/USESTC002M.do?txaAgrmBscId={t[name]['id']}"}


# ── 국세청 발간책자 본문 검색 (이전가격 안내·APA 보고서·세무 가이드북 등) ──
def publications(query, n=8):
    p = {"schVcb": query, "startCount": 1, "collection": "formerLibrary", "sortField": "SCORE/DESC", "searchType": "",
         "viewCount": str(max(1, min(int(n), 20))), "useSynonymYn": "Y", "mainIdCtl": [], "icldVcbCtl": [], "exclVcbCtl": [],
         "rltnStttCtl": [], "ntstTlawClCdList": []}
    d = _act("ASEISA001MR01", p)
    out = []
    for c in d["searchResultVO"]["collectionList"]:
        for r in c.get("resultList") or []:
            out.append({"책자": r.get("NTST_PLCN_BK_TTL", ""), "발간일": _date(r.get("PLCN_DT", "")), "분야": r.get("LBL2_TTL", ""),
                        "담당": r.get("NTST_JRSD_DNO_NM", ""), "발췌": _clean(r.get("FILE_CN", ""))[:400],
                        "링크": f"{BASE}/el/USEELA001M.do"})
    return out


# ── 조약별 원천징수 제한세율(배당·이자·사용료) — 원문에서 세율·요건을 뽑고 근거 문장을 함께 ──
INCOME = {"배당": "DIVIDEND", "이자": "INTEREST", "사용료": "ROYALT"}
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:per\s*cent|percent|%)", re.I)


def _rate_items(txt):
    """세율(총액의 %)과 지분 요건(자본·의결권의 %)을 문맥으로 구분. 근거는 그 항목 절((a)·(b)…) 전체."""
    rates, thresholds = [], []
    marks = [m.start() for m in re.finditer(r"\(\s*[a-z]\s*\)|\n\s*\d+\.\s|;", txt)] + [len(txt)]
    for m in _PCT.finditer(txt):
        st = max([x for x in marks if x <= m.start()] or [0]); en = min([x for x in marks if x > m.end()] or [len(txt)])
        if txt[en:en + 1] == ";": en += 1
        clause = re.sub(r"\s+", " ", txt[st:min(en + 250, len(txt))]).strip(" ;")[:400]
        right = txt[m.end():m.end() + 60].lower()
        v = float(m.group(1))
        if re.match(r"\s*of the (?:voting|capital|shares|stock|issued|outstanding)", right) or re.search(r"(?:owns|holds|holding)\D{0,40}$", txt[max(0, m.start() - 60):m.start()].lower()):
            thresholds.append({"지분요건(%)": v, "근거": clause})
        elif "gross amount" in clause.lower() or "shall not exceed" in clause.lower():
            rates.append({"세율(%)": v, "근거": clause})
        else:
            thresholds.append({"기타(%)": v, "근거": clause})
    return rates, thresholds


def withholding_rates(country, income=None):
    t = treaties()
    name = country if country in t else next((n for n in t if country and (country in n or n in country)), None)
    if not name: return {"error": f"조약 체결국에서 '{country}'를 찾지 못함", "체결국": sorted(t)}
    rows = _act("ASISTC002MR01", {"txaAgrmBscId": t[name]["id"]}).get("txaTraDVOList") or []
    meta, superseded = treaty_meta(t[name]["발효일"], rows)
    # 종전 협정 원문(최초협정 등)은 같은 소득 조문을 언급해도 현행 조문을 고친 문서가 아니다(실사용 점검 #108)
    prot = [r for r in rows if "의정서" in (r.get("txaAgrmTextUqnm") or "") and r.get("txaAgrmTextNm") not in ("전문",)
            and (r.get("txaAgrmTextNm") or "").strip() not in superseded]
    out = []
    for ko, en in INCOME.items():
        if income and income != ko: continue
        art = next((r for r in rows if en in (r.get("txaAgrmTextEnglNm") or "").upper() and "의정서" not in (r.get("txaAgrmTextUqnm") or "")), None)
        if not art: out.append({"소득": ko, "조문": None, "세율": [], "주의": "조약에 별도 조문 없음 — 국내법 세율 적용 여부 확인"}); continue
        rates, others = _rate_items(art.get("txaAgrmTextEnglCntn") or "")
        no = art.get("txaAgrmTextUqnm")
        touched = [f"{p.get('txaAgrmTextNm')}" for p in prot
                   if re.search(rf"(?:Article|제)\s*{re.sub(r'[^0-9]', '', no or '')}(?!\d)|{en.title()}", (p.get("txaAgrmTextEnglCntn") or "") + (p.get("txaAgrmTextCntn") or ""))]
        out.append({"소득": ko, "조문": no, "제목": art.get("txaAgrmTextNm"), "세율": rates, "요건·기타": others[:6],
                    "개정 문서 언급": touched, "주의": "개정 의정서·교환각서가 이 조문을 바꿨을 수 있음 — 언급된 문서 확인" if touched else ""})
    return {"국가": name, **meta, "제한세율": out, "지방소득세": local_tax_coverage(rows),
            "주의": "조약 원문에서 자동 추출 — 적용 전 원문·개정 의정서·교환각서 확인. 지방소득세를 제한세율 안에 넣을지는 '지방소득세' 항목 참고",
            "링크": f"{BASE}/st/USESTC002M.do?txaAgrmBscId={t[name]['id']}"}


# ── 별표·서식 (세율표·기준금액표·신고서 서식 등) ──
def forms(query, kind=None, n=10):
    out = _forms(query, kind, n)
    if not out:
        for k in (3, 2):
            q2 = _keywords(query, k)
            if q2 and q2 != query and (out := _forms(q2, kind, n)): break
    return out


def _forms(query, kind=None, n=10):
    p = {"schVcb": query, "startCount": 1, "collection": "appendForm", "sortField": "SCORE/DESC", "searchType": "",
         "viewCount": str(max(1, min(int(n) * 2, 40))), "useSynonymYn": "Y", "mainIdCtl": [], "icldVcbCtl": [], "exclVcbCtl": [],
         "rltnStttCtl": [], "ntstTlawClCdList": []}
    d = _act("ASEISA001MR01", p)
    out, seen = [], set()
    for c in d["searchResultVO"]["collectionList"]:
        for r in c.get("resultList") or []:
            name = _clean(r.get("FRML_NM", "")); typ = "별표" if "별표" in name or "별표" in (r.get("LBL1_NM") or "") else "서식"
            if kind and kind != typ: continue
            k = (name, r.get("BSC_ID"))
            if k in seen: continue   # 같은 서식의 여러 시행본 중 최신만
            seen.add(k)
            out.append({"구분": typ, "이름": name, "법령": r.get("NM", ""), "세법": r.get("LBL2_TTL", ""), "시행일": _date(r.get("ENFR_DT", "")),
                        "내용": _clean(r.get("FILE_CN", ""))[:600], "링크": f"{BASE}/af/USEAFE001M.do"})
            if len(out) >= n: break
    return out
