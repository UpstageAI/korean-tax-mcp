"""1단계 통합 확인: 실제 run_question 경로에서 토큰 누적·messages·run_config가 raw까지 가는지 (API·MCP 가짜). 작성 Claude 2026-10-20"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

FAKE_TOOL = {"type": "function", "function": {"name": "corporate_tax", "description": "법인세 산출세액", "parameters": {"type": "object", "properties": {"base": {"type": "integer"}}, "required": ["base"]}}}


def _fake_api(calls):
    def api(base_url, api_key, model, messages, **kw):
        calls.append(len(messages))
        if len(calls) == 1:
            return {"choices": [{"message": {"role": "assistant", "content": "계산 도구를 쓴다.",
                                              "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "corporate_tax", "arguments": "{\"base\": 500000000}"}}]}}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030}}
        return {"choices": [{"message": {"role": "assistant", "content": '{"reason": "산출세액 7,500만", "answer": 3}'}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 20, "total_tokens": 1220}}
    return api


def test_native_direct_end_to_end_records_everything(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run, "api_chat_complete", _fake_api(calls))
    monkeypatch.setattr(run, "_build_native_direct_tools", lambda: ([FAKE_TOOL], [], {"corporate_tax": ("fake", "corporate_tax")}))
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000}))
    monkeypatch.setattr(run, "HARNESS_V3", True)
    q = {"과목": "세법개론", "본문": "㈜A 과세표준 5억의 산출세액으로 옳은 것은? ① 5,000만 ② 6,000만 ③ 7,500만 ④ 8,000만 ⑤ 9,000만"}
    res = run.run_question(cond="native_direct", year="C2023", qno=1, question=q, correct=3, base_url="x", api_key="x",
                           model="solar-pro4", seed=42, exam_date="20230101", limit_tools=15)
    assert res.정오 == "O"
    assert res.입력토큰 == 2200 and res.출력토큰 == 50 and res.토큰수 == 2250          # 라운드 합산
    assert res._messages[-1]["role"] == "assistant" and any(m.get("role") == "tool" for m in res._messages)
    assert res._run_config["cond"] == "native_direct" and res._run_config["limit_tools"] == 15
    p = tmp_path / "raw.jsonl"
    run._append_raw_one(res, p, tool_call_records=res._tool_call_records)            # 호출자가 따로 안 넘겨도 res에서 가져감
    obj = json.loads(p.read_text().splitlines()[-1])
    assert obj["messages"] == res._messages and obj["run_config"]["limit_tools"] == 15 and obj["입력토큰"] == 2200


def test_api_exception_becomes_run_failure(monkeypatch):
    def boom(*a, **k): raise RuntimeError("timeout")
    monkeypatch.setattr(run, "api_chat_complete", boom)
    monkeypatch.setattr(run, "_build_native_direct_tools", lambda: ([FAKE_TOOL], [], {}))
    q = {"과목": "세법개론", "본문": "문제 ① 가 ② 나 ③ 다 ④ 라 ⑤ 마"}
    res = run.run_question_safe(cond="native_direct", year="C2023", qno=2, question=q, correct=1, base_url="x", api_key="x",
                                model="solar-pro4", seed=42, exam_date="20230101", limit_tools=15)
    assert res.정오 == "실행실패" and "RuntimeError" in res._error_raw
