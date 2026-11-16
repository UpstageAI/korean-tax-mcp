"""조세심판원 재결례 조회 — 법제처 특별행정심판재결례(target=ttSpecialDecc).

재결청 조세심판원, 국세·지방세 모두. 지방세 불복은 행정심판법 적용 배제
(지방세기본법 제98조제1항)·심판청구 필요적 전치(제3항)라 결정례는 조세심판원에 있고
국세법령정보시스템에는 거의 없다. law._get 재사용 → 재시도·예산·캐시 규칙 그대로.
"""
import re
import urllib.parse

from . import law

_LAW_LINK = "https://www.law.go.kr/LSW/specialDeccInfoP.do?spDeccSeq={seq}"

_LOCAL_TAX_CODE_RE = re.compile(r"지")
# 사건번호 형태: '2023서9158', '조심2023서9158', '조심 2023서9158', '조심-2023-서-9158', '국심2006서1465'
_CASE_NO_RE = re.compile(r"^\s*(?:(조심|국심)\s*-?\s*)?((?:19|20)\d{2})\s*-?\s*([가-힣]{1,2})\s*-?\s*(\d{1,5})\s*$")
# 일련번호 → 청구번호. 상세 응답(lawService)은 청구번호·사건번호 칸이 비어 오므로 검색 결과에서 기억해 둔다(2026-11-16 확인)
_BILL: dict[str, str] = {}


def case_number(query: str):
    """사건번호 형태면 (접두어, '2023서9158'), 아니면 None."""
    m = _CASE_NO_RE.match(query or "")
    if not m:
        return None
    return (m.group(1) or "", f"{m.group(2)}{m.group(3)}{m.group(4)}")


def _rows(d: dict) -> list[dict]:
    """lawSearch 응답의 decc 목록. 결과가 1건이면 법제처가 목록 대신 객체 하나를 보낸다."""
    decc = d.get("Decc", {}) if isinstance(d, dict) else {}
    rows = decc.get("decc", []) if isinstance(decc, dict) else []
    if isinstance(rows, dict):
        rows = [rows]
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _fmt_date(s: str) -> str:
    """'2026.08.19' → '2026.08.19.' (검색 응답 형식). 이미 '.'이 끝에 있으면 그대로."""
    s = s.strip()
    return s if s.endswith(".") else s + "."


def parse_search(d: dict, local_only: bool = False) -> list[dict]:
    """ttSpecialDecc lawSearch 응답을 항목 목록으로 파싱.

    반환 항목: {"구분","문서번호","제목","일자","id","링크","지방세"}
    - 지방세: 청구번호에 '지'가 들어가면 True (조심 20xx지xxxx).
    - local_only=True면 지방세 True인 항목만.
    """
    out: list[dict] = []
    for row in _rows(d):
        seq = (row.get("특별행정심판재결례일련번호") or "").strip()
        if not seq:
            continue
        bill = (row.get("청구번호") or "").strip()
        if bill:
            if len(_BILL) > 5000:
                _BILL.clear()
            _BILL[seq] = bill
        local = bool(_LOCAL_TAX_CODE_RE.search(bill))
        if local_only and not local:
            continue
        out.append({
            "구분": "조세심판",
            "문서번호": bill,
            "제목": (row.get("사건명") or "").strip(),
            "일자": _fmt_date((row.get("의결일자") or "").strip()),
            "id": "tt:" + seq,
            "링크": _LAW_LINK.format(seq=seq),
            "지방세": local,
        })
    return out


