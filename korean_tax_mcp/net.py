"""외부 조회(국세법령정보시스템·법제처) 공통 HTTP.

- 이 패키지 이름·버전을 밝히는 User-Agent(브라우저로 꾸미지 않음).
- 요청당 시간 제한은 MCP 60초 제한보다 훨씬 짧게(12초).
- 연결 끊김·시간 초과만 최대 3회 시도(지수 백오프 + 지터). 사이트가 응답한 HTTP 오류·거부는 재시도하지 않음.
- 모두 실패하면 원시 URLError 대신 무엇이 안 됐고 다음에 무엇을 할지 적은 Unreachable.
- 연결이 막힌 사이트는 잠시(20초) 바로 실패로 답해, 검색어 여러 개를 도는 도구가 재시도를 곱절로 쌓지 않게 한다.
- budget(초): 한 도구 호출 전체의 시간 예산. 그 안의 요청은 남은 시간만큼만 기다린다.
"""
import contextlib
import contextvars
import errno
import random
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

from . import __version__

USER_AGENT = f"korean-tax-mcp/{__version__} (+https://github.com/UpstageAI/korean-tax-mcp)"
TIMEOUT = 12.0          # 요청당(연결·응답 대기) 시간 제한, 초
MAX_ATTEMPTS = 3        # 첫 시도 포함
BACKOFF = 1.0           # 1회째 대기 ≈ 1초, 2회째 ≈ 2초 (각각 ×0.5~1.5 지터)
COOLDOWN = 20.0         # 연결이 막힌 사이트를 바로 실패로 답하는 시간, 초
MIN_LEFT = 1.0          # 예산이 이보다 적게 남으면 새 요청을 보내지 않음
_CHUNK = 65536

SITES = {   # 이름, 주격(이/가), 방향(으로/로), 영향 없을 수 있는 다른 도구
    "nts": {"name": "국세법령정보시스템(taxlaw.nts.go.kr)", "subj": "이", "to": "으로",
            "other": "법제처 조문 도구(law_article·find_article·article_history)는 이 사이트와 별개라 계속 써 볼 수 있습니다"},
    "law": {"name": "법제처 국가법령정보(www.law.go.kr)", "subj": "가", "to": "로",
            "other": "국세청 해석·판례 도구(search_tax_rulings·get_tax_ruling·basic_rules)는 이 사이트와 별개라 계속 써 볼 수 있습니다"},
}
_KIND = {   # (무엇이 안 됐나, 덧붙임)
    "reset": ("{name}{subj} 이 네트워크의 연결을 중간에 끊었습니다", "연결 재설정"),
    "timeout": ("{name}{subj} 이 네트워크에서 제한 시간 안에 응답하지 않았습니다", "요청당 {t:.0f}초"),
    "refused": ("{name}{subj} 이 네트워크의 연결을 거부했습니다", ""),
    "dns": ("이 네트워크에서 {name} 주소를 찾지 못했습니다", "DNS"),
    "network": ("이 네트워크에서 {name}{to} 가는 경로가 없습니다", ""),
}


class Unreachable(RuntimeError):
    """사이트에 연결하지 못함(재시도 후). str()이 사용자에게 보일 한국어 안내 전문."""

    def __init__(self, site, kind, attempts, cached=False):
        self.site, self.kind, self.attempts, self.cached = site, kind, attempts, cached
        s = {"name": site, "subj": "이(가)", "to": "(으)로", "other": ""} | SITES.get(site, {})
        how, note = _KIND.get(kind, ("이 네트워크에서 {name}에 연결하지 못했습니다", ""))
        tried = f"직전 {COOLDOWN:.0f}초 안에 같은 실패가 있어 다시 시도하지 않음" if cached else f"{attempts}회 시도"
        detail = ", ".join(x for x in (note.format(t=TIMEOUT), tried) if x)
        self.short = f"{s['name']} 연결 실패({tried})"
        super().__init__(
            f"{how.format(**s)}({detail}). "
            "일부 클라우드 실행 환경에서는 이 사이트에 접속되지 않을 수 있습니다. "
            + (f"{s['other']}. " if s["other"] else "") +
            "다음 단계: ① 잠시 후 다시 시도 ② 이 MCP 서버를 로컬 PC에서 실행(uvx korean-tax-mcp)")


class BudgetExceeded(RuntimeError):
    """도구 호출 전체 시간 예산을 다 씀."""

    def __init__(self, seconds):
        self.seconds = seconds
        super().__init__(f"시간 예산({seconds:.0f}초) 안에 응답을 다 받지 못했습니다 — 잠시 후 다시 시도하거나, "
                         "범위를 좁혀(keyword·paragraph, with_delegation 없이) 조회하세요")


