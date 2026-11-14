"""nominee_trust_guide 부동산 안내 — 부동산실명법·시행령 별표 대조 후 문구(2026-11-14, Claude 작성). 외부 호출 없음.
대조한 시행본(법제처 DRF): 부동산 실권리자명의 등기에 관한 법률 2020.3.24. 시행본(법률 제17091호) 제4조~제8조,
시행령 2016.9.1. 시행본(대통령령 제27472호)·2024.5.17. 시행본(대통령령 제34488호) 제3조의2·별표(5/10/15% + 5/10/15%)."""
from korean_tax_mcp import nominee_trust as N


def test_real_estate_text_no_unverified():
    r = N.guide("타인명의", "토지", "2020-05-01")
    items = {x["항목"]: x for x in r["부동산"]["부동산 실권리자명의 등기에 관한 법률"]}
    assert "미확인" not in str(items)
    assert "5억원 이하 5%" in items["과징금"]["내용"] and "2년 초과 15%" in items["과징금"]["내용"] and "100분의 50" in items["과징금"]["내용"]
    assert "100분의 20" in items["이행강제금·벌칙·특례"]["내용"] and "2억원 이하 벌금" in items["이행강제금·벌칙·특례"]["내용"]
    assert "상대방이 그 약정을 몰랐으면" in items["명의신탁약정·등기의 효력"]["내용"]
    assert "2016.1.6. 개정 전" in " ".join(r["한계"]) and "제34488호" in r["확인 시행본"]
