"""조세심판원 재결례 — 사건번호 검색과 상세 문서번호(2026-11-16).

재현: ① search_tribunal_decisions('2023서9158') → 결과가 1건이면 법제처가 decc를 목록이 아니라 객체로 보내 AttributeError
      ② get_tribunal_decision 결과의 문서번호가 빈 값 — 상세 응답(lawService)의 청구번호·사건번호 칸이 비어 옴
픽스처: tests/fixtures/tribunal_1116.json(2026-11-16 실제 응답, 키 제거).
"""
import json
import os

from korean_tax_mcp import law, server, tribunal

FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "tribunal_1116.json"), encoding="utf-8"))


def _fake(monkeypatch, search=None, detail=None):
    calls = []

    def fake_get(path, query):
        calls.append((path, query))
        if path == "lawService.do":
            return detail if detail is not None else FX["상세"]
        return search if search is not None else FX["검색_1건"]
    monkeypatch.setattr(law, "_get", fake_get)
    tribunal._BILL.clear()
    return calls


def test_fixture_shape_reproduces_single_object():
    assert isinstance(FX["검색_1건"]["Decc"]["decc"], dict)
    svc = FX["상세"]["SpecialDeccService"]
    assert svc["청구번호"] == "" and svc["사건번호"] == ""
    assert "OC=" not in json.dumps(FX, ensure_ascii=False).replace("OC=&", "")


def test_parse_search_single_object():
    items = tribunal.parse_search(FX["검색_1건"])
    assert len(items) == 1 and items[0]["문서번호"] == "조심 2023서9158" and items[0]["id"] == "tt:2058951"
    assert tribunal.parse_search({"Decc": {"totalCnt": "0"}}) == []
    assert tribunal.parse_search({"Decc": "x"}) == []


def test_case_number_detection():
    for q in ("2023서9158", "조심2023서9158", "조심 2023서9158", " 조심-2023-서-9158 ", "2024지0101", "국심2006서1465"):
        assert tribunal.case_number(q), q
    assert tribunal.case_number("조심2023서9158")[1] == "2023서9158"
    assert tribunal.case_number("국심 2006서1465")[1] == "2006서1465"
    for q in ("취득세 중과", "정상가격 비교대상 2023", "2023"):
        assert tribunal.case_number(q) is None, q


def test_search_tool_case_number(monkeypatch):
    calls = _fake(monkeypatch)
    for q in ("2023서9158", "조심2023서9158"):
        r = server.search_tribunal_decisions(q)
        assert "error" not in r, r
        assert [x["문서번호"] for x in r["결과"]] == ["조심 2023서9158"] and r["검색 방식"] == "사건번호"
    assert all("query=2023%EC%84%9C9158" in q for _, q in calls)       # 접두어를 떼고 번호로 찾는다


def test_search_tool_case_number_keeps_exact_match_only(monkeypatch):
    two = {"Decc": {"totalCnt": "2", "decc": [
        dict(FX["검색_1건"]["Decc"]["decc"], 청구번호="조심 2023서91580", 특별행정심판재결례일련번호="1"),
        FX["검색_1건"]["Decc"]["decc"]]}}
    _fake(monkeypatch, search=two)
    r = server.search_tribunal_decisions("2023서9158")
    assert [x["문서번호"] for x in r["결과"]] == ["조심 2023서9158"]


def test_detail_fills_number_from_search_cache(monkeypatch):
    calls = _fake(monkeypatch)
    server.search_tribunal_decisions("2023서9158")
    n = len(calls)
    f = getattr(server.get_tribunal_decision, "fn", server.get_tribunal_decision)
    d = f("tt:2058951")
    assert d["문서번호"] == "조심 2023서9158" and d["일자"] == "2025.04.09."
    assert len(calls) == n + 1                               # 상세 1회만 — 검색 결과에서 번호를 기억


def test_detail_fills_number_by_title_search(monkeypatch):
    calls = _fake(monkeypatch)
    d = tribunal.detail("2058951")
    assert d["문서번호"] == "조심 2023서9158"
    q = [q for p, q in calls if p == "lawSearch.do"]
    assert q and "display=" in q[0]


def test_detail_number_unknown_is_marked(monkeypatch):
    _fake(monkeypatch, search={"Decc": {"totalCnt": "0"}})
    d = tribunal.detail("tt:2058951")
    assert d["문서번호"] == "" and "문서번호 확인" in d
