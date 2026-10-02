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


STOP = ("여부", "경우", "해당", "관련", "대한", "있는지", "되는지", "하는지", "적용", "따른", "위한", "그", "및", "등")


def _keywords(q, k):
    """긴 쟁점 문장 → 조사·어미를 떼고 앞쪽 핵심 명사 k개."""
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", q):
        w = re.sub(r"(으로|에서|에게|로서|로써|까지|부터|하는|되는|하여|으로서|의|가|이|은|는|을|를|에|와|과|로|도|만|인|한|된|할)$", "", w)
        if len(w) >= 2 and w not in STOP and w not in out: out.append(w)
    return " ".join(out[:k])


def search(query, kinds=("해석", "판례"), tax=None, sort="최신", n=10, start="", end="", article=None, law=None):
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


def _bigrams(t):
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _pooled(query, kinds, tax, n, start, end):
    """긴 쟁점 문장: 원문·핵심어 5·4·3·2개로 각각 정확도 검색해 후보를 모은 뒤, 제목·요지가 질문과 얼마나 겹치는지(글자 2-gram)로 다시 순위.
    국세청 정확도 순위가 오래된 유사 해석을 앞세우는 문제를 줄인다(사례집 96건 기준 Recall@10 90%→95%)."""
    pool = {}
    for v in dict.fromkeys(x for x in (query[:80], _keywords(query, 5), _keywords(query, 4), _keywords(query, 3), _keywords(query, 2)) if x):
        try: rs = _search(v, kinds, tax, "정확도", 30, start, end)
        except Exception: continue
        for i, r in enumerate(rs):
            k = r["문서번호"] or r["id"]
            if k not in pool: pool[k] = (r, i, v == query[:80])
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


def treaty(country, article="", keyword="", english=False):
    """country: 국가명(예: '미국', '중국'). article: '제10조'·'의정서' 등. keyword: 조문 제목·본문 검색."""
    t = treaties()
    name = country if country in t else next((n for n in t if country and (country in n or n in country)), None)
    if not name: return {"error": f"조약 체결국에서 '{country}'를 찾지 못함", "체결국": sorted(t)}
    rows = _act("ASISTC002MR01", {"txaAgrmBscId": t[name]["id"]}).get("txaTraDVOList") or []
    out = []
    for r in rows:
        no, title = (r.get("txaAgrmTextUqnm") or "").strip(), (r.get("txaAgrmTextNm") or "").strip()
        body = (r.get("txaAgrmTextEnglCntn") if english else r.get("txaAgrmTextCntn")) or ""
        if article and article.replace(" ", "") not in no.replace(" ", ""): continue
        if keyword and keyword not in f"{title} {body} {r.get('txaAgrmTextEnglNm') or ''}": continue
        out.append({"조": no, "제목": title, "영문 제목": r.get("txaAgrmTextEnglNm") or "", "본문": body.strip()[:6000]})
    return {"국가": name, "발효일": t[name]["발효일"], "조문": out,
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
    prot = [r for r in rows if "의정서" in (r.get("txaAgrmTextUqnm") or "") and r.get("txaAgrmTextNm") not in ("전문",)]
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
    return {"국가": name, "발효일": t[name]["발효일"], "제한세율": out,
            "주의": "조약 원문에서 자동 추출 — 적용 전 원문·개정 의정서·국내법(지방소득세 별도 등) 확인", "링크": f"{BASE}/st/USESTC002M.do?txaAgrmBscId={t[name]['id']}"}


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
