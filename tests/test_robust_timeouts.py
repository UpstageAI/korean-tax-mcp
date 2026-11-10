"""외부 조회 견고성 — 일시 장애 제한 재시도, 짧은 요청 시간 제한, 연결 실패 시 분명한 안내, law_article 시간 예산.

네트워크 없이 urllib.request.urlopen을 가짜로 바꿔 연결 끊김·시간 초과를 흉내 낸다.
실행: .venv/bin/python -m pytest tests/test_robust_timeouts.py -q
"""
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

import korean_tax_mcp
from korean_tax_mcp import law, ntis, server

LONG = "업무무관 가지급금 인정이자 익금산입 시기 판단 기준"   # 여러 검색어로 모으는 경로(_pooled)
_REAL_SLEEP = time.sleep


class _Resp:
    def __init__(self, data): self._data = data
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, *a): d, self._data = self._data, b""; return d


def _reset():   # 104 — 일부 클라우드에서 실제로 본 오류와 같은 모양
    return urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))


NTIS_OK = json.dumps({"status": "SUCCESS", "data": {"X": {"ok": 1}}}).encode()


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("LAW_OC", "test")
    monkeypatch.setattr(ntis, "CACHE", tmp_path)           # 디스크 캐시가 결과를 대신 주지 않게
    for f in (law._versions.clear, law._three_tier.cache_clear, law._raw_units.cache_clear,
              law._full_units.cache_clear, law._phrase_defs.cache_clear, ntis.laws.cache_clear):
        f()
    law.clear_caches()
    net = getattr(korean_tax_mcp, "net", None)
    if net is not None: net.reset()
    yield
    if net is not None: net.reset()


@pytest.fixture
def sleeps(monkeypatch):
    got = []
    monkeypatch.setattr(time, "sleep", lambda s: got.append(s))
    return got


def _urlopen(monkeypatch, fn):
    calls = []
    def fake(req, context=None, timeout=None):
        calls.append({"url": req.full_url, "timeout": timeout, "ua": req.get_header("User-agent")})
        return fn(req, len(calls))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


# ── 1. 정직한 User-Agent ──

def test_user_agent_names_package_and_version(monkeypatch, sleeps):
    calls = _urlopen(monkeypatch, lambda req, n: _Resp(NTIS_OK if "taxlaw" in req.full_url else b"{}"))
    ntis._fetch("X", {}, 10)
    law._get("lawSearch.do", "target=eflaw&query=x")
    want = f"korean-tax-mcp/{korean_tax_mcp.__version__}"
    assert all(c["ua"] and c["ua"].startswith(want) for c in calls), [c["ua"] for c in calls]
    assert all("Mozilla" not in c["ua"] for c in calls)


# ── 2. 연결 끊김·시간 초과만 제한 재시도(지수 백오프 + 지터) ──

@pytest.mark.parametrize("exc", [_reset, lambda: socket.timeout("timed out"), lambda: ConnectionResetError(104, "reset")])
def test_nts_transient_then_success(monkeypatch, sleeps, exc):
    calls = _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(exc()) if n <= 2 else _Resp(NTIS_OK))
    assert ntis._fetch("X", {}, 10) == {"ok": 1}
    assert len(calls) == 3
    backoff = [s for s in sleeps if s > 0]
    assert len(backoff) == 2 and 0.25 <= backoff[0] <= 1.5 and 0.5 <= backoff[1] <= 3.0, backoff


def test_law_reset_then_success(monkeypatch, sleeps):
    calls = _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()) if n == 1 else _Resp(b'{"a": 1}'))
    assert law._get("lawSearch.do", "q=1") == {"a": 1}
    assert len(calls) == 2


def test_jitter_varies(monkeypatch, sleeps):
    _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()) if n % 2 else _Resp(NTIS_OK))
    for _ in range(8):
        ntis._fetch("X", {}, 10)
        if getattr(korean_tax_mcp, "net", None): korean_tax_mcp.net.reset()
    assert len({round(s, 6) for s in sleeps if s > 0}) > 1, sleeps


def test_no_retry_on_http_error(monkeypatch, sleeps):
    """사이트가 응답한 오류(HTTP 4xx·5xx)는 재시도하지 않는다 — 연결 끊김·시간 초과만."""
    def boom(req, n): raise urllib.error.HTTPError(req.full_url, 500, "err", {}, None)
    calls = _urlopen(monkeypatch, boom)
    with pytest.raises(urllib.error.HTTPError):
        law._get("lawSearch.do", "q=1")
    assert len(calls) == 1


