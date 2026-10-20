"""3단계 도구 오류 처리 정답 테스트 (하네스 점검). 작성 Claude 2026-10-20. API·MCP 호출 없음."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run

SCHEMA = {"type": "object",
          "properties": {"base": {"type": "integer", "description": "과세표준(원)"},
                         "is_sme": {"type": "boolean", "description": "중소기업 여부"},
                         "year": {"type": "integer"},
                         "kind": {"type": "string", "enum": ["일반", "간이"]}},
          "required": ["base", "year"]}


def test_coerce_values_from_model_strings():
    args, notes = run.coerce_args({"base": "500,000,000원", "is_sme": "예", "year": "2023", "kind": "일반"}, SCHEMA)
    assert args == {"base": 500000000, "is_sme": True, "year": 2023, "kind": "일반"}
    assert notes                                                       # 변환 사실을 기록


def test_validate_reports_missing_extra_and_enum_in_korean():
    err = run.validate_args({"base": 1, "kind": "면세", "foo": 3}, SCHEMA, tool_name="corporate_tax")
    assert err["error"].startswith("입력 오류")
    assert "year" in err["누락"] and "foo" in err["불필요"]
    assert err["허용값"]["kind"] == ["일반", "간이"]
    assert "예시" in err and err["예시"]["base"] == 500000000 or isinstance(err["예시"], dict)   # 예시 입력 제공
    assert run.validate_args({"base": 1, "year": 2023}, SCHEMA, tool_name="t") is None


def test_tool_error_not_truncated_and_structured():
    long_msg = "필수 항목 누락: " + ", ".join(f"항목{i}" for i in range(80))
    res = run.format_tool_error(RuntimeError(long_msg), tool_name="corporate_tax", schema=SCHEMA)
    assert res["error"] and len(res["error"]) >= len(long_msg)        # 200자 절단 없음
    assert res["도구"] == "corporate_tax" and "필수" in res and res["필수"] == ["base", "year"]


def test_mcp_text_error_is_detected():
    # MCP가 isError 텍스트로 돌려주는 오류("Error executing tool ...")를 {"error": ...}로 정규화
    out = run.normalize_tool_result('Error executing tool corporate_tax: 1 validation error for base\n  Input should be a valid integer', tool_name="corporate_tax")
    assert isinstance(out, dict) and "error" in out and "valid integer" in out["error"]
    assert run.normalize_tool_result('{"산출세액": 1}', tool_name="t") == {"산출세액": 1}
    assert run.normalize_tool_result("plain text", tool_name="t") == {"text": "plain text"}


def test_loop_validates_before_execute(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "_sync_call_tool", lambda server, name, args: (calls.append(args), json.dumps({"ok": 1}))[1])
    tool = {"type": "function", "function": {"name": "corporate_tax", "description": "x", "parameters": SCHEMA}}
    bad = {"id": "1", "type": "function", "function": {"name": "corporate_tax", "arguments": json.dumps({"base": "5억", "year": "2023"})}}
    result = run.execute_tool_call(bad, tools=[tool], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, cfg=run.preset("native_direct"), exam_date="20230101")
    assert "error" in result and "base" in result["error"] and calls == []               # 변환 못 하면 실행 안 함
    good = {"id": "2", "type": "function", "function": {"name": "corporate_tax", "arguments": json.dumps({"base": "500,000,000", "year": "2023"})}}
    result = run.execute_tool_call(good, tools=[tool], name_to_server={"corporate_tax": ("srv", "corporate_tax")}, cfg=run.preset("native_direct"), exam_date="20230101")
    assert result.get("ok") == 1 and calls[-1] == {"base": 500000000, "year": 2023}


def test_boolean_param_accepts_bool_and_integer_accepts_int():
    # 실측(10/20 21:04): bool 값이 'number' 타입오류로 거부됨 — 연산자 우선순위 버그
    sch = {"type": "object", "properties": {"one_house": {"type": "boolean"}, "n": {"type": "integer"}, "r": {"type": "number"}}, "required": []}
    assert run.validate_args({"one_house": True, "n": 3, "r": 2.5}, sch, tool_name="t") is None
    assert run.validate_args({"one_house": False, "r": 7}, sch, tool_name="t") is None
    assert "r" in run.validate_args({"r": True}, sch, tool_name="t")["타입오류"]
