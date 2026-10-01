"""korean-tax-mcp — 한국 세법 근거 MCP 서버.

국세청 질의회신·과세기준자문·사전답변·판례·조세심판·이의·심사, 국세 기본통칙, 세법집행기준, 세법해석 사례집,
시점별 조문과 법률→시행령→시행규칙 위임 체계를 한곳에서 찾는다.

키 없이: 해석·판례 검색과 본문, 조문별 해석, 기본통칙, 집행기준, 사례집
LAW_OC(법제처, 무료): 시점별 조문·위임 체계
UPSTAGE_API_KEY(Solar): 우리 사실관계와 해석·판례 대조
"""
import json
import os
import re
import ssl
import urllib.request

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from . import casebook, cite, i18n, law, localdocs, ntis, solar, timeline

mcp = MCPServer(
    "korean-tax-mcp", title="Korea Tax Law (한국 세법 근거)",
    instructions="한국 세법 쟁점의 근거(국세청 해석·판례·통칙·집행기준·조문)를 찾는다. search_tax_rulings로 넓게 찾고, get_tax_ruling으로 본문을 읽고, "
                 "조문 단위로는 rulings_by_article·basic_rules·law_article을 쓴다. 특정 사업연도 기준 정리는 research_issue, 초안 검수는 verify_citations, 국제거래는 tax_treaty·search_nts_publications. 문서번호는 결과에 있는 것만 인용하고, "
                 "해석·판례는 회신·선고 당시 법 기준이므로 적용 연도의 조문(law_article as_of)과 대조하라고 안내한다.")

TAXES = tuple(ntis.TAX_CODES)
RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
Tax = Literal["법인", "부가", "소득", "양도", "상증", "국기", "국징", "조특", "국조", "종부"]
Kind = Literal["해석", "판례"]
LAW = "세법 이름(정식 명칭). 예: '법인세법', '부가가치세법', '소득세법', '상속세 및 증여세법', '국세기본법'"
ART = "조문 번호. '제52조' 또는 '제28조의2' 형식"
NTIS_NOTE = "읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시."


def _err(e): return {"error": f"{type(e).__name__}: {e}"}

import contextvars
LANG = contextvars.ContextVar("lang", default="ko")
LangT = Annotated[Literal["ko", "en"], Field(description="Output language. 'en': English keys and labels, official English texts where available "
                                                     "(tax treaties, statutes), titles/summaries machine-translated by Upstage Solar when UPSTAGE_API_KEY is set. 기본 'ko'")]


def bilingual(fn):
    """도구에 lang 파라미터를 붙이고 lang='en'이면 결과를 영어로."""
    import functools, inspect
    sig = inspect.signature(fn)
    params = list(sig.parameters.values()) + [inspect.Parameter("lang", inspect.Parameter.KEYWORD_ONLY, default="ko", annotation=LangT)]

    @functools.wraps(fn)
    def wrapper(*a, lang="ko", **k):
        if lang == "en" and "english" in sig.parameters: k["english"] = True
        tok = LANG.set(lang)
        try: r = fn(*a, **k)
        finally: LANG.reset(tok)
        return i18n.english(r) if lang == "en" else r
    wrapper.__signature__ = sig.replace(parameters=params)
    wrapper.__annotations__ = {**fn.__annotations__, "lang": LangT}
    return wrapper



