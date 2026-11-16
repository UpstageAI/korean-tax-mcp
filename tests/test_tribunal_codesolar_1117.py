"""CodeSolar 지적(PR #123) 재현: 사건번호 정확 일치, 짧은 제목의 20자 재검색."""
from korean_tax_mcp import tribunal as TB


def _row(no):
    return {"문서번호": no}


def test_exact_case_number_rejects_longer_numbers(monkeypatch):
    rows = [_row("조심 2023서91580"), _row("조심 2023서19158"), _row("조심 2023서9158"), _row("국심 12023서9158")]
    monkeypatch.setattr(TB, "_search_raw", lambda *a, **k: {})
    monkeypatch.setattr(TB, "parse_search", lambda d, local_only=False: list(rows))
    got = TB.search("2023서9158")["결과"]
    assert [x["문서번호"] for x in got] == ["조심 2023서9158"]


def test_number_for_retries_20_chars_for_mid_length_title(monkeypatch):
    seen = []
    monkeypatch.setattr(TB, "_BILL", {})
    monkeypatch.setattr(TB, "_search_raw", lambda q, n, s: seen.append(q) or {})
    monkeypatch.setattr(TB, "parse_search", lambda d, local_only=False: [])
    TB._number_for("1", "가" * 30)
    assert seen == ["가" * 30, "가" * 20]
    seen.clear()
    TB._number_for("1", "가" * 15)
    assert seen == ["가" * 15]
