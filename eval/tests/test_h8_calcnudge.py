"""계산형 넛지(calc_nudge) 정답 테스트. API·MCP 가짜.
오답 분류에서 '도구 있는데 미호출' 문항이 조문만 상한까지 호출하고 계산 도구를 쓰지 않는 경우를 점검한다."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

LAW = {"type": "function", "function": {"name": "law_article", "description": "조문", "parameters": {"type": "object", "properties": {"article": {"type": "string"}}, "required": ["article"]}}}
CALC = {"type": "function", "function": {"name": "corporate_tax", "description": "법인세 산출세액", "parameters": {"type": "object", "properties": {"base": {"type": "integer"}}, "required": ["base"]}}}
CALC_Q = {"과목": "세법개론", "본문": "㈜A 과세표준 5억의 산출세액으로 옳은 것은? ① 5,000만원 ② 6,000만원 ③ 7,500만원 ④ 8,000만원 ⑤ 9,000만원"}
DESC_Q = {"과목": "세법개론", "본문": "법인세법상 익금에 관한 설명으로 옳은 것은? ① 가 ② 나 ③ 다 ④ 라 ⑤ 마"}
NUDGE_KEY = "계산형"


def _tc(name, args, i):
    return {"id": f"t{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _fake_api(log, law_rounds=6):
    """넛지 메시지를 보기 전까지는 조문만 부르고, 보면 계산 도구를 부른 뒤 calc 결과 수신 시 답한다."""
    def api(base_url, api_key, model, messages, **kw):
        n = sum(1 for m in messages if m.get("role") == "tool")
        nudged = any(m.get("role") == "user" and NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"] for m in messages[2:])
        log.append((n, nudged))
        u = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        # 계산형 넛지 후 calc 결과 수신 완료(이미 corporate_tax 결과가 messages에 있음) → 정답 응답
        if nudged and any(m.get("role") == "tool" and "산출세액" in (m.get("content") or "") for m in messages):
            return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "7,500만", "answer": 3}'}}], "usage": u}
        # 계산형 넛지 후 첫 응답(calc 결과 없음): 계산 도구 호출
        if nudged and not any(m.get("role") == "tool" and "산출세액" in (m.get("content") or "") for m in messages):
            return {"choices": [{"message": {"role": "assistant", "content": "계산한다.", "tool_calls": [_tc("corporate_tax", {"base": 500000000}, n)]}}], "usage": u}
        # 넛지 전: 조문 도구 호출 (n < law_rounds)
        if n < law_rounds and not nudged:
            return {"choices": [{"message": {"role": "assistant", "content": f"조문 {n}", "tool_calls": [_tc("law_article", {"article": f"제{n+1}조"}, n)]}}], "usage": u}
        return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "7,500만", "answer": 3}'}}], "usage": u}
    return api


def _setup(monkeypatch, log, override, law_rounds=6):
    monkeypatch.setattr(run, "api_chat_complete", _fake_api(log, law_rounds))
    monkeypatch.setattr(run, "_build_tools", lambda: ([LAW, CALC], [], {"law_article": ("ktm", "law_article"), "corporate_tax": ("ktcalc", "corporate_tax")}))
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000} if name == "corporate_tax" else {"본문": "조문 본문"}))
    monkeypatch.setattr(run, "HARNESS_V3", True)
    monkeypatch.setenv("CFG_OVERRIDE", json.dumps(override))


def _run(q, tmp_path):
    res = run.run_question(cond="native_direct", year="C2023", qno=1, question=q, correct=3, base_url="x", api_key="x",
                           model="solar-pro4", seed=42, exam_date="20230101", limit_tools=15)
    p = tmp_path / "raw.jsonl"
    run._append_raw_one(res, p, tool_call_records=res._tool_call_records)
    return res, json.loads(p.read_text().splitlines()[-1])


def test_config_field_default_off():
    cfg = run.preset("native_direct")
    assert cfg.calc_nudge == 0
    assert run.with_overrides(cfg, {"calc_nudge": 5}).calc_nudge == 5


def test_calc_question_gets_one_nudge_after_threshold(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"calc_nudge": 4})
    res, obj = _run(CALC_Q, tmp_path)
    msgs = res._messages
    nudges = [i for i, m in enumerate(msgs) if m.get("role") == "user" and i > 1 and NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"]]
    assert len(nudges) == 1                                                       # 한 번만
    tool_msgs_before = sum(1 for m in msgs[:nudges[0]] if m.get("role") == "tool")
    assert tool_msgs_before == 4                                                  # 4회째 조문 결과 직후
    assert "corporate_tax" in msgs[nudges[0]]["content"]                          # 노출된 계산 도구 이름을 알려줌
    tools_called = [t["tool"] for t in obj["tool_call_details"]]
    assert "corporate_tax" in tools_called and res.정오 == "O"
    assert obj["harness_events"]["calc_nudged"] is True


def test_no_nudge_when_off_or_descriptive_or_calc_already_called(tmp_path, monkeypatch):
    log = []
    _setup(monkeypatch, log, {"calc_nudge": 0})                                   # 꺼짐
    res, obj = _run(CALC_Q, tmp_path)
    assert not any(NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"] for m in res._messages[2:] if m.get("role") == "user")
    assert obj["harness_events"].get("calc_nudged", False) is False
    log2 = []
    _setup(monkeypatch, log2, {"calc_nudge": 4})                                  # 서술형은 안 찌름
    res2, _ = _run(DESC_Q, tmp_path)
    assert not any(NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"] for m in res2._messages[2:] if m.get("role") == "user")

    def api_calc_first(base_url, api_key, model, messages, **kw):               # 계산 도구를 이미 불렀으면 안 찌름
        n = sum(1 for m in messages if m.get("role") == "tool"); u = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        if n == 0: return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [_tc("corporate_tax", {"base": 500000000}, 0)]}}], "usage": u}
        if n < 6: return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [_tc("law_article", {"article": f"제{n}조"}, n)]}}], "usage": u}
        return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "x", "answer": 3}'}}], "usage": u}
    monkeypatch.setattr(run, "api_chat_complete", api_calc_first)
    res3, obj3 = _run(CALC_Q, tmp_path)
    assert obj3["harness_events"]["calc_nudged"] is False


def test_nudge_fires_when_multiple_tools_per_round(tmp_path, monkeypatch):
    """한 라운드에 도구 3개씩 부르면 누적이 5를 건너뛴다(3→6). 그래도 5회째 호출 직후 1회 찔러야 한다 (리뷰 반영)."""
    log = []
    def api(base_url, api_key, model, messages, **kw):
        n = sum(1 for m in messages if m.get("role") == "tool")
        nudged = any(m.get("role") == "user" and NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"] for m in messages[2:])
        u = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        if nudged and not any(m.get("role") == "tool" and "산출세액" in (m.get("content") or "") for m in messages):
            return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [_tc("corporate_tax", {"base": 500000000}, 99)]}}], "usage": u}
        if n < 9 and not nudged:
            calls = [_tc("law_article", {"article": f"제{n+i}조"}, n * 10 + i) for i in range(3)]      # 라운드당 3개
            return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": calls}}], "usage": u}
        return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "x", "answer": 3}'}}], "usage": u}
    monkeypatch.setattr(run, "api_chat_complete", api)
    monkeypatch.setattr(run, "_build_tools", lambda: ([LAW, CALC], [], {"law_article": ("ktm", "law_article"), "corporate_tax": ("ktcalc", "corporate_tax")}))
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000} if name == "corporate_tax" else {"본문": "x"}))
    monkeypatch.setattr(run, "HARNESS_V3", True)
    monkeypatch.setenv("CFG_OVERRIDE", json.dumps({"calc_nudge": 5}))
    res, obj = _run(CALC_Q, tmp_path)
    assert obj["harness_events"]["calc_nudged"] is True
    nudges = [m for m in res._messages if m.get("role") == "user" and NUDGE_KEY in (m.get("content") or "") and "계산 도구" in m["content"]]
    assert len(nudges) == 1