@mcp.tool(annotations=RO)
@bilingual
def search_tax_rulings(
    query: Annotated[str, Field(description="쟁점 키워드. 예: '업무무관 가지급금 인정이자', '폐업자 세금계산서 매입세액'")],
    tax: Annotated[Tax | None, Field(description="세목 필터. 생략하면 전체")] = None,
    kinds: Annotated[list[Kind] | None, Field(description="해석=질의회신·과세기준자문·사전답변, 판례=법원·조세심판·이의·심사. 생략하면 둘 다")] = None,
    sort: Annotated[Literal["최신", "정확도"], Field(description="최신=등록일 내림차순, 정확도=검색 점수순")] = "최신",
    since: Annotated[str, Field(description="등록일 시작 YYYYMMDD (선택)")] = "",
    until: Annotated[str, Field(description="등록일 끝 YYYYMMDD (선택)")] = "",
    n: Annotated[int, Field(description="종류별 최대 건수 1~30", ge=1, le=30)] = 10,
) -> dict:
    """Search Korean tax rulings and decisions by keyword. 국세청 해석(질의회신·과세기준자문·사전답변)과 판례(법원·조세심판·이의·심사)를 키워드로 찾는다.
    언제: 쟁점은 있는데 조문을 모를 때 첫 단계로. 조문을 알면 rulings_by_article, 사례집 요약만 필요하면 casebook_search.
    반환: {결과: [{구분, 문서번호, 제목, 요지(400자), 세목, 일자, id, 링크}], 주의}. 본문은 get_tax_ruling(id).
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    if tax and tax not in TAXES: return {"error": f"tax는 {TAXES} 중 하나"}
    kinds = tuple(kinds or ["해석", "판례"])
    if any(k not in ntis.KINDS for k in kinds): return {"error": "kinds: 해석 | 판례"}
    if sort not in ("최신", "정확도"): return {"error": "sort: 최신 | 정확도"}
    try:
        return {"결과": ntis.search(query, kinds, tax, sort, max(1, min(int(n), 30)), re.sub(r"\D", "", since), re.sub(r"\D", "", until)),
                "주의": "해석·판례는 회신·선고 당시 법 기준 — 적용 연도 조문과 대조"}
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def get_tax_ruling(id: Annotated[str, Field(description="search_tax_rulings·rulings_by_article 결과의 id (숫자 12~20자리)")]) -> dict:
    """Get the full text of one ruling or decision. 해석·판례 1건의 본문 전문.
    언제: 검색 결과 중 인용·요약할 문서를 정한 뒤. 요지만으로 판단하지 말고 본문을 읽을 때 사용.
    반환: {문서번호, 제목, 요지, 등록일, 관련조문[], 본문(질의회신: 사실관계·질의·회신 / 판례: 주문·이유, 최대 2만 자), 링크}.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.document(id)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def rulings_by_article(
    law_name: Annotated[str, Field(description=LAW)],
    article: Annotated[str, Field(description=ART)],
    kinds: Annotated[list[Kind] | None, Field(description="해석·판례 중 선택. 생략하면 둘 다")] = None,
    tax: Annotated[Tax | None, Field(description="세목 필터 (선택)")] = None,
    keyword: Annotated[str, Field(description="결과를 좁힐 추가 키워드 (선택)")] = "",
    sort: Annotated[Literal["최신", "정확도"], Field(description="정렬")] = "최신",
    n: Annotated[int, Field(description="종류별 최대 건수 1~30", ge=1, le=30)] = 10,
) -> dict:
    """List rulings and decisions that cite a specific statute article. 특정 조문을 관련 법령으로 인용한 해석·판례 모음.
    언제: 조문을 알고 그 조문의 실무 해석을 모을 때(예: 법인세법 제52조 → 부당행위계산). 키워드만 있으면 search_tax_rulings.
    반환: {법령, 조, 결과: [{구분, 문서번호, 제목, 요지, 세목, 일자, id, 링크}]}.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    kinds = tuple(kinds or ["해석", "판례"])
    if any(k not in ntis.KINDS for k in kinds): return {"error": "kinds: 해석 | 판례"}
    try:
        return {"법령": law_name, "조": article, "결과": ntis.search(keyword or law_name.split()[0], kinds, tax, sort, max(1, min(int(n), 30)),
                                                                   article=article.strip(), law=law_name)}
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def basic_rules(
    law_name: Annotated[str, Field(description=LAW)],
    article: Annotated[str, Field(description="법 조문('제52조'). 주면 그 조에 딸린 통칙 전부, 생략하면 전체에서 keyword로 검색")] = "",
    keyword: Annotated[str, Field(description="통칙 제목·본문 검색어 (선택)")] = "",
) -> dict:
    """Get NTS Basic Rules (국세 기본통칙) full text by article or keyword. 국세 기본통칙 전문(최신 고시본).
    언제: 조문의 국세청 공식 해석 기준이 필요할 때. 실무 집행 기준 목록은 execution_standards, 개별 사안 해석은 rulings_by_article.
    반환: {법령, 기준(고시 연도), 통칙: [{통칙(번호·제목), 본문}], 링크}.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.basic_rules(law_name, article, keyword)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def execution_standards(
    law_name: Annotated[str, Field(description=LAW + ". 소득세는 '소득세법'")],
    article: Annotated[str, Field(description="법 조문('제52조'). 주면 그 조의 집행기준 항목만")] = "",
    keyword: Annotated[str, Field(description="항목 제목 검색어 (선택)")] = "",
) -> dict:
    """List Tax Execution Standards (세법집행기준) items with page numbers. 세법집행기준 항목(최신 발간본).
    언제: 조문별 집행 기준이 있는지·몇 쪽인지 확인할 때. 본문은 책자(PDF)라 제공하지 않으므로 통칙 본문이 필요하면 basic_rules.
    반환: {법령, 기준(발간 연도), 항목: [{항목(번호·제목), 쪽}], 링크, 주의}.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.exec_standards(law_name, article, keyword)
    except Exception as e: return _err(e)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@bilingual
def casebook_search(
    query: Annotated[str, Field(description="쟁점 문장이나 키워드")],
    area: Annotated[Literal["법인", "부가", "소득", "상증", "양도", "국기", "국조", "종부"] | None, Field(description="분야 필터 (선택)")] = None,
    k: Annotated[int, Field(description="결과 수 1~10", ge=1, le=10)] = 5,
) -> dict:
    """Search the NTS 2025 Tax Interpretation Casebook (96 curated cases). 국세청 「2025 세법해석 사례집」 쟁점 검색.
    언제: 국세청이 대표 사례로 고른 해석을 빠르게 볼 때(오프라인, 즉시). 최신·전체 해석은 search_tax_rulings.
    반환: {결과: [{문서번호, 회신일, 분야, 쟁점, 답변요지, 쪽, 점수, 인용}]}. 읽기 전용, 외부 호출 없음.
    """
    if area and area not in casebook.AREAS: return {"error": f"area는 {casebook.AREAS} 중 하나"}
    return {"결과": casebook.search(query, area, max(1, min(int(k), 10)))}


@mcp.tool(annotations=RO)
@bilingual
def law_article(
    law_name: Annotated[str, Field(description="법령 정식 명칭. 예: '법인세법', '법인세법 시행령', '법인세법 시행규칙'")],
    article: Annotated[str, Field(description=ART)],
    as_of: Annotated[str, Field(description="기준일 YYYYMMDD. 그날 시행 중이던 연혁본. 생략하면 오늘")] = "",
    with_delegation: Annotated[bool, Field(description="True면 법률 조문에 연결된 시행령·시행규칙 위임 조문 전부(3단)")] = False,
    with_rules: Annotated[bool, Field(description="True면 그 조의 기본통칙 전문과 집행기준 항목도 함께")] = False,
) -> dict:
    """Get statute text as in force on a date, with optional Act → Decree → Rule chain. 조문 원문(기준일 시행본)과 3단 위임.
    언제: 세액·요건 판단처럼 사실 발생 시점의 법령이 필요할 때. 해석·판례는 회신 당시 법 기준이므로 이 도구로 적용 연도 조문과 대조.
    반환: {법령, 조, 적용 시행일, 본문, 링크} 또는 {위임체계: [{단계, 법령, 조, 적용 시행일, 본문}]} (+ 기본통칙·집행기준).
    읽기 전용. 법제처 공식 API — 환경변수 LAW_OC(무료) 필요, 없으면 발급 안내 오류.
    """
    ef = re.sub(r"\D", "", as_of or "")
    if ef and len(ef) != 8: return {"error": "as_of는 YYYYMMDD"}
    try:
        if LANG.get() == "en" and not with_delegation:   # 영어: 공식 영문 번역본 + 한국어 원문 시행본
            out = law.article_en(law_name, article.strip())
            ko = law.article(law_name, article.strip(), ef)
            out["원문(한국어)"] = {"적용 시행일": ko.get("적용 시행일"), "본문": ko.get("본문")}
        else:
            out = {"위임체계": law.tiers(law_name, article.strip(), ef)} if with_delegation else law.article(law_name, article.strip(), ef)
    except law.NoKey as e:
        return {"error": str(e)}
    except Exception as e:
        return _err(e)
    if with_rules:
        base = re.sub(r"\s*(시행령|시행규칙)$", "", law_name)
        for k, f in (("기본통칙", ntis.basic_rules), ("집행기준", ntis.exec_standards)):
            try: out[k] = f(base, article.strip())
            except Exception as e: out[k] = _err(e)
    return out


def _solar(prompt):
    from . import solar
    return solar.chat_json(prompt)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
@bilingual
def compare_with_case(
    facts: Annotated[str, Field(description="사실관계: 누가·언제·무엇을·얼마 (최대 1500자 사용)")],
    our_view: Annotated[str, Field(description="우리 주장: 과세 논리 또는 납세자 주장 한두 문장")],
    tax: Annotated[Tax | None, Field(description="세목 필터 (선택)")] = None,
) -> dict:
    """Check your facts and argument against rulings: supports / contradicts / distinguish. 사실관계·논리를 해석·판례와 대조해 항목마다 지지·반대·구별 필요를 판정.
    언제: 주장의 근거와 반대 사례를 한 번에 점검할 때(의견서·불복 검토). 단순 검색은 search_tax_rulings.
    반환: {해석: [{문서번호, 구분, 관계, 이유, 사실관계 차이, 링크}], 요약, 주의}. 문서번호는 검색 결과에 있는 것만.
    읽기 전용. Solar 호출 — UPSTAGE_API_KEY(클라우드) 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL(망분리 온프렘 Solar) 필요, 약 10초.
    """
    if not facts.strip() or not our_view.strip(): return {"error": "facts·our_view 둘 다 필요"}
    try:
        pool = ntis.search(f"{our_view[:60]}", ("해석", "판례"), tax, "정확도", 6)[:10]
    except Exception as e:
        return _err(e)
    pool += [{"구분": "사례집", "문서번호": c["문서번호"], "제목": c["쟁점"], "요지": c["답변요지"], "일자": c["회신일"], "링크": ""}
             for c in casebook.search(f"{facts} {our_view}", None, 3)]
    if not pool: return {"해석": [], "요약": "관련 해석·판례 없음"}
    keyed = {f"K{i}": x for i, x in enumerate(pool, 1)}
    lines = "\n".join(f"[{k}] {x['구분']} {x['문서번호']} {x['일자']} 제목: {x['제목']} / 요지: {x['요지'][:400]}" for k, x in keyed.items())
    try:
        j = _solar(f"""세법 논리를 아래 해석·판례와 대조한다. 항목마다 우리 논리와의 관계를 판정한다. 적힌 내용 밖의 사실을 만들지 않는다. 확신이 없으면 '구별 필요'.
