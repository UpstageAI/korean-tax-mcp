"""보기별 판정 묶음(judge_options / claims.judge) 정답 테스트 (Claude 작성 2026-10-14) — 수정 금지.
fixtures/judge_golden.json: 보기는 공개 검증 사례(세무사 1차 2024, 출처 Q-Net), 조문 단위는 claims_golden fixture의 법제처 원문.
기대: 정답 세트에서 '틀림'으로 확정된 보기 가운데 claims 정답 테스트가 이미 잡는 것(2024-41 ①②③ / 2024-48 ②④ / 2024-47 ②)은 '모순',
'옳음' 보기(2024-41 ④는 조문 단위 없음 → 제외, 2024-48 ③, 2024-47 ④)는 '모순' 아님. 조 선택은 겹침 최대.
실행: .venv/bin/python -m pytest tests/test_judge_golden.py -q
"""
import json, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from korean_tax_mcp import claims       # noqa: E402

FX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "judge_golden.json"), encoding="utf-8"))
UNITS = {k: [tuple(u) for u in v] for k, v in FX["조단위"].items()}
Q = {c["문항"]: c for c in FX["문항"]}


def units_for(law, articles):
    return {f"{law} {a}": UNITS[f"{law} {a}"] for a in articles}


def run(qid, articles):
    c = Q[qid]
    stmts = [{"id": o["id"], "text": o["text"]} for o in c["보기"]]
    r = claims.judge(stmts, units_for(c["법령"], articles))
    assert set(r) >= {"보기별", "요약"}, r.keys()
    assert [b["id"] for b in r["보기별"]] == [o["id"] for o in c["보기"]]
    return c, r


def test_2024_41_contradictions_and_article_choice():   # 국세기본법 제21조·제22조의2 — ①(제21조 시점) ②(제22조의2 반대말) 모순, 조 선택이 각각 맞아야
    c, r = run("2024-41", ["제21조", "제22조의2"])
    by = {b["id"]: b for b in r["보기별"]}
    assert by["①"]["판정"] == "모순" and by["①"]["조"].endswith("제21조")
    assert by["②"]["판정"] == "모순" and by["②"]["조"].endswith("제22조의2")
    assert "①" in r["요약"]["모순"] and "②" in r["요약"]["모순"]
    for b in r["보기별"]:                                   # 근거 원문은 어느 조의 단위 원문 그대로
        assert any(b["근거"]["원문"] == u[3] for us in UNITS.values() for u in us), b["id"]


def test_2024_48_true_option_not_flagged():              # 국세징수법 제112조·제115조·제109조 — ②④ 모순, ③(옳음, 제109조②) 모순 아님
    c, r = run("2024-48", ["제112조", "제115조", "제109조"])
    by = {b["id"]: b for b in r["보기별"]}
    assert by["②"]["판정"] == "모순" and by["②"]["조"].endswith("제115조")
    assert by["④"]["판정"] == "모순" and by["④"]["조"].endswith("제112조")
    assert by["③"]["판정"] != "모순" and by["③"]["조"].endswith("제109조")
    assert set(r["요약"]["모순"]) >= {"②", "④"} and "③" not in r["요약"]["모순"]


def test_2024_47_signals_carry_text():                   # 국세징수법 제80조·제84조 — ② 양태 모순(매수할 수 있다 vs 매수하지 못한다), ④ 옳음
    c, r = run("2024-47", ["제80조", "제84조"])
    by = {b["id"]: b for b in r["보기별"]}
    assert by["②"]["판정"] == "모순" and any(d["종류"] == "양태" for d in by["②"]["대조"])
    assert by["④"]["판정"] != "모순" and by["④"]["조"].endswith("제84조")
    for d in by["②"]["대조"]:
        assert d["조문"] in by["②"]["근거"]["원문"]


def test_low_overlap_statement_needs_judgment():         # 준 조문과 무관한 보기는 '판단 필요'로 (다른 조문일 수 있음)
    c = Q["2024-47"]
    r = claims.judge([{"id": "ㄱ", "text": "거주자의 소득세 납세지는 그 주소지로 한다."}], units_for("국세징수법", ["제80조"]))
    assert r["보기별"][0]["판정"] == "판단 필요" and "ㄱ" in r["요약"]["판단 필요"]


