# eval — Solar Pro 4 세법 객관식 종합 평가

Solar Pro 4가 **세법 MCP(korean-tax-mcp)**와 **계산 MCP(korean-tax-calc-mcp)**를 도구로 쓸 수 있을 때, 세법 객관식 문항의 정답률과 도구 호출을 측정하는 평가 도구다.

## 무엇을 재는가

- **정답률**: Solar Pro 4가 민법·세법 객관식 5지선다 문항에서 정답을 고르는 비율
- **도구 호출**: 문항당 MCP 도구 호출 횟수 (상한 15회), 중복·차단·오류 추적

도구 하나하나의 정확도는 `bench/`에서 따로 측정한다. 모델이 도구를 써서 문항 전체를 푸는 종합 평가는 이 폴더(`eval/`)에서 수행한다.

## 작동 흐름

1. **문항 로드**: `--qset`으로 지정한 JSON 파일에서 문항을 읽는다.
2. **도구 준비**: korean-tax-mcp와 korean-tax-calc-mcp 서버를 띄우지 않고 직접 import하여 도구 목록(스키마)을 얻는다. Upstage API가 거부하는 스키마 키워드는 제거한다.
3. **도구 루프 (상한 15회)**:
   - Solar Pro 4에 문항과 도구 목록을 전달하고 chat completions API를 호출한다.
   - 모델이 도구를 호출하면 실제 MCP 서버에서 결과를 받아 모델에 다시 전달한다.
   - 같은 입력 반복은 차단, 미래 날짜는 기준일로 clamping한다.
   - 15회 도달 또는 모델이 답을 주면 루프를 종료한다.
4. **답 추출**: 모델 응답 JSON에서 `answer`(1~5)와 `reason`을 파싱한다.
5. **채점**: 추출한 답과 정답을 비교해 정·오·무응답으로 기록한다.
6. **결과 저장**: 문항별 상세(raw jsonl)와 요약(summary.json)을 결과 폴더에 저장한다.

## 실행 조건

- **하네스**: HARNESS_V3=1 (중립 프롬프트 + 반복 차단) — 기본 켜짐
- **조문 찾기**: FIND_ARTICLE=1 (find_article 도구 포함) — 기본 켜짐
- **도구 상한**: 15회
- **API**: Upstage API (OpenAI 호환 엔드포인트, `api.upstage.ai`)

## 문항 파일 형식

문항 파일(`--qset`)과 정답 파일(`--anset`)은 JSON 형식이다.

**문항 파일** (`items.json`):

```json
{
  "2026": {
    "1": {
      "과목": "부가가치세",
      "본문": "문제와 보기 ①~⑤를 한 문자열로 작성\n\n① ...\n② ...\n③ ...\n④ ...\n⑤ ..."
    },
    "2": {
      "과목": "소득세",
      "본문": "..."
    }
  }
}
```

- 최상위 키: 연도 (문자열)
- 둘째 키: 문항 번호 (문자열, 정수 변환 가능)
- 값: `{"과목": "...", "본문": "..."}`
- 본문에 보기 ①~⑤를 포함한다.

**정답 파일** (`answers.json`):

```json
{
  "2026": {
    "1": 2,
    "2": 4
  }
}
```

- 값: 정답 번호 (1~5 정수)

문항에 `기준일` 필드를 추가하면 해당 문항의 기준 시점을 지정할 수 있다. 없으면 기본 기준일을 사용한다.

## 실행 방법

```bash
# 예시 문항으로 dry-run (API 호출 없이 문항 수·도구 수만 확인)
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --dry-run

# 실제 실행 (UPSTAGE_API_KEY 필수)
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42

# 연도 필터, 문항 수 제한
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --year 2026 --limit 2

# 결과 폴더 지정
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --results-dir eval/results/
```

환경변수:

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `UPSTAGE_API_KEY` | 예 | — | Upstage API 키 |
| `UPSTAGE_API_BASE_URL` | 아니오 | `https://api.upstage.ai/v1` | API 엔드포인트 |
| `LAW_OC` | 아니오 | — | 법제처 OC (조문 조회용) |
| `RESULTS_DIR` | 아니오 | `eval/results/` | 결과 폴더 |
| `HARNESS_V3` | 아니오 | `1` | 중립 하네스 켜기 |
| `FIND_ARTICLE` | 아니오 | `1` | find_article 도구 포함 |

## 결과 파일

결과 폴더(`eval/results/`)에 생성되는 파일:

- **`raw_native_direct.jsonl`**: 문항별 실행 결과. 한 줄에 한 문항. 모델 답, 정오, 근거, 도구 호출 목록, 토큰 수, 소요 시간, 도구 호출 상세 포함.
- **`summary.json`**: 조건별 요약 통계. 전체 정답률, 연도별 정답률, 문항당 평균 도구 호출·토큰·시간 포함.

## 계산 MCP 연동

이 평가는 **korean-tax-calc-mcp**(계산 MCP)와 함께 측정한다. 세법 MCP 도구뿐 아니라 법인세·소득세·부가가치세 등 계산 도구도 도구 목록에 포함되어, 모델이 계산 문제를 풀 때 계산 도구를 호출할 수 있다.

## 고지

- 이 평가 도구는 **세무대리·법률자문이 아니다**. 세법 객관식 문항에 대한 모델 응답 정확도를 측정하는 소프트웨어다.
- 문항의 본문과 모델 응답은 **Upstage API(api.upstage.ai)로 전송**된다. 개인정보 등 민감정보를 문항에 넣지 말아야 한다.
- 평가 결과는 모델의 성능을 나타낼 뿐, 실제 세법 해석이나 판단을 대신하지 않는다.
- 실제 세법 판단과 신고는 관련 전문가에게 확인해야 한다.

## 참고

- 도구 단위 정확도: `bench/`
- MCP 패키지: `korean_tax_mcp/`, `korean_tax_calc_mcp/` (별도 레포)

Created by Mia(윤승미)
