"""공통 픽스처.

KTM_BLOCK_NET=1: 모든 테스트에서 urllib.request.urlopen(net.request가 쓰는 가장 아래 HTTP 함수)이 연결 거부를 내게 해
네트워크가 막힌 환경(죽은 프록시·CI 격리망)을 프록시 없이 재현한다. net은 이를 '거부'로 분류해 20초 기억하므로,
urlopen을 직접 가짜로 바꾸는 테스트가 아니라 law._get·ntis._act 위에서 가짜 응답을 주는 테스트만 통과한다.
국세청 디스크 캐시(~/.cache/korean-tax-mcp)도 빈 임시 폴더로 돌려 지난 실제 응답이 네트워크 호출을 숨기지 않게 한다.
"""
import errno
import os
import urllib.error
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _block_net(monkeypatch, tmp_path):
    if os.environ.get("KTM_BLOCK_NET") != "1": return
    from korean_tax_mcp import ntis

    def refused(req, *a, **k):
        raise urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "blocked by KTM_BLOCK_NET"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    monkeypatch.setattr(ntis, "CACHE", tmp_path / "ntis-cache")