[사실관계] {facts[:1500]}
[우리 논리] {our_view[:500]}
[후보]
{lines}
JSON: {{"해석":[{{"키":"K1","관계":"지지|반대|구별 필요|무관","이유":"1문장","사실관계 차이":"없으면 없음"}}],"요약":"1~2문장"}}""")
    except Exception as e:
        return _err(e)
    rows = []
    for r in j.get("해석", []):
        x = keyed.get(r.get("키"))
        if x and r.get("관계") in ("지지", "반대", "구별 필요"):
            rows.append({"문서번호": x["문서번호"], "구분": x["구분"], "관계": r["관계"], "이유": r.get("이유", ""),
                         "사실관계 차이": r.get("사실관계 차이", ""), "링크": x.get("링크", "")})
    return {"해석": rows, "요약": j.get("요약", ""), "주의": f"{solar.where()} 판정은 검토 보조 — 본문 확인 후 인용"}


@mcp.tool(annotations=RO)
@bilingual
def research_issue(
    law_name: Annotated[str, Field(description=LAW)],
    article: Annotated[str, Field(description=ART)],
    period: Annotated[str, Field(description="사실이 속한 시점: '2023'(사업연도·과세기간), '2023-1'(부가 1기), '2023-12-31'(날짜)")],
    tax: Annotated[Tax | None, Field(description="세목. 부가세 과세기간 판단과 해석 필터에 사용 (선택)")] = None,
    n: Annotated[int, Field(description="해석·판례 종류별 최대 건수 1~20", ge=1, le=20)] = 8,
) -> dict:
    """Bundle everything that applied to an issue at a past date. 그 해 기준 묶음 조회 — 사실 발생 시점의 조문(3단)·기본통칙·집행기준·그 조문을 인용한 해석·판례를 한 번에.
    언제: 세무조사·불복처럼 특정 사업연도에 적용되는 근거를 정리할 때. 시점 판단을 코드로 고정한다 —
    기준일(사업연도·과세기간 종료일), 기준일 조문과 현행 조문의 변경 여부, 해석·판례마다 등록일 당시 조문이 기준일 조문과 같은지.
    반환: {기준일, 기준일 근거, 그 해 조문(3단), 현행과 비교, 기본통칙[], 집행기준[], 해석·판례[{…, 기준일 조문과}], 주의}.
    읽기 전용. 조문 부분은 LAW_OC 필요(없으면 해석·통칙만 반환). 10~30초.
    """
    try: return timeline.research(law_name, article.strip(), period, tax, n)
    except ValueError as e: return {"error": str(e)}
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def verify_citations(
    text: Annotated[str, Field(description="보고서·의견서·답변 초안 (해석·판례 문서번호와 '법인세법 제52조' 같은 조문 인용이 들어간 글, 최대 2만 자)")],
    as_of: Annotated[str, Field(description="조문 존재를 확인할 기준일 YYYYMMDD. 생략하면 오늘")] = "",
) -> dict:
    """Check that cited rulings, decisions and statute articles actually exist. 인용 검증 — 초안의 문서번호·조문이 실제로 있는지 확인.
    언제: AI나 사람이 쓴 초안을 내보내기 전. 지어낸 문서번호·없는 조문을 걸러낸다.
    반환: {문서번호: [{인용, 결과(확인/국세청 DB 미확인/조회 실패), 문서번호, 제목, 일자, 링크, 비슷한 번호}], 조문: [{인용, 결과, 적용 시행일}], 요약, 주의}.
    '확인'은 존재만 뜻함 — 내용 일치는 get_tax_ruling·law_article 본문으로 확인. 읽기 전용. 조문 확인은 LAW_OC 필요.
    """
    ef = re.sub(r"\D", "", as_of or "")
    if ef and len(ef) != 8: return {"error": "as_of는 YYYYMMDD"}
    try: return cite.verify(text[:20000], ef)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def tax_treaty(
    country: Annotated[str, Field(description="체약국 이름(한글). 예: '미국', '중국', '일본', '베트남'. 모르면 아무 이름이나 넣으면 체결국 목록을 돌려줌")],
    article: Annotated[str, Field(description="조문. 예: '제10조', '의정서'. 조약마다 번호 체계가 다르므로 주제로 찾을 땐 keyword 사용")] = "",
    keyword: Annotated[str, Field(description="조문 제목·본문 검색어. 예: '배당', '고정사업장', '이자', 'dividends'")] = "",
    english: Annotated[bool, Field(description="True면 영문 본문")] = False,
) -> dict:
    """Read Korea's bilateral tax treaties (96 countries) article by article, Korean or English. 한국의 조세조약 조문(국문·영문).
    언제: 비거주자 원천징수 제한세율, 고정사업장, 거주자 판정 등 국제거래 쟁점. 국내법 조문은 law_article, 국제조세 해석은 search_tax_rulings(tax='국조').
    반환: {국가, 발효일, 조문: [{조, 제목, 영문 제목, 본문}], 링크} — 조문 번호는 조약마다 다르니 keyword로 찾는 게 정확.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.treaty(country, article.strip(), keyword.strip(), english)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def search_nts_publications(
    query: Annotated[str, Field(description="찾을 내용. 예: '이전가격 정상가격 산출방법', '해외현지법인 명세서 제출', 'APA'")],
    n: Annotated[int, Field(description="결과 수 1~20", ge=1, le=20)] = 8,
) -> dict:
    """Full-text search inside NTS official guidebooks and reports (transfer pricing, APA reports, overseas business guides, filing guides). 국세청 발간책자 본문 검색.
    언제: 국세청이 공식 책자로 낸 실무 안내(이전가격·APA 연차보고서·해외진출기업 세무 가이드·신고 안내 등)의 설명이 필요할 때.
    반환: {결과: [{책자, 발간일, 분야, 담당, 발췌, 링크}]}. 책자 원문은 국세법령정보시스템 전자도서관에서.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return {"결과": ntis.publications(query, n)}
    except Exception as e: return _err(e)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@bilingual
def search_local_documents(
    query: Annotated[str, Field(description="찾을 내용. 영어·한국어·문단 번호(예: '2.14', 'comparability analysis', '무형자산')")],
    k: Annotated[int, Field(description="결과 수 1~10", ge=1, le=10)] = 5,
) -> dict:
    """Search PDFs you downloaded yourself, page by page — e.g. the OECD Transfer Pricing Guidelines. 내 PC의 PDF(예: OECD 이전가격 지침) 쪽 단위 검색.
    언제: 저작권상 재배포할 수 없는 자료(OECD 지침 등)를 각자 받아 근거로 쓸 때. 문서는 이 패키지에 들어 있지 않음.
    설정: 환경변수 KOREAN_TAX_MCP_DOCS에 PDF 폴더 경로, PDF 읽기용 pypdf 필요(uvx --with pypdf korean-tax-mcp).
    반환: {결과: [{파일, 쪽, 점수, 발췌}], 색인}. 읽기 전용, 외부 호출 없음. 첫 호출 때 색인(파일이 크면 수십 초).
    """
    try: return localdocs.search(query, k)
    except Exception as e: return {"error": str(e)}


@mcp.tool(annotations=RO)
@bilingual
def treaty_withholding_rates(
    country: Annotated[str, Field(description="체약국 이름(한글). 예: '미국', '중국', '일본', '싱가포르'")],
    income: Annotated[Literal["배당", "이자", "사용료"] | None, Field(description="소득 종류. 생략하면 셋 다")] = None,
) -> dict:
    """Treaty withholding tax caps on dividends, interest and royalties for a country, with the clause text. 조세조약 원천징수 제한세율(배당·이자·사용료).
    언제: "미국 법인에 배당하면 몇 %?" 같은 질문. 세율과 지분 요건을 조약 원문에서 뽑고 근거 조항((a)·(b)…)을 함께 준다. 조문 전체는 tax_treaty.
    반환: {국가, 발효일, 제한세율: [{소득, 조문, 세율: [{세율(%), 근거}], 요건·기타: [{지분요건(%), 근거}], 개정 문서 언급, 주의}], 주의, 링크}.
    자동 추출이라 개정 의정서·교환각서가 조문을 바꿨으면 '개정 문서 언급'에 표시 — 적용 전 확인. 지방소득세 등 국내법은 별도.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.withholding_rates(country, income)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def search_forms(
    query: Annotated[str, Field(description="별표·서식 이름에 들어가는 말. 예: '소득금액변동통지서', '국제거래명세서', '기준내용연수', '상각률표'")],
    kind: Annotated[Literal["별표", "서식"] | None, Field(description="별표(세율표·내용연수표 등)만 또는 서식(신고서·명세서)만. 생략하면 둘 다")] = None,
    n: Annotated[int, Field(description="결과 수 1~20", ge=1, le=20)] = 10,
) -> dict:
    """Search statutory annexes (rate and useful-life tables) and official tax forms. 세법 별표·서식 검색.
    언제: 세율표·기준내용연수표·상각률표 같은 별표나, 신고서·명세서·통지서 서식을 찾을 때. 조문 본문은 law_article.
    반환: {결과: [{구분(별표/서식), 이름, 법령, 세법, 시행일, 내용(서식 안 글 600자), 링크}]}. 같은 서식은 최신 시행본만.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return {"결과": ntis.forms(query, kind, n)}
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
@bilingual
def article_history(
    law_name: Annotated[str, Field(description="법령 정식 명칭. 예: '법인세법', '법인세법 시행규칙'")],
    article: Annotated[str, Field(description=ART)],
    last: Annotated[int, Field(description="비교할 최근 시행본 수 2~20 (시행예정 포함)", ge=2, le=20)] = 8,
) -> dict:
    """When did this article change, and will an upcoming amendment change it? 조문 개정 이력과 시행 예정 개정.
    언제: "이 조문 언제 바뀌었나", "곧 바뀌나" — 사업연도별 적용 조문이 다른지 판단할 때. 특정 날짜 원문은 law_article(as_of).
    반환: {법령, 조, 연혁: [{시행일, 공포일, 제개정, 상태(연혁/현행/시행예정), 이 조 변경(바뀜/그대로)}], 요약, 주의}.
    읽기 전용. 법제처 공식 API — LAW_OC 필요.
    """
    try: return law.history(law_name, article.strip(), last)
    except law.NoKey as e: return {"error": str(e)}
    except Exception as e: return _err(e)


def main():
    import argparse
    p = argparse.ArgumentParser(prog="korean-tax-mcp", description="한국 세법 근거 MCP 서버")
    p.add_argument("--http", action="store_true", help="HTTP(streamable) 모드 — 기본은 stdio")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    if a.http:
        import uvicorn
        uvicorn.run(mcp.streamable_http_app(streamable_http_path="/mcp", host=a.host), host=a.host, port=a.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