def test_empty_inputs_rejected():
    assert "error" in claims.judge([], units_for("국세징수법", ["제80조"]))
    assert "error" in claims.judge([{"id": "①", "text": "x"}], {})


@pytest.mark.skipif(not os.environ.get("LAW_OC"), reason="법제처 키 없음")
def test_live_tool():
    from korean_tax_mcp import server
    fn = getattr(server.judge_options, "fn", server.judge_options)
    c = Q["2024-48"]
    r = fn(statements=[o["text"] for o in c["보기"]], law_name="국세징수법", articles=["제112조", "제115조", "제109조"], as_of="20240101")
    assert r["법령"] == "국세징수법" and r["시행본"] == "20240101"
    assert [b["id"] for b in r["보기별"]] == ["①", "②", "③", "④", "⑤"]      # 문자열만 주면 ①~⑤ 부여
    assert set(r["요약"]["모순"]) >= {"②", "④"}


@pytest.mark.skipif(not os.environ.get("LAW_OC"), reason="법제처 키 없음")
def test_live_tool_accepts_joined_string_and_five_articles():   # Claude 10-14 (26회차 관찰): 보기 5개를 문장 하나로, 조문 5개로 넘겨도 계산
    from korean_tax_mcp import server
    fn = getattr(server.judge_options, "fn", server.judge_options)
    c = Q["2024-48"]
    joined = " ".join(f"{o['id']} {o['text']}" for o in c["보기"])
    r = fn(statements=joined, law_name="국세징수법", articles=["제112조", "제115조", "제109조", "제113조", "제85조의5"], as_of="20240101")
    assert "error" not in r and [b["id"] for b in r["보기별"]] == ["①", "②", "③", "④", "⑤"]
    assert set(r["요약"]["모순"]) >= {"②", "④"}


# ── 2026-10-15 추가 (Claude): 시나리오 녹화 중 발견한 세 가지 — 겹침이 낮아도 드문 내용어를 공유하면 숫자 모순 유지,
#    숫자가 전부 원문과 일치하면 차이 없음, 소수점·표기형(100분의 N vs N퍼센트) 구분. 조문 단위는 법제처 2026-01-01 시행본.
def test_demo_decree_41_low_overlap_number_contradiction():   # ① 경조금 10만원 vs 20만원(영 제41조①1호) — 겹침 0.06이어도 '경조금' 공유 → 모순
    c, r = run("2026-demo-접대비", ["제41조"])
    by = {b["id"]: b for b in r["보기별"]}
    assert by["①"]["판정"] == "모순" and any(d["종류"] == "숫자" and d["조문"] == "20만원" for d in by["①"]["대조"])
    assert by["②"]["판정"] == "차이 없음" and "3만원" in by["②"]["근거"]["원문"]          # 숫자 일치 → 차이 없음, 근거는 그 단위
    assert r["요약"]["모순"] == ["①"] and r["요약"]["차이 없음"] == ["②"]


def test_demo_act_25_decimal_and_fraction_formats():   # ③ 0.5퍼센트 vs 0.3퍼센트(소수점), ④ 100분의 20 vs 100분의 10(같은 표기형끼리), ⑤ 0.3퍼센트 일치
    c, r = run("2026-demo-한도", ["제25조"])
    by = {b["id"]: b for b in r["보기별"]}
    assert by["③"]["판정"] == "모순" and any(d["진술"] == "0.5퍼센트" and d["조문"] == "0.3퍼센트" for d in by["③"]["대조"])
    assert by["④"]["판정"] == "모순" and any(d["진술"] == "100분의 20" and d["조문"] == "100분의 10" for d in by["④"]["대조"])
    assert by["⑤"]["판정"] == "차이 없음"
    assert r["요약"]["모순"] == ["③", "④"] and r["요약"]["차이 없음"] == ["⑤"]
