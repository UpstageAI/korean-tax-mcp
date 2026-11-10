"""2026-11-10 트렌드 시나리오에서 잡힌 결함 3개 — 정답 테스트(수정 금지, Claude 작성).
① verify_statement·judge_options가 괄호 안 제외·포함·한정 단서를 대조 단위로 보지 않아 부가가치세법 제52조제1항의
   "(공급받은 그 용역등을 과세사업에 제공하는 경우는 제외하되, …)"를 놓치고 제2항으로 '판단 필요'를 냈다.
② 진술이 준 법령에 없는 내용(예: 조세특례제한법 제74조 특례)일 때 다른 법령을 찾으라는 안내가 없었다.
③ 지방세(취득세 등) 해석·심판례는 국세법령정보시스템에 거의 없는데 그 사실을 알리지 않았고 조세심판원 결정례를 가져오지도 않았다 — 지방세 불복은
   행정심판법 적용 배제(지방세기본법 제98조제1항)·심판청구 필요적 전치(제3항) → 법제처 특별행정심판재결례(ttSpecialDecc, 재결청 조세심판원)를 같은 키로 조회해 한 번에 돌려준다.
순수 함수 테스트(네트워크 없음). 실행: .venv/bin/python -m pytest tests/test_trend_fixes_1110.py -q
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from korean_tax_mcp import claims       # noqa: E402

FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "paren_proviso_1110.json"), encoding="utf-8"))
U52 = [tuple(u) for u in FX["부가가치세법 제52조"]]


# ── ① 괄호 단서 ──────────────────────────────────────────────────────────────
def test_paren_exclusion_matched_in_paragraph_1():
    r = claims.compare("국외사업자로부터 공급받은 용역등을 과세사업에 제공하는 경우는 대리납부 대상에서 제외한다.", U52)
    assert r["판정"] in ("차이 없음", "구절 다름"), r
    assert r["근거"]["위치"].startswith("제52조 ①"), r["근거"]
    assert "과세사업에 제공하는 경우는 제외" in r["근거"]["원문"]


def test_paren_inclusion_matched_and_wrong_statement_not_clean():
    r = claims.compare("제39조에 따라 매입세액이 공제되지 아니하는 용역등을 공급받는 경우는 대리납부 대상에 포함한다.", U52)
    assert r["판정"] in ("차이 없음", "구절 다름") and r["근거"]["위치"].startswith("제52조 ①"), r
    bad = claims.compare("제39조에 따라 매입세액이 공제되지 아니하는 용역등을 공급받는 경우는 대리납부 대상에서 제외한다.", U52)
    assert bad["판정"] != "차이 없음", bad


def test_paren_unit_text_is_substring_of_statute():
    r = claims.compare("국외사업자로부터 공급받은 용역등을 과세사업에 제공하는 경우는 대리납부 대상에서 제외한다.", U52)
    full = "\n".join(u[3] for u in U52)
    assert r["근거"]["원문"] in full


def test_definition_parentheses_not_promoted():
    """정의 괄호('이하 … 라 한다')는 단위로 올리지 않는다 — 제2항 진술은 여전히 제2항."""
    r = claims.compare("부가가치세를 징수한 자는 부가가치세 대리납부신고서를 제출하고 부가가치세를 납부하여야 한다.", U52)
    assert r["근거"]["위치"].startswith("제52조 ②"), r


# ── ② 다른 법령 안내 ─────────────────────────────────────────────────────────
def test_low_overlap_gets_next_step_find_article():
    r = claims.compare("학교법인은 수익사업에서 발생한 소득의 100분의 100을 고유목적사업준비금으로 손금에 산입할 수 있다.", U52)
    assert r["판정"] == "판단 필요"
    nx = r["다음 단계"]
    assert nx["도구"] == "find_article" and isinstance(nx["keyword"], str) and nx["keyword"].strip()
    assert "조세특례제한법" in nx["안내"] and "find_article" in nx["안내"]


def test_judge_marks_items_needing_other_law():
    stmts = [{"id": "①", "text": "국외사업자로부터 공급받은 용역등을 과세사업에 제공하는 경우는 대리납부 대상에서 제외한다."},
             {"id": "②", "text": "학교법인은 수익사업에서 발생한 소득의 100분의 100을 고유목적사업준비금으로 손금에 산입할 수 있다."}]
    r = claims.judge(stmts, {"부가가치세법 제52조": U52})
    by = {b["id"]: b for b in r["보기별"]}
    assert "다음 단계" not in by["①"] or by["①"]["판정"] == "판단 필요"
    assert by["②"]["판정"] == "판단 필요" and by["②"]["다음 단계"]["도구"] == "find_article"
    assert r["요약"].get("다른 조문 확인") == ["②"]


# ── ③ 지방세 안내 + 조세심판원 재결례(법제처 특별행정심판재결례 ttSpecialDecc) ───────────────
TT = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "tribunal_1110.json"), encoding="utf-8"))


def test_local_tax_note_by_query_and_by_results():
    from korean_tax_mcp import localtax
    n = localtax.local_tax_note("대도시 법인 설립 5년 이내 부동산 취득 취득세 중과", [])
    assert n and "조세심판원" in n and "지방세법령정보시스템" in n and "제98조" in n
    assert localtax.local_tax_note("업무무관 가지급금 인정이자", [{"세목": "법인세"}]) is None
    n2 = localtax.local_tax_note("등록세 중과", [{"세목": "지방세법"}])
    assert n2 and "조세심판원" in n2


def test_tribunal_parse_search_and_detail():
    from korean_tax_mcp import tribunal
    items = tribunal.parse_search(TT["검색"])
    assert len(items) == 8
    first = items[0]
    assert first["구분"] == "조세심판" and first["문서번호"] == "조심 2024지0101" and first["일자"] == "2026.08.19."
    assert first["id"] == "tt:2098157" and first["링크"] == "https://www.law.go.kr/LSW/specialDeccInfoP.do?spDeccSeq=2098157"
    assert first["지방세"] is True and "대도시" in first["제목"]
    assert len(tribunal.parse_search(TT["검색"], local_only=True)) == 8
    assert "OC=" not in json.dumps(items, ensure_ascii=False)
    d = tribunal.parse_detail(TT["상세"])
    assert d["세목"] == "취득" and d["일자"] == "2026.08.19." and d["id"] == "tt:2098157"
    assert d["관련법령"] == ["「지방세법」 제13조", "「지방세법 시행령」 제27조"]
    assert d["참조결정"] == ["조심2021지3246", "조심2018지0421"]
    assert "제13조 제2항" in d["요지"] and d["본문"].startswith("1. 처분개요") and d["주문"].startswith("서울특별시 강남구청장")


def test_search_tax_rulings_appends_tribunal_for_local_tax(monkeypatch):
    """지방세 질의면 한 번의 호출로 조세심판원 결정례까지 — 사용자가 두 번 찾게 하지 않는다."""
    from korean_tax_mcp import server, ntis, law
    monkeypatch.setattr(ntis, "search", lambda *a, **k: [{"구분": "심사청구", "문서번호": "심사감심2000-0029", "제목": "등록세 중과", "요지": "", "세목": "기타", "일자": "2000.02.22.", "id": "x", "링크": ""}])
    calls = []
    def fake_get(path, query):
        calls.append((path, query))
        return TT["검색"] if path == "lawSearch.do" else TT["상세"]
    monkeypatch.setattr(law, "_get", fake_get)
    r = server.search_tax_rulings("대도시 법인 설립 5년 이내 부동산 취득 취득세 중과")
    assert r["결과"][0]["문서번호"] == "심사감심2000-0029"                       # 기존 결과 그대로
    assert [x["문서번호"] for x in r["조세심판원 결정례"]][:2] == ["조심 2024지0101", "조심 2025지2527"]
    assert "조세심판원" in r["지방세 안내"]
    assert any("ttSpecialDecc" in q for _, q in calls)
    # 국세 질의는 조세심판원 조회를 하지 않음
    calls.clear()
    r2 = server.search_tax_rulings("업무무관 가지급금 인정이자")
    assert "조세심판원 결정례" not in r2 and not calls
