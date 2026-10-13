"""주장 대조(verify_statement) — 진술과 조문 원문을 글자 수준에서 대조.

순수 함수, 네트워크·LLM 없음. 돌려주는 조문 문구는 전부 시행본 원문의 부분 문자열(지어내지 않음).
Claude 작성 2026-10-13 (Solar 초안을 구조 단순화해 재작성: 주제 가중 선택, 신호별 위치, 부모 단위 승격).

흐름: 진술 문장 분리 → 조의 각 단위(조·항·호·목)에 문맥원문(호·목이면 머리글+호) → idf 가중 3-gram 겹침으로
문장마다 근거 단위 선택(진술 주제부 2배 가중) → 숫자·양태·반대말·시점 신호 → 단서 → 판정.
"""
from __future__ import annotations

import math
import re

Unit = tuple[str, str, str, str]          # (조, 항, 호, 원문) — law._full_units 형식

# ── 문장·n-gram ────────────────────────────────────────────────────────────────
_SENT_SPLIT = re.compile(r"(?<=다\.)\s+|(?<=다\.)(?=[^\s])")
_STRIP = re.compile(r"[\s,.;:!?\"'()\[\]{}<>\-_~@#$%^&*+=|\\/·ㆍ「」『』]")
_TOPIC = re.compile(r"^(.{4,}?)(?:은|는)\s")


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(re.sub(r"<[^>]*>", "", text)) if p and p.strip()]
    return parts or [text.strip()]


def _grams(text: str, n: int = 3) -> list[str]:
    s = _STRIP.sub("", text)
    return [s[i:i + n] for i in range(len(s) - n + 1)]


def _context(units: list[Unit], i: int) -> str:
    """호·목 단위의 문맥원문 = 그 항(항이 없으면 조) 머리글 + ' ' + 호 원문. 항·조 머리글은 자신."""
    jo, hang, ho, text = units[i]
    if not ho:
        return text
    head = _parent(units, i)
    return f"{units[head][3]} {text}" if head is not None and head != i else text


def _parent(units: list[Unit], i: int) -> int | None:
    """호·목 단위의 머리글 단위(같은 조·항의 호 없는 단위; 항이 없으면 조 머리글)."""
    jo, hang, ho, _ = units[i]
    if not ho:
        return None
    for j, (j_jo, j_hang, j_ho, _) in enumerate(units):
        if j_jo == jo and j_hang == hang and not j_ho:
            return j
    return None


def _location(u: Unit) -> str:
    jo, hang, ho, _ = u
    parts = [jo] + ([hang] if hang else []) + ([ho.rstrip(".") + "호"] if ho else [])
    return " ".join(parts)


# ── 숫자 ───────────────────────────────────────────────────────────────────────
_WON = {"천만원": 10_000_000, "백만원": 1_000_000, "만원": 10_000, "억원": 100_000_000, "원": 1}
_QUAL = r"(?:\s*(?:이상|이하|이내|미만|초과))?"
_NUM_RE = re.compile(r"(\d[\d,]*)\s*(개월|회|년|월|일|배|퍼센트|%)" + _QUAL)
_WON_RE = re.compile(r"(\d[\d,]*)\s*(천만원|백만원|만원|억원|원)" + _QUAL)
_FRAC_RE = re.compile(r"100분의\s*(\d+)")


def _numbers(text: str) -> list[tuple[int, str, str]]:
    """(정규화 값, 단위, 원문 문구). 금액은 원으로, 100분의 N·N퍼센트는 %로."""
    out = []
    for m in _NUM_RE.finditer(text):
        unit = "%" if m.group(2) in ("퍼센트", "%") else m.group(2)
        out.append((int(m.group(1).replace(",", "")), unit, m.group(0).strip()))
    for m in _WON_RE.finditer(text):
        out.append((int(m.group(1).replace(",", "")) * _WON[m.group(2)], "원", m.group(0).strip()))
    for m in _FRAC_RE.finditer(text):
        out.append((int(m.group(1)), "%", m.group(0)))
    return out


# ── 양태 ───────────────────────────────────────────────────────────────────────
_MODALITY = [  # (분류, 문장 끝 패턴) — 앞에서부터 먼저 맞는 것
    ("부정", re.compile(r"(하지\s*못한다|할\s*수\s*없다|아니\s*된다|하지\s*아니한다|되지\s*아니한다|지\s*아니한다|지\s*않는다|않는다|제외한다|없다)\s*$")),
    ("재량", re.compile(r"(할\s*수\s*있다|수\s*있다)\s*$")),
    ("의무", re.compile(r"(하여야\s*한다|해야\s*한다|여야\s*한다|하여야\s*하며)\s*$")),
]
_AUX_TAIL = re.compile(r"(지\s*(?:못한다|아니한다|않는다)|할\s*수\s*(?:있다|없다)|수\s*(?:있다|없다)|아니\s*된다|(?:하여야|해야|여야)\s*한다|한다|된다|이다|다)\s*$")


