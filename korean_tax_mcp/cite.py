"""인용 검증 — 초안의 해석·판례 문서번호와 조문 인용이 실제로 있는지 확인한다.

- 문서번호: 국세법령정보시스템에서 같은 번호를 찾는다(형식 차이 무시). 형사판결 등 국세청 DB에 없는 것은 '국세청 DB 미확인'으로 구분
- 조문: 법제처 API로 기준일(없으면 오늘) 시행본에 그 조가 있는지(LAW_OC 있을 때)
"""
import re
from concurrent.futures import ThreadPoolExecutor

from . import law, ntis

DOC = re.compile(r"(?:(?:서면|사전|기준|질의|법규|법령해석|이의|심사|심판|조심|국심|감심)[-\s]?(?:[가-힣]+[-\s]?)?\d{4}[-\s]?[가-힣]*[-\s]?\d{2,5}"
                 r"|[가-힣]{1,10}법원(?:\([가-힣]+\))?[-\s]?\d{4}[-\s]?[가-힣]{1,3}[-\s]?\d{2,6}"
                 r"|법규[가-힣]{1,4}\d{4}-\d{1,5})")
LAWREF = re.compile(r"((?:[가-힣]+에\s?관한\s?법률|(?:[가-힣]+\s및\s)?[가-힣]*?[가-힣]법)(?:\s?시행령|\s?시행규칙)?)\s*(제\d+조(?:의\d+)?)")


def _key(t): return re.sub(r"[^0-9A-Za-z가-힣]", "", re.sub(r"\(\d{4}\.[^)]*\)$", "", (t or "").strip()))


def _check_doc(raw):
    try: hits = ntis.search(raw, ("해석", "판례"), None, "정확도", 5)
    except Exception as e: return {"인용": raw, "결과": "조회 실패", "이유": str(e)[:80]}
    k = _key(raw)
    m = next((h for h in hits if _key(h["문서번호"]) == k), None)
    if m: return {"인용": raw, "결과": "확인", "문서번호": m["문서번호"], "제목": m["제목"], "일자": m["일자"], "링크": m["링크"]}
    kind = "형사·민사 판결 등은 국세청 DB에 없을 수 있음" if re.search(r"\d{4}[도노고]", raw) else "번호 오기 또는 존재하지 않는 문서 가능성"
    return {"인용": raw, "결과": "국세청 DB 미확인", "이유": kind, "비슷한 번호": [h["문서번호"] for h in hits[:3]]}


def _check_law(name, art, as_of):
    try:
        r = law.article(name.strip(), art, as_of)
    except law.NoKey:
        return {"인용": f"{name} {art}", "결과": "미검증", "이유": "LAW_OC 없음"}
    except Exception as e:
        return {"인용": f"{name} {art}", "결과": "조회 실패", "이유": str(e)[:80]}
    if r.get("error"): return {"인용": f"{name} {art}", "결과": "법령명 미확인", "이유": r["error"]}
    ok = r.get("본문") and not r["본문"].startswith("조문 없음")
    return {"인용": f"{name} {art}", "결과": "확인" if ok else "조문 없음", "적용 시행일": r.get("적용 시행일")}


def verify(text, as_of=""):
    docs = list(dict.fromkeys(m.group(0).strip() for m in DOC.finditer(text)))
    laws = list(dict.fromkeys((m.group(1).strip(), m.group(2)) for m in LAWREF.finditer(text)))
    with ThreadPoolExecutor(4) as ex:
        d = list(ex.map(_check_doc, docs[:30]))
        l = list(ex.map(lambda x: _check_law(x[0], x[1], as_of), laws[:30]))
    bad = [x for x in d + l if x["결과"] not in ("확인", "미검증")]
    return {"문서번호": d, "조문": l, "요약": f"문서 {len(d)}건·조문 {len(l)}건 중 확인 안 된 것 {len(bad)}건",
            "주의": "확인은 '존재'만 뜻함 — 인용한 내용이 그 문서·조문의 내용과 맞는지는 본문으로 확인"}
