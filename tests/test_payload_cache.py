"""같은 (법령, 기준일)의 법제처 전문(eflaw) 응답은 한 번만 받는다 — 네트워크 없이 돈다.

law_article(목차·연결) → find_article → verify_citations를 같은 법령·기준일로 이어 부르면
전문 payload·조문(JO) 응답이 도구마다 다시 내려오던 것을 잡는다: _get 호출 수 ≤ 서로 다른 URL 수.
"""
import asyncio
import json
import urllib.parse

import pytest

from korean_tax_mcp import law
from korean_tax_mcp.server import mcp

AS_OF = "20250101"
UNITS = [
    {"조문번호": "12", "조문가지번호": "00", "조문여부": "조문", "조문제목": "비과세소득",
     "조문내용": "제12조(비과세소득) 다음 각 호의 소득에 대해서는 소득세를 과세하지 아니한다.",
     "항": [{"항번호": "①", "항내용": "① 공익신탁의 이익", "호": [{"호번호": "1.", "호내용": "1. 공익신탁법에 따른 공익신탁의 이익"}]}]},
    {"조문번호": "13", "조문가지번호": "00", "조문여부": "조문", "조문제목": "비거주자", "조문내용": "제13조(비거주자) 비거주자의 소득."},
]


class FakeDRF:
    """법제처 DRF 대역 — 어떤 법령명이든 시행본 1건(20240101), 조문·전문·3단비교는 고정 응답."""

    def __init__(self): self.calls = []

    def __call__(self, path, query):
        self.calls.append((path, query))
        q = dict(kv.split("=", 1) for kv in query.split("&"))
        if path == "lawSearch.do":
            name = urllib.parse.unquote(q.get("query", ""))
            return {"LawSearch": {"law": [{"법령명한글": name, "법령일련번호": str(sum(map(ord, name)) % 10**6),
                                           "시행일자": "20240101", "현행연혁코드": "현행"}], "totalCnt": "1"}}
        if path == "lawService.do" and q.get("target") == "thdCmp":
            return {"LspttnThdCmpLawXService": {"위임조문삼단비교": {"법률조문": []}}}
        if path == "lawService.do" and "JO" in q:
            u = next((u for u in UNITS if law.jo6(law._jo_str(u["조문번호"], u["조문가지번호"])) == q["JO"]), None)
            return {"법령": {"조문": {"조문단위": [u] if u else []}}}
        if path == "lawService.do":
            return {"법령": {"조문": {"조문단위": UNITS}, "부칙": {"부칙단위": []}}}
        raise AssertionError(f"예상 못 한 호출 {path}?{query}")


@pytest.fixture
def drf(monkeypatch):
    monkeypatch.setenv("LAW_OC", "test")
    law.clear_caches()
    f = FakeDRF()
    monkeypatch.setattr(law, "_get", f)
    yield f
    law.clear_caches()


def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


def test_same_law_same_as_of_downloads_each_url_once(drf):
    a = _call("law_article", {"law_name": "소득세법", "article": "제12조", "as_of": AS_OF})
    assert "비과세소득" in a.get("본문", ""), a
    assert "error" not in a.get("목차", {}), a.get("목차")
    f = _call("find_article", {"keyword": "비과세소득", "law_name": "소득세법", "as_of": AS_OF, "n": 3})
    assert f.get("결과") and f["결과"][0]["조"] == "제12조", f
    v = _call("verify_citations", {"text": "소득세법 제12조에 따라 비과세.", "as_of": AS_OF})
    assert v["조문"] and v["조문"][0]["결과"] == "확인", v
    distinct = set(drf.calls)
    print(f"\n_get 호출 {len(drf.calls)}회, 서로 다른 URL {len(distinct)}개")
    dup = [c for c in distinct if drf.calls.count(c) > 1]
    assert len(drf.calls) <= len(distinct), f"같은 URL을 다시 받음: {dup}"


def test_concurrent_same_key_downloads_once(drf, monkeypatch):
    """verify_citations처럼 여러 스레드가 같은 (법령, 기준일)을 동시에 부르면 전문·연혁은 한 번만 받는다(_ttl_cache 잠금)."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from korean_tax_mcp import net
    real = drf.__call__
    def slow(path, query):
        time.sleep(0.05); return real(path, query)   # 실제 조회처럼 시간이 걸려야 동시 조회 중복이 드러난다
    monkeypatch.setattr(law, "_get", slow)
    with ThreadPoolExecutor(4) as ex:
        rows = [f.result() for f in [net.submit(ex, law._full_units, "소득세법", AS_OF) for _ in range(4)]]
    assert all(r == rows[0] for r in rows) and rows[0]
    assert len(drf.calls) == len(set(drf.calls)) == 2, drf.calls   # lawSearch 1 + eflaw 전문 1
