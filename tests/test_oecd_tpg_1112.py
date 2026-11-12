"""oecd_tp_guidelines(2026-11-12, Claude) — OECD 이전가격지침 2022 문단 색인."""
from korean_tax_mcp import oecd_tpg as O
from korean_tax_mcp import server as S
from korean_tax_mcp import transfer_pricing as T


def test_index_is_complete_and_sequential():
    rows = O._rows()
    assert len(rows) == 1391
    counts = {}
    for r in rows:
        counts[r["_ch"]] = counts.get(r["_ch"], 0) + 1
    assert counts == {1: 193, 2: 187, 3: 83, 4: 179, 5: 62, 6: 212, 7: 65, 8: 53, 9: 131, 10: 226}
    prev = None
    for r in rows:      # 장 안에서 번호가 빠짐없이 이어짐
        if prev and prev["_ch"] == r["_ch"]:
            assert r["_no"] == prev["_no"] + 1, r["문단"]
        prev = r
    assert all(r["본문"] and r["쪽"] > 0 for r in rows)
    assert not any("OECD TRANSFER PRICING GUIDELINES ©" in r["본문"] for r in rows)       # 머리글이 본문에 섞이지 않음


def test_known_paragraphs():
    r = O.lookup("2.14")["결과"][0]
    assert r["본문"].startswith("The CUP method compares") and r["쪽"] == 97
    r = O.lookup("3.57")["결과"][0]
    assert "interquartile range" in r["본문"] and r["쪽"] == 165
    assert "low value-adding" in O.lookup("7.61")["결과"][0]["본문"]
    assert O.lookup("2.27")["결과"][0]["본문"].startswith("The resale price method begins")


def test_lookup_ranges_limits_and_errors():
    r = O.lookup("3.55-3.62")
    assert r["문단 수"] == 8 and [x["문단"] for x in r["결과"]] == [f"3.{n}" for n in range(55, 63)]
    assert "doi.org/10.1787/0e655865-en" in r["출처"] and "법적 효력" in r["지위"]
    r = O.lookup("2.14-2.40")
    assert r["문단 수"] == 27 and len(r["결과"]) == 12 and "2.26" in r["더 있음"]
    assert O.lookup("1.36, 2.2")["문단 수"] == 2
    assert O.lookup("3.999")["없는 문단"] == ["3.999"]
    assert "error" in O.lookup("abc") and "error" in O.lookup("2.1-3.4")


def test_search_korean_terms_and_chapter_filter():
    assert O.search("사분위")["결과"][0]["문단"] == "3.57"
    r = O.search("판매법인 위험", chapter=1, n=4)
    assert r["결과"] and all(x["문단"].startswith("1.") for x in r["결과"]) and "발췌" in r["결과"][0]
    assert O.search("tested party")["전체건수"] >= 5
    z = O.search("zzzzqqqq")
    assert z["전체건수"] == 0 and "안내" in z


def test_crosswalk_rows_exist_in_index():
    cw = O.crosswalk()
    assert cw["전체건수"] == len(O.CROSSWALK) == 29
    for row in O.CROSSWALK:
        for part in row["문단"].split(","):
            res = O.lookup(part.strip(), limit=500)
            assert "error" not in res and not res.get("없는 문단"), row
    assert [x["문단"] for x in O.crosswalk("시행령 제15조")["대응표"]][:4] == ["3.1-3.8", "3.9-3.12", "3.47-3.54", "3.55-3.62"]
    assert O.crosswalk("재판매")["대응표"][0]["문단"] == "2.27-2.44"


def test_tool_modes():
    f = getattr(S.oecd_tp_guidelines, "fn", S.oecd_tp_guidelines)
    assert len(f()["장"]) == 10
    assert f(chapter=3)["절"][0]["시작 문단"] == "3.1"
    assert f(paragraph="1.60")["결과"][0]["문단"] == "1.60"
    assert f(keyword="interquartile")["결과"][0]["문단"] == "3.57"
    assert f(crosswalk="금전대차")["전체건수"] == 2 and f(crosswalk="전체")["전체건수"] == 29


def test_guide_links_to_guideline_paragraphs():
    r = T.guide("재화", facts={"buyer_resells": True})
    by = {m["방법"]: m for m in r["산출방법"]}
    assert by["재판매가격방법"]["OECD 지침 문단"] == "2.27-2.44" and by["거래순이익률방법"]["OECD 지침 문단"] == "2.64-2.113"
    topics = [x["주제"] for x in r["OECD 지침"]["관련 문단"]]
    assert any("정상가격 범위" in t for t in topics) and any("사업전략" in t for t in topics)
    assert any("지급보증" in x["주제"] for x in T.guide("지급보증")["OECD 지침"]["관련 문단"])