def test_attempts_bounded_and_fit_under_mcp_limit(monkeypatch, sleeps):
    """요청당 시간 제한은 MCP 60초보다 훨씬 짧고, 최대 3회 시도 + 대기를 모두 더해도 60초 미만."""
    for site, call in (("nts", lambda: ntis._fetch("X", {}, 40)), ("law", lambda: law._get("lawSearch.do", "q=1"))):
        sleeps.clear()
        calls = _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(socket.timeout("timed out")))
        with pytest.raises(Exception):
            call()
        assert 1 <= len(calls) <= 3, (site, len(calls))
        assert all(c["timeout"] and c["timeout"] <= 15 for c in calls), (site, [c["timeout"] for c in calls])
        worst = sum(c["timeout"] for c in calls) + sum(sleeps)
        assert worst < 50, (site, worst)
        if getattr(korean_tax_mcp, "net", None): korean_tax_mcp.net.reset()


# ── 3. 모두 실패하면 원시 URLError 대신 분명한 한국어 안내(0건 아님) ──

def _assert_nts_message(err):
    assert "국세법령정보시스템" in err, err
    assert "URLError" not in err and "Errno" not in err, err
    assert "law_article" in err, err                       # 법제처 조문 도구는 계속 쓸 수 있음
    assert "다시 시도" in err and "로컬" in err, err        # 다음 단계


def test_nts_all_fail_clear_error(monkeypatch, sleeps):
    def down(req, n): raise _reset()
    calls = _urlopen(monkeypatch, down)
    r = server.search_tax_rulings(LONG)
    assert "error" in r and "결과" not in r, r
    _assert_nts_message(r["error"])
    assert "끊" in r["error"]
    assert len(calls) <= 3, len(calls)                     # 검색어 5개 × 재시도로 불어나지 않음


def test_nts_refused_clear_error(monkeypatch, sleeps):
    def refused(req, n): raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    calls = _urlopen(monkeypatch, refused)
    r = server.basic_rules("법인세법", "제52조")
    _assert_nts_message(r["error"])
    assert "거부" in r["error"]
    assert len(calls) == 1                                 # 거부는 재시도하지 않음


def test_nts_by_issue_all_fail_clear_error(monkeypatch, sleeps):
    _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()))
    r = server.search_rulings_by_issue(["가지급금 인정이자", "업무무관 자산 지급이자"])
    assert "error" in r and "쟁점별" not in r, r
    _assert_nts_message(r["error"])


def test_verify_citations_reports_unreachable(monkeypatch, sleeps):
    monkeypatch.delenv("LAW_OC", raising=False)
    _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()))
    r = server.verify_citations("대법원 2002. 9. 24. 선고 2001두489 판결")
    assert r["문서번호"][0]["결과"] == "조회 실패"
    _assert_nts_message(json.dumps(r, ensure_ascii=False))


def test_law_all_fail_clear_error(monkeypatch, sleeps):
    _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()))
    r = server.law_article("법인세법", "제52조")
    err = r.get("error", "")
    assert "법제처" in err and "URLError" not in err and "다시 시도" in err and "로컬" in err, r
    assert "OC=" not in err


# ── 4. law_article 전체 시간 예산 — 늦으면 부분 결과 + 안내 ──

ARTICLE = {"법령": {"조문": {"조문단위": [{"조문여부": "조문", "조문번호": "52", "조문가지번호": "00",
                                     "조문내용": "제52조(부당행위계산의 부인) ① 과세당국은 …"}]}}}
THD = {"LspttnThdCmpLawXService": {"위임조문삼단비교": {"법률조문": [
    {"조번호": "0052", "조가지번호": "00", "시행령조문": {"조번호": "0088", "조가지번호": "00"}}]}}}


def _drf(stall):
    """lawSearch → 이름별 연혁 1건, JO 있는 본문 → 조문, 3단비교 → THD. stall(url)이 참이면 소켓 시간 초과를 흉내."""
    def fn(req, n):
        u = req.full_url
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
        if stall(u):
            _REAL_SLEEP(0.6)
            raise socket.timeout("timed out")
        if "lawSearch.do" in u:
            name = q["query"][0]
            return _Resp(json.dumps({"LawSearch": {"totalCnt": "1", "law": [
                {"법령명한글": name, "법령일련번호": "2" if name.endswith("시행령") else "1", "시행일자": "20240101"}]}}).encode())
        if "thdCmp" in u: return _Resp(json.dumps(THD).encode())
        return _Resp(json.dumps(ARTICLE).encode())
    return fn


def test_law_article_budget_returns_partial(monkeypatch):
    """본문은 받았는데 목차·연결(법령 전체 조회)이 멈추면 예산 안에 본문 + 부분 결과 안내로 끝낸다."""
    monkeypatch.setattr(server, "LAW_ARTICLE_BUDGET", 3, raising=False)
    _urlopen(monkeypatch, _drf(lambda u: "lawService.do" in u and "JO=" not in u))
    t0 = time.monotonic()
    r = server.law_article("법인세법", "제52조", as_of="20250101")
    took = time.monotonic() - t0
    assert took < 3 + 1.5, took
    assert "부당행위계산" in r.get("본문", ""), r
    assert r.get("부분 결과"), r


