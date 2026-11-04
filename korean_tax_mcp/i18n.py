"""영문 결과(lang="en") — 결과 키·상태값을 영어로. 짧은 본문(제목·요지) 번역은 기본적으로 사용자 AI(호스트)가 하고,
Solar 설정(UPSTAGE_API_KEY 또는 온프렘)이 있을 때만 Solar 기계 번역.

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
    "법령명": "law", "제한세율": "withholding_caps", "이름": "name", "시행일": "effective", "공포일": "promulgated", "제개정": "amendment_type",
    "상태": "status", "이 조 변경": "article_change", "연혁": "history", "내용": "content", "세법": "tax_law", "소득": "income", "세율": "rates", "세율(%)": "rate_pct", "근거": "basis",
    "요건·기타": "conditions", "지분요건(%)": "ownership_pct", "기타(%)": "other_pct", "개정 문서 언급": "amending_documents", "검색어": "query", "후보수": "candidates", "id": "id", "error": "error", "번역": "translation", "판단 안내": "host_ai_instructions", "후보": "candidates", "사실관계": "facts", "우리 논리": "our_view",
    "갈린 지점": "deciding_points", "이긴 쪽이 입증한 것": "what_winners_proved", "진 쪽에 부족했던 것": "what_losers_lacked", "안내": "guidance", "발췌 위치": "excerpts_at",
    # 모의 2차(2026-11-04) #34·#35 — lang='en'인데 한국어로 남던 키
    # timing_rules
    "규칙": "rules", "시기": "timing", "예외": "exception", "관련 세목": "related_taxes", "정의": "definition",
    "확인 시행본": "verified_versions", "세목별 건수": "rules_per_tax", "구분 목록": "available_types", "기준일 주의": "as_of_warning",
    # law_article · find_article
    "원문(한국어)": "original_korean", "목차": "toc", "개요": "outline", "이 조가 속한 곳": "located_in", "같은 곳 조문": "sibling_articles",
    "연결": "links", "상위": "upper", "하위": "lower", "참고(공식표만)": "reference_official_table_only", "항": "paragraph", "구절": "phrase",
    "확인": "evidence", "다음 단계": "next_step", "적용 기준일": "as_of_date", "기준일 안내": "as_of_note", "다시 조회": "retry_with",
    "설명": "explanation", "최근 개정": "recent_amendment", "요청 항": "requested_paragraph", "요청 위치": "requested_location",
    "요청 호": "requested_item", "반환 범위": "scope", "항 목록": "paragraph_list", "항 번호": "paragraph_no", "첫 문장": "first_sentence",
    "길이": "length", "잘린 항": "truncated_paragraph", "생략된 항": "omitted_paragraphs", "읽기 주의": "reading_notes", "종류": "kind",
    "원문": "original_text", "위치": "location", "읽기 주의 더 있음": "more_reading_notes", "일치_위치": "match_locations",
    "일치 없음": "no_match", "항_호_목록": "paragraph_item_list", "앞30자": "first_30_chars", "그림": "images",
    "법령명 안내": "law_name_note", "법령명 경고": "law_name_warning", "일치 문장": "matching_sentences", "관련 부칙": "related_addenda",
    "부칙": "addenda",
    # verify_citations · casebook_search
    "형식 미인식": "unrecognized", "생략": "omitted", "사례집에 없는 말": "terms_not_in_casebook",
    # residency_check
    "입력": "input", "법리": "legal_principle", "1단계(소득세법)": "stage1_income_tax_act", "주소 판정": "domicile_judgment",
    "주소 근거 조문": "domicile_article", "주소 판단 근거": "domicile_reason", "거소 판정": "residence_judgment",
    "국내 체류일수": "days_in_korea", "거소 근거 조문": "residence_article", "거소 판단 근거": "residence_reason",
    "파견 특례(§3) 적용": "dispatch_special_rule", "파견 특례 근거": "dispatch_reason", "1단계 종합": "stage1_result",
    "1단계 종합 근거": "stage1_reason", "2단계(이중거주자)": "stage2_dual_residence", "이중거주자 여부": "dual_resident",
    "판단 근거": "reason", "증명책임": "burden_of_proof", "3단계(조세조약 tie-break)": "stage3_treaty_tie_break",
    "조세조약 체결 여부": "treaty_status", "tie-break 적용": "tie_break_applied", "결정 단계": "deciding_step",
    "최종 거주지국": "residence_country", "3단계 근거": "stage3_reason", "조세조약 조문·원문": "treaty_article_text",
    "최종 판정": "final_outcome", "최종 판정 근거": "final_reason", "유사 판례 top3": "similar_cases_top3", "법원": "court",
    "사건번호": "case_no", "선고일": "decision_date", "사건명": "case_name", "결론": "conclusion", "판결요지": "holding",
    "비고": "remarks", "판단이 갈리는 지점·추가 확인 사항": "open_points",
}
# 키가 데이터(법령 조문명·세목)인 표 — 영어 결과에선 [{이름, 값}] 목록으로 바꿔 키를 영어로 둔다
DATA_MAPS = {"확인 시행본": ("provision", "effective_date"), "세목별 건수": ("tax", "count")}
VALUES = {
    "질의회신": "NTS reply", "사전답변": "advance ruling", "과세기준자문": "tax base advisory", "판례": "court decision",
    "심판청구": "Tax Tribunal decision", "이의신청": "objection decision", "심사청구": "NTS review decision", "판례·결정": "decision",
    "별표": "annex", "서식": "form", "바뀜": "changed", "그대로": "unchanged", "현행": "current", "시행예정": "upcoming", "기준": "baseline",
    "배당": "dividends", "이자": "interest", "사용료": "royalties",
    "법률": "Act", "시행령": "Enforcement Decree", "시행규칙": "Enforcement Rule",
    "확인": "verified", "국세청 DB 미확인": "not found in NTS database", "조회 실패": "lookup failed", "조문 없음": "article not found",
    "미검증": "not verified", "법령명 미확인": "law name not found", "지지": "supports", "반대": "contradicts", "구별 필요": "distinguish",
    "같은 시행본": "same version", "등록일 미상": "date unknown", "확인 불가": "cannot check",
    "법인세": "corporate tax", "부가가치세": "VAT", "종합소득세": "income tax", "양도소득세": "capital gains tax",
    "상속증여세": "inheritance & gift tax", "법인": "corporate tax", "부가": "VAT", "소득": "income tax", "양도": "capital gains tax",
    "상증": "inheritance & gift tax", "국기": "Framework Act on National Taxes", "국조": "international tax", "종부": "comprehensive real estate tax",
    "국징": "national tax collection", "조특": "tax incentives", "국세기본": "basic national tax", "국제조세": "international tax", "조세특례": "tax incentives",
    # timing_rules 구분·세목
    "공통": "common", "납세의무 성립": "tax liability established", "손익 귀속": "income/expense attribution",
    "재화 공급시기": "time of supply (goods)", "용역 공급시기": "time of supply (services)", "공급시기 특례": "time of supply (special rules)",
    "사업소득 수입시기": "receipt timing (business income)", "배당소득 수입시기": "receipt timing (dividend income)",
    "이자소득 수입시기": "receipt timing (interest income)", "기타소득 수입시기": "receipt timing (other income)",
    "근로소득 수입시기": "receipt timing (employment income)", "연금소득 수입시기": "receipt timing (pension income)",
    "퇴직소득 수입시기": "receipt timing (retirement income)", "동업기업 소득 수입시기": "receipt timing (partnership income)",
    "귀속연도": "attribution year",
    # verify_citations 결과
    "형식 미인식": "format not recognized", "항 없음": "paragraph not found", "호 없음": "item not found",
    # law_article 연결 근거
    "원문인용": "quoted in text", "공식표": "official table",
    # residency_check 라벨
    "적용": "applied", "미적용": "not applied", "체결(조회 성공)": "treaty in force (looked up)",
    "체결 전제(오프라인 mock)": "treaty assumed (offline mock)", "미체결/확인 필요": "no treaty / to be confirmed",
    "(해당 없음)": "(n/a)", "(조약 정보 없음)": "(no treaty information)",
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
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in DATA_MAPS and isinstance(v, dict):
                a, b = DATA_MAPS[k]
                out[KEYS.get(k, k)] = [{a: localize(x), b: localize(y)} for x, y in v.items()]
            else:
                out[KEYS.get(k, k)] = localize(v)
        return out
    if isinstance(obj, list): return [localize(v) for v in obj]
    if isinstance(obj, str): return _val(obj)
    return obj


def translate_short(items, fields=("title", "summary", "issue", "answer", "rule", "item", "excerpt")):
    """결과 안의 짧은 한국어 필드를 Solar로 영어 번역(한 번 호출에 묶음). 키 없으면 그대로."""
    from . import solar
    if not solar.available(): return False
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
    try:
        out = solar.chat_json("Translate each Korean tax-law string to concise professional English. Keep document numbers and article numbers as is. "
                              "Return JSON with the same keys.\n" + json.dumps(src, ensure_ascii=False), max_tokens=4000)
    except Exception:
        return False
    for i, (o, k) in enumerate(slots[:60]):
        t = out.get(str(i))
        if isinstance(t, str) and t.strip(): o[k + "_ko"] = o[k]; o[k] = t.strip()
    return True


def english(result, translate=True):
    r = localize(result)
    if isinstance(r, dict) and "error" not in r:
        from . import solar
        done = translate_short(r) if translate else False
        if done:
            r["language_note"] = f"Titles and summaries machine-translated by {solar.where('en')} (originals in *_ko); full texts are original Korean."
            r.setdefault("translation_mode", solar.mode())
            if solar.mode() in ("solar_cloud", "solar_onprem"):
                r["AI 생성 표시"] = "Judgments, summaries and translations in this result were written by generative AI (Upstage Solar Pro 4). Check them against the cited sources."
        else:
            r["language_note"] = ("Official English texts (tax treaties, English statutes) are returned as is. Other source texts are original Korean "
                                  "(nothing was sent to Upstage).")
            r["translation_mode"] = "host_ai"
            r["host_ai_translate"] = ("Translate the Korean strings (titles, summaries, issues, answers, excerpts) into English yourself when presenting them. "
                                      "Keep document numbers, article numbers and URLs unchanged; quote the Korean original next to any sentence you rely on; "
                                      "do not add content that is not in the text.")
    return r
