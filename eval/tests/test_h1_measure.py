"""1단계 측정 바로잡기 정답 테스트 (하네스 점검 반영). 작성 Claude 2026-10-20. API 호출 없음."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

O = lambda *t: [{"id": f"{c}", "text": x} for c, x in zip("①②③④⑤", t)]
V = lambda *p: [{"판정": x, "근거": ""} for x in p]


# ── per_option 종합: 발문을 극성×형식으로 분류 ──
def test_classify_stem():
    assert run.classify_stem("옳지 않은 것을 모두 고른 것은?") == ("틀림", "모두")
    assert run.classify_stem("옳지 않은 것은 몇 개인가?") == ("틀림", "개수")
    assert run.classify_stem("옳은 것은 몇 개인가?") == ("옳음", "개수")
    assert run.classify_stem("옳은 것을 모두 고른 것은?") == ("옳음", "모두")
    assert run.classify_stem("다음 중 옳지 아니한 것은?") == ("틀림", "단일")
    assert run.classify_stem("다음 설명 중 옳은 것은?") == ("옳음", "단일")


def test_aggregate_repro_cases():
    # 재현표 4건 — 원본 코드는 전부 무응답·오답
    opts = O("ㄱ, ㄴ", "ㄱ, ㄷ", "ㄴ, ㄹ", "ㄴ, ㄷ", "ㄷ, ㄹ")
    assert run.aggregate_verdicts("옳지 않은 것을 모두 고른 것은?", V("틀림", "옳음", "틀림", "옳음"), opts) == 2
    opts = O("1개", "2개", "3개", "4개", "없음")
    assert run.aggregate_verdicts("옳지 않은 것은 몇 개인가?", V("옳음", "옳음", "틀림", "옳음"), opts) == 1
    assert run.aggregate_verdicts("옳은 것은 몇 개인가?", V("틀림", "틀림", "틀림", "틀림"), O("0개", "1개", "2개", "3개", "4개")) == 1
    opts = O("ㄱ, ㄴ", "ㄱ, ㄷ", "ㄴ, ㄹ", "ㄴ, ㄷ", "ㄷ, ㄹ")
    assert run.aggregate_verdicts("옳은 것을 모두 고른 것은?", V("옳음", "틀림", "옳음", "틀림"), opts) == 2


def test_aggregate_single_and_unsure():
    opts = O("가", "나", "다", "라", "마")
    assert run.aggregate_verdicts("옳지 않은 것은?", V("옳음", "옳음", "틀림", "옳음", "옳음"), opts) == 3
    assert run.aggregate_verdicts("옳은 것은?", V("틀림", "틀림", "불확실", "틀림", "틀림"), opts) == 3   # 틀림 0·불확실 1 → 그 진술
    assert run.aggregate_verdicts("옳지 않은 것은?", V("옳음", "틀림", "틀림", "옳음", "옳음"), opts) is None   # 규칙으로 못 정함 → None


def test_stem_type_polarity_fixed():
    assert run._stem_type_of("옳지 않은 것을 모두 고른 것은?") != "모두 고른 것은"       # 극성 누락 버그


# ── 토큰 누적: 라운드별 usage 합산, 입력·출력 분리 ──
def test_usage_accumulate():
    acc = run.UsageAcc()
    acc.add({"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
    acc.add({"usage": {"prompt_tokens": 300, "completion_tokens": 50, "total_tokens": 350,
                       "completion_tokens_details": {"reasoning_tokens": 10}}})
    acc.add({})                                                 # usage 없는 응답도 안전
    assert (acc.prompt, acc.completion, acc.total, acc.reasoning) == (400, 70, 470, 10)


# ── 실행 실패 분리: API 예외는 오답이 아니라 '실행실패' ──
def test_failed_result_is_not_wrong():
    res = run.make_failed_result(year="C2021", qno=7, subject="세법개론", correct=3, exc=RuntimeError("timeout"))
    assert res.정오 == "실행실패" and res._error_raw.startswith("RuntimeError")
    assert run.score_counts([res])["실행실패"] == 1 and run.score_counts([res]).get("X", 0) == 0


# ── 기록: 문항별 messages 전체 저장 ──
def test_raw_includes_messages(tmp_path):
    res = run.make_failed_result(year="C2021", qno=1, subject="세법개론", correct=1, exc=ValueError("x"))
    msgs = [{"role": "system", "content": "s"}, {"role": "assistant", "content": "plan", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "{\"a\":1}"}]
    p = tmp_path / "raw.jsonl"
    run._append_raw_one(res, p, messages=msgs, run_config={"cond": "native_direct", "limit_tools": 15, "harness": "V3"})
    obj = json.loads(p.read_text().splitlines()[-1])
    assert obj["messages"] == msgs and obj["run_config"]["limit_tools"] == 15


# ── 집계: 서술형·계산형 분리 ──
def test_summary_by_type():
    r1 = run.make_failed_result(year="C2021", qno=1, subject="세법개론", correct=1, exc=ValueError("x")); r1.정오 = "O"
    r2 = run.make_failed_result(year="C2021", qno=2, subject="세법개론", correct=1, exc=ValueError("x")); r2.정오 = "X"
    qs = {"1": {"본문": "다음 중 옳은 것은? ① 가 ② 나"}, "2": {"본문": "㈜A의 접대비 한도초과액으로 옳은 것은? ① 1,000,000원 ② 2,000,000원"}}
    s = run.summarize_by_type([r1, r2], qs)
    assert s["서술형"]["n"] == 1 and s["서술형"]["O"] == 1
    assert s["계산형"]["n"] == 1 and s["계산형"]["O"] == 0
