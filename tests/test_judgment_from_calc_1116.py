"""계산 MCP에서 옮겨 온 판단 근거 — 몰수·추징된 위법소득(대법원 2014두5514 전원합의체)과 특수관계인 범위 조문 위치 찾기.

계산 MCP(korean-tax-calc-mcp)는 금액만 계산하고, 판단 근거는 이 서버 도구에서 본다.
- other_income_guide(뇌물·알선수재): '몰수·추징' 판정과 판례 요지(국세법령정보시스템 요지 대조 2026-11-16, id 000000000000354862).
- 계산 MCP에서 뺀 related_provision_at(기준일의 특수관계 조문 위치)은 find_article(as_of)·law_article(as_of)로 찾는다 — 찾는 법을 find_article 설명에 적음.
외부 호출 없음.
"""
import asyncio

from korean_tax_mcp import other_income as O
from korean_tax_mcp import server as S


def _p(r, name):
    return next(p for p in r["판정"] if p["항목"] == name)


def test_bribe_forfeiture_judgment():
    p = _p(O.guide("2024-05-01", "뇌물", 10_000_000), "몰수·추징")
    assert p["판정"] == "몰수·추징이 확정된 금액은 소득이 실현되지 않은 것으로 봄"
    assert "국세기본법 제45조의2제2항" in p["근거"] and "2014두5514 전원합의체" in p["근거"]
    assert "forfeited" in p["사유"]
    h = p["해석"][0]
    assert (h["문서번호"], h["일자"], h["id"]) == ("대법원-2014-두-5514(전원합의체)", "2015.07.16.", "000000000000354862")


def test_bribery_brokerage_same_rule_without_forfeited_arg():
    p = _p(O.guide("2019-03-01", "알선수재"), "몰수·추징")
    assert p["해석"][0]["id"] == "000000000000354862"
    assert "forfeited는 뇌물 항목만" in p["사유"]


def test_other_items_have_no_forfeiture_entry():
    assert all(p["항목"] != "몰수·추징" for p in O.guide("2024-05-01", "상금", 1_000_000)["판정"])


def test_find_article_explains_related_party_provision_by_date():
    doc = {t.name: t for t in asyncio.run(S.mcp.list_tools())}["find_article"].description
    for s in ("특수관계인의 범위", "국세기본법 시행령", "상속세 및 증여세법 시행령", "제12조의2", "제2조의2", "제87조",
              "법 제2조제12호", "제8항", "law_article(law_name, 조, as_of=기준일"):
        assert s in doc, s
