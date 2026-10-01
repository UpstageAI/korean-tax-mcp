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

BASE = "https://taxlaw.nts.go.kr"
CTX = ssl.create_default_context(); CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT
TAX_CODES = {"국기": "301", "국징": "302", "법인": "303", "소득": "305", "부가": "306", "양도": "307", "상증": "308", "조특": "309", "국조": "310", "종부": "311"}
KINDS = {"해석": "question", "판례": "precedent"}


CACHE = Path(os.environ.get("KOREAN_TAX_MCP_CACHE", Path.home() / ".cache" / "korean-tax-mcp"))
TTL = int(os.environ.get("KOREAN_TAX_MCP_CACHE_TTL", 86400))
_lock = threading.Lock(); _last = [0.0]
UA = "korean-tax-mcp (+https://github.com/seungmiyoon/korean-tax-mcp)"


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
    """NTIS 조세법령 이름 → ntstBscId."""
    return {x["ntstNm"]: x["ntstBscId"] for x in _act("ASISTZ001MR01", {"ntstSysClCd": "01"})}


def law_id(name):
    m = laws()
    if name in m: return m[name]
    base = re.sub(r"\s*(시행령|시행규칙)$", "", name)
    return m.get(base)


def search(query, kinds=("해석", "판례"), tax=None, sort="최신", n=10, start="", end="", article=None, law=None):
    """→ [{구분, 문서번호, 제목, 요지, 세목, 일자, id, 링크}]. sort: 최신 | 정확도. start/end: YYYYMMDD(등록일).
    article+law: 그 조문을 관련 법령으로 인용한 문서만."""
    p = {"schVcb": query, "startCount": 1, "collection": ",".join(KINDS[k] for k in kinds), "sortField": "DATE/DESC" if sort == "최신" else "SCORE/DESC",
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
            out.append({"구분": r.get("LBL1_TTL") or c.get("nameKr"), "문서번호": r.get("NTST_DCM_DSCM_CNTN", ""), "제목": _clean(r.get("TTL")),
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
