"""residency_check — 조세조약 tie-break로 상대국 거주자가 나올 때 lang='en'이 죽지 않는지, 이중거주자가 아닌데 tie-break 문구가 붙지 않는지.

2026-11-14 배포본(korean-tax-mcp 0.15.1)에서 lang='en' + tie-break 결과 '상대국(미국) 거주자'가 KeyError로 실패했다.
네트워크 없이 돈다(조약 조회는 거주자 조문 1건을 돌려주는 대역 — 본문은 검사하지 않는 자리 표시 문장).
"""
import asyncio
import json

import pytest

from korean_tax_mcp import ntis, solar
from korean_tax_mcp.server import mcp

TIE = {"judgment_year": 2026, "domestic_stay_days": 200, "job_needs_183_days": True,
       "treaty_country": "미국", "treaty_country_is_resident": True, "permanent_home": "양쪽",
       "center_of_vital_interests": "국외", "habitual_abode": "양쪽", "nationality": "외국"}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def fake_treaty(*a, **k):
        return {"발효일": "", "링크": "", "조문": [{"조": "제3조", "제목": "과세상의 주소", "본문": "(대역 본문)"}]}
    monkeypatch.setattr(ntis, "treaty", fake_treaty)
    monkeypatch.setattr(solar, "available", lambda: False)
    monkeypatch.setattr(solar, "mode", lambda: "host_ai")
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    monkeypatch.delenv("KOREAN_TAX_MCP_SOLAR_BASE_URL", raising=False)


def _call(args):
    r = asyncio.run(mcp.call_tool("residency_check", args))
    return json.loads(r.content[0].text)


def test_tie_break_foreign_resident_in_english():
    r = _call({**TIE, "lang": "en"})
    assert r["stage3_treaty_tie_break"]["residence_country"] == "foreign resident (미국)"
    assert r["final_outcome"] == "non-resident"


def test_tie_break_foreign_resident_in_korean_unchanged():
    r = _call(TIE)
    assert r["3단계(조세조약 tie-break)"]["최종 거주지국"] == "상대국(미국) 거주자"
    assert r["최종 판정"] == "비거주자"


def test_not_dual_resident_reason_has_no_tie_break_wording():
    args = {**TIE, "treaty_country_is_resident": False}
    r = _call(args)
    assert r["최종 판정"] == "거주자"
    assert "tie-break 결과" not in r["최종 판정 근거"] and "None" not in r["최종 판정 근거"]
    assert "이중거주자에 해당하지 않아" in r["최종 판정 근거"]
