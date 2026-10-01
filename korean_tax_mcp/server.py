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

from . import casebook, law, ntis

mcp = MCPServer(
    "korean-tax-mcp", title="한국 세법 근거",
    instructions="한국 세법 쟁점의 근거(국세청 해석·판례·통칙·집행기준·조문)를 찾는다. search_tax_rulings로 넓게 찾고, get_tax_ruling으로 본문을 읽고, "
                 "조문 단위로는 rulings_by_article·basic_rules·law_article을 쓴다. 문서번호는 결과에 있는 것만 인용하고, "
                 "해석·판례는 회신·선고 당시 법 기준이므로 적용 연도의 조문(law_article as_of)과 대조하라고 안내한다.")

TAXES = tuple(ntis.TAX_CODES)
RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
Tax = Literal["법인", "부가", "소득", "양도", "상증", "국기", "국징", "조특", "국조", "종부"]
Kind = Literal["해석", "판례"]
LAW = "세법 이름(정식 명칭). 예: '법인세법', '부가가치세법', '소득세법', '상속세 및 증여세법', '국세기본법'"
ART = "조문 번호. '제52조' 또는 '제28조의2' 형식"
NTIS_NOTE = "읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시."


def _err(e): return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations=RO)
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
def get_tax_ruling(id: Annotated[str, Field(description="search_tax_rulings·rulings_by_article 결과의 id (숫자 12~20자리)")]) -> dict:
    """Get the full text of one ruling or decision. 해석·판례 1건의 본문 전문.
    언제: 검색 결과 중 인용·요약할 문서를 정한 뒤. 요지만으로 판단하지 말고 본문을 읽을 때 사용.
    반환: {문서번호, 제목, 요지, 등록일, 관련조문[], 본문(질의회신: 사실관계·질의·회신 / 판례: 주문·이유, 최대 2만 자), 링크}.
    읽기 전용. 국세법령정보시스템 공개 조회(키 불필요), 같은 요청은 1일 캐시.
    """
    try: return ntis.document(id)
    except Exception as e: return _err(e)


@mcp.tool(annotations=RO)
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
    key = os.environ.get("UPSTAGE_API_KEY", "").strip()
    if not key: raise RuntimeError("UPSTAGE_API_KEY가 없습니다 — https://console.upstage.ai 에서 발급")
    body = {"model": os.environ.get("KOREAN_TAX_MCP_MODEL", "solar-pro4"), "temperature": 0, "max_tokens": 1600,
            "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]}
    ctx = ssl.create_default_context(); ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    req = urllib.request.Request("https://api.upstage.ai/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
        return json.loads(json.loads(r.read())["choices"][0]["message"]["content"])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def compare_with_case(
    facts: Annotated[str, Field(description="사실관계: 누가·언제·무엇을·얼마 (최대 1500자 사용)")],
    our_view: Annotated[str, Field(description="우리 주장: 과세 논리 또는 납세자 주장 한두 문장")],
    tax: Annotated[Tax | None, Field(description="세목 필터 (선택)")] = None,
) -> dict:
    """Check your facts and argument against rulings: supports / contradicts / distinguish. 사실관계·논리를 해석·판례와 대조해 항목마다 지지·반대·구별 필요를 판정.
    언제: 주장의 근거와 반대 사례를 한 번에 점검할 때(의견서·불복 검토). 단순 검색은 search_tax_rulings.
    반환: {해석: [{문서번호, 구분, 관계, 이유, 사실관계 차이, 링크}], 요약, 주의}. 문서번호는 검색 결과에 있는 것만.
    읽기 전용. Upstage Solar 호출 — 환경변수 UPSTAGE_API_KEY 필요(호출마다 토큰 비용), 약 10초.
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
    return {"해석": rows, "요약": j.get("요약", ""), "주의": "Solar 판정은 검토 보조 — 본문 확인 후 인용"}


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
