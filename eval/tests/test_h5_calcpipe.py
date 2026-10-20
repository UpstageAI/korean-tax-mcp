"""5단계 계산형 파이프라인 정답 테스트 (하네스 점검). 작성 Claude 2026-10-20. API 호출 없음."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

TOOL = {"type": "function", "function": {"name": "corporate_tax", "description": "법인세 산출세액", "parameters": {"type": "object", "properties": {"base": {"type": "integer"}, "months": {"type": "integer"}}, "required": ["base"]}}}
BODY = "㈜A(사업연도 1년) 과세표준 500,000,000원의 법인세 산출세액은? ① 50,000,000원 ② 75,000,000원 ③ 80,000,000원 ④ 90,000,000원 ⑤ 100,000,000원"


def test_options_amounts_parsed():
    assert run.parse_option_amounts(BODY) == {1: 50000000, 2: 75000000, 3: 80000000, 4: 90000000, 5: 100000000}


def test_match_result_to_option():
    opts = {1: 50000000, 2: 75000000, 3: 80000000}
    assert run.match_amount_to_option(75000000, opts) == 2
    assert run.match_amount_to_option(75000400, opts, tolerance=0.001) == 2       # 천원 단위 반올림 차이 허용
    assert run.match_amount_to_option(60000000, opts) is None


def test_pipeline_extract_run_match(monkeypatch):
    calls = {"api": 0}
    def api(base_url, api_key, model, messages, **kw):
        calls["api"] += 1
        return {"choices": [{"message": {"content": '{"tool": "corporate_tax", "args": {"base": 500000000, "months": 12}}'}}], "usage": {"prompt_tokens": 800, "completion_tokens": 40, "total_tokens": 840}}
    monkeypatch.setattr(run, "api_chat_complete", api)
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["answer"] == 2 and out["tool"] == "corporate_tax" and out["extractions"] == 1 and calls["api"] == 1
    assert out["result"]["산출세액"] == 75000000


def test_pipeline_reextracts_on_mismatch_then_majority(monkeypatch):
    seq = iter([{"base": 5000000}, {"base": 500000000}, {"base": 500000000}])
    def api(base_url, api_key, model, messages, **kw):
        a = next(seq)
        return {"choices": [{"message": {"content": json.dumps({"tool": "corporate_tax", "args": a})}}], "usage": {"total_tokens": 10}}
    monkeypatch.setattr(run, "api_chat_complete", api)
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000 if args["base"] == 500000000 else 750000}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["answer"] == 2 and out["extractions"] == 3                            # 불일치 → 재추출, 3회 다수결


def test_pipeline_gives_up_when_no_match(monkeypatch):
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": '{"tool": "corporate_tax", "args": {"base": 1}}'}}], "usage": {"total_tokens": 1}})
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 123}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["answer"] is None and out["extractions"] == 3 and out["fallback"] is True


def test_calc_pipeline_config_flag():
    assert run.preset("native_direct").calc_pipeline is False


def test_pipeline_records_attempts(monkeypatch):
    # 실측(10/20 22:40): fallback 시 추출 내용이 안 남아 원인 확인 불가 → 시도별 기록
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": '{"tool": "corporate_tax", "args": {"base": 1}}'}}], "usage": {"total_tokens": 1}})
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 123}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert len(out["attempts"]) == 3
    a = out["attempts"][0]
    assert a["tool"] == "corporate_tax" and a["args"] == {"base": 1} and a["matched"] is None and "123" in json.dumps(a["result"]) and "content" in a


def test_pipeline_records_unparsed_content(monkeypatch):
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": "도구가 없어 계산할 수 없습니다."}}], "usage": {"total_tokens": 1}})
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["fallback"] and out["attempts"][0]["tool"] is None and "계산할 수 없습니다" in out["attempts"][0]["content"]


def test_pipeline_attempts_result_truncated_to_1000_chars(monkeypatch):
    """결과 JSON이 1000자를 초과하면 attempts[i]["result"]가 잘린 dict로 기록된다."""
    big_result = {"k" + str(i): "v" * 200 for i in range(20)}  # ~4000자
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": json.dumps({"tool": "corporate_tax", "args": {"base": 500000000}})}}], "usage": {"total_tokens": 1}})
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps(big_result))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["attempts"][0]["result"] is not None
    assert len(json.dumps(out["attempts"][0]["result"], ensure_ascii=False)) <= 1000


def test_pipeline_fallback_messages_include_attempt_summary(monkeypatch):
    """fallback 시 messages[1]에 시도별 도구·입력·결과값·불일치가 한 줄씩 포함된다."""
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": '{"tool": "corporate_tax", "args": {"base": 1}}'}}], "usage": {"total_tokens": 1}})
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 123}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    assert out["fallback"]
    # attempts 필드에 후보 숫자(candidates)와 불일치(matched=None)가 기록됨
    a = out["attempts"][0]
    assert a["candidates"] == [123]
    assert a["matched"] is None
    # result 필드는 dict 형태
    assert isinstance(a["result"], dict) and a["result"].get("산출세액") == 123


def test_pipeline_attempt_structure_complete(monkeypatch):
    """일치 시도: attempts[i]에 content·tool·args·validation·result·candidates·matched 7필드가 모두 존재."""
    monkeypatch.setattr(run, "api_chat_complete", lambda *a, **k: {"choices": [{"message": {"content": json.dumps({"tool": "corporate_tax", "args": {"base": 500000000, "months": 12}})}}], "usage": {"total_tokens": 1}})
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: json.dumps({"산출세액": 75000000}))
    out = run.run_calc_pipeline(BODY, tools=[TOOL], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, base_url="x", api_key="x", model="m", seed=1, exam_date="20230101", usage_acc=run.UsageAcc())
    a = out["attempts"][0]
    for key in ("content", "tool", "args", "validation", "result", "candidates", "matched"):
        assert key in a, f"attempts[0]에 {key} 없음"
    assert a["tool"] == "corporate_tax"
    assert a["args"] == {"base": 500000000, "months": 12}
    assert a["validation"] is None
    assert a["result"] == {"산출세액": 75000000}
    assert a["candidates"] == [75000000]
    assert a["matched"] == 2

