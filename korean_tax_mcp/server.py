"""korean-tax-mcp — 한국 세법 근거 MCP 서버.

국세청 질의회신·과세기준자문·사전답변·판례·조세심판·이의·심사, 국세 기본통칙, 세법집행기준, 세법해석 사례집,
시점별 조문과 법률→시행령→시행규칙 위임 체계를 한곳에서 찾는다.

키 없이: 해석·판례 검색과 본문, 조문별 해석, 기본통칙, 집행기준, 사례집
LAW_OC(법제처, 무료): 시점별 조문·위임 체계
AI 판단(대조·요약·번역): 기본은 사용자 AI(호스트)가 수행 — 원문 발췌와 판단 안내를 반환, Upstage로 전송 없음
UPSTAGE_API_KEY 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL(선택): Solar가 대조·요약·번역 수행
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

from . import _mask_oc, casebook, cite, i18n, law, localdocs, ntis, outcome, residency, solar, timeline

mcp = MCPServer(
    "korean-tax-mcp", title="Korea Tax Law (한국 세법 근거)",
    instructions="한국 세법 쟁점의 근거(국세청 해석·판례·통칙·집행기준·조문)를 찾는다. search_tax_rulings로 넓게 찾고, get_tax_ruling으로 본문을 읽고, "
                 "조문 단위로는 rulings_by_article·basic_rules·law_article을 쓴다. 조문 번호를 모르면 find_article로 먼저 찾고, 긴 조문은 law_article의 keyword/paragraph로 필요한 항만 보라. "
                 "특정 사업연도 기준 정리는 research_issue, 쟁점의 납세자 승·패 사례 비교는 compare_outcomes, 초안 검수는 verify_citations, 국제거래는 tax_treaty·search_nts_publications. 문서번호는 결과에 있는 것만 인용하고, "
                 "해석·판례는 회신·선고 당시 법 기준이므로 적용 연도의 조문(law_article as_of)과 대조하라고 안내한다.")

TAXES = tuple(ntis.TAX_CODES)
RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
Tax = Literal["법인", "부가", "소득", "양도", "상증", "국기", "국징", "조특", "국조", "종부"]
Kind = Literal["해석", "판례"]
LAW = "세법 이름(정식 명칭). 예: '법인세법', '부가가치세법', '소득세법', '상속세 및 증여세법', '국세기본법'"
ART = "조문 번호. '제52조' 또는 '제28조의2' 형식"
NTIS_NOTE = "읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시."


def _err(e): return {"error": f"{type(e).__name__}: {_mask_oc(str(e))}"}

import contextvars
LANG = contextvars.ContextVar("lang", default="ko")
LangT = Annotated[Literal["ko", "en"], Field(description="Output language. 'en': English keys and labels, official English texts where available "
                                                     "(tax treaties, statutes), other Korean texts returned with a host_ai_translate instruction (your AI translates); Solar machine translation only when UPSTAGE_API_KEY or on-prem Solar is configured. 기본 'ko'")]


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
        norm, hang = law.normalize_article(article)
        r = {"법령": law_name, "조": norm, "결과": ntis.search(keyword or law_name.split()[0], kinds, tax, sort, max(1, min(int(n), 30)),
                                                                   article=norm, law=law_name)}
        if hang: r["요청 항"] = hang
        return r
    except ValueError as e:
        return {"error": str(e)}
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
    try:
        norm, hang = law.normalize_article(article)
        r = ntis.basic_rules(law_name, norm, keyword)
        r["조"] = norm
        if hang: r["요청 항"] = hang
        return r
    except ValueError as e:
        return {"error": str(e)}
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
    try:
        norm, hang = law.normalize_article(article)
        r = ntis.exec_standards(law_name, norm, keyword)
        r["조"] = norm
        if hang: r["요청 항"] = hang
        return r
    except ValueError as e:
        return {"error": str(e)}
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


RESP_MAX_CHARS = int(os.environ.get("KTM_RESP_MAX_CHARS", 20000))


def _truncate_text(text, limit=RESP_MAX_CHARS):
    """일정 길이 초과 응답을 잘라내고 '생략됨, 링크 참조' 표시."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[이하 생략됨 — 전체 본문은 링크 참조]"


