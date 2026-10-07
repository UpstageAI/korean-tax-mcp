# korean-tax-mcp — Korea Tax Law MCP (한국 세법)

<!-- mcp-name: io.github.seungmiyoon/korean-tax-mcp -->

![데모: 법인세법 제52조 인용 해석 조회](https://raw.githubusercontent.com/seungmiyoon/korean-tax-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-mcp)](https://pypi.org/project/korean-tax-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) · [English](README-EN.md)

**Korea (South Korea) tax law for AI agents.** Search National Tax Service rulings, court and Tax Tribunal decisions, basic rules, execution standards and Korea's tax treaties (96 countries); read statutes as in force on any past date with the Act → Decree → Rule chain; bundle everything that applied in a given tax year; and verify citations in a draft. 13 tools, read-only, no API key needed for lookups. Every tool supports `lang="en"` for English output (official English treaty and statute texts; machine-translated summaries via Upstage Solar). → [English README](README-EN.md)

---

> 세법 쟁점을 AI에 물으면, 국세청 해석·판례·기본통칙·조문을 문서번호와 함께 가져옵니다.

**이렇게 물어보세요**

- "법인세법 제52조를 인용한 최근 질의회신·판례 보여줘"
- "폐업자에게 받은 세금계산서 매입세액 공제 — 관련 판례 본문 요약해줘"
- "가지급금 인정이자 기본통칙이랑 집행기준 같이 보여줘"
- "2023년 12월 31일 기준 법인세법 시행규칙 제43조 원문"
- "대표이사 무상 대여, 인정이자 익금산입 논리 — 지지·반대 판례 대조해줘"
- "2019 사업연도 기준으로 법인세법 제52조 관련 조문·통칙·해석 정리해줘"
- "이 의견서 초안에 인용된 문서번호랑 조문 실제로 있는지 검증해줘"
- "중국 법인에 배당하면 조약상 몇 %야? 근거 조항도"
- "법인세법 제55조 최근에 언제 바뀌었어? 시행 예정 개정 있어?"
- "국제거래명세서 서식 찾아줘"
- "국세청 책자에서 정상가격 산출방법 설명 찾아줘"

**설치 한 줄** — `claude mcp add korean-tax -- uvx korean-tax-mcp`

한국 세법 근거를 찾는 MCP 서버입니다. Claude·Cursor 같은 AI 도구에 붙이면 세법 쟁점을 물을 때 국세청 해석·판례·통칙·조문을 문서번호와 함께 찾아 줍니다.

- 국세청 **질의회신·과세기준자문·사전답변**, 법원 **판례**·**조세심판**·이의·심사 — 최신순 검색과 본문 전문
- **조문별 모음** — "법인세법 제52조를 인용한 해석·판례"
- **국세 기본통칙** 전문, **세법집행기준** 항목
- **시점별 조문** — 그날 시행 중이던 조문, 법률 → 시행령 → 시행규칙 위임 체계
- 국세청 「2025 세법해석 사례집」 96건 색인
- **사실관계 대조** — 우리 주장과 해석·판례가 지지·반대·구별 필요인지 (Upstage Solar)

## 설치

[uv](https://docs.astral.sh/uv/)가 있으면 설치 없이 바로 실행됩니다.

```json
{
  "mcpServers": {
    "korean-tax": {
      "command": "uvx",
      "args": ["korean-tax-mcp"],
      "env": { "LAW_OC": "법제처 OC(선택)", "UPSTAGE_API_KEY": "Upstage 키(선택)" }
    }
  }
}
```

Claude Code: `claude mcp add korean-tax -- uvx korean-tax-mcp`

## 키

| 키 | 필요한 도구 | 발급 |
|---|---|---|
| 없음 | 해석·판례 검색과 본문, 조문별 모음, 기본통칙, 집행기준, 사례집, 인용 검증(문서번호) | — |
| `LAW_OC` | `law_article`, `research_issue`, `verify_citations`(조문) — 시점별 조문·3단 위임 | [open.law.go.kr](https://open.law.go.kr) 무료 신청 |
| `UPSTAGE_API_KEY` | `compare_with_case` (사실관계 대조), `compare_outcomes`의 `explain=True` (승패 요약), `lang="en"` 영문 번역 | [console.upstage.ai](https://console.upstage.ai) |

> **데이터 전송 안내** — 기본 검색 기능은 법제처·국세청 공개 API만 호출하며 Upstage로 전송되는 내용은 없습니다. Solar 기능(사실관계 대조, 승패 요약, 영문 번역)은 `UPSTAGE_API_KEY`를 설정한 경우에만 동작하고, 이때 입력 내용이 Upstage API(api.upstage.ai)로 전송되니 **개인정보 등 민감정보는 넣지 마세요**. 망분리 환경에서는 `KOREAN_TAX_MCP_SOLAR_BASE_URL`로 기관 내부 Solar에 연결하면 외부 전송 없이 사용할 수 있습니다.

## 도구

| 도구 | 하는 일 |
|---|---|
| `search_tax_rulings` | 해석·판례 검색 (세목·종류·기간·최신순/정확도순) |
| `get_tax_ruling` | 본문 전문 — 사실관계·질의·회신 / 주문·이유, 관련 조문 |
| `rulings_by_article` | 특정 조문을 인용한 해석·판례 |
| `basic_rules` | 국세 기본통칙 전문 (조문별) |
| `execution_standards` | 세법집행기준 항목·쪽·링크 |
| `casebook_search` | 2025 세법해석 사례집 검색 |
| `law_article` | 시점별 조문 원문, 3단 위임, 통칙·집행기준 함께 |
| `compare_with_case` | 사실관계·논리 대조 (지지·반대·구별 필요) |
| `research_issue` | **그 해 기준 묶음** — 사업연도·과세기간 종료일 기준 조문 3단·통칙·집행기준·해석, 현행 대비 조문 변경, 해석마다 당시 조문과 같은지 표시 |
| `treaty_withholding_rates` | **조약별 원천징수 제한세율** — 배당·이자·사용료 세율과 지분 요건, 근거 조항 원문 |
| `search_forms` | **별표·서식** — 기준내용연수표·상각률표, 신고서·명세서·통지서 |
| `article_history` | **조문 개정 이력·시행 예정 개정** — 언제 바뀌었고 곧 바뀌는지 |
| `tax_treaty` | **조세조약** 96개국 조문 (국문·영문, 키워드로 배당·고정사업장 등) |
| `search_nts_publications` | **국세청 발간책자 본문 검색** — 이전가격·APA 연차보고서·해외진출기업 세무 가이드 등 |
| `search_local_documents` | **내 PC의 PDF 검색** — OECD 이전가격 지침처럼 각자 받은 자료를 쪽 단위로 |
| `verify_citations` | **인용 검증** — 초안의 문서번호·조문이 실제로 있는지 (지어낸 번호·없는 조문 찾기) |

## 함께 쓰면 좋은 MCP

일반 법령 검색·판례 전반·인용 실존 검증은 류승인 주무관님의 [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)를 함께 붙여 쓰세요.
korean-law-mcp가 법령 전반을, 이 서버가 세법 해석·판례·기본통칙·집행기준을 맡는 구성입니다.

```json
{
  "mcpServers": {
    "korean-law": { "...": "korean-law-mcp 설정은 해당 저장소 README 참고" },
    "korean-tax": { "command": "uvx", "args": ["korean-tax-mcp"] }
  }
}
```

## 유의

- 해석·판례는 **회신·선고 당시 법 기준**입니다. 적용 연도 조문(`law_article`의 `as_of`)과 대조하세요.
- 국세법령정보시스템(taxlaw.nts.go.kr)의 공개 조회를 사용합니다. 서버 부담을 줄이려고 같은 요청은 1일 캐시, 호출 간격은 0.5초 이상입니다.
- 집행기준 본문은 책자(PDF)로만 제공돼 항목·쪽·링크까지만 돌려줍니다.
- 도구 결과는 검토 보조 자료이며 세무 자문이 아닙니다.

## 출처

국세청 국세법령정보시스템 · 법제처 국가법령정보 공동활용 · 국세청 「2025 세법해석 사례집」

## 라이선스

MIT © 2026 Upstage

Created by Mia(윤승미)
