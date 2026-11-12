"""0.12.21 sme_tax_incentives_guide — 조문 문언 대조 테스트(2026-11-12, Claude 작성).
근거: 조세특례제한법 제6조(2016~2026 시행본)·시행령 제5조·시행규칙 제4조의2, 제7조, 제127조④, 제132조①, 법인세법 제72조."""
from korean_tax_mcp import sme_incentives as G

OEM = {"domestic_maker": True, "own_planning": True, "own_name": True, "own_sale": True}


def test_overview_without_inputs():
    r = G.guide()
    assert len(r["창업중소기업 세액감면"]["창업 시기별 감면율"]) == 5 and len(r["창업중소기업 세액감면"]["위탁제조 요건"]) == 4
    assert len(r["중소기업 특별세액감면"]["감면율"]) == 6 and "법인세법 제72조" in r["결손금 소급공제"]["근거"]


def test_youth_oem_in_zone():
    r = G.guide("20210302", "수도권과밀억제권역", True, "위탁제조", OEM, size="소기업")
    s = r["창업중소기업 세액감면"]
    assert s["해당"] == "해당" and s["감면율"] == "50%" and "창업벤처중소기업" not in r
    assert r["중소기업 특별세액감면"]["감면율"] == "20%" and "하나만 선택" in r["선택"]


def test_non_youth_in_zone_goes_to_venture_and_special():
    r = G.guide("20210302", "수도권과밀억제권역", False, "위탁제조", OEM, venture_confirmed_on="20230110")
    assert r["창업중소기업 세액감면"]["해당"] == "대상 아님" and r["창업벤처중소기업"]["해당"] == "해당"
    assert G.guide("20210302", "수도권과밀억제권역", False, "위탁제조", OEM, venture_confirmed_on="20240601")["창업벤처중소기업"]["해당"] == "대상 아님"
    assert G.guide("20210302", "수도권과밀억제권역", False, "위탁제조", OEM)["창업벤처중소기업"]["해당"] == "확인 필요"


def test_industry():
    assert G.guide("20210302", "수도권 밖", False, "도매업")["창업중소기업 세액감면"]["해당"] == "대상 아님"
    assert G.guide("20170601", "수도권 밖", False, "통신판매업")["창업중소기업 세액감면"]["해당"] == "대상 아님"
    assert G.guide("20190601", "수도권 밖", False, "통신판매업")["창업중소기업 세액감면"]["감면율"] == "50%"
    r = G.guide("20210302", "수도권 밖", True, "위탁제조", dict(OEM, domestic_maker=False), size="소기업")     # 해외 제조업체 위탁
    assert r["창업중소기업 세액감면"]["해당"] == "대상 아님" and r["중소기업 특별세액감면"]["감면율"] == "10%"
    assert G.guide("20210302", "수도권 밖", True, "위탁제조")["창업중소기업 세액감면"]["해당"] == "확인 필요"       # 요건 미입력
    assert G.guide("20180301", "수도권 밖", False, "제조업")["창업중소기업 세액감면"]["해당"] == "확인 필요"       # 대조 못 한 기간


def test_rates_by_founding_date():
    f = lambda d, reg, y: G.guide(d, reg, y, "제조업")["창업중소기업 세액감면"].get("감면율")
    assert f("20160601", "수도권 밖", False) == "50%" and f("20160601", "수도권과밀억제권역", False) is None
    assert f("20170601", "수도권 밖", True).startswith("처음 3개 과세연도 75%")
    assert f("20200601", "수도권", True) == "100%" and f("20200601", "수도권과밀억제권역", True) == "50%"
    assert f("20260201", "수도권", True) == "75%" and f("20260201", "수도권", False) == "25%" and f("20260201", "수도권 인구감소지역", False) == "50%"
    assert G.guide("20250201", "수도권 밖", True, "제조업")["창업중소기업 세액감면"]["한도"].startswith("과세연도별 감면세액 합계 5억원")


def test_special_reduction_and_errors():
    assert G.guide("20210302", "수도권", False, "제조업", size="중기업")["중소기업 특별세액감면"]["해당"] == "대상 아님"
    assert G.guide("20210302", "수도권 밖", False, "제조업", size="중기업")["중소기업 특별세액감면"]["감면율"] == "15%"
    assert G.guide("20210302", "수도권", False, "제조업", hq_in_capital_area=False)["중소기업 특별세액감면"]["감면율"] == {"소기업": "30%", "중기업": "15%"}
    assert "error" in G.guide("20210302") and "error" in G.guide("2021-03-02", "수도권", False, "제조업") and "error" in G.guide("20210302", "서울", False, "제조업")


def test_consignment_rulings_in_special_reduction():
    # 0.12.23: 위탁제조면 제7조 결정례 2건과 업종 분류 주의를 함께 안내, 다른 업종에는 넣지 않음
    sp = G.guide("20210302", "수도권과밀억제권역", True, "위탁제조", OEM, size="소기업")["중소기업 특별세액감면"]
    assert [d["문서번호"] for d in sp["결정례"]] == ["조심2023서10448", "조심2010중3890"] and all(d["id"] and d["요지"] for d in sp["결정례"])
    assert "제4조의2" in sp["업종 주의"] and "자기명의" in sp["업종 주의"] and "원재료" in sp["업종 분류 주의"]
    assert sp["업종 구분"] == "그 밖의 감면 업종"
    bad = G.guide("20210302", "수도권과밀억제권역", True, "위탁제조", dict(OEM, own_name=False), size="소기업")["중소기업 특별세액감면"]
    assert bad["업종 구분"].startswith("도매업등") and "결정례" in bad
    assert "결정례" not in G.guide("20210302", "수도권과밀억제권역", True, "통신판매업", size="소기업")["중소기업 특별세액감면"]