@mcp.tool(annotations=RO)
@bilingual
def law_article(
    law_name: Annotated[str, Field(description="법령 정식 명칭. 예: '법인세법', '법인세법 시행령', '법인세법 시행규칙'")],
    article: Annotated[str, Field(description=ART + ". '제52조 제1항'처럼 항을 함께 줄 수 있음")],
    as_of: Annotated[str, Field(description="기준일 YYYYMMDD. 그날 시행 중이던 연혁본. 생략하면 오늘")] = "",
    with_delegation: Annotated[bool, Field(description="True면 법률 조문에 연결된 시행령·시행규칙 위임 조문 전부(3단)")] = False,
    with_rules: Annotated[bool, Field(description="True면 그 조의 기본통칙 전문과 집행기준 항목도 함께")] = False,
    keyword: Annotated[str, Field(description="키워드가 들어간 항(①②…/제1항…)만 반환. 긴 조문(4,000자 초과)에서 항 번호 모를 때 사용")] = "",
    paragraph: Annotated[str, Field(description="원하는 항만 지정. '①'·'1'·'제1항'·'②' 등. 그 항만 반환")] = "",
) -> dict:
    """Get statute text as in force on a date, with optional Act → Decree → Rule chain. 조문 원문(기준일 시행본)과 3단 위임.

    언제: 세액·요건 판단처럼 사실 발생 시점의 법령이 필요할 때. 해석·판례는 회신 당시 법 기준이므로 이 도구로 적용 연도 조문과 대조.
    조문 번호를 모르면 find_article로 먼저 찾는다. 긴 조문(4,000자 초과)은 keyword(키워드가 든 항만) 또는 paragraph(특정 항)로 필요한 항만 조회 — 둘 다 없으면 항 목록과 안내 반환.
    반환: {법령, 조, 적용 시행일, 본문, 링크, 반환 범위} 또는 {위임체계: [{단계, 법령, 조, 적용 시행일, 본문}]} (+ 기본통칙·집행기준).
    읽기 전용. 법제처 공식 API — 환경변수 LAW_OC(무료) 필요, 없으면 발급 안내 오류.
    """
    ef = re.sub(r"\D", "", as_of or "")
    if ef and len(ef) != 8: return {"error": "as_of는 YYYYMMDD"}
    try:
        norm, hang = law.normalize_article(article)
        if LANG.get() == "en" and not with_delegation:   # 영어: 공식 영문 번역본 + 한국어 원문 시행본
            out = law.article_en(law_name, norm)
            ko = law.article(law_name, norm, ef)
            out["원문(한국어)"] = {"적용 시행일": ko.get("적용 시행일"), "본문": _truncate_text(ko.get("본문", ""))}
        else:
            if with_delegation:
                tiers = law.tiers(law_name, norm, ef)
                out = {"위임체계": [{"단계": t["단계"], "법령": t["법령"], "조": t["조"],
                                     "적용 시행일": t["적용 시행일"], "본문": _truncate_text(t.get("본문", ""))}
                                    for t in tiers]}
            else:
                a = law._article_body_with_scope(law_name, norm, hang, ef, paragraph, keyword)
                a["본문"] = _truncate_text(a.get("본문", ""))
                out = a
        if hang and not paragraph:
            out["요청 항"] = hang
    except ValueError as e:
        return {"error": str(e)}
    except law.NoKey as e:
        return {"error": str(e)}
    except Exception as e:
        return _err(e)
    if with_rules:
        base = re.sub(r"\s*(시행령|시행규칙)$", "", law_name)
        for k, f in (("기본통칙", ntis.basic_rules), ("집행기준", ntis.exec_standards)):
            try:
                r = f(base, norm)
                if "통칙" in r:
                    r["통칙"] = [{"통칙": t["통칙"], "본문": _truncate_text(t.get("본문", ""))} for t in r["통칙"]]
                if "항목" in r:
                    r["항목"] = [{"항목": it["항목"], "쪽": it["쪽"]} for it in r["항목"]]
                out[k] = r
            except Exception as e: out[k] = _err(e)
    return out


@mcp.tool(annotations=RO)
@bilingual
def find_article(
    keyword: Annotated[str, Field(description="찾을 키워드(공백으로 여러 단어). 예: '압류금지 생계비계좌'")],
    law_name: Annotated[str | None, Field(description="법령명(정식 명칭). 생략하면 주요 세법 전부(국세기본법·징수법·소득세법·법인세법·부가가치세법·상속세및증여세법·조세특례제한법·국제조세조정법 + 각 시행령)에서 조회")] = None,
    as_of: Annotated[str, Field(description="기준일 YYYYMMDD. 생략하면 오늘")] = "",
    n: Annotated[int, Field(description="반환 건수(1~20)", ge=1, le=20)] = 5,
) -> dict:
    """Find statute articles by keyword — first step when you don't know the article number. 키워드로 조문 위치를 찾는다.

    언제: 쟁점 키워드는 있는데 조문 번호를 모를 때 first step. 예: '압류금지 생계비계좌' → 국세징수법 제41조.
    반환: [{법령, 조, 제목, 적용 시행일, 일치 문장: 키워드가 든 문장 1~2개(각 200자 이내)}], 다음 단계: law_article(law_name, 조, keyword=...)로 해당 항만 조회.
    결과 길이 4,000자 이내. 읽기 전용. 법제처 공식 API — LAW_OC 필요, 없으면 오류.
    """
    if not keyword.strip():
        return {"error": "keyword 필요"}
    if n < 1 or n > 20:
        return {"error": "n은 1~20"}
    ef = re.sub(r"\D", "", as_of or "")
    if ef and len(ef) != 8:
        return {"error": "as_of는 YYYYMMDD 또는 YYYY-MM-DD"}
    try:
        return law.find_article(keyword, law_name, as_of or "", n)
    except Exception as e:
        return _err(e)


def _solar(prompt):
    from . import solar
    return solar.chat_json(prompt)