def _modality(sentence: str) -> tuple[str, str]:
    """(분류, 술어 문구). 문장 끝 기준."""
    s = re.sub(r"[\s.]+$", "", sentence)
    s = re.sub(r"<[^>]*>$", "", s).rstrip(" .")
    for label, pat in _MODALITY:
        m = pat.search(s)
        if m:
            start = max(0, m.start() - 6)
            return label, s[start:].strip()
    tail = s.split()[-1] if s.split() else s
    return "서술", tail


def _stem(sentence: str) -> str:
    """술어 어간: 보조 용언·어미를 떼고 남은 마지막 어절의 앞부분."""
    s = re.sub(r"[\s.]+$", "", sentence)
    s = _AUX_TAIL.sub("", s).rstrip()
    last = s.split()[-1] if s.split() else s
    return last


def _drop_n(stem: str) -> str:
    """어간 끝 글자의 ㄴ받침 제거(본→보, 한→하, 된→되) — '본다'와 '보지 않는다'를 같은 어간으로."""
    if not stem:
        return stem
    code = ord(stem[-1]) - 0xAC00
    if 0 <= code < 11172 and code % 28 == 4:
        return stem[:-1] + chr(0xAC00 + code - 4)
    return stem


def _same_stem(a: str, b: str) -> bool:
    sa, sb = _drop_n(_stem(a)), _drop_n(_stem(b))
    if not sa or not sb:
        return False
    if len(sa) == 1 or len(sb) == 1:
        return sa == sb
    return sa[:2] == sb[:2] or sa.startswith(sb) or sb.startswith(sa)


# ── 반대말·시점 ────────────────────────────────────────────────────────────────
_ANTONYMS = [("증액", "감액"), ("합산", "구분"), ("이상", "초과"), ("이하", "미만"), ("포함", "제외"), ("가산", "차감"),
             ("직접", "간접"), ("거주자", "비거주자"), ("내국법인", "외국법인"), ("과세", "비과세"), ("익금", "손금"),
             ("상속", "증여"), ("유보", "사외유출"), ("본다", "보지 아니한다")]
_TIME_RE = re.compile(r"((?:[가-힣]+\s)?[가-힣]*(?:하는|되는|끝나는|개시되는|취득하는|작성한|확정되는|성립하는|지급하는|발생한))\s*때")


def _has(text: str, word: str, other: str) -> bool:
    """word가 text에 있는지 — other(긴 쪽)에 포함된 형태는 제외 (비거주자 안의 거주자)."""
    if other.endswith(word) and len(other) > len(word):
        return word in text.replace(other, "")
    return word in text


def _best_sentence(stmt: str, context: str) -> str:
    cs = _sentences(context)
    sg = set(_grams(stmt))
    return max(cs, key=lambda c: len(sg & set(_grams(c))) / max(len(sg), 1))


def _signals(stmt: str, context: str) -> list[dict]:
    out: list[dict] = []
    # 숫자: 문맥원문 전체
    law_nums = _numbers(context)
    for val, unit, phrase in _numbers(stmt):
        same = [n for n in law_nums if n[1] == unit]
        if same and not any(n[0] == val for n in same):
            out.append({"종류": "숫자", "진술": phrase, "조문": same[0][2]})
    # 양태: 가장 겹치는 조문 문장과 비교, 같은 어간일 때만
    cs = _best_sentence(stmt, context)
    sm, sp = _modality(stmt)
    lm, lp = _modality(cs)
    if sm != lm and _same_stem(stmt, cs):
        out.append({"종류": "양태", "진술": sp, "조문": lp})
    # 반대말: 진술에 A, 조문 문장에 B (양방향)
    for a, b in _ANTONYMS:
        for x, y in ((a, b), (b, a)):
            if _has(stmt, x, y) and not _has(stmt, y, x) and _has(cs, y, x) and not _has(cs, x, y):
                out.append({"종류": "반대말", "진술": x, "조문": y})
                break
    # 시점: 때-구절
    st = [m.group(0) for m in _TIME_RE.finditer(stmt)]
    lt = [m.group(0) for m in _TIME_RE.finditer(context)]
    if st and lt and not any(_STRIP.sub("", s) in {_STRIP.sub("", l) for l in lt} for s in st):
        out.append({"종류": "시점", "진술": st[0], "조문": lt[0]})
    return out


def _provisos(ref: str, statement: str) -> list[str]:
    if any(k in statement for k in ("다만", "제외", "그러하지")):
        return []
    return [s for s in _sentences(ref) if "다만" in s or "제외한다" in s or "그러하지 아니하다" in s]


