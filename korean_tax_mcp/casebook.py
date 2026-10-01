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


def search(query, area=None, k=5):
    cases, docs, df, avg = _load(); N = len(cases); q = Counter(_grams(query)); out = []
    for c, d in zip(cases, docs):
        if area and c["분야"] != area: continue
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