# ── 시간 예산 ──
_deadline = contextvars.ContextVar("ktm_deadline", default=None)   # (monotonic 마감, 예산 초)


@contextlib.contextmanager
def budget(seconds):
    """이 블록 안의 모든 요청이 합쳐서 seconds 안에 끝나게. 바깥 예산이 더 짧으면 그것을 따른다."""
    end = time.monotonic() + seconds
    cur = _deadline.get()
    if cur and cur[0] < end: end, seconds = cur
    tok = _deadline.set((end, seconds))
    try: yield
    finally: _deadline.reset(tok)


def remaining():
    d = _deadline.get()
    return None if d is None else d[0] - time.monotonic()


def expired():
    r = remaining()
    return r is not None and r < MIN_LEFT


def _over():
    d = _deadline.get()
    return BudgetExceeded(d[1] if d else 0)


def submit(ex, fn, *a, **k):
    """ThreadPoolExecutor.submit — 작업 스레드에도 시간 예산(contextvars)을 넘긴다."""
    return ex.submit(contextvars.copy_context().run, fn, *a, **k)


# ── 연결이 막힌 사이트 잠시 기억 ──
_lock = threading.Lock()
_down = {}   # site → (until, kind)


def reset():
    with _lock: _down.clear()


def _blocked(site):
    with _lock:
        v = _down.get(site)
        if v and v[0] > time.monotonic(): return v[1]
        _down.pop(site, None)
    return None


def _trip(site, kind):
    with _lock: _down[site] = (time.monotonic() + COOLDOWN, kind)


def _kind(e):
    """재시도·안내 판단용 분류. 사이트가 응답한 오류(HTTPError)나 그 밖의 예외는 None(그대로 올림)."""
    if isinstance(e, urllib.error.HTTPError): return None
    wrapped = isinstance(e, urllib.error.URLError)
    if wrapped:
        if not isinstance(e.reason, BaseException): return None
        e = e.reason
    if isinstance(e, (ConnectionResetError, ConnectionAbortedError, ssl.SSLEOFError)): return "reset"
    if isinstance(e, (TimeoutError, socket.timeout)): return "timeout"
    if isinstance(e, ConnectionRefusedError): return "refused"
    if isinstance(e, socket.gaierror): return "dns"
    if isinstance(e, OSError) and e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH): return "network"
    return None


def _read(r):
    left = remaining()
    if left is None: return r.read()
    end = time.monotonic() + left
    chunks = []
    while True:
        try: b = r.read(_CHUNK)
        except TypeError: return b"".join(chunks) + r.read()   # read(n)를 받지 않는 단순 응답 객체
        if not b: return b"".join(chunks)
        chunks.append(b)
        if time.monotonic() > end: raise _over()


def request(req, *, site, ctx=None, timeout=TIMEOUT):
    """urllib Request → 응답 bytes. 연결 끊김·시간 초과만 최대 MAX_ATTEMPTS회 시도.
    다 실패하면 Unreachable, 예산을 다 쓰면 BudgetExceeded, 그 밖의 오류(HTTP 오류 등)는 그대로."""
    if not req.has_header("User-agent"): req.add_header("User-Agent", USER_AGENT)
    k = _blocked(site)
    if k: raise Unreachable(site, k, 0, cached=True)
    timeout = min(timeout or TIMEOUT, TIMEOUT)
    kind, last, attempts = None, None, 0
    for i in range(MAX_ATTEMPTS):
        left = remaining()
        if left is not None and left < MIN_LEFT:
            if kind: break
            raise _over()
        attempts += 1
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout if left is None else min(timeout, left)) as r:
                return _read(r)
        except BudgetExceeded:
            raise
        except Exception as e:
            kind, last = _kind(e), e
            if kind is None: raise
        if kind not in ("reset", "timeout") or i + 1 >= MAX_ATTEMPTS: break
        wait = BACKOFF * (2 ** i) * random.uniform(0.5, 1.5)
        left = remaining()
        if left is not None and left - wait < MIN_LEFT: break
        time.sleep(wait)
    # 연결 단계 실패(거부·DNS·경로 없음)이거나 끝까지 다 시도해도 안 됐을 때만 사이트를 잠시 막힘으로 기억
    if kind not in ("reset", "timeout") or attempts >= MAX_ATTEMPTS: _trip(site, kind)
    raise Unreachable(site, kind, attempts) from last
