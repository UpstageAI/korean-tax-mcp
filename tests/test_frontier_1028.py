"""10/28 프론티어 점검 회귀 테스트(오프라인). 작성 Claude 2026-10-28."""
import json, os
from korean_tax_mcp import claims, law

FX = os.path.join(os.path.dirname(__file__), "fixtures", "jtt136_20251231.json")


def _units():
    return [tuple(u) for u in json.load(open(FX, encoding="utf-8"))]


def test_verify_statement_anchors_on_rare_topic_not_number():
    u = _units()
    r = claims.compare("문화 기업업무추진비는 일반 기업업무추진비 한도액의 100분의 30을 한도로 추가로 손금에 산입한다.", u)
    assert r["판정"] == "모순" and r["근거"]["위치"].endswith("③")
    assert r["대조"][0]["조문"] == "100분의 20"
    r = claims.compare("전통시장에서 지출한 기업업무추진비는 한도액의 100분의 30 범위에서 손금에 산입한다.", u)
    assert r["근거"]["위치"].endswith("⑥") and r["대조"][0]["조문"] == "100분의 10"


def test_addenda_article_match_excludes_branch_articles():
    assert law._article_mentioned("제87조제2호의 개정규정", "제87조")
    assert not law._article_mentioned("제87조의2제1항의 개정규정", "제87조")