def parse_detail(d: dict) -> dict:
    """ttSpecialDecc lawService 상세 응답을 parsed dict로.

    반환: {"구분","문서번호","제목","일자","세목","주문","요지","본문","관련법령","참조결정","id","링크"}
    - 문서번호: 상세 응답의 청구번호(대개 빈 값 — detail()이 검색 결과로 채운다)
    - 일자: 'SpecialDeccService'.'의결일자'('20260819') → '2026.08.19.'
    - 관련법령: ','로 나눠 strip. 참조결정: '/'로 나눠 strip, 빈 것 제외.
    """
    svc = d.get("SpecialDeccService", {})
    seq = (svc.get("특별행정심판재결례일련번호") or "").strip()
    raw_date = (svc.get("의결일자") or "").strip()
    y, m, dd = raw_date[:4], raw_date[4:6], raw_date[6:8]
    date_str = f"{y}.{m}.{dd}."

    rel_raw = (svc.get("관련법령") or "").strip()
    related = [x.strip() for x in rel_raw.split(",") if x.strip()] if rel_raw else []

    ref_raw = (svc.get("참조결정") or "").strip()
    refs = [x.strip() for x in ref_raw.split("/") if x.strip()] if ref_raw else []

    return {
        "구분": "조세심판",
        "문서번호": (svc.get("청구번호") or "").strip(),
        "제목": (svc.get("사건명") or "").strip(),
        "일자": date_str,
        "세목": (svc.get("세목") or "").strip(),
        "주문": (svc.get("주문") or "").strip(),
        "요지": (svc.get("재결요지") or "").strip(),
        "본문": (svc.get("이유") or "").strip(),
        "관련법령": related,
        "참조결정": refs,
        "id": "tt:" + seq,
        "링크": _LAW_LINK.format(seq=seq),
    }


def _search_raw(query: str, n: int, sort: str) -> dict:
    q = urllib.parse.quote(query)
    if sort == "정확도":
        qstr = f"target=ttSpecialDecc&display={n}&page=1&query={q}"
    else:
        qstr = f"target=ttSpecialDecc&display={n}&page=1&sort=ddes&query={q}"
    return law._get("lawSearch.do", qstr)


def search(query: str, n: int = 10, sort: str = "최신", local_only: bool = False) -> dict:
    """조세심판원 재결례 검색. 반환 {"결과": [...], "전체건수": int, "검색 방식": "사건번호"|"키워드"}.

    사건번호('2023서9158', '조심2023서9158')를 넣으면 접두어를 떼고 번호로 찾고, 청구번호가 그 번호와 같은 것만 남긴다
    (같은 번호가 없으면 받은 결과 그대로)."""
    cn = case_number(query)
    d = _search_raw(cn[1] if cn else query, n, sort)
    decc = d.get("Decc", {}) if isinstance(d, dict) else {}
    total = int((decc.get("totalCnt") if isinstance(decc, dict) else 0) or 0)
    items = parse_search(d, local_only=local_only)
    if cn:
        exact = [x for x in items if "".join(x["문서번호"].split()).replace("-", "").endswith(cn[1])
                 and not re.search(r"\d" + re.escape(cn[1]) + "$", "".join(x["문서번호"].split()))]
        if exact:
            items, total = exact, len(exact)
    return {"결과": items, "전체건수": total, "검색 방식": "사건번호" if cn else "키워드"}


def detail(id: str) -> dict:
    """조세심판원 재결례 상세. id='tt:2098157' 또는 '2098157'."""
    seq = id
    if id.startswith("tt:"):
        seq = id[3:]
    d = law._get("lawService.do", f"target=ttSpecialDecc&ID={seq}")
    out = parse_detail(d)
    if not out["문서번호"]:
        out["문서번호"] = _number_for(seq, out["제목"])
        if not out["문서번호"]:
            out["문서번호 확인"] = "법제처 상세 응답에 청구번호가 없고 사건명 검색으로도 찾지 못함 — 링크의 결정문 첫머리에서 확인"
    return out


def _number_for(seq: str, title: str) -> str:
    """상세 응답에 없는 청구번호를 찾는다 — 검색 결과에서 기억한 값, 없으면 사건명 앞부분으로 검색해 일련번호가 같은 행.
    사건명 전체로는 검색이 안 되는 경우가 있어(2026-11-16 확인: 60자 0건, 40자·20자 1~2건) 40자 → 20자 순으로 찾는다."""
    if seq in _BILL:
        return _BILL[seq]
    t = " ".join((title or "").split())
    for k in (40, 20):
        if not t:
            break
        parse_search(_search_raw(t[:k], 30, "정확도"))
        if seq in _BILL:
            return _BILL[seq]
        if len(t) <= k:
            break
    return ""