@mcp.tool(annotations=RO)
@bilingual
def compare_outcomes(
    issue: Annotated[str, Field(description="쟁점 한 문장. 예: '특정 임원만을 위한 퇴직금 지급규정에 따른 퇴직금의 손금산입 여부'")],
    tax: Annotated[Tax | None, Field(description="세목 필터 (선택)")] = None,
    n: Annotated[int, Field(description="본문까지 읽을 결정·판결 수(4~20). 많을수록 느림(건당 약 0.5초)", ge=4, le=20)] = 12,
    explain: Annotated[bool, Field(description="True면 '승패를 가른 지점' 정리. 기본은 사용자 AI용 판단 안내 반환(전송 없음), Solar 설정 시 Solar가 요약")] = False,
) -> dict:
    """Win/loss side by side for one issue: taxpayer-won vs lost decisions with both sides' arguments and the deciding reasoning. 같은 쟁점의 조세심판·심사·이의·법원 판결을 납세자 승(인용·취소)/일부 인용/패(기각)로 나누고, 건마다 납세자 주장·과세관청 의견·결정 이유(판단 끝부분)를 나란히.
    언제: 불복·조사 대응에서 '이긴 쪽은 무엇을 입증했고 진 쪽은 무엇이 부족했나'를 볼 때. 이긴 사례만 걸러 보지 않는다(양쪽을 같이).
    결과 판정은 본문 주문(主文)·결론 문장을 규칙으로 읽음(모델 추정 아님). 주장·이유는 본문에서 잘라 온 발췌.
    반환: {쟁점, 집계, 납세자 승(인용·취소), 일부 인용, 납세자 패(기각), 각하·기타, 갈린 지점?(explain), mode?, 주의}.
    explain=True: Solar 설정이 없으면 mode="host_ai" — 갈린 지점에 사용자 AI용 판단 안내(발췌는 위 목록). 설정 시 Solar 요약(mode=solar_cloud/solar_onprem).
    읽기 전용. 국세법령정보시스템 조회, 약 5~10초.
    """
    if not issue.strip(): return {"error": "issue 필요"}
    try: r = outcome.compare(issue, tax, n)
    except Exception as e: return _err(e)
    r["주의"] = "결정 당시 법 기준 — 적용 연도 조문(law_article as_of)과 대조. 사실관계가 다르면 결론도 다를 수 있음"
    if r["집계"][outcome.WIN] + r["집계"][outcome.PART] == 0:
        r["안내"] = "납세자 승 사례가 검색 상위에 없음 — 쟁점 문구를 바꾸거나 n을 늘려 다시 찾기"
    if explain:
        sides = [(k, x) for k in (outcome.WIN, outcome.PART, outcome.LOSE) for x in r[k][:5]]
        r["mode"] = solar.mode()
        if sides and r["mode"] == "host_ai":
            r["갈린 지점"] = {"mode": "host_ai", "발췌 위치": "위 납세자 승·일부 인용·납세자 패 목록의 납세자 주장·과세관청 의견·결정 이유(판단 끝부분)",
                         "판단 안내": "사용자 AI가 판단: 위 발췌만으로 승패를 가른 지점을 사실·증빙 기준으로 비교해 "
                                   "{갈린 지점: [한 줄 (근거 문서번호)], 이긴 쪽이 입증한 것: [...], 진 쪽에 부족했던 것: [...]} 로 정리. "
                                   "각 항목에 근거 문장과 문서번호를 인용하고, 발췌에 없는 사실은 만들지 않으며, 문서번호는 목록에 있는 것만 사용. "
                                   "판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요."}
        elif sides:
            lines = "\n".join(f"[{k}] {x['문서번호']} 납세자: {x.get('납세자 주장', '')[:250]} / 판단: {x.get('결정 이유(판단 끝부분)', '')[-350:]}" for k, x in sides)
            try:
                j = _solar(f"""같은 세법 쟁점의 결정·판결을 납세자 승/패로 나눈 발췌다. 승패를 가른 지점을 비교한다. 발췌에 없는 사실을 만들지 않는다. 문서번호는 아래 것만.
[쟁점] {issue[:200]}
{lines}
JSON: {{"갈린 지점":["사실·증빙 기준 한 줄 (근거 문서번호)"],"이긴 쪽이 입증한 것":["..."],"진 쪽에 부족했던 것":["..."]}}""")
                r["갈린 지점"] = {**j, "주의": f"{solar.where()} 요약 — 본문 확인 후 인용"}
                r["AI 생성 표시"] = "이 결과의 판단·요약·번역 문장은 생성형 AI(Upstage Solar Pro 4)가 작성했습니다. 근거 원문과 대조해 확인하세요."
            except Exception as e:
                r["갈린 지점"] = {"error": f"Solar 요약 실패: {e}"}
    return r


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
@bilingual
def compare_with_case(
    facts: Annotated[str, Field(description="사실관계: 누가·언제·무엇을·얼마 (최대 1500자 사용)")],
    our_view: Annotated[str, Field(description="우리 주장: 과세 논리 또는 납세자 주장 한두 문장")],
    tax: Annotated[Tax | None, Field(description="세목 필터 (선택)")] = None,
) -> dict:
    """Check your facts and argument against rulings: supports / contradicts / distinguish. 사실관계·논리를 해석·판례와 대조해 항목마다 지지·반대·구별 필요를 판정.
    언제: 주장의 근거와 반대 사례를 한 번에 점검할 때(의견서·불복 검토). 단순 검색은 search_tax_rulings.
    기본(mode="host_ai"): Solar 설정이 없으면 후보 문서의 원문 발췌(제목·요지, 문서번호, 링크)와 판단 안내를 반환 — 판정은 사용자 AI가 수행, Upstage로 전송 없음.
    반환(host_ai): {mode, 사실관계, 우리 논리, 후보: [{문서번호, 구분, 일자, 제목, 요지, 링크}], 판단 안내, 주의}.
    선택(Solar): UPSTAGE_API_KEY(클라우드, 입력이 api.upstage.ai로 전송) 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL(망분리 온프렘 Solar) 설정 시
    반환: {mode, 해석: [{문서번호, 구분, 관계, 이유, 사실관계 차이, 링크}], 요약, 주의}. 문서번호는 검색 결과에 있는 것만. 약 10초.
    읽기 전용.
    """
    if not facts.strip() or not our_view.strip(): return {"error": "facts·our_view 둘 다 필요"}
    try:
        pool = ntis.search(f"{our_view[:60]}", ("해석", "판례"), tax, "정확도", 6)[:10]
    except Exception as e:
        return _err(e)
    pool += [{"구분": "사례집", "문서번호": c["문서번호"], "제목": c["쟁점"], "요지": c["답변요지"], "일자": c["회신일"], "링크": ""}
             for c in casebook.search(f"{facts} {our_view}", None, 3)]
    if not pool: return {"해석": [], "요약": "관련 해석·판례 없음"}
    if solar.mode() == "host_ai":
        return {"mode": "host_ai", "사실관계": facts[:1500], "우리 논리": our_view[:500],
                "후보": [{"문서번호": x["문서번호"], "구분": x["구분"], "일자": x["일자"], "제목": x["제목"], "요지": x["요지"][:800],
                        "링크": x.get("링크", "")} for x in pool],
                "판단 안내": "사용자 AI가 판단: 후보 문서마다 우리 논리와의 관계를 지지/반대/구별 필요(무관하면 제외)로 판정하고, "
                          "판정마다 근거가 된 요지 문장과 문서번호를 인용하며 사실관계 차이를 한 줄로 적는다. 확신이 없으면 '구별 필요'. "
                          "적힌 내용 밖의 사실을 창작하지 않고, 문서번호는 후보에 있는 것만 쓴다. 필요하면 get_tax_ruling으로 본문 확인. "
                          "판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요.",
                "주의": "요지 발췌 기준 — 인용 전 본문 확인"}
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
    result = {"mode": solar.mode(), "해석": rows, "요약": j.get("요약", ""), "주의": f"{solar.where()} 판정은 검토 보조 — 본문 확인 후 인용"}
    if mode := solar.mode():
        if mode in ("solar_cloud", "solar_onprem"):
            result["AI 생성 표시"] = "이 결과의 판단·요약·번역 문장은 생성형 AI(Upstage Solar Pro 4)가 작성했습니다. 근거 원문과 대조해 확인하세요."
        elif mode == "host_ai":
            result["판단 안내"] = result.get("판단 안내", "") + " 판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요."
    return result


