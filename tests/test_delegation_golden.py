"""위임 연결 정답 테스트 (Claude 작성 2026-10-12) — 기준(쌍·허용 누락 수) 수정 금지. 실제 법제처 API 호출(LAW_OC 필요).
실제 호출은 KTM_LIVE=1 이고 LAW_OC가 있을 때만 — 없으면 건너뛰어 `pytest tests/` 전체가 오프라인으로 돈다.
실행: KTM_LIVE=1 LAW_OC=… .venv/bin/python -m pytest tests/test_delegation_golden.py -q
"""
import json
import os
import re

import pytest

LIVE = os.environ.get("KTM_LIVE") == "1" and bool(os.environ.get("LAW_OC", "").strip())
pytestmark = pytest.mark.skipif(not LIVE, reason="실제 법제처 호출 — KTM_LIVE=1 과 LAW_OC가 있을 때만")

FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "delegation_golden.json"), encoding="utf-8"))
AS_OF = FX["기준일"]
N = lambda s: re.sub(r"\s+", "", s or "")


def tool(fn):
    return getattr(fn, "fn", fn)


# 1. law.links(법령, 조, as_of) → {"상위": [{"법령","조"}...], "하위": [{"법령","조","항"?, "구절"?}...]}
def test_article_links_400_pairs():
    from korean_tax_mcp import law
    miss_down = []; miss_up = []
    for p in FX["조연결"]:
        d = law.links(p["상위"], p["상위조"], AS_OF)
        if not any(N(x["법령"]) == N(p["하위"]) and x["조"] == p["하위조"] for x in d.get("하위", [])):
            miss_down.append(p)
        u = law.links(p["하위"], p["하위조"], AS_OF)
        if not any(N(x["법령"]) == N(p["상위"]) and x["조"] == p["상위조"] for x in u.get("상위", [])):
            miss_up.append(p)
    assert len(miss_down) <= 4, f"하위 연결(상위 조 → 하위 조) 400쌍 누락 {len(miss_down)} 예 {miss_down[:3]}"
    assert len(miss_up) <= 4, f"상위 연결(하위 조 → 상위 조) 400쌍 누락 {len(miss_up)} 예 {miss_up[:3]}"


# 2. 구절 단위: 상위 조문 위임 구절 → 하위 조(항)
def test_phrase_links_80():
    from korean_tax_mcp import law
    miss_ph = []
    for p in FX["구절연결"]:
        d = law.links(p["상위"], p["상위조"], AS_OF)
        ok = any(N(x["법령"]) == N(p["하위"]) and x["조"] == p["하위조"] and N(p["구절"])[:10] in N(x.get("구절", ""))
                 for x in d.get("하위", []))
        if not ok:
            miss_ph.append(p)
    assert len(miss_ph) <= 2, f"구절 연결 80건 누락 {len(miss_ph)} 예 {miss_ph[:3]}"


# 3. law_article 기본 출력에 '연결'(행선지 포인터, 본문 없음) 포함 — 법률·시행령·시행규칙 모두
@pytest.mark.parametrize("nm,art,want", [("법인세법", "제16조", ("하위", "법인세법 시행령", "제12조")),
                                         ("법인세법 시행령", "제12조", ("상위", "법인세법", "제16조")),
                                         ("조세특례제한법", "제104조의5", ("하위", "조세특례제한법 시행령", "제104조의2"))])
def test_law_article_has_links(nm, art, want):
    from korean_tax_mcp import server
    o = tool(server.law_article)(law_name=nm, article=art, as_of=AS_OF)
    con = o.get("연결", {})
    assert any(N(x["법령"]) == N(want[1]) and x["조"] == want[2] for x in con.get(want[0], [])), str(con)[:200]
    assert all("본문" not in x for v in con.values() for x in v), "연결은 포인터만(본문 없음)"


# 4. with_delegation이 시행령·시행규칙 입력에서도 오류 없이 동작
@pytest.mark.parametrize("nm,art", [("국세기본법 시행령", "제11조"), ("법인세법 시행령", "제12조"), ("소득세법 시행규칙", "제2조")])
def test_with_delegation_lower_tiers(nm, art):
    from korean_tax_mcp import server
    o = tool(server.law_article)(law_name=nm, article=art, as_of=AS_OF, with_delegation=True)
    assert "error" not in o and o.get("위임체계"), str(o)[:200]
