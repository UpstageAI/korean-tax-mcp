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
- **도구 상한**: 15회 (RunConfig `limit_tools`로 변경 가능)
- **API**: Upstage API (OpenAI 호환 엔드포인트, `api.upstage.ai`)

### RunConfig 설정 항목

`eval/run_eval.py`는 `RunConfig` dataclass로 실행 조건을 관리한다. 프리셋(`native_direct` 등)에 환경변수 `CFG_OVERRIDE`로 JSON 덮어쓰기를 적용할 수 있다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | str | 조건 이름 (프리셋 키) |
| `system_prompt` / `user_prompt` | str | 프롬프트 상수 이름 |
| `tool_set` | str | "direct" | "tree" | "meta" | "none" |
| `limit_tools` | int | 도구 호출 상한 |
| `truncate_chars` | int \| None | 도구 결과 자름 길이 (None이면 자르지 않음) |
| `repeat_block` | bool \| str | True(일반 반복 안내) | "3rd_only"(3회째 차단) | False(비활성화) |
| `clamp_dates` | bool | 미래 날짜(기준일로 clamping) |
| `error_streak` | bool | 도구 오류 3회 연속 시 안내 메시지 추가 |
| `nudge_tool` | bool | 첫 응답에 도구 호출이 없으면 도구 사용 안내 |
| `keep_content` | bool | assistant 메시지 content 유지 여부 |
| `routing` | bool | 4단계 라우팅 활성화 (기본 False) |
| `calc_pipeline` | bool | 5단계 계산 파이프라인 활성화 (기본 False) |
| `calc_nudge` | int | 계산형 문항에서 계산 도구 미호출 시 넛지 임계값 (0=끔, 기본값 0) |
| `extra` | dict | 조건별 특수 옵션 |

**CFG_OVERRIDE 예시** — 라우팅·계산 파이프라인 켜기:

```bash
# 라우팅 + 계산 파이프라인 활성화
CFG_OVERRIDE='{"routing": true, "calc_pipeline": true}' python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42

# 계산형 넛지 활성화 (계산 도구 미호출 시 5회째에 1회 안내)
CFG_OVERRIDE='{"routing": true, "calc_nudge": 5}' python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42

# 도구 상한 12회, 3000자 자름, 3회째 차단
CFG_OVERRIDE='{"limit_tools": 12, "truncate_chars": 3000, "repeat_block": "3rd_only"}' python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42
```

라우팅 관련 상세는 `eval/data/routing_table.json`을 참고한다. 라우팅이 활성화되면 분류 호출 1회로 문항을 주제·유형(서술형/계산형)으로 분류하고, 매핑표 기반 도구만 노출한다. `expand_tools` 도구로 다른 주제 도구를 최대 2회 추가할 수 있다.

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

문항에 `기준일`(선택, YYYYMMDD) 필드를 추가하면 해당 문항의 기준 시점을 지정할 수 있다.

**기준일 우선순위**:
1. 문항에 `기준일` 필드가 있으면 그 값
2. 명령줄 `--basis-date`
3. 연도 키가 4자리 숫자면 그 연도 12월 31일 (예: "2024" → "20241231")
4. 오늘 날짜

예: 문항에 `"기준일": "20241231"`이 있으면 해당 날짜를 사용, 없으면 `--basis-date` 값을 사용, 둘 다 없으면 연도 말일을 사용한다.

## 실행 방법

