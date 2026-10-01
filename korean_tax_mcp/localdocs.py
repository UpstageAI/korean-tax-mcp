"""사용자 PC의 PDF(예: OECD 이전가격 지침) 쪽 단위 검색 — 문서는 저장소에 넣지 않고 각자 받은 파일만 색인.

환경변수 KOREAN_TAX_MCP_DOCS: PDF가 든 폴더. 색인은 ~/.cache/korean-tax-mcp/localdocs.json 에 저장.
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from .ntis import CACHE


def _folder():
    f = os.environ.get("KOREAN_TAX_MCP_DOCS", "").strip()
    if not f: raise RuntimeError("KOREAN_TAX_MCP_DOCS(PDF 폴더 경로)가 없습니다 — 예: OECD 이전가격 지침 PDF를 받은 폴더")
    p = Path(f).expanduser()
    if not p.is_dir(): raise RuntimeError(f"폴더 없음: {p}")
    return p


def _tok(t): return re.findall(r"[A-Za-z]{3,}|[가-힣]{2,}|\d+(?:\.\d+)+", (t or "").lower())


def _index(folder):
    idx_f = CACHE / "localdocs.json"
    pdfs = sorted(folder.glob("**/*.pdf"))
    sig = [[str(p), p.stat().st_mtime] for p in pdfs]
    if idx_f.exists():
        d = json.loads(idx_f.read_text())
        if d.get("sig") == sig: return d["pages"]
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("PDF 읽기 패키지가 없습니다 — uvx --with pypdf korean-tax-mcp 로 실행하거나 pip install pypdf")
    pages = []
    for p in pdfs:
        for i, pg in enumerate(PdfReader(str(p)).pages, 1):
            t = re.sub(r"\s+", " ", pg.extract_text() or "").strip()
            if t: pages.append({"파일": p.name, "쪽": i, "본문": t})
    CACHE.mkdir(parents=True, exist_ok=True); idx_f.write_text(json.dumps({"sig": sig, "pages": pages}, ensure_ascii=False))
    return pages


def search(query, k=5):
    pages = _index(_folder())
    if not pages: return {"결과": [], "주의": "폴더에 PDF가 없거나 글자를 읽을 수 없음(스캔본)"}
    docs = [Counter(_tok(p["본문"])) for p in pages]; df = Counter(w for d in docs for w in d); N = len(docs)
    avg = sum(sum(d.values()) for d in docs) / N; q = _tok(query); out = []
    for p, d in zip(pages, docs):
        L = sum(d.values()); s = sum(math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5)) * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * L / avg)) for w in q if w in d)
        if s > 0: out.append((s, p))
    out.sort(key=lambda x: -x[0])
    res = []
    for s, p in out[:k]:
        t = p["본문"]; i = max(0, min((t.lower().find(w) for w in q if w in t.lower()), default=0) - 150)
        res.append({"파일": p["파일"], "쪽": p["쪽"], "점수": round(s, 2), "발췌": t[i:i + 700]})
    return {"결과": res, "색인": f"{len({p['파일'] for p in pages})}개 파일 · {N}쪽"}
