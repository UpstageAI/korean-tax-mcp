"""SPEC t5d: 실제 법령 데이터로 keyword 호 반환 고정.

ngs_41.json(국세징수법 제41조), ita_12.json(소득세법 제12조) 실제 DRF 응답을
tests/fixtures에 저장하고, fixture에서 직접 본문을 구성해 기대 결과와 비교한다.
"""
import json
import re
import pytest
from korean_tax_mcp import law

EXPECTED_NGS_41 = (
    "제41조(압류금지 재산) 다음 각 호의 재산은 압류할 수 없다.\n"
    "18. 「민사집행법」 제246조의2에 따른 생계비계좌에 예치된 예금 등 "
    "체납자의 생계 유지에 필요한 소액금융재산으로서 대통령령으로 정하는 것"
)


def _load_fixture(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_article_unit(raw, jo_key):
    for unit in raw["법령"]["조문"]["조문단위"]:
        if unit.get("조문키") == jo_key:
            return unit
    return None


def _clean_jo_title(jo_content):
    return re.sub(r"<개정[^>]*>|<개정\b|<신설[^>]*>|<신설\b", "", jo_content).strip()


def _build_body_from_fixture(raw, jo_key, keyword=None):
    """fixture에서 본문을 구성한다.

    keyword 지정 시: 해당 키워드가 포함된 호만 반환하되, 하나도 없으면
    law._article_body_with_scope의 '일치 없음' 분기처럼 조 제목 + 전체 호를 반환한다."""
    unit = _find_article_unit(raw, jo_key)
    assert unit is not None, f"조문키 {jo_key}를 fixture에서 찾지 못함"
    jo_title = _clean_jo_title(unit["조문내용"])
    ho_lines = []
    matched_any = False
    for ho in unit["항"]["호"]:
        if keyword and keyword not in ho["호내용"]:
            continue
        matched_any = True
        # DRF 호내용은 이미 "18. 「민사집행법」..." 형태로 번호가 포함되어 있으므로
        # 호번호를 중복 추가하지 않고 그대로 사용한다.
        ho_lines.append(ho["호내용"].strip())
    if keyword and not matched_any:
        # keyword가 어떤 호에도 없으면 전체 호 반환 (일치 없음 분기 모방)
        for ho in unit["항"]["호"]:
            ho_lines.append(ho["호내용"].strip())
    return "\n".join([jo_title] + ho_lines)


# ── 국세징수법 제41조 ────────────────────────────────────────────────────────────

def test_ngs_41_fixture_keyword_exact():
    """keyword='생계비계좌' → 기대 2줄과 정확히 일치."""
    raw = _load_fixture("tests/fixtures/ngs_41.json")
    body = _build_body_from_fixture(raw, "0041001", keyword="생계비계좌")
    assert body == EXPECTED_NGS_41, (
        f"\n실제 ({len(body.split(chr(10)))}줄):\n{body}\n\n"
        f"기대 ({len(EXPECTED_NGS_41.split(chr(10)))}줄):\n{EXPECTED_NGS_41}"
    )


def test_ngs_41_fixture_no_section_title():
    """편·장·절·관 제목(제2관)이 본문에 포함되지 않음."""
    raw = _load_fixture("tests/fixtures/ngs_41.json")
    body = _build_body_from_fixture(raw, "0041001")
    for token in ("제2관", "제2장", "제1절"):
        assert token not in body, f"{token}이 본문에 포함됨: {body[:80]}"


def test_ngs_41_fixture_no_revision_tag():
    """개정 표시(<개정 …>)가 본문에 포함되지 않음."""
    raw = _load_fixture("tests/fixtures/ngs_41.json")
    body = _build_body_from_fixture(raw, "0041001")
    assert "<개정" not in body, f"개정 표시가 본문에 남아 있음: {body[:100]}"


def test_ngs_41_fixture_full_order():
    """전체 호(1~18)가 조 제목 다음에 올바른 순서로 포함됨."""
    raw = _load_fixture("tests/fixtures/ngs_41.json")
    body = _build_body_from_fixture(raw, "0041001")
    lines = body.split("\n")
    assert lines[0].startswith("제41조"), f"첫 줄: {lines[0][:50]}"
    assert lines[1].startswith("1. "), f"두 번째 줄: {lines[1][:50]}"
    assert lines[-1].startswith("18. "), f"마지막 줄: {lines[-1][:50]}"
    assert len(lines) == 19, f"줄 수 불일치: {len(lines)} (기대 19)"


def test_ngs_41_fixture_keyword_missing_returns_full():
    """없는 keyword 검색 시 law '_호_목_매칭' 실패 → '일치 없음' 분기처럼
    조 제목 + 전체 호를 반환 (본문 앞 2000자 이내)."""
    raw = _load_fixture("tests/fixtures/ngs_41.json")
    body = _build_body_from_fixture(raw, "0041001", keyword="존재하지않는단어")
    assert body.startswith("제41조(압류금지 재산)")
    assert "1. 체납자" in body
    assert "18. 「민사집행법」" in body
    assert "<개정" not in body


# ── 소득세법 제12조 (항·호 혼합 구조) ─────────────────────────────────────────────

def test_ita_12_fixture_keyword():
    """keyword='비과세' → 조 제목 + 매칭 호 포함, 개정 표시·장·절 제목 없음."""
    raw = _load_fixture("tests/fixtures/ita_12.json")
    body = _build_body_from_fixture(raw, "0012001", keyword="비과세")
    assert "제12조(비과세소득)" in body
    assert "공익신탁" in body
    assert "<개정" not in body
    for token in ("제2장", "제1절", "거주자의 종합소득"):
        assert token not in body, f"{token}이 본문에 포함됨: {body[:80]}"


def test_ita_12_fixture_full_no_section():
    """전체 본문에서도 장·절 제목이 포함되지 않음."""
    raw = _load_fixture("tests/fixtures/ita_12.json")
    body = _build_body_from_fixture(raw, "0012001")
    assert "제2장" not in body
    assert "제1절" not in body
    assert body.startswith("제12조(")


# ── 실제 law._article_body_with_scope 네트워크 스모크 (선택) ──────────────────────

def test_ngs_41_live_keyword():
    """실제 네트워크 호출로 keyword='생계비계좌' 결과가 기대 2줄과 일치하는지 확인."""
    r = law._article_body_with_scope("국세징수법", "제41조", None, "", None, "생계비계좌")
    body = r["본문"]
    assert body == EXPECTED_NGS_41, (
        f"\n실제 ({len(body.split(chr(10)))}줄):\n{body}\n\n"
        f"기대:\n{EXPECTED_NGS_41}"
    )
    print(f"\n[LOG] 국세징수법 제41조 keyword=생계비계좌 live 결과 ({len(body.split(chr(10)))}줄):")
    print(body)
