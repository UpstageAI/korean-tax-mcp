"""WP4 원문 대조분(2026-11-15, 법제처 DRF·국세법령정보시스템). Claude 작성. 외부 호출 없음.

대조한 원문:
- 국세기본법 제26조의2 2019.1.1. 시행본(제1항제4호·제4항)과 2026.10.2. 시행본(제4항·제5항제7호), 법률 제16841호 부칙 제18조
- 상속세 및 증여세법 시행령 제34조의2(2020.10.8.·2026.10.1. 현재 시행본), 제15조(2019.12.31.~2026.10.1. 현재 시행본 8개)와 대통령령 제30391호·제34267호·제35351호 부칙
- 부동산 실권리자명의 등기에 관한 법률 제7조: 법률 제11998호(2014.8.7.)·제13713호(2017.1.7.)·제17091호(2020.3.24.) 시행본
- 조세범 처벌법 제3조~제16조: 2016.3.2.·2021.1.1. 시행본의 조·항별 법정형
- 국세청 상속세 및 증여세 사무처리규정 제12조(훈령 제2760호, 2026.8.3.), 대법원 2017.2.21. 선고 2011두10232(법제처 판례)
- 해석: 서면-2016-상속증여-5376, 서울고등법원 2016누33027, 조심 2014서5656
"""
import json

from korean_tax_mcp import admrul, law
from korean_tax_mcp import family_business_succession as G
from korean_tax_mcp import nominee_trust as N
from korean_tax_mcp import tax_crime, tax_crime_procedure as P


def _txt(o):
    return json.dumps(o, ensure_ascii=False)


def test_nominee_labels_closed():
    old = N.guide("타인명의", "비상장주식", "2018-06-01", no_shareholder_register=True, origin="매도대금_재취득")
    new = N.guide("타인명의", "비상장주식", "2021-06-01", no_shareholder_register=True)
    for r in (old, new):
        assert "미확인" not in _txt(r) and "대조하지 못" not in _txt(r)
    # 2019.1.1. 경계: 종전 체계만 10년 합산(해석), 새 체계는 합산배제
    assert "서면-2016-상속증여-5376" in _txt(old["납세의무"]) and "납부세액공제" in old["납세의무"]["합산"]
    assert "합산배제" in new["납세의무"]["합산"] and "합산 해석" not in new["납세의무"]
    assert "조심 2014서5656" in _txt(old) and "조심 2014서5656" in _txt(new)
    assert "대법원 2011두10232" in _txt(old)
    # 2020.1.1. 경계: 주주명부가 없을 때 증여일(시행령 제34조의2)
    assert "시행령 제34조의2: 1. 증여세" in _txt(new) and "시행령 제34조의2: 1. 증여세" not in _txt(old)
    assert "제26조의2①4호" in _txt(new) and "법률 제16841호 부칙 제18조" in _txt(new)
    assert "제12조" in _txt(new) and "2001.7.23." in _txt(new) and "20억원" in _txt(new)


def test_nominee_real_estate_penalty():
    r = N.guide("타인명의", "토지", "2016-06-01")
    t = _txt(r)
    assert "2억원 이하 벌금" in t and "1억원 이하 벌금" in t and "3천만원 이하 벌금" in t and "2017.1.7. 시행" in t
    assert "미확인" not in t


def test_family_business_2023_gap_and_decree_changes():
    ev = [{"event": "가업 미종사", "date": "2023-02-01"}]
    r = G.guide("2022-06-01", post_events=ev)
    t = _txt(r)
    assert "부칙에 적용례가 없어 확인 필요" not in t and "미확인" not in t
    ch = {c["개정"]: c for c in r["시행령 개정(2020~2025)"]}
    assert ch["2020.2.11."]["이 상속개시일"] == "적용" and ch["2025.2.28."]["이 상속개시일"].startswith("적용 안 됨")
    a, b = G.guide("2025-02-27"), G.guide("2025-02-28")
    assert {c["개정"]: c for c in a["시행령 개정(2020~2025)"]}["2025.2.28."]["이 상속개시일"].startswith("적용 안 됨")
    assert {c["개정"]: c for c in b["시행령 개정(2020~2025)"]}["2025.2.28."]["이 상속개시일"] == "적용"
    assert "100분의 200" in _txt(b) and "대분류" in _txt(b)


def _warrant(**kw):
    r = P.guide("2024-03-01", flight_or_destroy_risk=True, **kw)
    return next(p for p in r["판정"] if p["항목"].startswith("영장 없는 압수"))