```bash
# 예시 문항으로 dry-run (API 호출 없이 문항 수·도구 수만 확인)
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --dry-run

# 실제 실행 (UPSTAGE_API_KEY 필수)
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --seed 42

# 기준일을 직접 지정 (문항에 기준일 필드가 없을 때 사용)
python eval/run_eval.py --qset eval/examples/items.json --anset eval/examples/answers.json --basis-date 20230226 --seed 42

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

- **`raw_native_direct.jsonl`**: 문항별 실행 결과. 한 줄에 한 문항. 모델 답, 정오, 근거, 도구 호출 목록, 토큰 수(입력·출력 분리), 소요 시간, 도구 호출 상세, **사용한 기준일(basis_date)**, 대화 기록(messages), 실행 구성(run_config) 포함.
- **`summary.json`**: 조건별 요약 통계. 전체 정답률, 연도별 정답률, 문항당 평균 도구 호출·토큰·시간 포함.

### raw jsonl 필드

| 필드 | 설명 |
|------|------|
| `연도`, `번호`, `과목` | 문항 식별자 |
| `basis_date` | 문항 실행에 사용한 기준일 (YYYYMMDD) |
| `모델답` | 모델 응답 JSON ({answer, reason, tools_used}) |
| `정오` | "O" / "X" / "무응답" / "실행실패" / "제외" |
| `근거` | 모델 응답의 reason 필드 |
| `도구호출목록` | 도구 호출 요약 목록 (도구명[인자]) |
| `토큰수`, `입력토큰`, `출력토큰` | 누적 토큰 수 (입력·출력 분리) |
| `소요초` | 실행 소요 시간 |
| `messages` | 해당 문항의 전체 대화 기록 (system, user, assistant, tool) |
| `run_config` | 실행 구성 (cond, harness, limit_tools, 안전장치 on/off 등) |
| `tool_call_details` | 도구 호출별 상세 (도구명, 인자, 결과 미리보기 200자, 오류 여부) |
| `harness_events` | 하네스 이벤트 (nudge, clamping, repeat, block, error_streak 등) |

## 결과 비교

두 실행 결과(조건 A vs 조건 B, 또는 시드별 반복)를 비교할 때 `eval/compare_runs.py`를 사용한다.

### 사용법

```bash
# 두 결과 디렉토리 비교
python eval/compare_runs.py eval/results_A eval/results_B
# 시드별 반복 측정 집계: 위치 인자는 라벨, 폴더는 {root}/calcset_{라벨}_s{시드}
python eval/compare_runs.py --seeds 42,43,44 --root eval/results base routing
```

### compare_runs.py CLI

```
usage: compare_runs.py [-h] [--seeds SEEDS] [--root ROOT] [--label-a LABEL_A] [--label-b LABEL_B] a b

두 실행 결과 디렉토리를 비교한다.

positional arguments:
  a                     조건 A의 결과 디렉토리 (기본) 또는 --seeds 모드에서는 라벨 A
  b                     조건 B의 결과 디렉토리 (기본) 또는 --seeds 모드에서는 라벨 B

optional arguments:
  --seeds SEEDS         시드별 반복 측정 집계 (콤마 구분, 예: --seeds 42,43,44)
  --root ROOT           results 루트 디렉토리 (--seeds 사용 시 필수)
  --label-a LABEL_A     A 라벨 (--seeds 사용 시, 미지정 시 a 사용)
  --label-b LABEL_B     B 라벨 (--seeds 사용 시, 미지정 시 b 사용)
```

### 출력 예시

```
문항수: 44
A 정답: 20/44  (95% CI: [0.352, 0.563])
B 정답: 24/44  (95% CI: [0.418, 0.653])

둘 다 맞음: 15
A만 맞음  : 5
B만 맞음  : 9
둘 다 틀림: 15
제외(실행실패): 0

McNemar p: 0.317
판정      : 차이 없음
```

`--seeds` 모드에서는 시드별 줄이 먼저 출력된다:

```
시드별:
  s42  A 20/44  B 17/44  p=0.607
  s43  A 23/44  B 20/44  p=0.629
  s44  A 19/44  B 18/44  p=0.841
합산 (문항×시드 짝): 132

문항수: 132
A 정답: 62/132  (95% CI: [0.399, 0.528])
B 정답: 55/132  (95% CI: [0.345, 0.469])

둘 다 맞음: 42
A만 맞음  : 20
B만 맞음  : 13
둘 다 틀림: 57
제외(실행실패): 0

