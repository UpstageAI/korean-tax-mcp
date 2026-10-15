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
_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(개월|회|년|월|일|배|퍼센트|%)" + _QUAL)
_WON_RE = re.compile(r"(\d[\d,]*)\s*(천만원|백만원|만원|억원|원)" + _QUAL)
_FRAC_RE = re.compile(r"(100|1만|1천|10)분의\s*(\d+)")


def _numbers(text: str) -> list[tuple[float, str, str, str]]:
    """(정규화 값, 단위, 원문 문구, 표기형). 금액은 원으로, 100분의 N·N퍼센트·1만분의 N은 %로.
    표기형(frac/pct/won/…)이 같은 것끼리 먼저 짝지어 '100분의 20'을 '0.3퍼센트'와 비교하는 일을 막는다. 소수점 지원 (Claude 2026-10-15)."""
    out = []
    for m in _NUM_RE.finditer(text):
        unit = "%" if m.group(2) in ("퍼센트", "%") else m.group(2)
        out.append((float(m.group(1).replace(",", "")), unit, m.group(0).strip(), "pct" if unit == "%" else unit))
    for m in _WON_RE.finditer(text):
        out.append((float(m.group(1).replace(",", "")) * _WON[m.group(2)], "원", m.group(0).strip(), "won"))
    for m in _FRAC_RE.finditer(text):
        base = {"100": 100.0, "1만": 10000.0, "1천": 1000.0, "10": 10.0}[m.group(1)]
        out.append((float(m.group(2)) * 100.0 / base, "%", m.group(0), "frac"))
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
    for val, unit, phrase, fmt in _numbers(stmt):
        same = [n for n in law_nums if n[1] == unit and n[3] == fmt] or [n for n in law_nums if n[1] == unit]   # 같은 표기형 우선
        if same and not any(abs(n[0] - val) < 1e-9 for n in same):
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
_PARTICLE = re.compile(r"(으로|에서|에게|까지|부터|이나|이든|은|는|이|가|을|를|의|에|도|만|와|과|로)$")


def _content_tokens(text: str) -> set[str]:
    """진술의 한글 내용어(조사 제거, 2자 이상). 주제 공유 판단용."""
    out = set()
    for tok in re.findall(r"[가-힣]{2,}", text):
        tok = _PARTICLE.sub("", tok)
        if len(tok) >= 2:
            out.add(tok)
    return out


def _shares_rare_topic(statement: str, unit_text: str, all_texts: list[str]) -> bool:
    """진술과 단위 원문이 '드문' 내용어(전체 단위의 40% 이하에만 나오는 말)를 하나 이상 공유하는지.
    예: '경조금'은 공유하면 같은 얘기, '기업업무추진비'처럼 어디에나 있는 말은 근거가 못 됨 (Claude 2026-10-15)."""
    n = max(1, len(all_texts))
    for tok in _content_tokens(statement):
        if tok in unit_text:
            df = sum(1 for t in all_texts if tok in t)
            if df / n <= 0.4:
                return True
    return False


# ── 구절 차이 ────────────────────────────────────────────────────────────────
# 숫자·양태·반대말·시점 신호만으로는 낱말이 바뀌거나(확정일 ↔ 압류등기일) 두 구절 자리가 뒤바뀐 진술
# (환입된 날 ↔ 처음 공급한 날)을 못 잡아 '차이 없음'이 나가던 문제 — 진술과 원문 문장을 어절 단위로 맞대어
# 서로 다른 구절을 원문 그대로 보여 준다 (Claude 2026-10-15)
_TOK = re.compile(r"[^\s,.;:·ㆍ「」『』｢｣\[\]]+")
_BOILER = re.compile(r"^(?:다만|이 경우|이경우|불구하고|다음 각 호|다음 각 목|이하|해당|각 호 외의 부분|같은|그|이)$")
_PAREN = re.compile(r"\([^)]*\)")
_ENDING = re.compile(r"(한다|하다|된다|이다|한|된|하는|되는|하여|되어|하고|되고|할|될|함|됨|하며|이며)$")
_REF_ONLY = re.compile(r"^(?:제\d+조(?:의\d+)?|제\d+항|제\d+호|[가-하]목|및|또는|같은|이|그|법|영|각|호|목)+$")


