"""쟁점별 해석·판례 검색(search_rulings_by_issue) 정답 테스트 (Claude 작성 2026-11-03) — 수정 금지.
실행: .venv/bin/python -m pytest tests/test_rulings_by_issue.py -q
"""
import urllib.error
from korean_tax_mcp import ntis, server


def row(no, date="2020.01.01."):
    return {"구분": "질의회신", "문서번호": no, "제목": no, "요지": no, "세목": "법인", "일자": date, "id": no, "링크": "x", "전체건수": 1}


def fake_search(query, kinds=("해석", "판례"), tax=None, sort="정확도", n=10, start="", end="", article=None, law=None):
    return [row(f"{query}-정확도-{i}") for i in range(n)]


def fake_recent(query, kinds=("해석", "판례"), tax=None, sort="최신", n=10, start="", end="", article=None, law=None):
    assert sort == "최신" and start   # 최근 문서는 최신순 + 시작일로 찾는다
    return [row(f"{query}-최근-{i}", "2026.05.01.") for i in range(n)]


def setup(monkeypatch, search=fake_search, recent=fake_recent):
    monkeypatch.setattr(ntis, "search", search)
    monkeypatch.setattr(ntis, "_search", recent)


def test_grouped_by_issue(monkeypatch):
    setup(monkeypatch)
    r = server.search_rulings_by_issue(["가지급금 인정이자 익금산입", "업무무관 자산 지급이자 손금불산입"], n_per=3, recent_years=0)
    assert [g["쟁점"] for g in r["쟁점별"]] == ["가지급금 인정이자 익금산입", "업무무관 자산 지급이자 손금불산입"]
    for g in r["쟁점별"]:
        assert len(g["결과"]) == 3 and all(x["선정"] == "정확도" for x in g["결과"])
    assert "주의" in r


def test_recent_added_and_labeled(monkeypatch):
    setup(monkeypatch)
    r = server.search_rulings_by_issue(["공급시기 장기할부판매"], n_per=3, recent_years=3)
    labels = [x["선정"] for x in r["쟁점별"][0]["결과"]]
    assert labels[:3] == ["정확도"] * 3 and labels[3:] == ["최근"] * 2   # 최근 문서는 쟁점마다 최대 2건 덧붙임


def test_recent_dedup(monkeypatch):
    same = lambda q, *a, **k: [row("같은문서", "2026.05.01.")]
    setup(monkeypatch, search=same, recent=lambda q, *a, **k: [row("같은문서", "2026.05.01."), row("새문서", "2026.06.01.")])
    r = server.search_rulings_by_issue(["쟁점"], n_per=3, recent_years=3)
    nos = [x["문서번호"] for x in r["쟁점별"][0]["결과"]]
    assert nos == ["같은문서", "새문서"]


def test_one_issue_fails_others_continue(monkeypatch):
    def flaky(q, *a, **k):
        if q == "나쁜쟁점": raise urllib.error.URLError("down")
        return fake_search(q, *a, **k)
    setup(monkeypatch, search=flaky)
    r = server.search_rulings_by_issue(["좋은쟁점", "나쁜쟁점"], n_per=2, recent_years=0)
    good, bad = r["쟁점별"]
    assert len(good["결과"]) == 2 and "오류" not in good
    assert "오류" in bad and bad["결과"] == []


def test_all_fail_is_error(monkeypatch):
    def down(*a, **k): raise urllib.error.URLError("down")
    setup(monkeypatch, search=down, recent=down)
    r = server.search_rulings_by_issue(["가", "나"], recent_years=0)
    assert "error" in r


def test_input_limits():
    assert "error" in server.search_rulings_by_issue([])
    assert "error" in server.search_rulings_by_issue(["쟁점"] * 7)