McNemar p: 0.112
판정      : 차이 없음
```

### McNemar 검정

McNemar 정확 이항검정(양측)으로 두 조건 간 정답률 차이가 유의한지 판단한다.

- **귀무가설**: 두 조건의 정답률이 같다.
- **대립가설**: 두 조건의 정답률이 다르다.
- **p < 0.05**: 통계적으로 유의한 차이 (B 우세 또는 A 우세)
- **p >= 0.05**: 차이 없음

McNemar 검정은 **불일치 쌍**(A만 맞음, B만 맞음)만 사용한다. 둘 다 맞거나 둘 다 틀린 문항은 검정에 기여하지 않는다.

### Wilson 95% 신뢰구간

정답률의 Wilson score 95% 신뢰구간을 함께 출력한다. 표본 크기가 작을 때 정규 근사보다 정확하다.

### 반복 측정 (시드별 집계)

`--seeds` 옵션으로 여러 시드의 결과를 누적하여 비교할 수 있다. 문항 × 시드가 한 짝이 되며, 모든 시드 결과를 합산하여 McNemar 검정을 수행한다.

위치 인자 `a`, `b`는 이 모드에서 라벨로 동작한다. 각 시드의 결과 폴더는 `{root}/calcset_{라벨}_s{시드}` 형식으로 찾는다. `--label-a`/`--label-b`를 지정하면 해당 라벨이 우선하고, 미지정 시 위치 인자 값을 사용한다.

```bash
# 시드 42, 43, 44의 결과를 누적 비교 (base vs routing)
python eval/compare_runs.py --seeds 42,43,44 --root eval/results base routing
```

이 경우 `results_root/calcset_{label}_s{seed}` 폴더들을 시드별로 짝지어 합산한다.

### 중복 및 실행실패 처리

- **중복**: 같은 (연도, 번호)가 여러 번 나타나면 마지막 줄 사용
- **실행실패**: 한쪽이라도 "실행실패"면 비교 대상에서 제외 (분모에서 제외, 별도 집계)

## 보류셋

보류셋(holdout set)은 공개 보고 전용 평가 세트다. 개발·튜닝 중 실행하지 않는다.

보류셋 정보는 `eval/data/holdout_manifest.json`에 기록되어 있다.

```json
{
  "설명": "보류셋(공개 보고 전용). 개발·튜닝 중 실행 금지.",
  "files": [
    {"id": "N2026", "questions": "data_new40/문제_new40.json", "answers": "data_new40/정답_new40.json", "evidence": "data_new40/근거_new40.json", "basis_date": "20261015", "n": 40}
  ]
}
```

보류셋 실행이 필요한 경우(공식 보고 전 최종 검증 등) 위 manifest에 기록된 파일 경로·기준일을 참고하여 실행한다.

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

## 오답 원인 분류

`eval/classify_failures.py`는 `eval/results/` 아래의 raw jsonl 결과를 읽어 오답을 7개 분류 중 하나로 붙인다. 규칙 층(실행실패·무응답·도구 미호출·인자 오류)은 raw 기록만으로 결정하고, 나머지는 판정 층에서 API 호출로 분류한다.

### 분류 정의

| 분류 | 명칭 | 설명 |
|------|------|------|
| 0 | 정답 | 정오 "O" |
| 1 | 도구 미호출 | 계산형 문항인데 계산 도구를 호출하지 않음 |
| 2 | 잘못된 도구 선택 | 호출한 계산 도구가 문항 주제와 다름 |
| 3 | 인자 오류 | 계산 도구 인자가 문항 사실관계와 다름(값 오추출) |
| 4 | 도구 결과 부족·오류 | 인자는 맞으나 결과가 틀리거나 필요한 자료를 도구가 못 반환 |
| 5 | 판단 오류 | 도구 결과는 맞고 충분한데 합산·차감·보기 대조 단계에서 틀림 |
| 6 | 집계·파싱·무응답 | 무응답 또는 모델 답에서 정답을 파싱하지 못함 |
| 7 | 실행 실패 | 도구 호출 중 예외가 발생해 실행이 중단됨 |

### 규칙 층 / 판정 층

- **규칙 층**: 실행실패(7), 무응답/파싱(6), 도구 미호출(1), 모든 계산 호출이 인자 오류(3)는 raw 기록만으로 분류.
- **판정 층**: 위 규칙에 해당하지 않는 오답(2·4·5 후보는 계산형, 4·5 후보는 서술형)은 API 호출로 분류. `--no-judge` 옵션 사용 시 규칙 층만 적용하고 나머지는 미판정으로 남긴다.

### 사용법

```bash
# 기본 실행 (판정 층 포함, questions는 기본값으로 eval/examples/items.json 사용)
python eval/classify_failures.py eval/results/calcset_base_s42

# questions 파일 지정
python eval/classify_failures.py eval/results/calcset_base_s42 --questions eval/examples/items.json

# 판정 층 없이 규칙 층만 사용
python eval/classify_failures.py eval/results/calcset_base_s42 --questions eval/examples/items.json --no-judge
```

### 캐시 파일

분류 결과는 `eval/results/calcset_base_s42/failure_classes.jsonl`에 캐시된다. 같은 디렉토리에서 다시 실행하면 캐시된 결과를 재사용하며, 판정 버전이 변경되지 않은 경우 API 재호출을 건너뛴다. 캐시 파일은 한 줄에 한 문항의 분류 결과(연도, 번호, 분류, 소분류, 근거, flags 포함)를 JSON으로 저장한다.

Created by Mia(윤승미)
