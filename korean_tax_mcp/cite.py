"""인용 검증 — 초안의 해석·판례 문서번호와 조문 인용이 실제로 있는지 확인한다.

- 문서번호: 국세법령정보시스템에서 같은 번호를 찾는다(형식 차이 무시). 형사판결 등 국세청 DB에 없는 것은 '국세청 DB 미확인'으로 구분
  판결문 표준 인용('대법원 2002. 9. 24. 선고 2001두489 판결', 두 자리 연도 '88누3123')과 조심·국심 번호도 읽는다.
- 조문: 법제처 API로 기준일(없으면 오늘) 시행본에 그 조가 있는지, 항·호를 인용했으면 그 항·호까지 있는지(LAW_OC 있을 때)
- 읽지 못한 인용(번호 없는 판결 언급, '같은 법 제5조'처럼 법령명이 없는 조문)은 버리지 않고 '형식 미인식'으로 센다.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from . import _mask_oc, law, net, ntis

MAX = 30   # 종류별 조회 상한 — 넘으면 '생략'으로 알림

# 판결: 법원 [선고일] [선고] 사건번호 [판결]. 연도는 네 자리 또는 두 자리(1990년대 이전 '88누3123')
COURT = re.compile(r"(?<![가-힣])((?:대법원|[가-힣]{1,10}법원)(?:\s*\([가-힣]+\))?)\s*"
                   r"(?:(?:19|20)\d{2}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?\s*)?(?:선고\s*)?"
                   r"((?:19|20)?\d{2})\s*-?\s*([가-힣]{1,3})\s*-?\s*(\d{1,6})(?!\d)")
# 조세심판·옛 국세심판·감사원 심사: '조심 2015전1925', '조심2015-서-1234', '국심 98서164'
TRIB = re.compile(r"(?<![가-힣])(조심|국심|감심)\s*-?\s*((?:19|20)?\d{2})\s*-?\s*([가-힣]{1,2})\s*-?\s*(\d{1,6})(?!\d)")
DOC = re.compile(r"(?:(?:서면|사전|기준|질의|법규|법령해석|이의|심사|심판|조심|국심|감심)[-\s]?(?:[가-힣]+[-\s]?)?\d{4}[-\s]?[가-힣]*[-\s]?\d{2,5}"
                 r"|[가-힣]{1,10}법원(?:\([가-힣]+\))?[-\s]?\d{4}[-\s]?[가-힣]{1,3}[-\s]?\d{2,6}"
                 r"|법규[가-힣]{1,4}\d{4}-\d{1,5})")
LAWREF = re.compile(r"((?:[가-힣]+에\s?관한\s?법률|(?:[가-힣]+\s및\s)?[가-힣]*?[가-힣]법)(?:\s?시행령|\s?시행규칙)?)\s*(제\d+조(?:의\d+)?)"
                    r"(?:\s*(제\d+항|[①-⑳]))?(?:\s*(제\d+호(?:의\d+)?))?")
JO = re.compile(r"(제\d+조(?:의\d+)?)(?:\s*(제\d+항|[①-⑳]))?(?:\s*(제\d+호(?:의\d+)?))?")
# 법령명 뒤에 '및'·'·'·'부터' 등으로 이어진 조문은 앞 법령명을 이어받는다('소득세법 제45조 및 제46조')
CHAIN = re.compile(r"^(?:\s*(?:제\d+항|[①-⑳]|제\d+호(?:의\d+)?|[가-힣]목))*\s*(?:및|또는|와|과|,|·|ㆍ|~|부터|내지)\s*$")
# 판결·결정을 가리키는데 번호를 못 읽은 곳: 법원·심판 이름 뒤 40자 안에 숫자가 있으면 인용으로 본다
CUE = re.compile(r"(?<![가-힣])(?:대법원|[가-힣]{2,10}법원|조세심판원|조심|국심|감심)")


def _year4(y):
    return y if len(y) == 4 else ("19" + y if int(y) >= 50 else "20" + y)


def _key(t):
    """문서번호 비교 열쇠 — 구분자·연도 자릿수('88'↔'1988')·일련번호 앞 0('0164'↔'164') 차이를 무시."""
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", re.sub(r"\(\d{4}\.[^)]*\)$", "", (t or "").strip()))
    m = re.fullmatch(r"([가-힣]+?)((?:19|20)?\d{2})([가-힣]{1,3})(\d+)", s)
    return f"{m.group(1)}{_year4(m.group(2))}{m.group(3)}{int(m.group(4))}" if m else s


def _check_doc(raw):
    try: hits = ntis._search(raw, ("해석", "판례"), None, "정확도", 5)   # 번호 조회는 재정렬 없이
    except net.Unreachable as e: return {"인용": raw, "결과": "조회 실패", "이유": e.short, "_net": str(e)}
    except Exception as e: return {"인용": raw, "결과": "조회 실패", "이유": str(e)[:80]}
    k = _key(raw)
    m = next((h for h in hits if _key(h["문서번호"]) == k), None)
    if m: return {"인용": raw, "결과": "확인", "문서번호": m["문서번호"], "제목": m.get("제목", ""), "일자": m.get("일자", ""), "링크": m.get("링크", "")}
    kind = "형사·민사 판결 등은 국세청 DB에 없을 수 있음" if re.search(r"\d{2}[도노고]\d", raw) else "번호 오기 또는 존재하지 않는 문서 가능성"
    return {"인용": raw, "결과": "국세청 DB 미확인", "이유": kind, "비슷한 번호": [h["문서번호"] for h in hits[:3]]}


def _docs(text):
    """→ (조회할 문서번호 목록, 읽은 구간 목록)."""
    found, spans = [], []
    for m in COURT.finditer(text):
        court = re.sub(r"\s+", "", m.group(1))
        found.append((m.start(), f"{court} {m.group(2)}{m.group(3)}{m.group(4)}")); spans.append(m.span())
    for m in TRIB.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in spans): continue
        found.append((m.start(), f"{m.group(1)} {m.group(2)}{m.group(3)}{m.group(4)}")); spans.append(m.span())
    for m in DOC.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in spans): continue
        found.append((m.start(), m.group(0).strip())); spans.append(m.span())
    found.sort()
    return list(dict.fromkeys(x for _, x in found)), spans


def _laws(text):
    """→ ([(법령명, 조, 항, 호)], 읽은 구간, [법령명 없는 조문 인용])."""
    refs, spans = [], []
    for m in LAWREF.finditer(text):
        refs.append((m.start(), (m.group(1).strip(), m.group(2), m.group(3) or "", m.group(4) or ""))); spans.append(m.span())
    unknown = []
    for m in JO.finditer(text):
        if any(a <= m.start() < b for a, b in spans): continue
        prev = max((s for s in spans if s[1] <= m.start()), key=lambda s: s[1], default=None)
        owner = next((r for st, r in refs if prev and st == prev[0]), None)
        if prev and owner and CHAIN.match(text[prev[1]:m.start()]):
            refs.append((m.start(), (owner[0], m.group(1), m.group(2) or "", m.group(3) or ""))); spans.append((prev[0], m.end()))
            refs.sort(key=lambda x: x[0])
            continue
        words = text[max(0, m.start() - 20):m.start()].split()[-2:]
        while words and re.search(r"\d조", words[0]): words = words[1:]   # 앞 인용('제5조와')은 빼고 바로 앞 말만
        unknown.append(" ".join(words + [m.group(0)]))
    refs.sort(key=lambda x: x[0])
    return list(dict.fromkeys(r for _, r in refs)), spans, unknown


def _hang_no(h):
    if not h: return None
    if law.hang_num(h): return f"제{law.hang_num(h)}항"
    return h


def _locate(body, hang, ho):
    """조 본문에 인용한 항·호가 있는지 → (있음 여부, 없을 때 결과 라벨)."""
    hang = _hang_no(hang)
    scope = body
    if hang:
        scope = law._pick_paragraph(body, hang)
        if not scope: return False, "항 없음"
    if ho:
        want = law._ho_tuple(ho)
        for ln in scope.split("\n"):
            m = law._HO_LINE.match(ln.lstrip())
            if m and (int(m.group(1)), int(m.group(2) or 0)) == want: return True, ""
        return False, "호 없음"
    return True, ""


def _fetch(name, art, as_of):
    try: return law.article(name.strip(), art, as_of)
    except Exception as e: return {"_exc": e}


def _check_law(ref, got):
    name, art, hang, ho = ref
    label = " ".join(x for x in (name, art, hang, ho) if x)
    e = got.get("_exc")
    if isinstance(e, law.NoKey): return {"인용": label, "결과": "미검증", "이유": "LAW_OC 없음"}
    if isinstance(e, net.Unreachable): return {"인용": label, "결과": "조회 실패", "이유": e.short, "_net": str(e)}
    if e is not None: return {"인용": label, "결과": "조회 실패", "이유": _mask_oc(str(e))[:80]}
    if got.get("error"): return {"인용": label, "결과": "법령명 미확인", "이유": _mask_oc(got["error"])}
    ok = got.get("본문") and not got["본문"].startswith("조문 없음")
    out = {"인용": label, "결과": "확인" if ok else "조문 없음", "적용 시행일": got.get("적용 시행일")}
    if ok and (hang or ho):
        found, why = _locate(got["본문"], hang, ho)
        if not found:
            out["결과"] = why
            out["이유"] = f"{art}는 있으나 {why.split()[0]}({' '.join(x for x in (hang, ho) if x)})이 기준일 시행본에 없음"
    for k in ("법령명 안내", "법령명 경고"):
        if got.get(k): out[k] = got[k]
    return out


def verify(text, as_of=""):
    text = text or ""
    docs, doc_spans = _docs(text)
    laws, law_spans, unknown_jo = _laws(text)

    # 번호를 못 읽은 판결·결정 언급(법원·심판 이름 뒤 40자 안에 숫자, 읽은 구간 밖)
    unparsed = []
    taken = []
    for m in CUE.finditer(text):
        if any(a <= m.start() < b for a, b in doc_spans + taken): continue
        nxt = min([a for a, _ in doc_spans if a >= m.end()] + [m.end() + 40])   # 다음에 읽은 번호 앞까지만
        tail = re.split(r"[\n。;]|(?<=[가-힣])\.(?:\s|$)", text[m.end():nxt])[0]
        if not re.search(r"\d", tail): continue
        seg = (m.group(0) + tail).strip()
        cut = re.search(r"(판결|결정)", seg)
        seg = seg[:cut.end()] if cut else seg
        unparsed.append({"인용": seg, "결과": "형식 미인식", "이유": "문서번호(사건번호)를 읽지 못함 — 번호를 '대법원 2016두59188'·'조심 2015전1925'처럼 적어 다시 검증"})
        taken.append((m.start(), m.end() + len(tail)))
    for s in dict.fromkeys(unknown_jo):
        unparsed.append({"인용": s, "결과": "형식 미인식", "이유": "법령명이 없거나 줄임말('같은 법'·'영' 등)이라 조문을 특정하지 못함 — 정식 법령명을 붙여 다시 검증"})

    with ThreadPoolExecutor(4) as ex:   # net.submit: 작업 스레드에도 시간 예산을 넘김
        d = [f.result() for f in [net.submit(ex, _check_doc, x) for x in docs[:MAX]]]
        # 같은 법령·같은 조는 한 번만 받는다 — 연혁 목록(법령마다 여러 쪽)을 인용마다 동시에 다시 받던 문제
        names = list(dict.fromkeys(r[0].strip() for r in laws[:MAX]))
        try: [f.result() for f in [net.submit(ex, law._versions, x) for x in names]]
        except Exception: pass   # 오류는 아래 조문 조회에서 인용별로 보고
        uniq = list(dict.fromkeys((r[0], r[1]) for r in laws[:MAX]))
        got = dict(zip(uniq, [f.result() for f in [net.submit(ex, _fetch, x[0], x[1], as_of) for x in uniq]]))
    l = [_check_law(r, got[(r[0], r[1])]) for r in laws[:MAX]]

    items = d + l + unparsed
    # 사이트 연결 실패는 인용마다 짧게, 무엇을 할지는 한 번만
    net_msgs = list(dict.fromkeys(x.pop("_net") for x in d + l if "_net" in x))
    ok = sum(1 for x in items if x["결과"] == "확인")
    nv = sum(1 for x in items if x["결과"] == "미검증")
    out = {"문서번호": d, "조문": l}
    if unparsed: out["형식 미인식"] = unparsed
    s = f"문서 {len(d)}건·조문 {len(l)}건·형식 미인식 {len(unparsed)}건 중 확인 안 된 것 {len(items) - ok}건"
    if nv: s += f"(미검증 {nv}건 — LAW_OC 없음)"
    if not items and text.strip(): s = "인용(문서번호·조문)을 하나도 찾지 못함 — 확인된 것 없음"
    out["요약"] = s
    skipped = max(0, len(docs) - MAX) + max(0, len(laws) - MAX)
    if skipped: out["생략"] = f"상한({MAX}건/종류) 초과로 {skipped}건 확인 안 함 — 나눠서 다시 검증"
    if net_msgs: out["연결 안내"] = " / ".join(net_msgs)
    out["주의"] = "확인은 '존재'만 뜻함 — 인용한 내용이 그 문서·조문의 내용과 맞는지는 본문으로 확인"
    return out
