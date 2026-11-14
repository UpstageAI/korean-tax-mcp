"""한국 세법 근거 MCP 서버."""
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# 버전은 pyproject.toml 한 곳에서만 관리한다. 손으로 적은 값이 0.12.17에 멈춰 있었다(2026-11-14).
try:
    __version__ = _pkg_version("korean-tax-mcp")
except PackageNotFoundError:  # 설치하지 않고 소스 폴더에서 바로 돌릴 때
    __version__ = "0.0.0+unknown"

import re

_OC_RE = re.compile(r"OC=[^&]+")


def _mask_oc(msg: str) -> str:
    """오류 메시지에서 법제처 OC 키가 노출되지 않도록 마스킹한다."""
    return _OC_RE.sub("OC=***", msg)
