"""한국 세법 근거 MCP 서버."""
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# 버전은 pyproject.toml 한 곳에서만 관리한다. 손으로 적은 값이 0.12.17에 멈춰 있었다(2026-11-14).
try:
    __version__ = _pkg_version("korean-tax-mcp")
except PackageNotFoundError:  # 설치하지 않고 소스 폴더에서 바로 돌릴 때
    __version__ = "0.0.0+unknown"

import os
import re

# 법제처 DRF는 인증키를 주소에 붙이고(…?OC=<키>&…) 응답 JSON의 링크에도 그 주소를 되돌려 준다.
# OC=, oc=, LAW_OC=, 그리고 '='의 URL 인코딩(%3D)·JSON 이스케이프(\u003d) 뒤에 오는 값을 잡는다. 이미 가린 OC=***는 건드리지 않는다.
_OC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(OC(?:=|%3D|\\u003d))(?!\*{3})[^&\s\"'<>\\#;,)\]}|`]+")


def _mask_oc(msg: str, literal: bool = True) -> str:
    """문자열(오류 메시지·응답 본문·주소)에서 법제처 OC 키 값을 OC=***로 가린다.
    literal=True(오류 메시지용)면 환경변수 LAW_OC 값(4자 이상)이 OC= 없이 홀로 적힌 곳도 가린다.
    응답 본문에는 literal=False — 짧은 키가 조문 글자와 우연히 겹쳐 본문이 바뀌는 일을 막는다."""
    msg = _OC_RE.sub(r"\1***", msg)
    if literal:
        oc = os.environ.get("LAW_OC", "").strip()
        if len(oc) >= 4 and oc in msg: msg = msg.replace(oc, "***")
    return msg


def scrub_oc(obj):
    """중첩 JSON 값(dict·list·문자열) 전체에서 OC=<값>을 OC=***로 가린 사본을 돌려준다. 법제처 응답을 받는 즉시, 그리고 원자료를 저장하기 전에 쓴다."""
    if isinstance(obj, str): return _mask_oc(obj, literal=False)
    if isinstance(obj, dict): return {(_mask_oc(k, literal=False) if isinstance(k, str) else k): scrub_oc(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return type(obj)(scrub_oc(v) for v in obj)
    return obj
