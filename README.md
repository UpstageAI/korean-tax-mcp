# korean-tax-mcp

<!-- mcp-name: io.github.seungmiyoon/korean-tax-mcp -->

[![PyPI](https://img.shields.io/pypi/v/korean-tax-mcp)](https://pypi.org/project/korean-tax-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) · [English](README-EN.md)

> 류승인 주무관님 [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)의 세법판 — 국세청 해석·판례·기본통칙·조문을 AI에서 문서번호째로.

**이렇게 물어보세요**

- "법인세법 제52조를 인용한 최근 질의회신·판례 보여줘"
- "폐업자에게 받은 세금계산서 매입세액 공제 — 관련 판례 본문 요약해줘"
- "가지급금 인정이자 기본통칙이랑 집행기준 같이 보여줘"
- "2023년 12월 31일 기준 법인세법 시행규칙 제43조 원문"
- "대표이사 무상 대여, 인정이자 익금산입 논리 — 지지·반대 판례 대조해줘"

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
| 없음 | 해석·판례 검색과 본문, 조문별 모음, 기본통칙, 집행기준, 사례집 | — |
| `LAW_OC` | `law_article` (시점별 조문·3단 위임) | [open.law.go.kr](https://open.law.go.kr) 무료 신청 |
| `UPSTAGE_API_KEY` | `compare_with_case` (사실관계 대조) | [console.upstage.ai](https://console.upstage.ai) |

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

작성 Mia(윤승미) · Upstage

## 라이선스

MIT
