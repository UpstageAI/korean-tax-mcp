"""tax_crime_procedure_guide — 조세범 처벌절차법 2026.10.2. 시행본 대조 후 고친 문구(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(법제처 DRF): 조세범 처벌절차법 2026.10.2. 시행본(법률 제21857호 형사소송법 개정 부칙 제15조<48>, 2026.8.4. 공포)
- 제2조제4호가목·나목 "지방검찰청의 검사장" → "지방공소청장", 제18조제1항·제2항 "검사" → "사법경찰관"
국세청 훈령 조사사무처리규정 제2734호(2026.4.20.) 제92조(14일·3일 전·재심의), 제95조(압수물 검사 인계)."""
from korean_tax_mcp import tax_crime_procedure as P


def step(r, name):
    return [x for x in r["절차"] if x["단계"] == name][0]


def test_boundary_2026_10_02():
    old, new = P.guide("2026-10-01"), P.guide("2026-10-02")
    assert "검사장 지명" in step(old, "조사")["주체"] and "지방공소청장" not in step(old, "조사")["주체"]
    assert "지방공소청장 지명" in step(new, "조사")["주체"] and "제21857호" in step(new, "조사")["근거"]
    assert "검사에게 인계" in step(old, "고발")["내용"] and "사법경찰관에게 인계" not in step(old, "고발")["내용"]
    assert "사법경찰관에게 인계" in step(new, "고발")["내용"] and "제21857호" in step(new, "고발")["근거"]
    assert old["날짜별 규정"]["고발 때 압수물건 인계처"].startswith("검사")
    assert new["날짜별 규정"]["고발 때 압수물건 인계처"].startswith("사법경찰관")
    assert new["날짜별 규정"]["세무공무원 지명권자"].startswith("관할 지방공소청장")
    assert P.guide("2019-05-01")["날짜별 규정"]["세무공무원 지명권자"].startswith("관할 지방검찰청의 검사장")


def test_directive_limits_and_verified():
    r = P.guide("2026-11-14")
    lim = " ".join(r["한계"])
    assert "제2734호" in lim and "14일" in lim and "3일 전" in lim and "재심의 1회" in lim and "원문을 대조하지 못해" not in lim
    assert "제21857호" in r["확인 시행본"]
