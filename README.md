# korean-tax-mcp — Korea Tax Law MCP (한국 세법)

<!-- mcp-name: io.github.UpstageAI/korean-tax-mcp -->

![데모: 법인세법 제52조 인용 해석 조회](https://raw.githubusercontent.com/UpstageAI/korean-tax-mcp/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/korean-tax-mcp)](https://pypi.org/project/korean-tax-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/) · [English](README-EN.md)

> **0.7.0부터 업스테이지 Solar Pro 4로 개발합니다.** (0.6.0까지는 Solar Pro 4 이전 개발분) 거주자 판정(`residency_check`·`residency_report`), 조세조약 키워드 동의어, 조회 안정화(재시도·캐시·인증키 가림)는 Solar Pro 4(Solar Code CLI)가 코드를 작성하고, Solar Pro 4 기반 코드 리뷰(CodeSolar)가 PR을 검토했으며, Claude가 테스트로 교차 검증했습니다.

**Korea (South Korea) tax law for AI agents.** Search National Tax Service rulings, court and Tax Tribunal decisions, basic rules, execution standards and Korea's tax treaties (96 countries); read statutes as in force on any past date with the Act → Decree → Rule chain; bundle everything that applied in a given tax year; verify citations in a draft; and run a rule-based 3-stage residence/non-residence determination (`residency_check`) with an optional Solar review report (`residency_report`). 20 tools, read-only, no API key needed for lookups. Every tool supports `lang="en"` for English output (official English treaty and statute texts; your AI translates summaries by default; optional Upstage Solar machine translation). → [English README](README-EN.md)

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
- **사실관계 대조** — 우리 주장과 해석·판례가 지지·반대·구별 필요인지 (기본: 사용자 AI가 판단, 선택: Upstage Solar)

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
| `UPSTAGE_API_KEY` (선택) | 없어도 `compare_with_case`(사실관계 대조)·`compare_outcomes` `explain=True`(승패 요약)·`lang="en"`(영문)은 동작 — 원문 발췌와 판단 안내를 돌려주고 사용자 AI가 판단·번역(`mode: "host_ai"`). 설정하면 Solar가 대조·요약·번역(`mode: "solar_cloud"`) | [console.upstage.ai](https://console.upstage.ai) |
| `KOREAN_TAX_MCP_SOLAR_BASE_URL` (선택) | 망분리 환경에서 기관 내부 Solar로 위 기능 수행(`mode: "solar_onprem"`) | — |

> **데이터 전송 안내** — 기본 동작은 법제처·국세청 공개 API만 호출하며, AI 판단·요약·번역(사실관계 대조, 승패 요약, 영문 번역)은 사용자 AI가 수행합니다. Upstage로 전송되는 내용은 없습니다. 선택: `UPSTAGE_API_KEY`를 설정하면 Solar가 대조·요약·번역을 수행하며, 이때 입력 내용이 Upstage API(api.upstage.ai)로 전송되니 **개인정보 등 민감정보는 넣지 마세요**. 망분리 환경에서는 `KOREAN_TAX_MCP_SOLAR_BASE_URL`로 기관 내부 Solar에 연결하면 외부 전송 없이 사용할 수 있습니다.

## 면책

이 도구의 결과는 **세무 자문이 아닙니다**. 세법 근거를 찾아 보여 주는 참고 자료이며, 실제 신고·세무조사·불복 판단은 세무사·회계사·변호사 등 전문가에게 확인하세요. 해석·판례·조문은 원문 링크로 확인하세요.

## AI 사용 고지

- **조회·검색·거주자 규칙 판정**(`search_tax_rulings`, `get_tax_ruling`, `law_article`, `residency_check` 등)은 코드로 동작합니다 — 생성형 AI가 개입하지 않습니다.
- **생성형 AI가 작성하는 결과**: 사실관계 대조(`compare_with_case`), 승패 요약(`compare_outcomes` `explain=True`), 영문 번역(`lang="en"`), 거주자 판정 보고서(`residency_report`)는 생성형 AI(기본: 사용자 AI, 선택: Upstage Solar Pro 4)가 작성합니다.
- Solar가 작성한 결과(`mode: "solar_cloud"` 또는 `"solar_onprem"`)에는 결과에 `AI 생성 표시` 필드가 함께 반환됩니다. 이 표시의 문구는 AI 기본법 제31조에 따른 것입니다.
- 사용자 AI(`mode: "host_ai"`)가 판단하는 경우는 결과에 AI 생성 표시가 붙지 않으며, 대신 안내 문구에 "판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요"가 포함됩니다. 실제 표시는 사용자 측 AI 도구에서 수행하세요.

## 도구

| 도구 | 하는 일 |
|---|---|
| `search_tax_rulings` | 해석·판례 검색 (세목·종류·기간·최신순/정확도순) |
| `get_tax_ruling` | 본문 전문 — 사실관계·질의·회신 / 주문·이유, 관련 조문 |
| `rulings_by_article` | 특정 조문을 인용한 해석·판례 |
| `basic_rules` | 국세 기본통칙 전문 (조문별) |
| `execution_standards` | 세법집행기준 항목·쪽·링크 |
| `casebook_search` | 2025 세법해석 사례집 검색 |
| `find_article` | **조문 위치 찾기** — 조문 번호를 모를 때 키워드로 상위 n개 조회(제목·본문 키워드 점수). 결과: [{법령, 조, 제목, 적용 시행일, 일치 문장}], 다음 단계: law_article로 해당 항만 조회. LAW_OC 필요. |
| `law_article` | 시점별 조문 원문, 3단 위임, 통칙·집행기준 함께. 긴 조문(4,000자 초과)은 keyword(키워드가 든 항만) 또는 paragraph(특정 항)로 필요한 항만 조회 — 둘 다 없으면 항 목록·안내 반환. |
| `compare_with_case` | 사실관계·논리 대조 (지지·반대·구별 필요) — 기본은 후보 원문 발췌+판단 안내를 반환해 사용자 AI가 판정, Solar 설정 시 Solar 판정 |
| `research_issue` | **그 해 기준 묶음** — 사업연도·과세기간 종료일 기준 조문 3단·통칙·집행기준·해석, 현행 대비 조문 변경, 해석마다 당시 조문과 같은지 표시 |
| `treaty_withholding_rates` | **조약별 원천징수 제한세율** — 배당·이자·사용료 세율과 지분 요건, 근거 조항 원문 |
| `search_forms` | **별표·서식** — 기준내용연수표·상각률표, 신고서·명세서·통지서 |
| `article_history` | **조문 개정 이력·시행 예정 개정** — 언제 바뀌었고 곧 바뀌는지 |
| `tax_treaty` | **조세조약** 96개국 조문 (국문·영문, 키워드로 배당·고정사업장 등) |
| `search_nts_publications` | **국세청 발간책자 본문 검색** — 이전가격·APA 연차보고서·해외진출기업 세무 가이드 등 |
| `search_local_documents` | **내 PC의 PDF 검색** — OECD 이전가격 지침처럼 각자 받은 자료를 쪽 단위로 |
| `verify_citations` | **인용 검증** — 초안의 문서번호·조문이 실제로 있는지 (지어낸 번호·없는 조문 찾기) |
| `residency_check` | **거주자·비거주자 3단계 판정** (규칙 기반, 외부 호출 없이 동작) — 소득세법 §1의2·시행령 §2·§3·§4로 주소/거소/파견 특례 판정, 이중거주자 여부(증명책임: 대법원 2006두3964), 조세조약 tie-break(항구적 주거 → 중대한 이해관계 중심지 → 일상적 거소 → 국적 → 상호합의)까지. 입력: 판정 연도, 국내 체류일수 또는 입국·출국 날짜 목록(입국 다음날~출국일 자동 계산, 일시 출국 포함), 국내 가족·자산·직업, 외국 국적·영주권, 파견 vs 현지채용 구분, 상대국·조세조약·항구적 주거·중대한 이해관계 중심지·일상적 거소·국적. rules.md 판례 top3(사실관계 키워드 매칭, 판결요지 요약) 첨부. 6-4절(찾지 못함/추정) 판례는 인용하지 않음. 법리(대법원 92누11695: 국내 생활관계만으로 판단) 명시. `lang` 지원. |
| `residency_report` | **residency_check 결과 + rules.md를 Solar Pro 4에 넣어 판정 검토 보고서 작성** (report_template.md 형식). Solar 선택 구조 기존과 동일: 키 없으면 안내 + residency_check 결과만 반환, 키 있으면 Solar가 보고서 작성. 결론은 residency_check 결과를 바꾸지 못함(Solar는 서술만, 판정은 코드). |

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
