"""계산형 사실관계 표(fact_sheet) 정답 테스트. API·MCP 가짜.
도구 검증: 도구는 입력이 맞으면 정답을 냄. 병목은 모델이 문항에서 값을 빼먹고·혼동하는 추출 단계 → 루프 전에 사실관계를 표로 먼저 뽑게 한다."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

CALC = {"type": "function", "function": {"name": "corporate_tax", "description": "법인세 산출세액", "parameters": {"type": "object", "properties": {"base": {"type": "integer"}}, "required": ["base"]}}}
CALC_Q = {"과목": "세법개론", "본문": "㈜A의 제23기 과세표준은 500,000,000원이고 2023.3.3. 중간예납 10,000,000원을 냈다. 산출세액으로 옳은 것은? ① 5,000만원 ② 6,000만원 ③ 7,500만원 ④ 8,000만원 ⑤ 9,000만원"}
DESC_Q = {"과목": "세법개론", "본문": "법인세법상 익금에 관한 설명으로 옳은 것은? ① 가 ② 나 ③ 다 ④ 라 ⑤ 마"}
TABLE = "| 항목 | 값 | 비고 |\n|---|---|---|\n| 과세표준 | 500,000,000원 | 제23기 |\n| 중간예납 | 10,000,000원 | 2023.3.3. |\n| 묻는 값 | 산출세액 | |"


def _fake_api(log):
    def api(base_url, api_key, model, messages, **kw):
        sys_txt = messages[0].get("content") or ""
        if "사실관계" in sys_txt and not kw.get("tools"):
            log.append(("factsheet", len(messages)))
            return {"choices": [{"message": {"role": "assistant", "content": TABLE}}], "usage": {"prompt_tokens": 700, "completion_tokens": 80, "total_tokens": 780}}
        n = sum(1 for m in messages if m.get("role") == "tool")
        log.append(("loop", n))
        u = {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030}
        if n == 0:
            return {"choices": [{"message": {"role": "assistant", "content": "계산한다.", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "corporate_tax", "arguments": "{\"base\": 500000000}"}}]}}], "usage": u}
        return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "7,500만", "answer": 3}'}}], "usage": u}
    return api


def _setup(monkeypatch, log, override):
    monkeypatch.setattr(run, "api_chat_complete", _fake_api(log))
    monkeypatch.setattr(run, "_build_native_direct_tools", lambda: ([CALC], [], {"corporate_tax": ("ktcalc", "corporate_tax")}))
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000}))
    monkeypatch.setattr(run, "HARNESS_V3", True)
    monkeypatch.setenv("CFG_OVERRIDE", json.dumps(override))


def _run(q, tmp_path):
    res = run.run_question(cond="native_direct", year="C2023", qno=1, question=q, correct=3, base_url="x", api_key="x",
                           model="solar-pro4", seed=42, exam_date="20230101", limit_tools=15)
    p = tmp_path / "raw.jsonl"
    run._append_raw_one(res, p, tool_call_records=res._tool_call_records)
    return res, json.loads(p.read_text().splitlines()[-1])


def test_config_default_off():
    assert run.preset("native_direct").fact_sheet is False
    assert run.with_overrides(run.preset("native_direct"), {"fact_sheet": True}).fact_sheet is True


def test_calc_question_gets_fact_sheet_before_loop(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"fact_sheet": True})
    res, obj = _run(CALC_Q, tmp_path)
    assert log[0][0] == "factsheet" and sum(1 for k, _ in log if k == "factsheet") == 1       # 루프 전에 정확히 1회
    users = [m for m in res._messages if m.get("role") == "user"]
    assert any("사실관계" in (m.get("content") or "") and "500,000,000" in m["content"] for m in users)   # 표가 문항과 함께 모델에 감
    assert res.정오 == "O"
    assert obj["harness_events"]["fact_sheet"] is True and obj["fact_sheet"].startswith("| 항목")      # raw에 표 원문 저장
    assert res.입력토큰 == 700 + 1000 * 2 and res.출력토큰 == 80 + 30 * 2                              # 표 호출 토큰도 누적


def test_no_fact_sheet_when_off_or_descriptive(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"fact_sheet": False})
    res, obj = _run(CALC_Q, tmp_path)
    assert not any(k == "factsheet" for k, _ in log) and obj["harness_events"]["fact_sheet"] is False
    log2 = []
    _setup(monkeypatch, log2, {"fact_sheet": True})
    res2, obj2 = _run(DESC_Q, tmp_path)
    assert not any(k == "factsheet" for k, _ in log2) and obj2["harness_events"]["fact_sheet"] is False


def test_fact_sheet_failure_does_not_break_question(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"fact_sheet": True})
    inner = run.api_chat_complete
    def flaky(base_url, api_key, model, messages, **kw):
        if "사실관계" in (messages[0].get("content") or "") and not kw.get("tools"):
            raise RuntimeError("timeout")
        return inner(base_url, api_key, model, messages, **kw)
    monkeypatch.setattr(run, "api_chat_complete", flaky)
    res, obj = _run(CALC_Q, tmp_path)
    assert res.정오 == "O" and obj["harness_events"]["fact_sheet"] is False and obj["fact_sheet"] == ""   # 표 실패해도 문항은 진행


def test_fact_sheet_event_recorded_without_routing_or_v3(tmp_path, monkeypatch):
    """fact_sheet 이벤트는 routing·calc_pipeline·HARNESS_V3와 무관하게 기록돼야 한다 (리뷰 반영)."""
    log = []
    _setup(monkeypatch, log, {"fact_sheet": True, "routing": False, "calc_pipeline": False})
    monkeypatch.setattr(run, "HARNESS_V3", False)
    res, obj = _run(CALC_Q, tmp_path)
    assert "fact_sheet" in obj["harness_events"] and obj["harness_events"]["fact_sheet"] is True


def test_save_raw_includes_fact_sheet(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"fact_sheet": True})
    res, _ = _run(CALC_Q, tmp_path)
    monkeypatch.setattr(run, "RESULTS_DIR", tmp_path)
    p = run.save_raw([res], "native_direct", "C2023")
    txt = pathlib.Path(p).read_text()
    assert '"fact_sheet"' in txt and "| 항목" in txt                     # save_raw 경로에도 표 원문 저장