@mcp.tool(annotations=RO)
@bilingual
def research_issue(
    law_name: Annotated[str, Field(description=LAW)],
    article: Annotated[str, Field(description=ART)],
    period: Annotated[str, Field(description="사실이 속한 시점: '2023'(사업연도·과세기간), '2023-1'(부가 1기), '2023-12-31'(날짜)")],
    tax: Annotated[Tax | None, Field(description="세목. 부가세 과세기간 판단과 해석 필터에 사용 (선택)")] = None,
    n: Annotated[int, Field(description="해석·판례 종류별 최대 건수 1~20", ge=1, le=20)] = 8,
    event: Annotated[Literal["양도", "상속", "증여", "원천"] | None, Field(description="사건 기준 세목. 양도=양도일(잔금일), 상속=상속개시일, 증여=증여일(등기 대상은 등기접수일), 원천=지급일. 주면 period는 날짜여야 함")] = None,
    registered: Annotated[str, Field(description="양도: 소유권이전등기 접수일 YYYY-MM-DD (잔금일보다 빠르면 이 날이 양도일, 선택)")] = "",
) -> dict:
    """Bundle everything that applied to an issue at a past date. 그 해 기준 묶음 조회 — 사실 발생 시점의 조문(3단)·기본통칙·집행기준·그 조문을 인용한 해석·판례를 한 번에.
    언제: 세무조사·불복처럼 특정 사업연도에 적용되는 근거를 정리할 때. 시점 판단을 코드로 고정한다 —
    기준일(법인·소득·부가는 사업연도·과세기간 종료일, 양도는 양도일, 상속은 상속개시일, 증여는 증여일, 원천은 지급일), 기준일 조문과 현행 조문의 변경 여부, 해석·판례마다 등록일 당시 조문이 기준일 조문과 같은지.
    반환: {기준일, 기준일 근거, 그 해 조문(3단), 현행과 비교, 기본통칙[], 집행기준[], 해석·판례[{…, 기준일 조문과}], 주의}.
    읽기 전용. 조문 부분은 LAW_OC 필요(없으면 해석·통칙만 반환). 10~30초.
    """
    try:
        norm, hang = law.normalize_article(article)
        r = timeline.research(law_name, norm, period, tax, n, event, registered or None)
        if hang: r["요청 항"] = hang
        return r
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
    try:
        norm, hang = law.normalize_article(article)
        r = ntis.treaty(country, norm or article.strip(), keyword.strip(), english)
        if norm: r["조"] = norm
        if hang: r["요청 항"] = hang
        return r
    except ValueError as e:
        return {"error": str(e)}
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
    try:
        norm, hang = law.normalize_article(article)
        r = law.history(law_name, norm, last)
        if hang: r["요청 항"] = hang
        return r
    except ValueError as e:
        return {"error": str(e)}
    except law.NoKey as e: return {"error": str(e)}
    except Exception as e: return _err(e)


# ── residency_check / residency_report (지시서 1~2) ─────────────────────────
from .residency.models import ResidencyInput
from .residency.judgment import run_check

_RULES_MD = os.path.join(os.path.dirname(__file__), "data", "residency", "rules.md")
try:
    with open(_RULES_MD, encoding="utf-8") as _f:
        _RULES_TEXT = _f.read()
except Exception:
    _RULES_TEXT = "(rules.md 읽기 실패 — residency_report 정상 동작 안 됨)"