def test_law_article_delegation_partial_rows(monkeypatch):
    """3단 위임 중 한 단계가 멈추면 받은 단계는 돌려주고 못 받은 단계는 오류로 표시."""
    monkeypatch.setattr(server, "LAW_ARTICLE_BUDGET", 4, raising=False)
    _urlopen(monkeypatch, _drf(lambda u: "lawService.do" in u and "MST=2" in u and "JO=" in u))
    t0 = time.monotonic()
    r = server.law_article("법인세법", "제52조", as_of="20250101", with_delegation=True)
    took = time.monotonic() - t0
    assert took < 4 + 1.5, took
    rows = r.get("위임체계")
    assert rows and len(rows) == 2, r
    assert "부당행위계산" in rows[0].get("본문", "")
    assert rows[1]["법령"] == "법인세법 시행령" and rows[1].get("error"), rows[1]
    assert "위임체계" in (r.get("부분 결과") or ""), r


# ── 리뷰 반영: 예산이 모자라 재시도를 멈춘 경우는 사이트 장애가 아니라 예산 소진으로 알림 ──
def test_budget_cut_retry_reports_budget_not_unreachable(monkeypatch, sleeps):
    from korean_tax_mcp import net
    _urlopen(monkeypatch, lambda req, n: (_ for _ in ()).throw(_reset()))
    req = urllib.request.Request("https://taxlaw.nts.go.kr/x")
    with net.budget(1.5):                          # 첫 시도 후 대기(≈1초)를 하면 MIN_LEFT보다 적게 남음
        with pytest.raises(net.BudgetExceeded):
            net.request(req, site="nts")
    assert not net._blocked("nts")                 # 사이트를 막힘으로 기록하지 않음


# ── PR-B: 스레드 풀 호출에도 시간 예산이 전파되고, find_article이 망 장애를 '법령을 찾지 못함'으로 덮지 않음 ──

def _drf_versions(monkeypatch, slow_body=None):
    """연혁 2건, 조문 본문은 slow_body(초)만큼 자고 돌려줌."""
    def get(path, query):
        if path == "lawSearch.do":
            return {"LawSearch": {"law": [{"법령명한글": "법인세법", "법령일련번호": str(i), "시행일자": f"202{i}0101"} for i in (1, 2)]}}
        if slow_body: _REAL_SLEEP(slow_body)
        return {"법령": {"조문": [{"조문내용": "제52조(부당행위계산) 본문"}]}}
    monkeypatch.setattr(law, "_get", get)


def test_history_propagates_budget_to_worker_threads(monkeypatch):
    """history()의 본문 조회는 작업 스레드에서 돈다 — net.budget 안이면 예산 소진을 BudgetExceeded로 올리고 '확인 불가'로 삼키지 않음."""
    from korean_tax_mcp import net
    def get(path, query):
        if path == "lawSearch.do":
            return {"LawSearch": {"law": [{"법령명한글": "법인세법", "법령일련번호": str(i), "시행일자": f"202{i}0101"} for i in (1, 2)]}}
        _REAL_SLEEP(0.15)
        if net.expired(): raise net._over()        # net.request가 예산을 확인하는 지점과 같은 동작
        return {"법령": {"조문": [{"조문내용": "본문"}]}}
    monkeypatch.setattr(law, "_get", get)
    with net.budget(0.1):
        with pytest.raises(net.BudgetExceeded):
            law.history("법인세법", "제52조")


def test_history_still_swallows_parse_errors(monkeypatch):
    _drf_versions(monkeypatch)
    real = law._get
    monkeypatch.setattr(law, "_get", lambda p, q: (_ for _ in ()).throw(KeyError("x")) if p == "lawService.do" and "MST=1" in q else real(p, q))
    r = law.history("법인세법", "제52조")
    assert [x["이 조 변경"] for x in r["연혁"]] == ["확인 불가", "기준"], r


def test_history_raises_unreachable(monkeypatch):
    from korean_tax_mcp import net
    real_rows = lambda: {"LawSearch": {"law": [{"법령명한글": "법인세법", "법령일련번호": "1", "시행일자": "20210101"}]}}
    monkeypatch.setattr(law, "_get", lambda p, q: real_rows() if p == "lawSearch.do" else (_ for _ in ()).throw(net.Unreachable("law", "reset", 3)))
    with pytest.raises(net.Unreachable):
        law.history("법인세법", "제52조")


def test_find_article_reports_network_failure_not_law_name(monkeypatch):
    """법제처가 안 될 때 find_article은 '법령을 찾지 못함 — law_name 확인'이 아니라 서버의 연결 실패 안내문을 돌려준다."""
    from korean_tax_mcp import net
    law._versions.clear(); law._FIND_CACHE.clear()
    monkeypatch.setattr(law, "_get", lambda p, q: (_ for _ in ()).throw(net.Unreachable("law", "reset", 3)))
    r = server.find_article("압류금지 생계비계좌", "국세징수법")
    assert "law_name 확인" not in r["error"], r
    assert r["error"] == server._err(net.Unreachable("law", "reset", 3))["error"]
    assert "법제처" in r["error"] and "잠시 후 다시 시도" in r["error"], r
