"""국세청 「2025 세법해석 사례집」 96건 색인 — 문서번호·쟁점·결론·분야·쪽(본문은 국세법령정보시스템에서 문서번호로).

검색: 문자 2-gram BM25(외부 호출 없음).
"""
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

IDX = Path(__file__).parent / "data" / "casebook_2025.json"
AREAS = ("법인", "부가", "소득", "상증", "양도", "국기", "국조", "종부")


def _grams(t):
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t or "")
    return [t[i:i + 2] for i in range(len(t) - 1)]


@lru_cache(maxsize=1)
def _load():
    cases = json.loads(IDX.read_text())
    docs = [Counter(_grams(" ".join([c["쟁점"] * 3, c["답변요지"] * 3, c.get("관련법령", "")]))) for c in cases]
    df = Counter(g for d in docs for g in d)
    return cases, docs, df, sum(sum(d.values()) for d in docs) / max(1, len(docs))


_PART = re.compile(r"(에서|으로|에게|의|을|를|이|가|은|는|에|로|과|와)$")
MIN_COVER = 0.5   # 검색어 낱말(희귀할수록 무겁게) 중 이만큼은 사례에 있어야 결과로 낸다


def _words(query):
    out = []
    for w in re.split(r"[\s,·/]+", query or ""):
        w = re.sub(r"[^가-힣A-Za-z0-9]", "", w)
        if len(w) > 2: w = _PART.sub("", w)
        if len(w) >= 2: out.append(w)
    return list(dict.fromkeys(out))


def _has(word, text):
    if word in text: return True
    if len(word) >= 4:   # 긴 합성어는 글자쌍 3/4 이상이 있으면 같은 말로 봄('부당행위계산'↔'부당행위 계산')
        g = [word[i:i + 2] for i in range(len(word) - 1)]
        return sum(x in text for x in g) / len(g) >= 0.75
    return False


@lru_cache(maxsize=1)
def _texts():
    cases = _load()[0]
    return [re.sub(r"[^가-힣A-Za-z0-9]", "", " ".join([c["쟁점"], c["답변요지"], c.get("관련법령", "")])) for c in cases]


def coverage_weights(query):
    """검색어 낱말별 무게 — 사례집에서 드문 말일수록 무겁다. 사례집에 아예 없는 말은 가장 드문 말(1건)과 같은 무게."""
    texts = _texts(); N = len(texts); ws = _words(query)
    df = {w: sum(_has(w, t) for t in texts) for w in ws}
    return {w: math.log(1 + N / (1 + max(1, df[w]))) for w in ws}, [w for w in ws if df[w] == 0]


def search(query, area=None, k=5):
    """글자쌍 BM25로 순위를 매기되, 검색어 낱말(무게 기준) 절반 이상이 들어 있지 않은 사례는 뺀다.
    글자쌍만 맞는 엉뚱한 사례(예: '부당행위 시가 판단 시점' → 월세 세액공제 '기준시가 판단기준')가 상위에 오던 문제(모의 2차 #72)."""
    cases, docs, df, avg = _load(); N = len(cases); q = Counter(_grams(query)); out = []
    wt, _ = coverage_weights(query); total = sum(wt.values()); texts = _texts()
    for c, d, t in zip(cases, docs, texts):
        if area and c["분야"] != area: continue
        if total and sum(v for w, v in wt.items() if _has(w, t)) / total < MIN_COVER - 1e-9: continue
        L = sum(d.values()); s = 0.0
        for g in q:
            if g in d:
                idf = math.log(1 + (N - df[g] + 0.5) / (df[g] + 0.5))
                s += idf * d[g] * 2.2 / (d[g] + 1.2 * (0.25 + 0.75 * L / avg))
        if s > 0: out.append((s, c))
    out.sort(key=lambda x: -x[0])
    return [{**c, "점수": round(s, 2), "인용": cite(c)} for s, c in out[:k]]


def cite(c):
    return f"{c['문서번호']}({c['회신일']}) — {c['쟁점']}: {c['답변요지']} [2025 세법해석 사례집 {c['쪽']}쪽, 회신 당시 법 기준]"