@mcp.tool(annotations=RO)
@bilingual
def residency_check(
    judgment_year: Annotated[int, Field(description="판정 대상 연도 (소득 지급 연도). 예: 2026")],
    domestic_stay_days: Annotated[int | None, Field(description="직전연도(판정 연도-1) 국내 체류일수. 직접 입력값. entry_dates를 제공하면 자동 계산이 우선.")] = None,
    entry_dates: Annotated[list[str] | None, Field(description="입국 날짜 목록(YYYY-MM-DD). 제공 시 입국 다음날~출국일로 체류일수 자동 계산.")] = None,
    exit_dates: Annotated[list[str] | None, Field(description="출국 날짜 목록(YYYY-MM-DD). entry_dates와 1:1 대응.")] = None,
    temporary_exit_days: Annotated[int, Field(description="관광·질병 치료 등 명백히 일시적인 출국 기간 합계(일). 시행령 §4②에 따라 국내 거소로 간주.")] = 0,
    temporary_exit_reason: Annotated[str, Field(description="일시적 출국 사유 (예: '관광 5일, 치료 3일').")] = "",
    family_in_korea: Annotated[bool, Field(description="국내에 생계를 같이하는 가족이 있는지 여부.")] = False,
    family_desc: Annotated[str, Field(description="국내 가족 상황 설명 (예: '배우자·자녀 2명 서울 거주, 자녀 국내 학교 재학').")] = "",
    domestic_assets: Annotated[bool, Field(description="국내 부동산·예금·사업용 자산 등 국내 소재 자산이 있는지 여부.")] = False,
    asset_desc: Annotated[str, Field(description="국내 자산 요약 (예: '서울 아파트 자가(부부 공동명의), 국내 증권사 주식, 성남 상가 임대').")] = "",
    job_needs_183_days: Annotated[bool, Field(description="국내 183일 이상 거주를 통상 필요로 하는 직업인지 여부 (시행령 §2③1).")] = False,
    domestic_business_activity: Annotated[bool, Field(description="국내 사업·경영 활동, 국내 사업자등록, 국내 근로소득 등 국내 경제활동 유무.")] = False,
    economic_activity_desc: Annotated[str, Field(description="경제활동 요약 (예: '국내 A건설 자문·임원 근로소득, 국내 C컨설팅 사업, 국내 B법인 배당').")] = "",
    foreign_nationality: Annotated[bool, Field(description="외국 국적이 있는지 여부.")] = False,
    foreign_permanent_residency: Annotated[bool, Field(description="외국 영주권 또는 그에 준하는 장기체류자격을 얻었는지 여부 (시행령 §2④).")] = False,
    foreign_nationality_desc: Annotated[str, Field(description="외국 국적·영주권 상세 (예: '미국 국적, 2015년 미국 영주권 취득').")] = "",
    dispatched_by_korean_company: Annotated[bool, Field(description="내국법인(100% 출자 현지법인 포함) 파견 여부 (시행령 §3 특례 적용 대상).")] = False,
    local_hire_not_dispatch: Annotated[bool, Field(description="해외 현지법인에 '파견'이 아니라 퇴직 후 현지 채용된 경우 (§3 미적용, 대법원 2010두15056 구조).")] = False,
    dispatch_desc: Annotated[str, Field(description="파견/현지채용 상세 (예: 'S국 현지법인에 2018년 파견' 또는 '미국 현지법인에 퇴직 후 Senior Director로 신규 채용').")] = "",
    public_official_overseas: Annotated[bool, Field(description="공무원으로서 국외 근무 중인지 여부 (시행령 §3 특례 적용 대상).")] = False,
    overseas_job_desc: Annotated[str, Field(description="해외 근무 형태 종합 설명.")] = "",
    treaty_country: Annotated[str, Field(description="상대국 이름(한글). 예: '미국', '일본', '사우디아라비아'. 모르면 빈 문자열.")] = "",
    treaty_country_is_resident: Annotated[bool, Field(description="상대국 국내법상 거주자로 취급되는지 여부.")] = False,
    treaty_country_resident_desc: Annotated[str, Field(description="상대국 거주자 근거 (예: '미국 영주권자로서 미국 세법 거주지 테스트 충족').")] = "",
    permanent_home: Annotated[Literal["국내만", "국외만", "양쪽", "없음"], Field(description="항구적 주거 소재. 단기체류용이 아닌 계속 사용 가능한 주거 (소유·임차 무관).")] = "없음",
    permanent_home_desc: Annotated[str, Field(description="항구적 주거 상세 (예: '국내: 서울 아파트 자가(부부 공동), 국외: S국 아파트 임차(실사용 낮음)').")] = "",
    center_of_vital_interests: Annotated[Literal["국내", "국외", "판단 보류"], Field(description="중대한 이해관계의 중심지(판례상 양국 사업규모·소득규모·체류일수 등 비교).")] = "판단 보류",
    habitual_abode: Annotated[Literal["국내", "국외", "양쪽", "판단 보류"], Field(description="일상적 거소.")] = "판단 보류",
    nationality: Annotated[Literal["대한민국", "외국", "복수국적", "미입력"], Field(description="국적 (조약 tie-break 4단계). 미입력 시 4단계 보류 → 판정 보류.")] = "미입력",
    notes: Annotated[str, Field(description="추가 참고사항.")] = "",
) -> dict:
    """비거주자·거주자 3단계 판정 (규칙 기반, 외부 호출 없이 동작).

    언제: 판정 입력 데이터로 거주자·비거주자·이중거주자·조세조약 tie-break 결과를 즉시 확인할 때.
    판단은 코드 규칙 기반 — Solar 키 없어도 동작. AI 판단 기본은 사용자 AI(호스트)가 수행 — 판정 코드는 고정.
    반환: {입력, 법리, 1단계(소득세법), 2단계(이중거주자), 3단계(조세조약 tie-break), 최종 판정, 유사 판례 top3, 판단이 갈리는 지점·추가 확인 사항, 주의}.
    읽기 전용, 외부 호출 없음(tax_treaty는 선택 호출, 실패 시 mock 안내 첨부).

    판단 순서: (1) 소득세법 §1의2·시행령 §2(①③④)·§3·§4 → 주소/거소/파견 특례 → 거주자·비거주자·판단 보류
    (2) 이중거주자 여부 (증명책임: 납세의무자, 대법원 2006두3964)
    (3) 조세조약 tie-break (항구적 주거 → 중대한 이해관계 중심지 → 일상적 거소 → 국적 → 상호합의)
    - 상대국이 주어지면 tax_treaty(country, keyword='거주자')로 조약 거주자 조문 번호·tie-break 원문 일부를 첨부한다.
      (오프라인/모의 환경에서는 treaty_country만 있으면 조약 체결국임을 전제하고 mock tie-break 원문을 첨부한다.)
    - rules.md의 유사 판례(사실관계 키워드 매칭 상위 3건, 판결요지 요약)를 첨부한다.
    - rules.md 6-4절(찾지 못함/추정) 판례는 인용하지 않는다.
    - 법리: 국내 생활관계만으로 판단(국내외 비교 아님, 대법원 92누11695)을 결과에 명시한다.
    """
    inp = ResidencyInput(
        judgment_year=judgment_year,
        domestic_stay_days=domestic_stay_days,
        entry_dates=entry_dates, exit_dates=exit_dates,
        temporary_exit_days=temporary_exit_days,
        temporary_exit_reason=temporary_exit_reason,
        family_in_korea=family_in_korea, family_desc=family_desc,
        domestic_assets=domestic_assets, asset_desc=asset_desc,
        job_needs_183_days=job_needs_183_days,
        domestic_business_activity=domestic_business_activity,
        economic_activity_desc=economic_activity_desc,
        foreign_nationality=foreign_nationality,
        foreign_permanent_residency=foreign_permanent_residency,
        foreign_nationality_desc=foreign_nationality_desc,
        dispatched_by_korean_company=dispatched_by_korean_company,
        local_hire_not_dispatch=local_hire_not_dispatch,
        dispatch_desc=dispatch_desc,
        public_official_overseas=public_official_overseas,
        overseas_job_desc=overseas_job_desc,
        treaty_country=treaty_country,
        treaty_country_is_resident=treaty_country_is_resident,
        treaty_country_resident_desc=treaty_country_resident_desc,
        permanent_home=permanent_home, permanent_home_desc=permanent_home_desc,
        center_of_vital_interests=center_of_vital_interests,
        habitual_abode=habitual_abode,
        nationality=nationality,
        notes=notes,
    )

    treaty_info: dict | None = None
    if inp.treaty_country:
        # tax_treaty 도구로 실제 조회 시도 (오프라인에서는 mock/실패해도 정상 진행)
        try:
            t = ntis.treaty(inp.treaty_country, "", "거주자")
            if t and "조문" in t:
                arts = [a for a in t["조문"] if "거주자" in (a.get("제목") or "").lower()
                        or "address" in (a.get("제목") or "").lower()
                        or "resident" in (a.get("제목") or "").lower()
                        or "과세상의 주소" in (a.get("제목") or "")]
                if arts:
                    txt = arts[0].get("본문", "")
                    treaty_info = {
                        "country": inp.treaty_country,
                        " 발효일": t.get("발효일", ""),
                        " article": arts[0].get("조", ""),
                        " article_title": arts[0].get("제목", ""),
                        "article_text": txt[:500],
                        "link": t.get("링크", ""),
                        "source": "tax_treaty (실제 NTIS 조회)",
                    }
                else:
                    treaty_info = {
                        "country": inp.treaty_country,
                        "발효일": t.get("발효일", ""),
                        "article": "(거주자 조문 특정 못 함)",
                        "article_text": "(조세조약 거주자 조문을 tax_treaty로 확인 필요)",
                        "link": t.get("링크", ""),
                        "source": "tax_treaty (실제 NTIS 조회 — 거주자 조문 특정 안 됨)",
                    }
        except Exception:
            # tax_treaty 조회 실패: treaty_info 없음 → stage3에서 미체결국/확인 필요로 처리
            pass

    result = run_check(inp, treaty_info)

    # ── 출력 구성 ──────────────────────────────────────────────────────────
    _lang = LANG.get()
    def L(text): return i18n.english({"근거": text})["근거"] if _lang == "en" else text
    def s1label(): return i18n.english({"거주자": "resident", "비거주자": "non-resident", "판단 보류": "pending"})[result.stage1.overall] if _lang == "en" else result.stage1.overall
    def s2label(): return i18n.english({"이중거주자": "dual resident", "이중거주자 아님": "not dual resident", "확인 필요": "needs confirmation"})[result.stage2.dual] if _lang == "en" else result.stage2.dual
    def s3label(): return i18n.english({"한국 거주자": "Korea resident", "상대국 거주자": "foreign resident", "양국 과세(미체결국)": "taxed in both countries (no treaty)", "판정 보류": "pending"})[result.stage3.outcome] if _lang == "en" else result.stage3.outcome
    def finallabel(): return i18n.english({"거주자": "resident", "비거주자": "non-resident", "이중거주자(조세조약 적용 필요)": "dual resident (treaty tie-break needed)", "판정 보류": "pending", "양국 과세(미체결국)": "taxed in both countries (no treaty)"})[result.final_outcome] if _lang == "en" else result.final_outcome

    return {
        "입력": result.input_digest,
        "법리": result.legal_principle,
        "1단계(소득세법)": {
            "주소 판정": result.stage1.addr_judgment,
            "주소 근거 조문": result.stage1.addr_article,
            "주소 판단 근거": result.stage1.addr_reason,
            "거소 판정": result.stage1.residence_judgment,
            "국내 체류일수": result.stage1.residence_days,
            "거소 근거 조문": result.stage1.residence_article,
            "거소 판단 근거": result.stage1.residence_reason,
            "파견 특례(§3) 적용": "적용" if result.stage1.dispatch_special else "미적용",
            "파견 특례 근거": result.stage1.dispatch_reason,
            "1단계 종합": s1label(),
            "1단계 종합 근거": result.stage1.overall_reason,
        },
        "2단계(이중거주자)": {
            "이중거주자 여부": s2label(),
            "판단 근거": result.stage2.reason,
            "증명책임": result.stage2.burden_of_proof,
        },
        "3단계(조세조약 tie-break)": {
            "조세조약 체결 여부": "체결(조회 성공)" if (result.treaty_info and result.treaty_info.get("source") == "tax_treaty (실제 NTIS 조회)") else ("체결 전제(오프라인 mock)" if result.treaty_info else "미체결/확인 필요"),
            "tie-break 적용": "적용(이중거주자)" if result.stage3.tie_break_applied else "미적용",
            "결정 단계": result.stage3.decisive_stage or "(해당 없음)",
            "최종 거주지국": s3label(),
            "3단계 근거": result.stage3.reason,
            "조세조약 조문·원문": result.stage3.article_note or "(조약 정보 없음)",
        },
        "최종 판정": finallabel(),
        "최종 판정 근거": result.final_reason,
        "유사 판례 top3": [
            {
                "법원": p.court, "사건번호": p.case_no, "선고일": p.date,
                "사건명": p.case_name, "결론": p.conclusion,
                "판결요지": p.holding,
                "사실관계": p.facts,
                "비고": p.misc,
            }
            for p in result.similar_cases
        ],
        "판단이 갈리는 지점·추가 확인 사항": result.conflicting_points,
        "주의": "본 판정은 rules.md 기반 데모용 규칙이며, 실제 조세 판단에는 현행 법령·확정 판례 확인과 조세 전문가 검토가 필요하다.",
    }


