"""주장 대조(verify_statement) 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
fixtures/claims_golden.json: 진술은 공개 검증 사례(세무사 1차 2024, 출처 Q-Net) 보기, 조문 단위는 법제처 시행본 원문 그대로.
기대 판정은 Claude가 조문 원문과 대조해 확정한 것. 오프라인(네트워크 없이) 실행.
(10-13 Claude 수정: 두 문장 진술은 신호마다 위치를 가지므로 조문 문구는 그 위치 단위 원문에서 확인, 2024-44-5 근거는 ④)
실행: .venv/bin/python -m pytest tests/test_claims_golden.py -q
"""
import json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from korean_tax_mcp import claims       # noqa: E402

FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "claims_golden.json"), encoding="utf-8"))
CASES = {c["id"]: c for c in FX["사례"]}


def _loc(u):
    return " ".join([u[0]] + ([u[1]] if u[1] else []) + ([u[2].rstrip(".") + "호"] if u[2] else []))


def run(cid):
    c = CASES[cid]
    r = claims.compare(c["진술"], [tuple(u) for u in c["단위"]])
    assert set(r) >= {"판정", "근거", "대조", "단서", "겹침"}, r.keys()
    return c, r


@pytest.mark.parametrize("cid", [k for k, c in CASES.items() if c["기대"]["판정"] == "모순"])
def test_contradiction_detected(cid):
    c, r = run(cid)
    exp = c["기대"]
    assert r["판정"] == "모순", (cid, r)
    kinds = {d["종류"] for d in r["대조"]}
    assert set(exp["신호"]) <= kinds, (cid, kinds, r["대조"])
    assert r["근거"]["위치"].startswith(exp["근거위치"]), (cid, r["근거"]["위치"])
    # 근거 원문은 단위 원문 그대로(지어내지 않음)
    assert any(r["근거"]["원문"] == u[3] for u in c["단위"]), cid
    for d in r["대조"]:                                   # 대조 표의 조문 쪽 문구는 그 신호의 위치 단위 원문 안에 있어야 함(지어내지 않음)
        src = next(u for u in c["단위"] if _loc(u) == d["위치"])
        assert d["조문"] in src[3], (cid, d)


@pytest.mark.parametrize("cid", [k for k, c in CASES.items() if c["기대"]["판정"] == "차이 없음"])
def test_true_statement_not_flagged(cid):
    c, r = run(cid)
    assert r["판정"] != "모순", (cid, r["대조"])
    assert r["판정"] == "차이 없음", (cid, r)
    assert r["근거"]["위치"].startswith(c["기대"]["근거위치"]), (cid, r["근거"]["위치"])


def test_low_overlap_needs_judgment():
    c, r = run("synthetic-low-overlap")
    assert r["판정"] == "판단 필요" and r["겹침"] < 0.3, r


def test_two_sentence_statement_reports_each():      # 2024-61-3: 2개월→3개월, 3개월 미만→1개월 미만 두 군데
    c, r = run("2024-61-3")
    nums = [d for d in r["대조"] if d["종류"] == "숫자"]
    assert len(nums) >= 2, nums
    assert any("2개월" in d["진술"] and "3개월" in d["조문"] for d in nums), nums
    assert any("3개월" in d["진술"] and "1개월" in d["조문"] for d in nums), nums


def test_number_signal_values():                      # 2024-48-4: 2회 vs 3회, 2천만원 vs 500만원
    c, r = run("2024-48-4")
    nums = {(d["진술"], d["조문"]) for d in r["대조"] if d["종류"] == "숫자"}
    assert any("2회" in a and "3회" in b for a, b in nums), nums
    assert any("2천만원" in a and "500만원" in b for a, b in nums), nums


def test_modality_signal_labels():                    # 2024-48-2: 진술 '할 수 있다'(재량) vs 조문 '아니한다'(부정)
    c, r = run("2024-48-2")
    m = [d for d in r["대조"] if d["종류"] == "양태"]
    assert m and m[0]["진술"].endswith("있다") and "아니한다" in m[0]["조문"], m


def test_proviso_listed_when_statement_ignores_it():  # 2024-48-4 근거 ②에 '다만' 단서 → 단서 목록에 원문 포함
    c, r = run("2024-48-4")
    assert r["단서"] and all(s in r["근거"]["원문"] for s in r["단서"]), r["단서"]


@pytest.mark.skipif(not os.environ.get("LAW_OC"), reason="법제처 키 없음")
def test_live_tool_wraps_compare():
    from korean_tax_mcp import server
    fn = getattr(server.verify_statement, "fn", server.verify_statement)
    c = CASES["2024-48-4"]
    r = fn(statement=c["진술"], law_name="국세징수법", article="제112조", as_of="2024-01-01")
    assert r["판정"] == "모순" and r["시행본"] == c["시행본"] and r["법령"] == "국세징수법" and r["조"] == "제112조"
