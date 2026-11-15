"""0.17.0 통합 확인 — 따로 만든 변경이 합쳐진 뒤에도 서로 맞물리는지. Claude 작성. 외부 호출 없음.

1. 서면 결과물 안내(공통 래퍼)가 이번에 새로 넣거나 고친 입력으로 부른 요건 안내 도구 결과에도 붙는지(국문·영문).
2. 법제처 응답 가림이 영문법령의 새 응답 형식(검색 결과의 강조 태그, JoSection 본문)과 행정규칙 검색 1건 응답에서도 동작하는지.

가짜 키는 글자를 이어 붙여 만든다 — 검사 대상 모양이 소스에 그대로 적히지 않게.
"""
import asyncio
import json

import pytest

from korean_tax_mcp import admrul, law, net
from korean_tax_mcp import server as S
from korean_tax_mcp.server import mcp

FAKE = "rel" + "fake" + "0170"          # 가짜 키(실제 키 아님)
OC = "OC" + "="
MASKED = OC + "***"


def _call(name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


def _txt(o): return json.dumps(o, ensure_ascii=False, default=str)


# ── 1. 서면 결과물 안내 ──

NEW_INPUT_CALLS = [
    ("dividend_income_guide", {"date": "2025-06-01", "dividend_type": "이익배당", "facts": {"reserve_reduction": "재평가적립금_토지"}}),
    ("dividend_income_guide", {"date": "2025-06-01", "dividend_type": "이익배당", "facts": {"reserve_reduction": "재평가적립금_토지외"}}),
    ("royalty_withholding_guide", {"payment_date": "2024-05-01", "recipient_country": "미국", "settled_by_setoff": True}),
    ("royalty_withholding_guide", {"payment_date": "2018-05-01", "recipient_country": "미국", "recipient_type": "개인"}),
    ("tax_crime_procedure_guide", {"decision_date": "2024-03-01", "offense_article": 10, "offense_paragraph": 3, "flight_or_destroy_risk": True}),
    ("tax_crime_procedure_guide", {"decision_date": "2024-03-01", "offense_article": 9, "flight_or_destroy_risk": True}),
    ("one_house_exemption_guide", {"transfer_date": "2021-06-01", "existing_tenant_lease_end": "2021-12-31"}),
    ("vat_exempt_zero_rate_guide", {"supply_date": "2024-05-01", "facts": {"packaged_for_sale": True, "payment_method": "국외 발급 신용카드"}}),
    ("permanent_establishment_guide", {"year": 2024, "agent_types": ["주로 특정 외국법인만을 위한 독립대리인"]}),
    ("sme_tax_incentives_guide", {}),
    ("family_business_succession_guide", {"inheritance_date": "2025-02-28"}),
    ("nominee_trust_guide", {}),
]


def _args_for(name, wanted):
    """도구가 실제로 받는 인자만 남긴다 — 인자 이름이 바뀌어도 이 테스트가 안내 줄만 보게."""
    props = set((mcp._tool_manager.get_tool(name).parameters or {}).get("properties", {}))
    return {k: v for k, v in wanted.items() if k in props}


@pytest.mark.parametrize("name,args", NEW_INPUT_CALLS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(NEW_INPUT_CALLS)])
def test_memo_line_follows_new_inputs(name, args, monkeypatch):
    monkeypatch.setattr(S.ntis, "withholding_rates", lambda *a, **k: {"error": "offline"})   # 조약 조회는 건너뜀
    for lang in ("ko", "en"):
        r = _call(name, {**_args_for(name, args), "lang": lang})
        assert "error" not in r, (name, r)
        assert S.MEMO_NEXT[lang] in _txt(r), (name, lang)
        if lang == "ko": assert r[S.NEXT_KEY][-1] == S.MEMO_NEXT["ko"], name


def test_new_inputs_are_registered_on_the_tools():
    props = lambda n: set((mcp._tool_manager.get_tool(n).parameters or {}).get("properties", {}))
    assert "settled_by_setoff" in props("royalty_withholding_guide")
    assert "offense_paragraph" in props("tax_crime_procedure_guide")
    assert "existing_tenant_lease_end" in props("one_house_exemption_guide")
    assert "재평가적립금_토지외" in mcp._tool_manager.get_tool("dividend_income_guide").description or \
           "재평가적립금_토지외" in _txt(mcp._tool_manager.get_tool("dividend_income_guide").parameters)


