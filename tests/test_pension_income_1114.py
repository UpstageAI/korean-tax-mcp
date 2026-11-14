"""pension_income_guide — 소득세법 2016.1.1.~2026.7.1. 시행본 12개(제12조제4호·제14조제3항·제20조의3·제21조·제47조의2·제64조의4·제129조·제146조)와 부칙,
소득세법 시행령 2016.2.17.~2026.10.1. 시행본 17개(제20조의2·제40조·제40조의2~제40조의4·제187조의2·제187조의3·제202조의2)와 부칙을
국세법령정보시스템 응답 캐시로 대조(2026-11-14). 경계일은 부칙 적용례·경과조치로 정함:
법률 제16834호 부칙 제22조(2020.1.1.), 제19196호 부칙 제2조(2023.1.1.), 제19933호 부칙 제13조(2024.1.1.), 제21221호 부칙 제15조제1항(2026.1.1.),
대통령령 제27829호 부칙 제4조(2017.2.3.), 제32420호 부칙 제3조(2022.2.15.). Claude 작성. 외부 호출 없음."""
from korean_tax_mcp import pension_income as P


def J(r):
    return {p["항목"]: p["판정"] for p in r["판정"]}


def W(r):
    return J(r)["원천징수"]


BASE = dict(age=60, join_date="2010-01-01", start_requested=True, pension_year=12)


def test_overview_and_errors():
    o = P.guide()
    assert len(o["날짜에 따라 달라지는 것"]) == 6 and "공적연금" in o["입력 안내"]["pension_type"]
    assert "error" in P.guide("2015-12-31", "공적연금") and "error" in P.guide("2027-01-01", "연금저축계좌")
    assert "error" in P.guide("2024-02-30", "연금저축계좌") and "error" in P.guide("2024-01-01", "개인연금")
    assert "error" in P.guide(pension_type="연금저축계좌") and "error" in P.guide("2024-01-01", "연금저축계좌", source="없는 재원")
    assert "error" in P.guide("2024-01-01", "연금저축계좌", pension_year=0) and "error" in P.guide("2024-01-01", "연금저축계좌", age=-1)
    assert P.guide("2024-01-01")["안내"].startswith("pension_type")


def test_threshold_1200_to_1500_2024():      # 법 제14조제3항제9호다목, 법률 제19933호 부칙 제13조
    assert P.threshold(P.datetime.date(2023, 12, 31)) == 12_000_000 and P.threshold(P.datetime.date(2024, 1, 1)) == 15_000_000
    a = P.guide("2023-12-31", "연금저축계좌", source="운용수익", annual_private_total=13_000_000, **BASE)
    b = P.guide("2024-01-01", "연금저축계좌", source="운용수익", annual_private_total=13_000_000, **BASE)
    assert J(a)["사적연금 분리과세"] == "종합과세" and J(b)["사적연금 분리과세"] == "분리과세(선택)"
    assert J(P.guide("2023-06-01", "연금저축계좌", source="운용수익", annual_private_total=12_000_000, **BASE))["사적연금 분리과세"] == "분리과세(선택)"
    assert J(P.guide("2025-06-01", "연금저축계좌", source="운용수익", annual_private_total=15_000_001, **BASE))["사적연금 분리과세"] == "종합과세"
    assert b["분리과세 기준"]["기준금액"].startswith("연 1,500만원") and a["분리과세 기준"]["기준금액"].startswith("연 1,200만원")


def test_choice_15pct_2023():               # 법 제64조의4(2022.12.31. 신설), 법률 제19196호 부칙 제2조
    a = P.guide("2022-12-31", "연금저축계좌", source="운용수익", annual_private_total=13_000_000, **BASE)
    b = P.guide("2023-01-01", "연금저축계좌", source="운용수익", annual_private_total=13_000_000, **BASE)
    sa = next(p for p in a["판정"] if p["항목"] == "사적연금 분리과세")
    sb = next(p for p in b["판정"] if p["항목"] == "사적연금 분리과세")
    assert "특례(법 제64조의4) 없음" in sa["사유"] and "100분의 15" in sb["사유"] and "제64조의4" in sb["근거"]
    assert a["분리과세 기준"]["선택 특례"].startswith("없음") and b["분리과세 기준"]["선택 특례"].startswith("있음")


