"""2단계 실행 루프 통합 정답 테스트 (하네스 점검). 작성 Claude 2026-10-20. API 호출 없음."""
import json, sys, pathlib, dataclasses
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from eval import run_eval as run


def test_presets_cover_existing_conditions():
    for name in ["native_direct", "native_direct2", "native2", "native_tree", "native_search", "native_annot", "B", "B2"]:
        cfg = run.preset(name)
        assert isinstance(cfg, run.RunConfig) and cfg.name == name


def test_preset_values_match_review_table():
    nd = run.preset("native_direct")                       # V3 주력
    assert nd.limit_tools == 15 and nd.truncate_chars is None
    assert nd.repeat_block and nd.clamp_dates and nd.error_streak and nd.nudge_tool
    nd2 = run.preset("native_direct2")
    assert nd2.limit_tools == 12 and nd2.truncate_chars == 3000 and nd2.repeat_block == "3rd_only"
    assert not nd2.clamp_dates and not nd2.nudge_tool
    n2 = run.preset("native2")
    assert n2.limit_tools == 8 and n2.truncate_chars == 3000
    tree = run.preset("native_tree")
    assert tree.limit_tools == 15 and not tree.repeat_block and not tree.nudge_tool
    b2 = run.preset("B2")
    assert b2.nudge_tool and b2.tool_set == "meta"


def test_config_is_serializable_and_one_field_override():
    cfg = run.preset("native_direct")
    d = json.loads(json.dumps(dataclasses.asdict(cfg), ensure_ascii=False))
    assert d["name"] == "native_direct" and "limit_tools" in d and "system_prompt" in d
    cfg2 = run.with_overrides(cfg, {"limit_tools": 8, "nudge_tool": False})
    assert cfg2.limit_tools == 8 and cfg2.nudge_tool is False and cfg.limit_tools == 15   # 원본 불변
    assert cfg2.name == "native_direct"


def test_env_override_parsed(monkeypatch):
    monkeypatch.setenv("CFG_OVERRIDE", '{"limit_tools": 10, "keep_content": true}')
    cfg = run.effective_config("native_direct")
    assert cfg.limit_tools == 10 and cfg.keep_content is True


def test_assistant_replay_keeps_content_and_all_tool_calls():
    msg = {"role": "assistant", "content": "먼저 조문을 보고 계산한다.",
           "tool_calls": [{"id": "a", "function": {"name": "law_article", "arguments": "{}"}},
                          {"id": "b", "function": {"name": "corporate_tax", "arguments": "{}"}}]}
    kept = run.replay_assistant_message(msg, keep_content=True)
    assert kept["content"] == msg["content"] and [t["id"] for t in kept["tool_calls"]] == ["a", "b"]
    legacy = run.replay_assistant_message(msg, keep_content=False)
    assert legacy["content"] is None                       # 옛 동작도 재현 가능(비교용)


def test_native_direct_default_keeps_content():
    assert run.preset("native_direct").keep_content is True


def test_run_config_written_to_raw(tmp_path):
    res = run.make_failed_result(year="C2021", qno=3, subject="세법개론", correct=2, exc=ValueError("x"))
    cfg = run.preset("native_direct")
    run._append_raw_one(res, tmp_path / "r.jsonl", run_config=dataclasses.asdict(cfg))
    obj = json.loads((tmp_path / "r.jsonl").read_text().splitlines()[-1])
    assert obj["run_config"]["name"] == "native_direct" and obj["run_config"]["limit_tools"] == 15