def test_every_guide_tool_goes_through_the_wrapper():
    names = [t.name for t in asyncio.run(mcp.list_tools()) if t.name.endswith("_guide") and t.name != "tax_memo_guide"]
    assert len(names) == 19
    for n in names:
        assert "lang" in (mcp._tool_manager.get_tool(n).parameters or {}).get("properties", {}), n   # bilingual 래퍼를 지난다는 표시


def test_article_9_without_paragraph_is_not_allowed():
    r = _call("tax_crime_procedure_guide", {"decision_date": "2024-03-01", "offense_article": 9, "flight_or_destroy_risk": True})
    row = next(p for p in r["판정"] if p["항목"].startswith("영장 없는 압수"))
    assert row["판정"] == "불가(모든 항이 장기 3년 미만)"
    assert r[S.NEXT_KEY][-1] == S.MEMO_NEXT["ko"]


# ── 2. 응답 가림 × 새 응답 형식 ──

@pytest.fixture
def fake_law(monkeypatch):
    def clear():
        for name in ("_versions", "_three_tier", "_raw_units", "_full_units", "_phrase_defs", "_en_versions"):
            f = getattr(law, name)
            (f.clear if hasattr(f, "clear") else f.cache_clear)()
        law.clear_caches(); net.reset()
    monkeypatch.setenv("LAW_OC", FAKE)
    clear()
    urls = []

    def fake(req, **k):
        u = req.full_url
        urls.append(u)
        link = f"/DRF/lawService.do?{OC}{FAKE}&target=elaw&MST=77&type=HTML"
        if "lawSearch.do" in u and "target=elaw" in u:
            body = {"LawSearch": {"law": {"법령명한글": '<strong class="tbl_tx_type">국제조세조정에 관한 법률</strong>', "법령명영문": "ADJUSTMENT OF INTERNATIONAL TAXES ACT",
                                          "법령일련번호": "77", "시행일자": "20260101", "법령상세링크": link}}}
        elif "lawService.do" in u and "target=elaw" in u:
            body = {"Law": {"링크": link, "JoSection": {"Jo": [
                {"joNo": "0016", "joBrNo": "00", "joYn": "N", "joCts": "SECTION 3"},
                {"joNo": "0016", "joBrNo": "00", "joYn": "Y", "joCts": f"Article 16 (Made-up heading) text, see https://www.law.go.kr/DRF/lawService.do?{OC}{FAKE}&target=elaw"},
                {"joNo": "0016", "joBrNo": "02", "joYn": "Y", "joCts": "Article 16-2 other"}]}}}
        elif "target=admrul" in u:
            body = {"AdmRulSearch": {"admrul": {"행정규칙일련번호": "9", "행정규칙명": "지어낸 사무처리규정", "행정규칙종류": "훈령", "시행일자": "20260803",
                                                 "소관부처명": "국세청", "행정규칙상세링크": f"/DRF/lawService.do?{OC}{FAKE}&target=admrul&ID=9"}}}
        else:
            body = {}
        return json.dumps(body, ensure_ascii=False).encode()

    monkeypatch.setattr(net, "request", fake)
    yield urls
    clear()


def test_masking_holds_in_the_english_statute_format(fake_law):
    r = law.article_en("국제조세조정에 관한 법률", "제16조")
    assert r["본문"].startswith("Article 16 (Made-up heading)") and "Article 16-2" not in r["본문"]
    assert r["법령"] == "ADJUSTMENT OF INTERNATIONAL TAXES ACT"
    assert FAKE not in _txt(r) and MASKED in r["본문"]
    raw = law._get("lawService.do", "target=elaw&MST=77&JO=001600")
    assert FAKE not in _txt(raw) and raw["Law"]["링크"].startswith(f"/DRF/lawService.do?{MASKED}&")
    assert fake_law and all(f"{OC}{FAKE}" in u for u in fake_law)          # 키는 요청 주소에만 쓰인다


def test_masking_holds_for_a_single_row_admin_rule_search(fake_law):
    r = admrul.search("지어낸 사무처리규정")
    assert r["시행일자"] == "20260803" and FAKE not in _txt(r)
    raw = law._get("lawSearch.do", "target=admrul&display=10&query=x")
    assert isinstance(raw["AdmRulSearch"]["admrul"], dict) and FAKE not in _txt(raw)
    assert MASKED in raw["AdmRulSearch"]["admrul"]["행정규칙상세링크"]
