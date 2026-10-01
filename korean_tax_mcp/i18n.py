"""영문 결과(lang="en") — 결과 키·상태값을 영어로, 짧은 본문(제목·요지)은 Solar 기계 번역(UPSTAGE_API_KEY 있을 때).

원문이 한국어뿐인 해석·판례·통칙 본문은 번역하지 않고 원문을 둔다(길고, 인용은 원문 기준이어야 하므로).
"""
import json
import os
import re
import ssl
import urllib.request

KEYS = {
    "결과": "results", "주의": "note", "구분": "type", "문서번호": "doc_no", "제목": "title", "요지": "summary", "세목": "tax",
    "일자": "date", "링크": "url", "전체건수": "total", "등록일": "registered", "관련조문": "cited_statutes", "본문": "text",
    "법령": "law", "조": "article", "기준": "edition", "통칙": "rule", "항목": "item", "쪽": "page", "적용 시행일": "effective_date",
    "위임체계": "delegation_chain", "단계": "level", "기본통칙": "basic_rules", "집행기준": "execution_standards", "해석": "rulings",
    "관계": "relation", "이유": "reason", "사실관계 차이": "fact_differences", "요약": "summary", "기준일": "base_date",
    "기준일 근거": "base_date_basis", "그 해 조문(3단)": "statutes_at_base_date", "현행과 비교": "vs_current",
    "기준일 시행본": "version_at_base_date", "현행 시행본": "current_version", "조문 변경": "article_changed",
    "해석·판례": "rulings_and_decisions", "기준일 조문과": "vs_base_date_text", "인용": "citation", "비슷한 번호": "similar_numbers",
    "조문": "articles", "국가": "country", "발효일": "in_force_since", "영문 제목": "title_en", "책자": "publication",
    "발간일": "published", "분야": "area", "담당": "department", "발췌": "excerpt", "파일": "file", "점수": "score", "색인": "index",
    "회신일": "reply_date", "쟁점": "issue", "답변요지": "answer", "관련법령": "related_law", "체결국": "treaty_countries",
    "법령명": "law", "검색어": "query", "후보수": "candidates", "id": "id", "error": "error", "번역": "translation",
}
VALUES = {
    "질의회신": "NTS reply", "사전답변": "advance ruling", "과세기준자문": "tax base advisory", "판례": "court decision",
    "심판청구": "Tax Tribunal decision", "이의신청": "objection decision", "심사청구": "NTS review decision", "판례·결정": "decision",
    "법률": "Act", "시행령": "Enforcement Decree", "시행규칙": "Enforcement Rule",
    "확인": "verified", "국세청 DB 미확인": "not found in NTS database", "조회 실패": "lookup failed", "조문 없음": "article not found",
    "미검증": "not verified", "법령명 미확인": "law name not found", "지지": "supports", "반대": "contradicts", "구별 필요": "distinguish",
    "같은 시행본": "same version", "등록일 미상": "date unknown", "확인 불가": "cannot check",
    "법인세": "corporate tax", "부가가치세": "VAT", "종합소득세": "income tax", "양도소득세": "capital gains tax",
    "상속증여세": "inheritance & gift tax", "법인": "corporate tax", "부가": "VAT", "소득": "income tax", "양도": "capital gains tax",
    "상증": "inheritance & gift tax", "국기": "Framework Act on National Taxes", "국조": "international tax", "종부": "comprehensive real estate tax",
    "국징": "national tax collection", "조특": "tax incentives", "국세기본": "basic national tax", "국제조세": "international tax", "조세특례": "tax incentives",
}
PATTERNS = [
    (r"^다른 시행본\((\d+)\)이나 이 조 본문 동일$", r"different version (\1), same article text"),
    (r"^조문 개정 후\((\d+)\) — 인용 전 차이 확인$", r"issued after amendment (\1) — check differences before citing"),
    (r"^있음 — 현행 조문을 그대로 적용하면 안 됨$", "changed — do not apply the current text"),
    (r"^없음\(법률 조문 본문 동일\)$", "unchanged (Act article text identical)"),
]
NOTES = {
    "해석·판례는 회신·선고 당시 법 기준 — 적용 연도 조문과 대조": "Rulings reflect the law when issued — compare with the statute in force for the relevant year.",
    "확인은 '존재'만 뜻함 — 인용한 내용이 그 문서·조문의 내용과 맞는지는 본문으로 확인": "'verified' means the item exists — check the text to confirm the cited content.",
}


def _val(v):
    if v in VALUES: return VALUES[v]
    if v in NOTES: return NOTES[v]
    for p, r in PATTERNS:
        if re.match(p, v): return re.sub(p, r, v)
    return v


def localize(obj):
    if isinstance(obj, dict): return {KEYS.get(k, k): localize(v) for k, v in obj.items()}
    if isinstance(obj, list): return [localize(v) for v in obj]
    if isinstance(obj, str): return _val(obj)
    return obj


def translate_short(items, fields=("title", "summary", "issue", "answer", "rule", "item", "excerpt")):
    """결과 안의 짧은 한국어 필드를 Solar로 영어 번역(한 번 호출에 묶음). 키 없으면 그대로."""
    key = os.environ.get("UPSTAGE_API_KEY", "").strip()
    if not key: return False
    slots = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in fields and isinstance(v, str) and re.search(r"[가-힣]", v) and len(v) <= 600: slots.append((o, k))
                else: walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(items)
    if not slots: return True
    src = {str(i): o[k] for i, (o, k) in enumerate(slots[:60])}
    body = {"model": os.environ.get("KOREAN_TAX_MCP_MODEL", "solar-pro4"), "temperature": 0, "max_tokens": 4000,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": "Translate each Korean tax-law string to concise professional English. Keep document numbers and article numbers as is. "
                          "Return JSON with the same keys.\n" + json.dumps(src, ensure_ascii=False)}]}
    ctx = ssl.create_default_context(); ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    try:
        req = urllib.request.Request("https://api.upstage.ai/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
            out = json.loads(json.loads(r.read())["choices"][0]["message"]["content"])
    except Exception:
        return False
    for i, (o, k) in enumerate(slots[:60]):
        t = out.get(str(i))
        if isinstance(t, str) and t.strip(): o[k + "_ko"] = o[k]; o[k] = t.strip()
    return True


def english(result, translate=True):
    r = localize(result)
    if isinstance(r, dict) and "error" not in r:
        done = translate_short(r) if translate else False
        r["language_note"] = ("Titles and summaries machine-translated by Upstage Solar (originals in *_ko); full texts are original Korean."
                              if done else "Source texts are Korean (official). Set UPSTAGE_API_KEY to machine-translate titles and summaries.")
    return r