def test_warrantless_seizure_by_paragraph():
    assert _warrant(offense_article=10, offense_paragraph=3)["판정"] == "가능"          # 제10조제3항 3년
    assert _warrant(offense_article=10, offense_paragraph=1)["판정"].startswith("불가")   # 제10조제1항 1년
    assert _warrant(offense_article=10)["판정"].startswith("항에 따라 다름")
    assert _warrant(offense_article=7, offense_paragraph=3)["판정"].startswith("불가")    # 제7조제3항 2년
    assert _warrant(offense_article=7, offense_paragraph=2)["판정"] == "가능"
    assert _warrant(offense_article=13, offense_paragraph=1)["판정"].startswith("불가")   # 벌금형만
    assert _warrant(offense_article=3, evasion_proviso=True)["판정"] == "가능"
    assert _warrant(offense_article=3)["판정"].startswith("불가")
    assert _warrant(offense_article=5)["판정"] == "가능" and _warrant(offense_article=8)["판정"].startswith("불가")
    assert "확인 필요" not in _txt(_warrant(offense_article=10))
    assert "error" in P.guide("2024-03-01", offense_article=10, offense_paragraph=9)


def test_warrantless_seizure_without_paragraph_all_below_three_years(monkeypatch):
    # 항을 주지 않은 경우 — 조세범 처벌법 항별 장기(TERM_BY_PARA, 2016.3.2.·2021.1.1. 시행본 대조분)
    for art in (9, 11, 13):          # 제9조 2년·1년, 제11조 2년·1년, 제13조 벌금형만·2년 → 어느 항도 3년 미만
        w = _warrant(offense_article=art)
        assert w["판정"] == "불가(모든 항이 장기 3년 미만)", (art, w)
        assert "제항" not in _txt(w) and "가능" not in w["판정"]
        assert "항에 따라 다름" in w["사유"]                      # 항별 법정형은 사유에 그대로
    for art in (7, 10):              # 섞인 조 — 제7조 3년·3년·2년, 제10조 1년·1년·3년·3년
        w = _warrant(offense_article=art)
        assert w["판정"].startswith("항에 따라 다름 — 제") and "제항" not in w["판정"]
    assert "제1·2항은 가능" in _warrant(offense_article=7)["판정"]
    assert "제3·4항은 가능" in _warrant(offense_article=10)["판정"]
    # 모든 항이 3년 이상인 조는 현행 표에 없음 — 그런 표가 생겨도 '나머지 항은 불가'라고 하지 않는지 분기만 확인(표를 지어낸 값으로 바꿔서)
    monkeypatch.setitem(P.TERM_BY_PARA, 10, {1: 3, 2: 5})
    w = _warrant(offense_article=10)
    assert w["판정"] == "가능(모든 항이 장기 3년 이상)" and "나머지" not in w["판정"]


def test_tax_crime_limits_point_to_calc_tool():
    assert "tax_crime_settlement_amount" in tax_crime._LIMITS[0] and "대조하지 않음" not in tax_crime._LIMITS[0]


def test_admrul_search_single_row(monkeypatch):
    row = {"행정규칙일련번호": "1", "행정규칙명": "상속세 및 증여세 사무처리규정", "행정규칙종류": "훈령", "시행일자": "20260803", "소관부처명": "국세청"}
    monkeypatch.setattr(law, "_get", lambda path, query: {"AdmRulSearch": {"admrul": row}})
    assert admrul.search("상속세 및 증여세 사무처리규정")["시행일자"] == "20260803"


def test_english_law_search_strips_highlight_tags(monkeypatch):
    row = {"법령일련번호": "283631", "시행일자": "20260227", "법령명영문": "ENFORCEMENT DECREE OF THE INCOME TAX ACT",
           "법령명한글": '<strong class="tbl_tx_type"><strong class="tbl_tx_type">소득세법</strong> 시행령</strong>'}
    monkeypatch.setattr(law, "_get", lambda path, query: {"LawSearch": {"law": row}})
    assert [v["법령일련번호"] for v in law._en_versions("소득세법 시행령")] == ["283631"]
    assert law._en_versions("소득세법") == []


def test_english_article_new_response_format(monkeypatch):
    row = {"법령일련번호": "280389", "시행일자": "20260101", "법령명한글": '<strong class="tbl_tx_type">국제조세조정에 관한 법률</strong>'}
    full = {"Law": {"JoSection": {"Jo": [{"joNo": "0016", "joYn": "N", "joBrNo": "00", "joCts": "Subsection 3 ..."},
                                        {"joNo": "0016", "joYn": "Y", "joBrNo": "00", "joCts": "Article 16 (Obligation to Submit Data on International Transactions)"},
                                        {"joNo": "0016", "joYn": "Y", "joBrNo": "02", "joCts": "Article 16-2 (...)"}]}}}
    monkeypatch.setattr(law, "_get", lambda path, query: {"LawSearch": {"law": row}} if path == "lawSearch.do" else full)
    r = law.article_en("국제조세조정에 관한 법률", "제16조")
    assert r["본문"].startswith("Article 16 (Obligation") and "16-2" not in r["본문"]
    assert law.article_en("국제조세조정에 관한 법률", "제16조의2")["본문"].startswith("Article 16-2")