@mcp.tool(annotations=RO)
@bilingual
def residency_report(
    judgment_year: Annotated[int, Field(description="판정 대상 연도. residency_check와 동일.")],
    domestic_stay_days: Annotated[int | None, Field(description="직전연도 국내 체류일수.")] = None,
    entry_dates: Annotated[list[str] | None, Field(description="입국 날짜 목록(YYYY-MM-DD).")] = None,
    exit_dates: Annotated[list[str] | None, Field(description="출국 날짜 목록(YYYY-MM-DD).")] = None,
    temporary_exit_days: Annotated[int, Field(description="일시 출국 기간 합계(일).")] = 0,
    temporary_exit_reason: Annotated[str, Field(description="일시 출국 사유.")] = "",
    family_in_korea: Annotated[bool, Field(description="국내 생계 가족 유무.")] = False,
    family_desc: Annotated[str, Field(description="국내 가족 상황.")] = "",
    domestic_assets: Annotated[bool, Field(description="국내 자산 유무.")] = False,
    asset_desc: Annotated[str, Field(description="국내 자산 요약.")] = "",
    job_needs_183_days: Annotated[bool, Field(description="183일 거주 필요 직업 여부.")] = False,
    domestic_business_activity: Annotated[bool, Field(description="국내 경제활동 유무.")] = False,
    economic_activity_desc: Annotated[str, Field(description="경제활동 요약.")] = "",
    foreign_nationality: Annotated[bool, Field(description="외국 국적 유무.")] = False,
    foreign_permanent_residency: Annotated[bool, Field(description="외국 영주권 유무.")] = False,
    foreign_nationality_desc: Annotated[str, Field(description="외국 국적·영주권 상세.")] = "",
    dispatched_by_korean_company: Annotated[bool, Field(description="내국법인 파견 여부.")] = False,
    local_hire_not_dispatch: Annotated[bool, Field(description="현지 채용(§3 미적용) 여부.")] = False,
    dispatch_desc: Annotated[str, Field(description="파견/현지채용 상세.")] = "",
    public_official_overseas: Annotated[bool, Field(description="공무원 국외 근무 여부.")] = False,
    overseas_job_desc: Annotated[str, Field(description="해외 근무 형태.")] = "",
    treaty_country: Annotated[str, Field(description="상대국 이름(한글).")] = "",
    treaty_country_is_resident: Annotated[bool, Field(description="상대국 거주자 여부.")] = False,
    treaty_country_resident_desc: Annotated[str, Field(description="상대국 거주자 근거.")] = "",
    permanent_home: Annotated[Literal["국내만", "국외만", "양쪽", "없음"], Field(description="항구적 주거.")] = "없음",
    permanent_home_desc: Annotated[str, Field(description="항구적 주거 상세.")] = "",
    center_of_vital_interests: Annotated[Literal["국내", "국외", "판단 보류"], Field(description="중대한 이해관계 중심지.")] = "판단 보류",
    habitual_abode: Annotated[Literal["국내", "국외", "양쪽", "판단 보류"], Field(description="일상적 거소.")] = "판단 보류",
    nationality: Annotated[Literal["대한민국", "외국", "복수국적", "미입력"], Field(description="국적. 미입력 시 4단계 보류 → 판정 보류.")] = "미입력",
    notes: Annotated[str, Field(description="추가 참고사항.")] = "",
) -> dict:
    """residency_check 결과 + rules.md를 Solar Pro 4에 넣어 판정 검토 보고서(마크다운) 작성.

    언제: residency_check 결과를 더 상세한 서술형 판정 검토 보고서(report_template.md 형식)로 만들 때.
    Solar 선택 구조(기존 korean-tax-mcp와 동일): UPSTAGE_API_KEY(클라우드) 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL(온프렘) 설정 시 Solar가 보고서 작성,
    키 없으면 친절한 안내 + residency_check 결과만 반환.
    결론: 보고서 결론은 residency_check 결과를 바꾸지 못함(Solar는 서술만, 판정은 코드).
    읽기 전용, 외부 호출: tax_treaty·rules.md 읽기·Solar 호출(키 있을 때만).
    """
    # 1) residency_check 먼저 실행
    check_result = residency_check(
        judgment_year=judgment_year, domestic_stay_days=domestic_stay_days,
        entry_dates=entry_dates, exit_dates=exit_dates,
        temporary_exit_days=temporary_exit_days,
        temporary_exit_reason=temporary_exit_reason,
        family_in_korea=family_in_korea, family_desc=family_desc,
        domestic_assets=domestic_assets, asset_desc=asset_desc,
        job_needs_183_days=job_needs_183_days,
        domestic_business_activity=domestic_business_activity,
        economic_activity_desc=economic_activity_desc,
        foreign_nationality=foreign_nationality,
        foreign_permanent_residency=foreign_permanent_residency,
        foreign_nationality_desc=foreign_nationality_desc,
        dispatched_by_korean_company=dispatched_by_korean_company,
        local_hire_not_dispatch=local_hire_not_dispatch,
        dispatch_desc=dispatch_desc,
        public_official_overseas=public_official_overseas,
        overseas_job_desc=overseas_job_desc,
        treaty_country=treaty_country,
        treaty_country_is_resident=treaty_country_is_resident,
        treaty_country_resident_desc=treaty_country_resident_desc,
        permanent_home=permanent_home, permanent_home_desc=permanent_home_desc,
        center_of_vital_interests=center_of_vital_interests,
        habitual_abode=habitual_abode,
        nationality=nationality,
        notes=notes,
        lang=LANG.get(),
    )

    # 2) Solar 설정 확인
    _lang = LANG.get()
    mode = solar.mode()
    if mode == "host_ai":
        # 키 없음 → 안내 + check 결과만 반환
        lang_note = (
            "한국어 안내: Upstage API 키(UPSTAGE_API_KEY) 또는 온프렘 Solar(KOREAN_TAX_MCP_SOLAR_BASE_URL) 설정 후 "
            "다시 실행하면 판정 검토 보고서를 작성합니다. 현재는 키 없이 residency_check 결과만 반환합니다. "
            "보고서 결론은 residency_check 결과를 바꾸지 않습니다."
        ) if _lang == "ko" else (
            "English: Set UPSTAGE_API_KEY (Upstage cloud) or KOREAN_TAX_MCP_SOLAR_BASE_URL (on-prem Solar) "
            "and run again to get the review report. Without a key, only the residency_check result is returned. "
            "The report conclusion cannot change the residency_check result."
        )
        return {
            "mode": "host_ai",
            "안내": lang_note,
            "residency_check 결과": check_result,
            "Solar 설정 방법": "export UPSTAGE_API_KEY=발급키  또는  export KOREAN_TAX_MCP_SOLAR_BASE_URL=http://온프렘주소/v1",
            "AI 생성 표시 안내": "판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요.",
        }

    # 3) Solar 호출 → 보고서 작성
    rules_text = _RULES_TEXT if _RULES_TEXT and not _RULES_TEXT.startswith("(") else "(rules.md 읽기 실패)"
    prompt = (
        f"[residency_check 판정 결과]\n"
        + "\n".join(f"{k}: {v}" for k, v in check_result.items())
        + f"\n\n[판정 규칙(rules.md)]\n{rules_text[:8000]}"
        + "\n\n위 판정 결과와 규칙을 근거로 report_template.md 형식의 판정 검토 보고서(마크다운)를 작성하라. "
        "결론은 위 residency_check 결과를 바꾸지 말고, 그 결과를 서술적으로 풀어서 부기하라. "
        "가상 사례면 '본 사례는 가상(합성) 데이터 기반 검토 보조 자료' 안내문을 맨 위에 한 번 넣는다. "
        "마지막에 '조세 전문가 확인 필요' 디스클레이머를 포함하라."
    )

    try:
        report_md = solar.chat_json(prompt, max_tokens=8192).get("0", "")
        if not report_md:
            raise RuntimeError("Solar 응답이 비어 있음")
    except Exception as e:
        return {
            "mode": mode,
            "오류": f"Solar 보고서 생성 실패: {e}",
            "residency_check 결과": check_result,
        }

    return {
        "mode": mode,
        "solar": solar.where(_lang),
        "보고서": report_md,
        "residency_check 결과": check_result,
        "AI 생성 표시": "이 결과의 판단·요약·번역 문장은 생성형 AI(Upstage Solar Pro 4)가 작성했습니다. 근거 원문과 대조해 확인하세요.",
        "주의": "보고서는 서술만 제공할 뿐 residency_check의 판정 결과를 바꾸지 않는다. 판정은 코드(규칙 기반)로 고정된다.",
    }


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