def test_age_rates_and_lifetime_2026():      # 법 제129조제1항제5호의2 가목 표(2016~2026 같음)·다목(2026.1.1. 4%→3%, 법률 제21221호 부칙 제15조제1항)
    assert [P.age_rate(a) for a in (55, 69, 70, 79, 80, 95)] == [5, 5, 4, 4, 3, 3]
    k = dict(source="세액공제 받은 납입액", join_date="2010-01-01", start_requested=True, pension_year=12)
    assert W(P.guide("2025-06-01", "연금저축계좌", age=69, **k)) == "5%" and W(P.guide("2025-06-01", "연금저축계좌", age=70, **k)) == "4%"
    assert W(P.guide("2025-06-01", "연금저축계좌", age=80, **k)) == "3%"
    assert W(P.guide("2025-12-31", "연금저축계좌", age=72, lifetime_contract=True, **k)) == "4%"
    assert W(P.guide("2026-01-01", "연금저축계좌", age=72, lifetime_contract=True, **k)) == "3%"
    assert W(P.guide("2025-12-31", "연금저축계좌", age=60, lifetime_contract=True, **k)) == "4%"     # 5%·4% 중 낮은 세율
    assert W(P.guide("2026-01-01", "연금저축계좌", age=60, lifetime_contract=True, **k)) == "3%"


def test_retirement_source_ratio_2020_2026():   # 법 제129조제1항제5호의3 — 법률 제16834호 부칙 제22조, 제21221호 부칙 제15조제1항
    k = dict(source="이연퇴직소득", age=60, start_requested=True, pension_year=12)
    assert W(P.guide("2019-12-31", "퇴직연금계좌", actual_receipt_year=12, **k)) == "연금외수령 원천징수세율의 100분의 70"
    assert W(P.guide("2020-01-01", "퇴직연금계좌", actual_receipt_year=12, **k)) == "연금외수령 원천징수세율의 100분의 60"
    assert W(P.guide("2020-01-01", "퇴직연금계좌", actual_receipt_year=10, **k)) == "연금외수령 원천징수세율의 100분의 70"
    assert W(P.guide("2025-12-31", "퇴직연금계좌", actual_receipt_year=21, **k)) == "연금외수령 원천징수세율의 100분의 60"
    assert W(P.guide("2026-01-01", "퇴직연금계좌", actual_receipt_year=21, **k)) == "연금외수령 원천징수세율의 100분의 50"
    assert W(P.guide("2026-01-01", "퇴직연금계좌", actual_receipt_year=20, **k)) == "연금외수령 원천징수세율의 100분의 60"
    assert W(P.guide("2024-01-01", "퇴직연금계좌", **k)) == "확인 필요"
    r = P.guide("2024-01-01", "퇴직연금계좌", **k)
    assert J(r)["가입 5년 경과"] == "적용 제외" and J(r)["과세"] == "연금소득·분리과세"


def test_requirements_age_five_years_limit():     # 시행령 제40조의2제3항 각 호·제4항·제5항(2016~2026 개정 없음)
    r = P.guide("2025-06-01", "연금저축계좌", age=54, join_date="2010-01-01", start_requested=True, source="운용수익")
    assert J(r)["55세 이후 연금수령 개시 신청"] == "미충족" and J(r)["수령 형태"] == "연금외수령" and J(r)["과세(연금외수령분)"] == "기타소득·분리과세"
    k = dict(age=60, start_requested=True, source="운용수익", pension_year=12)
    assert J(P.guide("2024-03-09", "연금저축계좌", join_date="2019-03-10", **k))["가입 5년 경과"] == "미충족"
    assert J(P.guide("2024-03-10", "연금저축계좌", join_date="2019-03-10", **k))["가입 5년 경과"] == "충족"
    # 한도 = 1억 ÷ (11 − 1) × 120/100 = 1천200만원
    k2 = dict(age=60, start_requested=True, join_date="2015-01-01", source="운용수익", account_value=100_000_000, pension_year=1)
    assert J(P.guide("2025-06-01", "연금저축계좌", amount=12_000_000, **k2))["연금수령한도"] == "충족"
    r = P.guide("2025-06-01", "연금저축계좌", amount=13_000_000, **k2)
    assert J(r)["연금수령한도"] == "초과" and J(r)["수령 형태"] == "연금수령(한도 초과분은 연금외수령)"
    assert "1,000,000원" in next(p["사유"] for p in r["판정"] if p["항목"] == "연금수령한도") and J(r)["과세(연금외수령분)"] == "기타소득·분리과세"
    assert J(P.guide("2025-06-01", "연금저축계좌", age=60, start_requested=True, join_date="2015-01-01", source="운용수익", pension_year=11))["연금수령한도"] == "충족"
    assert J(P.guide("2025-06-01", "연금저축계좌", age=60, start_requested=False, join_date="2015-01-01", pension_year=11))["수령 형태"] == "연금외수령"
    assert J(P.guide("2025-06-01", "연금저축계좌"))["수령 형태"] == "확인 필요"


