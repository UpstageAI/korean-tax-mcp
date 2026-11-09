"""패키지 전 파일이 requires-python 하한(3.10) 문법으로 파싱되는지 확인.

0.11.0~0.12.11에서 f-string 식 안의 백슬래시 때문에 3.10·3.11에서 import가
깨졌는데, 테스트가 3.12에서만 돌아 걸러지지 않았다(공개 검증 사례).
"""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent.parent / "korean_tax_mcp"
FILES = sorted(PKG.rglob("*.py"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(PKG).as_posix())
def test_parses_as_python_310(path):
    src = path.read_text(encoding="utf-8")
    ast.parse(src, filename=str(path), feature_version=(3, 10))