def _norm_tok(t: str) -> str:
    t = re.sub(r"^[①-⑳]+", "", t)
    t = _PAREN.sub("", t)
    t = re.sub(r"[()\[\]\"'“”‘’]", "", t)
    t = re.sub(r"(에는|에서는|으로는|로는|에게는|에도|에만|이라|라는|이란|란)$", "", t) if len(t) > 3 else t
    t = _PARTICLE.sub("", t) if len(t) > 2 else t
    return t


def _toks(text: str) -> list[tuple[str, int, int]]:
    """(정규화 어절, 시작, 끝) — 시작·끝은 원문 위치라 원문 부분 문자열을 그대로 꺼낼 수 있음.
    괄호 안(정의·인용 조문)의 어절과 '다만'·'불구하고' 같은 연결어는 대조에서 뺌."""
    depth, inside = 0, [False] * (len(text) + 1)
    for i, ch in enumerate(text):
        if ch == "(": depth += 1
        inside[i] = depth > 0
        if ch == ")" and depth: depth -= 1
    out = []
    for m in _TOK.finditer(text):
        if inside[m.start()] and inside[max(m.end() - 1, m.start())]:
            continue
        raw = "".join(ch for k, ch in enumerate(m.group(0), m.start()) if not inside[k] and ch not in "()")
        n = _norm_tok(raw)
        if _BOILER.match(n) or n in ("불구하고", "다만"):
            continue
        if n and not re.fullmatch(r"\d+\.?|[가-하]\.|[①-⑳]", n):
            out.append((n, m.start(), m.end()))
    return out


def _trivial(a: list[str], b: list[str]) -> bool:
    """어미·조사만 다른 차이, 조문 번호 표기만 다른 차이는 무시."""
    sa = "".join(_ENDING.sub("", x) for x in a)
    sb = "".join(_ENDING.sub("", x) for x in b)
    if sa == sb or not sa or not sb or sa in sb or sb in sa:      # 띄어쓰기·'그' 따위만 다른 차이(그기간은 ↔ 기간은)
        return True
    if b and re.match(r"제\d+(?:조|항|호)", b[0]) and len(b) <= 5:
        # 원문 '제1항에 따른 신청을 할' ↔ 진술이 그 신청 내용을 풀어 씀 — 지시어 뒤 낱말이 진술에 다 있으면 같은 말
        rest = [_ENDING.sub("", x) for x in b[1:] if x not in ("따른", "따라", "규정", "규정에")]
        rest = [x for x in rest if x]
        ka2 = [_ENDING.sub("", x) for x in a]
        if rest and all(any(k in y or y in k for y in ka2 if y) for k in rest):
            return True
    tiny = {"날", "경우", "때", "것", "가", "자", "등", "말", "말한"}
    if set(a) <= tiny or set(b) <= tiny:                          # 한쪽이 '날'·'경우' 한 낱말뿐이면 정렬 잔여물
        return True
    if _REF_ONLY.match("".join(b)) or _REF_ONLY.match("".join(a)):
        return True
    ka = {_ENDING.sub("", x) for x in a} - {""}; kb = {_ENDING.sub("", x) for x in b} - {""}
    if ka <= kb or kb <= ka:                  # 한쪽이 낱말을 더 붙였을 뿐(수정세금계산서를 발급 ↔ 발급)
        return True
    if all(re.fullmatch(r"(?:제\d+(?:조|항|호)(?:의\d+)?)+(?:에도|에|의|에서|에따른|따른|따라)?", x) or x in ("따른", "따라", "규정", "규정에") for x in b):
        return True
    generic = {"법령", "법", "관계법령", "관련법령", "규정", "같은법", "이법", "세법"}
    ref_like = lambda xs: any(re.search(r"제\d+조", x) or x.endswith("법」") or x.endswith("법") for x in xs)
    if (ka <= generic and ref_like(b)) or (kb <= generic and ref_like(a)):   # 법령 ↔ 국세징수법 제13조
        return True
    return False