def test_other_withdrawal_taxation():           # 법 제21조제1항제21호·제14조제3항제8호나목·제129조제1항제6호나목, 제146조제2항
    k = dict(age=50, join_date="2010-01-01", start_requested=False)
    assert J(P.guide("2018-06-01", "퇴직연금계좌", source="이연퇴직소득", **k))["과세(연금외수령분)"] == "퇴직소득"
    assert J(P.guide("2018-06-01", "연금저축계좌", source="세액공제 받은 납입액", **k))["과세(연금외수령분)"] == "기타소득·분리과세"
    assert J(P.guide("2018-06-01", "연금저축계좌", source="세액공제 받지 않은 납입액", **k))["과세"] == "과세 제외"
    assert J(P.guide("2018-06-01", "연금저축계좌", source="그 밖의 이연소득", **k))["과세"] == "확인 필요"


def test_unavoidable_disaster_2022_and_items():   # 시행령 제20조의2제1항제1호라목 — 대통령령 제32420호 부칙 제3조(2022.2.15. 이후 인출)
    k = dict(source="세액공제 받은 납입액", age=50, docs_within_6m=True)
    a = P.guide("2022-02-14", "연금저축계좌", reason="재난 15일 이상 입원", **k)
    b = P.guide("2022-02-15", "연금저축계좌", reason="재난 15일 이상 입원", **k)
    assert J(a)["부득이한 인출"] == "해당 없음" and J(a)["수령 형태"] == "연금외수령"
    assert J(b)["부득이한 인출"] == "연금수령으로 봄" and J(b)["수령 형태"] == "부득이한 인출" and J(b)["과세"] == "연금소득·분리과세"
    assert "제1호라목" in P.guide("2021-06-01", "연금저축계좌", reason="파산·개인회생", **k)["판정"][0]["사유"]
    assert "제1호마목" in P.guide("2022-06-01", "연금저축계좌", reason="파산·개인회생", **k)["판정"][0]["사유"]
    assert J(P.guide("2022-06-01", "연금저축계좌", reason="3개월 이상 요양", source="운용수익", age=50, docs_within_6m=False))["부득이한 인출"] == "해당 없음"
    assert J(P.guide("2022-06-01", "연금저축계좌", reason="사망", source="운용수익", age=50))["부득이한 인출"] == "확인 필요"
    m = P.guide("2022-06-01", "연금저축계좌", reason="본인 의료비", source="운용수익", age=56, start_requested=True, join_date="2010-01-01", docs_within_6m=True)
    assert J(m)["의료비 인출"] == "연금수령으로 봄"
    assert J(P.guide("2022-06-01", "연금저축계좌", reason="본인 의료비", source="운용수익", age=50, docs_within_6m=True))["의료비 인출"] == "해당 없음"


def test_emigration_deferred_retirement_2017():   # 시행령 제40조의2제3항 단서 — 대통령령 제27829호 부칙 제4조(2017.2.3. 이후 입금분)
    k = dict(source="이연퇴직소득", reason="해외이주", docs_within_6m=True)
    assert J(P.guide("2019-01-01", "퇴직연금계좌", deposit_date="2017-02-02", **k))["부득이한 인출"] == "연금수령으로 봄"
    assert J(P.guide("2019-01-01", "퇴직연금계좌", deposit_date="2017-02-03", **k))["부득이한 인출"] == "해당 없음"
    assert J(P.guide("2020-02-03", "퇴직연금계좌", deposit_date="2017-02-03", **k))["부득이한 인출"] == "연금수령으로 봄"
    assert J(P.guide("2019-01-01", "퇴직연금계좌", **k))["부득이한 인출"] == "확인 필요"


def test_public_pension():                      # 법 제12조제4호, 제20조의3제2항, 제22조제1항제1호, 시행령 제40조
    assert J(P.guide("2016-06-01", "공적연금", public_benefit="유족연금"))["비과세 연금"] == "비과세"
    assert J(P.guide("2026-06-01", "공적연금", public_benefit="산업재해보상보험 연금"))["비과세 연금"] == "비과세"
    assert J(P.guide("2020-06-01", "공적연금", public_benefit="일시금"))["공적연금 일시금"] == "퇴직소득"
    r = P.guide("2020-06-01", "공적연금", public_benefit="노령·퇴직연금", public_fund="국민연금")
    assert J(r)["공적연금소득"] == "과세(종합과세)" and J(r)["원천징수"] == "기본세율" and "환산소득" in next(p["사유"] for p in r["판정"] if p["항목"] == "과세기준금액")
    assert "납입월수" in next(p["사유"] for p in P.guide("2020-06-01", "공적연금", public_fund="그 밖의 공적연금")["판정"] if p["항목"] == "과세기준금액")
    assert any(x["문서번호"] == "서면-2023-원천-1024" for x in r["관련 해석"]) and "pension_income" in r["다음 단계"][0]


def test_outputs_common():
    r = P.guide("2024-06-01", "퇴직연금계좌", source="운용수익", **BASE)
    assert "900만원" in r["연금소득공제"]["내용"] and "미확인" in " ".join(r["한계"]) and r["확인 시행본"] == P.VERIFIED
    assert "pension_account_withdrawal" in r["다음 단계"][0] and all(x["id"] for x in r["관련 해석"])