# ── 공개 API ───────────────────────────────────────────────────────────────────
def compare(statement: str, units: list[Unit]) -> dict:
    """진술과 한 조의 단위 목록을 대조.

    반환 {"판정", "근거": {"위치", "원문"}, "대조": [{"종류", "진술", "조문", "위치"}], "단서": [...], "겹침"}
    - 근거 원문·대조의 조문 문구·단서는 모두 시행본 원문의 부분 문자열
    - 판정: 신호 있으면 '모순', 없고 겹침 ≥ 0.5 '차이 없음', 아니면 '판단 필요'
    """
    if not units:
        return {"error": "조문 단위가 없음"}
    sents = _sentences(statement)
    contexts = [_context(units, i) for i in range(len(units))]
    ctx_grams = [set(_grams(c)) for c in contexts]
    n = len(units)
    df: dict[str, int] = {}
    for gs in ctx_grams:
        for g in gs:
            df[g] = df.get(g, 0) + 1

    def idf(g: str) -> float:
        return math.log(n / df[g]) + 1.0 if g in df else math.log(n) + 2.0   # 어느 단위에도 없는 말은 가장 무겁게(불일치 벌점)

    def overlap(sent: str, i: int) -> float:
        topic = (_TOPIC.match(sent).group(1) if _TOPIC.match(sent) else "")
        topic_g = set(_grams(topic))
        gs = _grams(sent)
        w = {g: (2.0 if g in topic_g else 1.0) for g in set(gs)}           # 주제부(…은/는) 2배 — 같은 '때' 구절보다 누구 얘기인지가 먼저
        num = sum(w[g] * idf(g) for g in w if g in ctx_grams[i])
        den = sum(w[g] * idf(g) for g in w) or 1.0
        return num / den

    best = [max(range(n), key=lambda i: overlap(s, i)) for s in sents]
    signals: list[dict] = []
    for s, bi in zip(sents, best):
        for sig in _signals(s, contexts[bi]):
            loc_i = bi if sig["조문"] in units[bi][3] else _parent(units, bi)   # 문구가 머리글에만 있으면 부모 단위
            if loc_i is None or sig["조문"] not in units[loc_i][3]:
                continue
            sig["위치"] = _location(units[loc_i])
            signals.append(sig)

    ref_i = best[0]
    first_locs = [s["위치"] for s in signals]
    if first_locs and _location(units[ref_i]) not in first_locs:
        p = _parent(units, ref_i)
        if p is not None and _location(units[p]) in first_locs:
            ref_i = p
    ref = units[ref_i]
    all_grams = set().union(*ctx_grams)                                   # 겹침 = 이 조 전체가 진술을 얼마나 덮는지(idf 가중)
    sg = set(_grams(sents[0]))
    overlap_val = round(sum(idf(g) for g in sg if g in all_grams) / (sum(idf(g) for g in sg) or 1.0), 3)
    verdict = "모순" if signals else ("차이 없음" if overlap_val >= 0.5 else "판단 필요")
    out = {"판정": verdict, "근거": {"위치": _location(ref), "원문": ref[3]}, "대조": signals,
           "단서": _provisos(ref[3], statement), "겹침": overlap_val}
    if verdict == "판단 필요":
        out["안내"] = "이 조에서 진술과 겹치는 단위가 적음 — find_article·search로 다른 조문 확인"
    return out


def judge(statements: list[dict], article_units: dict[str, list[Unit]]) -> dict:
    """보기(진술) 여러 개를 조문 1~3개의 단위 목록과 한 번에 대조.

    statements: [{"id": "①", "text": "..."}]  — id는 ①~⑤·ㄱ~ㄹ·1~5 등 그대로
    article_units: {"법령 조": [(조, 항, 호, 원문)...]} — 조마다 law._full_units 형식 단위 목록

    반환 {"보기별": [{id, 조, 판정, 근거:{위치,원문}, 대조, 단서, 겹침, 사유?}],
           "요약": {"모순":[], "차이 없음":[], "판단 필요":[]},
           "주의": "..."}
    """
    if not statements:
        return {"error": "보기가 비어 있음"}
    if not article_units:
        return {"error": "조 단위가 비어 있음"}

    jo_candidates: list[tuple[str, list[Unit]]] = []
    for jo_key, units in article_units.items():
        if units:
            jo_candidates.append((jo_key, units))
    if not jo_candidates:
        return {"error": "조 단위가 비어 있음"}

    results: list[dict] = []
    for stmt in statements:
        best_jo = jo_candidates[0][0]
        best_overlap = -1.0
        best_result: dict = {}
        best_has_signals = False
        for jo_key, units in jo_candidates:
            r = compare(stmt["text"], units)
            ov = r.get("겹침", 0.0)
            has_sig = bool(r.get("대조"))
            if ov > best_overlap or (ov == best_overlap and has_sig and not best_has_signals):
                best_overlap = ov
                best_jo = jo_key
                best_result = r
                best_has_signals = has_sig

        res: dict = {"id": stmt["id"], "조": best_jo,
                     "판정": best_result["판정"],
                     "근거": best_result["근거"],
                     "대조": best_result.get("대조", []),
                     "단서": best_result.get("단서", []),
                     "겹침": best_overlap}
        if best_overlap < 0.3 and best_result["판정"] == "모순":
            res["판정"] = "판단 필요"
            res["사유"] = "겹침 낮음 — 다른 조문일 수 있음"
        results.append(res)

    summary = {"모순": [], "차이 없음": [], "판단 필요": []}
    for res in results:
        summary[res["판정"]].append(res["id"])
    return {"보기별": results, "요약": summary,
            "주의": "글자 대조 결과 — 법적 판단은 원문으로 확인. '판단 필요'는 준 조문과 겹침이 낮은 보기(다른 조문일 수 있음)"}