def _phrase_diffs(stmt: str, ref_sentence: str, limit: int = 4) -> list[dict]:
    import difflib
    stmt = re.sub(r"(?<=[가-힣])\s*\n\s*(?=[가-힣])", "", stmt)     # 시험지 줄바꿈으로 끊긴 낱말('대하\n여') 잇기
    st, rt = _toks(stmt), _toks(ref_sentence)
    if not st or not rt:
        return []
    sm = difflib.SequenceMatcher(a=[t[0] for t in st], b=[t[0] for t in rt], autojunk=False)
    if sm.ratio() < 0.3:                      # 서로 다른 얘기면 구절 대조가 의미 없음
        return []
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace" or (i2 - i1) > 8 or (j2 - j1) > 10:
            continue
        a = [t[0] for t in st[i1:i2]]; b = [t[0] for t in rt[j1:j2]]
        if _trivial(a, b):
            continue
        out.append({"종류": "구절", "진술": stmt[st[i1][1]:st[i2 - 1][2]],
                    "조문": ref_sentence[rt[j1][1]:rt[j2 - 1][2]]})
        if len(out) >= limit:
            break
    return out


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
    diffs: list[dict] = []
    if not signals:
        for s_, bi in zip(sents, best):
            cs = _best_sentence(s_, contexts[bi])
            for d in _phrase_diffs(s_, cs):
                loc_i = bi if d["조문"] in units[bi][3] else _parent(units, bi)
                if loc_i is None or d["조문"] not in units[loc_i][3]:
                    continue
                d["위치"] = _location(units[loc_i])
                diffs.append(d)
    if signals:
        verdict = "모순"
    elif overlap_val >= 0.5:
        verdict = "구절 다름" if diffs else "차이 없음"
    else:
        verdict = "판단 필요"
    out = {"판정": verdict, "근거": {"위치": _location(ref), "원문": ref[3]}, "대조": signals + diffs,
           "단서": _provisos(ref[3], statement), "겹침": overlap_val}
    if verdict == "구절 다름":
        out["안내"] = "숫자·양태 신호는 없지만 진술과 원문 구절이 다름 — '대조'의 진술·조문 구절을 비교해 같은 뜻인지 판단"
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
        units_here = dict(jo_candidates)[best_jo]
        all_texts = [u[3] for u in units_here]
        ref_text = (best_result.get("근거") or {}).get("원문", "")
        same_topic = _shares_rare_topic(stmt["text"], ref_text, all_texts)
        if best_overlap < 0.3 and best_result["판정"] == "모순":
            # 겹침은 낮아도 숫자·반대말·양태 신호가 있고 드문 내용어(예: 경조금)를 공유하면 같은 얘기 → 모순 유지 (Claude 2026-10-15)
            if not same_topic:
                res["판정"] = "판단 필요"
                res["사유"] = "겹침 낮음 — 다른 조문일 수 있음"
        elif best_result["판정"] == "판단 필요":
            # 신호 없음 + 진술의 숫자를 전부 담은 단위가 이 조에 있고 그 단위와 드문 내용어를 공유 → 차이 없음, 근거를 그 단위로 (숫자 일치는 강한 증거)
            phrases = [n[2] for n in _numbers(stmt["text"])]
            if phrases:
                for u in units_here:
                    if all(ph in u[3] for ph in phrases) and _shares_rare_topic(stmt["text"], u[3], all_texts):
                        res["판정"] = "차이 없음"
                        res["사유"] = "진술의 숫자가 근거 원문과 일치"
                        res["근거"] = {"위치": _location(u), "원문": u[3]}
                        break
        results.append(res)

    summary = {"모순": [], "구절 다름": [], "차이 없음": [], "판단 필요": []}
    for res in results:
        summary[res["판정"]].append(res["id"])
    return {"보기별": results, "요약": summary,
            "주의": "글자 대조 결과 — 법적 판단은 원문으로 확인. '판단 필요'는 준 조문과 겹침이 낮은 보기(다른 조문일 수 있음)"}
