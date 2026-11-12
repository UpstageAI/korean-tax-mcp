# korean-tax-mcp — Korea Tax Law MCP (한국 세법)

<!-- mcp-name: io.github.UpstageAI/korean-tax-mcp -->

![데모: 사실관계 입력 → 쟁점별 법리(특수관계인·사택 제공 예외·부당행위계산) → 유사 심판례 → 한글(HWPX) 검토서 초안](https://raw.githubusercontent.com/UpstageAI/korean-tax-mcp/main/docs/demo.gif)

<sub>영상: Claude 앱(코워크) + 이 서버 + [korean-report-hwpx](https://github.com/UpstageAI/korean-report-hwpx). '대표이사 사택 제공' 사례(실제 심판례 조심2017부0367을 바탕으로 회사명·숫자만 바꾼 예시)로 요건별 법리를 따지고 유사 심판례를 붙여 검토서 초안까지 만듭니다(2026-11-08 공개).</sub>

[![PyPI](https://img.shields.io/pypi/v/korean-tax-mcp)](https://pypi.org/project/korean-tax-mcp/) [![MCP Registry](https://img.shields.io/badge/MCP%20Registry-korean--tax--mcp-blue)](https://registry.modelcontextprotocol.io/v0/servers?search=korean-tax-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/) · [English](README-EN.md)

> **작성 주체(정확한 고지):** 0.7.0부터 0.11.1까지(2026-10-13부터 10-19까지)은 **Solar Pro 4**(Solar Work CLI)가 코드를 쓰고 CodeSolar가 리뷰, Claude가 테스트로 교차 검증했습니다(0.10.0은 목차만 Solar, 나머지는 Claude 작성). **0.12.0(2026-10-28)부터는 기존 세법 MCP 뼈대는 Solar Pro 4 그대로이고, 점검·버그 수정·보완은 Claude(Anthropic)가 작성**하며 CodeSolar가 리뷰합니다. **0.12.15(2026-11-10)부터 보강은 Claude가 명세·정답 테스트를 먼저 쓰고 Solar Pro 4가 뼈대를 구현한 뒤 Claude가 검수·보완합니다**(커밋별 작성자 표기). 버전별 작성 주체는 [CHANGELOG](CHANGELOG.md) 각 절 머리에 적혀 있습니다. 도구 27개.

**Korea tax law for AI agents** — statutes as in force on any date, NTS rulings and court decisions, basic rules, treaties. [English](README-EN.md)

---

> 세법 쟁점을 AI에 물으면, 그 시점의 조문과 국세청 해석·판례를 문서번호와 함께 가져옵니다.

## 작동 방식

```mermaid
flowchart LR
  Q["AI의 요청<br/>법령·조문·기준일·키워드"] --> V["시행본 고르기<br/>기준일에 시행 중인 판"]
  V --> P["조문 정리<br/>항·호 분리, 단서 표시"]
  P --> L["위임 연결<br/>법→시행령→시행규칙"]
  Q --> S["해석·판례 검색<br/>쟁점별로 나눠 찾기·문서번호·요지"]
  Q --> Y["그 해 기준 묶음<br/>조문·통칙·해석, 현행과 바뀐 점"]
  Q --> C["대조·판정<br/>원문과 글자 비교"]
  V -.-> A1[("법제처 Open API")]
  L -.-> A1
  S -.-> A2[("국세법령정보시스템")]
  Y -.-> A1
  Y -.-> A2
  P --> R["결과<br/>원문·시행일·문서번호·링크"]
  L --> R
  S --> R
  Y --> R
  C --> R
```

1. **조문** — 법제처에서 기준일에 시행 중이던 판을 골라 원문을 주고, 단서 구절과 위임 조문(법→시행령→시행규칙)을 함께 붙입니다. 기준일을 안 주면 오늘 기준입니다. 법령에 없는 이름(외국환거래규정·국세청 고시 같은 행정규칙)은 현행본으로 자동 조회합니다(연혁 없음).
2. **해석·판례** — 국세법령정보시스템에서 질의회신·판례·심판례·통칙·집행기준을 문서번호·링크로 찾습니다. 쟁점이 여러 개인 질문은 쟁점마다 따로 검색합니다(`search_rulings_by_issue`). 취득세·재산세 같은 지방세 질의면 조세심판원 결정례(법제처 특별행정심판재결례)를 같은 호출에 덧붙입니다(`search_tribunal_decisions`·`get_tribunal_decision`).
3. **그 해 기준** — 세목별 기준일(사업연도 말일, 양도일 등)의 조문·해석을 모으고 현행과 바뀐 점을 표시합니다. 손익 귀속·공급시기 같은 시기 규칙은 `timing_rules` 표로 먼저 봅니다.
4. **대조** — 진술·보기를 원문과 글자 단위로 비교해 다른 숫자·단서를 표시합니다.

판단과 결론은 사용자의 AI와 전문가 몫입니다. 이 서버는 근거를 가져옵니다.

## 이렇게 물어보세요

- "2023년 12월 31일 기준 법인세법 시행규칙 제43조 원문"
- "법인세법 제52조를 인용한 최근 질의회신·판례 보여줘"
- "2019 사업연도 기준으로 법인세법 제52조 관련 조문·통칙·해석 정리해줘"
- "가지급금 인정이자와 업무무관 지급이자 손금불산입, 두 쟁점 해석·판례를 각각 찾아줘"
- "'경조금은 건당 10만원까지 증빙 없이 손금'이라는 말, 2026 시행령 제41조 원문과 맞아?"
- "미국 시민권자 대표이사, 작년 국내 체류 200일, 가족은 미국 — 거주자야?"

## 설치

```bash
claude mcp add korean-tax -- uvx korean-tax-mcp
```

```json
{
  "mcpServers": {
    "korean-tax": {
      "command": "uvx",
      "args": ["korean-tax-mcp"],
      "env": { "LAW_OC": "법제처 OC(선택)", "UPSTAGE_API_KEY": "Upstage 키(선택)" }
    },
    "korean-tax-calc": { "command": "uvx", "args": ["korean-tax-calc-mcp"] }
  }
}
```

두 번째 줄의 [korean-tax-calc-mcp](https://github.com/UpstageAI/korean-tax-calc-mcp)는 짝 서버입니다 — 여기서 찾은 조문·해석을 근거로 세액·한도·판정을 코드로 계산하고(104개 도구), 법정서식 엑셀까지 만듭니다. 같이 두면 **근거 찾기 → 계산 → 서식**이 한 대화에서 이어집니다. 조문·판례만 쓰려면 첫 줄만 넣어도 됩니다.

| 키 | 쓰는 곳 |
|---|---|
| 없음 | 해석·판례·통칙·집행기준·사례집·조약·서식·책자 검색, 승패 비교, 거주자 판정 |
| `LAW_OC` ([open.law.go.kr](https://open.law.go.kr) 무료) | 조문 조회·찾기·개정 이력, 그 해 기준 묶음, 진술·보기 대조, 인용 검증(조문) |
| `UPSTAGE_API_KEY` (선택) | 사실관계 대조·승패 요약·영문 번역을 Solar가 수행. 없으면 사용자 AI가 수행 |
| `KOREAN_TAX_MCP_SOLAR_BASE_URL` (선택) | 망분리 환경에서 기관 내부 Solar 사용 |

> **데이터 전송 안내** — 기본 동작은 법제처·국세청 공개 API만 호출하며, AI 판단·요약·번역(사실관계 대조, 승패 요약, 영문 번역)은 사용자 AI가 수행합니다. Upstage로 전송되는 내용은 없습니다. 선택: `UPSTAGE_API_KEY`를 설정하면 Solar가 대조·요약·번역을 수행하며, 이때 입력 내용이 Upstage API(api.upstage.ai)로 전송되니 **개인정보 등 민감정보는 넣지 마세요**. 망분리 환경에서는 `KOREAN_TAX_MCP_SOLAR_BASE_URL`로 기관 내부 Solar에 연결하면 외부 전송 없이 사용할 수 있습니다.

## 함께 쓰면 좋은 지침

AI가 도구를 언제 부르고, 도구의 답을 언제 믿을지 정해 주는 다섯 줄입니다. 서버 안내문(instructions)에도 같은 규칙이 들어 있지만, 클라이언트에 따라 안내문을 약하게 반영하거나 읽지 않습니다. 아래를 시스템 프롬프트에 넣으면 더 잘 지킵니다(Claude Desktop 프로젝트 지침, Claude Code의 `CLAUDE.md`, 그 밖의 맞춤 지침).

```text
세금 질문에 답할 때 korean-tax-mcp와 korean-tax-calc-mcp를 이렇게 쓴다.
1. 숫자 하나, 판단 하나마다 쓸 수 있는 도구가 있는지 먼저 찾는다. 이름을 모르면 find_tool로 찾고, 귀속·공급시기는 timing_rules를 먼저 본다.
2. 도구가 있으면 손으로 풀기 전에 도구부터 부른다.
3. 도구의 답과 내 계산이 다르면 바로 고르지 않는다. 입력을 다시 확인하고, 차이를 가르는 조문을 law_article로 열어 요건을 사실관계에 하나씩 맞춰 본다.
4. 조문에서 도구가 틀렸다는 근거를 못 찾으면 도구의 답을 따른다. 다른 값을 쓰면 그 이유(입력 오류 또는 조문 번호)를 한 줄 적는다.
5. 답이 두 개 나오면(안분 전후, 전체와 과세분 등) 질문이 묻는 하나만 답한다.
```

## 도구 (33개)

| 묶음 | 도구 | 하는 일 |
|---|---|---|
| 조문 | `law_article` | 기준일 시행본 원문, 목차, 위임 조문, 단서 구절 |
| | `find_article` | 조문 번호를 모를 때 키워드로 찾기 |
| | `article_history` | 언제 바뀌었는지, 시행 예정 개정 |
| | `article_addenda` | 부칙 — 개정 조문이 언제·어느 소득분부터 적용되는지(시행일·적용례·경과조치) |
| 해석·판례 | `search_tax_rulings` | 질의회신·판례·심판례 검색 |
| | `search_rulings_by_issue` | 쟁점이 여러 개인 질문을 쟁점별로 나눠 검색, 쟁점마다 정확도순 + 최근 문서 |
| | `get_tax_ruling` | 문서 본문 전문 |
| | `search_tribunal_decisions` | 조세심판원 재결례(특별행정심판재결례) 검색 — 국세·지방세 |
| | `get_tribunal_decision` | 조세심판원 재결례 1건 본문 |
| | `rulings_by_article` | 특정 조문을 인용한 해석·판례 |
| | `basic_rules` | 국세 기본통칙 전문 |
| | `execution_standards` | 세법집행기준 항목·쪽·링크 |
| | `casebook_search` | 2025 세법해석 사례집(96건) |
| 그 해 기준·검증 | `research_issue` | 세목별 기준일의 조문·통칙·해석 묶음, 현행 대비 변경 |
| | `timing_rules` | 시기 규칙표 — 납세의무 성립·손익 귀속·소득별 수입시기·부가 공급시기 |
| | `transfer_pricing_guide` | 정상가격 산출방법 안내 — 국외특수관계인 거래의 적용 규정(국조법·법인세법 제52조), 산출방법·선택 기준·거래 유형별 특칙 |
| | `transfer_pricing_report` | 정상가격 검토 보고서 뼈대 — 개별기업보고서(국조칙 별지 제13호) 목차 24개 항목별 작성방법·준비 자료·근거·OECD 지침 문단·결정례 |
| | `transfer_pricing_far` | 기능·자산·위험 분석 — 위험 부담자 결정(시행규칙 제10조), 분석대상 당사자 후보, 산출방법 적합성·이익 지표(제6조) |
| | `sme_tax_incentives_guide` | 중소기업 조세지원 안내 — 창업중소기업 세액감면·창업벤처·특별세액감면·결손금 소급공제의 적용 여부, 감면율, 근거 조문(창업일·지역·업종 기준) |
| | `transfer_pricing_cases` | 이전가격 쟁점별 결정례 — 납세자 승·과세관청 승 사례를 쟁점 9개별로 나란히, 보고서에 반영할 점 |
| | `oecd_tp_guidelines` | OECD 이전가격지침 2022 문단 조회·검색·국조법령 대응표(본문 1,391개 문단, 영문 원문) |
| | `verify_citations` | 초안 속 문서번호·조문이 실제로 있는지 |
| 대조·판정 | `verify_statement` | 한 문장을 원문과 글자 대조 |
| | `judge_options` | 보기 여러 개를 조문과 한 번에 대조 |
| | `compare_outcomes` | 같은 쟁점의 납세자 승·패 결정 나란히 |
| | `compare_with_case` | 우리 사실관계와 해석·판례 비교(지지·반대·구별) |
| 조약·거주자 | `tax_treaty` | 조세조약 96개국 조문(국·영문) |
| | `treaty_withholding_rates` | 배당·이자·사용료 제한세율 |
| | `residency_check` | 거주자·비거주자 3단계 판정(규칙) |
| | `residency_report` | 판정 검토 보고서(Solar) |
| 문서·서식 | `search_forms` | 별표·서식 |
| | `search_nts_publications` | 국세청 발간책자 본문 |
| | `search_local_documents` | 내 PC PDF 검색(`KOREAN_TAX_MCP_DOCS`) |

모든 도구는 `lang="en"`으로 영어 결과를 받을 수 있습니다.

## 면책

이 도구의 결과는 **세무 자문이 아닙니다**. 세법 근거를 찾아 보여 주는 참고 자료이며, 실제 신고·세무조사·불복 판단은 세무사·회계사·변호사 등 전문가에게 확인하세요. 해석·판례·조문은 원문 링크로 확인하세요.

이 도구는 **세무사법 제2조의 세무대리**(세무조정계산서 작성, 신고·불복 대리, 세무상담 등)를 수행하지 않으며, 그 업무는 세무사와 등록한 공인회계사·변호사만 할 수 있습니다(세무사법 제20조). 공개된 법령·해석·결정례 원문을 찾아 보여 주는 소프트웨어이고, 데모 화면의 "대표이사 사택 제공 검토" 같은 사례도 자료 조회·정리 기능의 시연일 뿐 사실관계 판단이나 대응 전략 제시가 아닙니다. 사실관계 판단과 대응은 세무 전문가(세무사·회계사·변호사)와 함께 확인해 주세요.

## AI 사용 고지

- **조회·검색·거주자 규칙 판정**(`search_tax_rulings`, `get_tax_ruling`, `law_article`, `residency_check` 등)은 코드로 동작합니다 — 생성형 AI가 개입하지 않습니다.
- **생성형 AI가 작성하는 결과**: 사실관계 대조(`compare_with_case`), 승패 요약(`compare_outcomes` `explain=True`), 영문 번역(`lang="en"`), 거주자 판정 보고서(`residency_report`)는 생성형 AI(기본: 사용자 AI, 선택: Upstage Solar Pro 4)가 작성합니다.
- Solar가 작성한 결과(`mode: "solar_cloud"` 또는 `"solar_onprem"`)에는 결과에 `AI 생성 표시` 필드가 함께 반환됩니다. 이 표시의 문구는 AI 기본법 제31조에 따른 것입니다.
- 사용자 AI(`mode: "host_ai"`)가 판단하는 경우는 결과에 AI 생성 표시가 붙지 않으며, 대신 안내 문구에 "판단 결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요"가 포함됩니다. 실제 표시는 사용자 측 AI 도구에서 수행하세요.

## 유의

- 해석·판례는 회신·선고 당시 법 기준입니다. 적용 연도 조문(`law_article`의 `as_of`)과 대조하세요.
- 국세법령정보시스템 공개 조회를 1일 캐시, 0.5초 간격으로 사용합니다. 집행기준은 항목·쪽·링크까지만 제공합니다.
- 일반 법령 전반은 [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)와 함께 쓰면 좋습니다.

## 평가 방법

Solar Pro 4가 이 MCP 서버들을 도구로 써서 세법 객관식 문항을 푸는 종합 평가는 `eval/` 폴더를 참고한다. 도구 하나하나의 정확도는 `bench/`에서 측정한다.

## 출처 · 라이선스

국세청 국세법령정보시스템 · 법제처 국가법령정보 공동활용 · 국세청 「2025 세법해석 사례집」

MIT © 2026 Upstage · Created by Mia(윤승미)
