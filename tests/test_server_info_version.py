"""initialize 응답의 serverInfo.version이 비지 않고 설치된 패키지 버전과 같은지.

2026-11-14 `uvx korean-tax-mcp==0.15.1`의 initialize 응답에서 serverInfo.version이 ''였다
(MCPServer에 version을 넘기지 않았고, __init__.__version__은 0.12.17에 멈춰 있었다).
"""
import asyncio
from importlib.metadata import version

from mcp import Client

import korean_tax_mcp
from korean_tax_mcp.server import mcp


def test_server_info_version_matches_installed_package():
    async def run():
        async with Client(mcp) as c:
            return c.server_info

    info = asyncio.run(run())
    assert info is not None and info.name == "korean-tax-mcp"
    assert info.version == version("korean-tax-mcp") == korean_tax_mcp.__version__
    assert info.version and info.version != "0.12.17"
    assert info.description and "tax treaties" in info.description
