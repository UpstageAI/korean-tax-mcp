"""미확인 채우기(조특) — 조문 MCP 안내 도구. Claude 작성(2026-11-15).
대조한 원문(법제처 시행본·부칙, 2026-11-15 조회):
  조세특례제한법 제6조 2018.2.9. 시행본(법률 제15227호, 2018.1.1. 시행)·부칙 제4조·제39조, 법률 제15623호(2018.5.29.) 부칙 제4조, 법률 제16835호 부칙 제4조
  조세특례제한법 시행령 제5조 2017.2.7.·2018.2.13. 시행본(청년 15~29세), 대통령령 제29116호(2018.8.28.) 부칙 제2조(2018.5.29. 이후 창업분부터 34세),
  대통령령 제27848호(2017.2.7.) 부칙 제2조, 조세특례제한법 시행규칙 제2조제1항(2016.8.13. 시행본)·제4조의2(2017.3.17. 시행본)
  해석: 서면-2017-소득-0523(2017.3.22.)"""
from korean_tax_mcp import employment_requirements as E
from korean_tax_mcp import sme_incentives as G

OEM = {"domestic_maker": True, "own_planning": True, "own_name": True, "own_sale": True}


def test_founded_2018_before_may_29_uses_2017_rates():
    f = lambda d, reg, y: G.guide(d, reg, y, "제조업")["창업중소기업 세액감면"]
    assert f("20180528", "수도권 밖", True)["감면율"].startswith("처음 3개 과세연도 75%")      # 경계 앞: 2018.1.1. 시행본
    assert f("20180529", "수도권 밖", True)["감면율"] == "100%"                                # 경계 뒤: 2018.5.29. 개정
    assert f("20180301", "수도권과밀억제권역", True)["해당"] == "대상 아님"                    # 그 시행본은 과밀억제권역 밖만
    assert f("20180529", "수도권과밀억제권역", True)["감면율"] == "50%"
    assert "15~29세" in f("20180528", "수도권 밖", True)["청년창업 요건"] and "15~34세(병역" in f("20180529", "수도권 밖", True)["청년창업 요건"]
    row = next(r for r in G.RATE_TABLE if r["창업 시기"] == "2018.1.1.~5.28.")
    assert "대조하지 못" not in row["감면율"] and "2017년 창업과 같음" in row["감면율"]


def test_contract_manufacturing_founded_2016():
    r = G.guide("20160502", "수도권 밖", False, "위탁제조", OEM)["창업중소기업 세액감면"]
    assert r["해당"] == "해당" and r["감면율"] == "50%" and "확인할 것" not in r
    assert any("서면-2017-소득-0523" in x for x in r["근거"]) and any("시행규칙 제2조제1항" in x for x in r["사유"])
    r = G.guide("20170301", "수도권 밖", False, "위탁제조", OEM)["창업중소기업 세액감면"]
    assert r["해당"] == "해당" and not any("서면-2017-소득-0523" in x for x in r["근거"])
    assert G.guide("20160502", "수도권 밖", False, "위탁제조", dict(OEM, domestic_maker=False))["창업중소기업 세액감면"]["해당"] == "대상 아님"


def test_no_unverified_wording_left():
    assert "2020.1.1. 이후 창업분부터 개정 목록" in G.guide()["창업중소기업 세액감면"]["업종"]
    for year, credit in ((2025, "통합고용"), (2026, "통합고용"), (2020, "고용증대")):
        text = " ".join(E.guide(year, credit=credit)["한계"])
        assert "확인하지 못함" not in text and "아직 계산 도구에 없음" not in text
    assert "제29조의8 항목이 없음" in " ".join(E.guide(2025, credit="통합고용")["한계"])
