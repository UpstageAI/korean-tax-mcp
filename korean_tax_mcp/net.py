"""외부 조회(국세법령정보시스템·법제처) 공통 HTTP.

- 이 패키지 이름·버전을 밝히는 User-Agent(브라우저로 꾸미지 않음).
- 요청당 시간 제한은 MCP 60초 제한보다 훨씬 짧게(12초).
- 연결 끊김·시간 초과만 최대 3회 시도(지수 백오프 + 지터). 사이트가 응답한 HTTP 오류·거부는 재시도하지 않음.
- 모두 실패하면 원시 URLError 대신 무엇이 안 됐고 다음에 무엇을 할지 적은 Unreachable.
- 연결 실패 기억(20초)은 (사이트, 실패 종류)별. 연결 단계 실패(거부·DNS·경로 없음)는 그동안 시도 없이 실패로 답하고,
  재시도를 다 써도 끊긴 경우(연결 재설정)는 그동안 재시도 없이 한 번만 시도한다 — 같은 사이트의 다른 요청이 줄줄이
  실패하지 않게. 시간 초과(느린 응답)·시간 예산 소진은 기억하지 않고, 그 사이트 요청이 한 번이라도 성공하면 지운다.
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
COOLDOWN = 20.0         # 연결 실패를 기억하는 시간, 초
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
        tried = (f"직전 {COOLDOWN:.0f}초 안에 같은 실패가 있어 " + (f"{attempts}회만 시도" if attempts else "다시 시도하지 않음")
                 if cached else f"{attempts}회 시도")
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


# ── 연결 실패 잠시 기억 — (사이트, 실패 종류)별 ──
_lock = threading.Lock()
_down = {}   # (site, kind) → until
_HARD = ("refused", "dns", "network")   # 연결 단계에서 바로 거절 — 기억하는 동안 시도 없이 실패
_SOFT = ("reset",)                       # 재시도를 다 써도 끊김 — 기억하는 동안 한 번만 시도


def reset():
    with _lock: _down.clear()


def _active(site):
    """지금 기억 중인 이 사이트의 실패 종류들."""
    now = time.monotonic()
    with _lock:
        for k in [k for k, until in _down.items() if until <= now]: del _down[k]
        return [k[1] for k in _down if k[0] == site]


def _blocked(site):
    """기억 중인 실패 종류(연결 단계 실패 우선), 없으면 None."""
    kinds = _active(site)
    return next((k for k in kinds if k in _HARD), None) or (kinds[0] if kinds else None)


def _trip(site, kind):
    with _lock: _down[(site, kind)] = time.monotonic() + COOLDOWN


def _clear(site):
    with _lock:
        for k in [k for k in _down if k[0] == site]: del _down[k]


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
    known = _active(site)
    hard = next((k for k in known if k in _HARD), None)
    if hard: raise Unreachable(site, hard, 0, cached=True)
    probe = any(k in _SOFT for k in known)          # 직전 끊김 기억 중 — 한 번만 시도(성공하면 기억을 지움)
    tries = 1 if probe else MAX_ATTEMPTS
    timeout = min(timeout or TIMEOUT, TIMEOUT)
    kind, last, attempts, by_budget = None, None, 0, False
    for i in range(tries):
        left = remaining()
        if left is not None and left < MIN_LEFT:
            if kind:
                by_budget = True
                break
            raise _over()
        attempts += 1
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout if left is None else min(timeout, left)) as r:
                data = _read(r)
            _clear(site)                                 # 이 사이트에 닿았으니 지난 실패 기억은 지움
            return data
        except BudgetExceeded:
            raise
        except Exception as e:
            kind, last = _kind(e), e
            if kind is None: raise
        if kind not in ("reset", "timeout") or i + 1 >= tries: break
        wait = BACKOFF * (2 ** i) * random.uniform(0.5, 1.5)
        left = remaining()
        if left is not None and left - wait < MIN_LEFT:
            by_budget = True
            break
        time.sleep(wait)
    # 재시도할 수 있었는데 시간 예산이 모자라 멈춘 경우는 사이트 장애가 아니라 예산 소진으로 알린다
    if by_budget and kind in ("reset", "timeout") and attempts < tries:
        raise _over() from last
    # 기억하는 것: 연결 단계 실패(거부·DNS·경로 없음), 그리고 재시도를 다 써도(또는 기억 중 한 번 시도에도) 끊긴 경우.
    # 시간 초과(느린 응답)·예산 소진은 기억하지 않는다.
    if kind in _HARD or (kind in _SOFT and attempts >= tries): _trip(site, kind)
    raise Unreachable(site, kind, attempts, cached=probe and kind in _SOFT) from last
