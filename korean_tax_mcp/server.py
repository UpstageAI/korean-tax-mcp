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

from mcp.server.mcpserver import MCPServer

from . import casebook, law, ntis

mcp = MCPServer(
    "korean-tax-mcp", title="한국 세법 근거",
    instructions="한국 세법 쟁점의 근거(국세청 해석·판례·통칙·집행기준·조문)를 찾는다. search_tax_rulings로 넓게 찾고, get_tax_ruling으로 본문을 읽고, "
                 "조문 단위로는 rulings_by_article·basic_rules·law_article을 쓴다. 문서번호는 결과에 있는 것만 인용하고, "
                 "해석·판례는 회신·선고 당시 법 기준이므로 적용 연도의 조문(law_article as_of)과 대조하라고 안내한다.")

TAXES = tuple(ntis.TAX_CODES)


def _err(e): return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def search_tax_rulings(query: str, tax: str | None = None, kinds: list[str] | None = None, sort: str = "최신",
                       since: str = "", until: str = "", n: int = 10) -> dict:
    """국세법령정보시스템에서 세법 해석·판례를 찾는다.
    query: 쟁점 키워드(예: '업무무관 가지급금 인정이자', '폐업자 세금계산서 매입세액').
    tax: 세목 — 법인·부가·소득·양도·상증·국기·국징·조특·국조·종부.
    kinds: 해석(질의회신·과세기준자문·사전답변) · 판례(법원 판례·조세심판·이의·심사). 기본 둘 다.
    sort: 최신 | 정확도. since/until: 등록일 YYYYMMDD. n: 종류별 최대 건수(30).
    → [{구분, 문서번호, 제목, 요지, 세목, 일자, id, 링크}] — 본문은 get_tax_ruling(id)."""
    if tax and tax not in TAXES: return {"error": f"tax는 {TAXES} 중 하나"}
    kinds = tuple(kinds or ["해석", "판례"])
    if any(k not in ntis.KINDS for k in kinds): return {"error": "kinds: 해석 | 판례"}
    if sort not in ("최신", "정확도"): return {"error": "sort: 최신 | 정확도"}
    try:
        return {"결과": ntis.search(query, kinds, tax, sort, max(1, min(int(n), 30)), re.sub(r"\D", "", since), re.sub(r"\D", "", until)),
                "주의": "해석·판례는 회신·선고 당시 법 기준 — 적용 연도 조문과 대조"}
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_tax_ruling(id: str) -> dict:
    """해석·판례 본문 전문 — 질의회신은 사실관계·질의·회신, 판례·결정은 주문·이유, 관련 조문 목록. id: search 결과의 id."""
    try: return ntis.document(id)
    except Exception as e: return _err(e)


@mcp.tool()
def rulings_by_article(law_name: str, article: str, kinds: list[str] | None = None, tax: str | None = None,
                       keyword: str = "", sort: str = "최신", n: int = 10) -> dict:
    """특정 조문을 관련 법령으로 인용한 해석·판례 모음(예: 법인세법 제52조 → 부당행위계산 질의회신·판례).
    law_name: '법인세법' 등 세법 이름. article: '제52조'. keyword: 추가 키워드."""
    kinds = tuple(kinds or ["해석", "판례"])
    if any(k not in ntis.KINDS for k in kinds): return {"error": "kinds: 해석 | 판례"}
    try:
        return {"법령": law_name, "조": article, "결과": ntis.search(keyword or law_name.split()[0], kinds, tax, sort, max(1, min(int(n), 30)),
                                                                   article=article.strip(), law=law_name)}
    except Exception as e:
        return _err(e)


@mcp.tool()
def basic_rules(law_name: str, article: str = "", keyword: str = "") -> dict:
    """국세 기본통칙 전문(최신 고시본). article: 법 조문('제52조') — 그 조의 통칙 전부. keyword: 제목·본문 검색."""
    try: return ntis.basic_rules(law_name, article, keyword)
    except Exception as e: return _err(e)


@mcp.tool()
def execution_standards(law_name: str, article: str = "", keyword: str = "") -> dict:
    """세법집행기준 항목(최신 발간본) — 번호·제목·책자 쪽·링크(본문은 국세법령정보시스템 책자 뷰어)."""
    try: return ntis.exec_standards(law_name, article, keyword)
    except Exception as e: return _err(e)


@mcp.tool()
def casebook_search(query: str, area: str | None = None, k: int = 5) -> dict:
    """국세청 「2025 세법해석 사례집」 96건에서 쟁점 검색 — 문서번호·쟁점·결론·쪽. 본문은 search_tax_rulings(문서번호)로."""
    if area and area not in casebook.AREAS: return {"error": f"area는 {casebook.AREAS} 중 하나"}
    return {"결과": casebook.search(query, area, max(1, min(int(k), 10)))}


@mcp.tool()
def law_article(law_name: str, article: str, as_of: str = "", with_delegation: bool = False, with_rules: bool = False) -> dict:
    """조문 원문 — as_of(YYYYMMDD)에 시행 중이던 연혁본(세액은 사실 발생 시점 법령 적용). LAW_OC 필요.
    with_delegation: 법률 조문에 연결된 시행령·시행규칙 위임 조문 전부(3단).
    with_rules: 그 조의 기본통칙 전문과 집행기준 항목도 함께."""
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


@mcp.tool()
def compare_with_case(facts: str, our_view: str, tax: str | None = None) -> dict:
    """우리 사실관계·논리를 국세청 해석·판례와 대조해 항목마다 지지 / 반대 / 구별 필요를 판정(Solar). UPSTAGE_API_KEY 필요.
    facts: 누가·언제·무엇을·얼마. our_view: 우리 주장(과세 논리 또는 납세자 주장)."""
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
