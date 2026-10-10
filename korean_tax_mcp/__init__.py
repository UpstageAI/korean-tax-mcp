"""한국 세법 근거 MCP 서버."""
__version__ = "0.8.1"

import re

_OC_RE = re.compile(r"OC=[^&]+")


def _mask_oc(msg: str) -> str:
    """오류 메시지에서 법제처 OC 키가 노출되지 않도록 마스킹한다."""
    return _OC_RE.sub("OC=***", msg)
