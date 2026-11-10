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
    decc = d.get("Decc", {})
    rows = decc.get("decc", []) if isinstance(decc, dict) else []
    out: list[dict] = []
    for row in rows:
        seq = (row.get("특별행정심판재결례일련번호") or "").strip()
        if not seq:
            continue
        bill = (row.get("청구번호") or "").strip()
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


def search(query: str, n: int = 10, sort: str = "최신", local_only: bool = False) -> dict:
    """조세심판원 재결례 검색. 반환 {"결과": [...], "전체건수": int}."""
    q = urllib.parse.quote(query)
    if sort == "정확도":
        qstr = f"target=ttSpecialDecc&display={n}&page=1&query={q}"
    else:
        qstr = f"target=ttSpecialDecc&display={n}&page=1&sort=ddes&query={q}"
    d = law._get("lawSearch.do", qstr)
    decc = d.get("Decc", {})
    total = int(decc.get("totalCnt") or 0)
    return {"결과": parse_search(d, local_only=local_only), "전체건수": total}


def detail(id: str) -> dict:
    """조세심판원 재결례 상세. id='tt:2098157' 또는 '2098157'."""
    seq = id
    if id.startswith("tt:"):
        seq = id[3:]
    d = law._get("lawService.do", f"target=ttSpecialDecc&ID={seq}")
    return parse_detail(d)
