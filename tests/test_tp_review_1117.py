"""tp_comparability_review — 비교가능성 AI 권고(2026-11-17).

정답 세트는 tests/fixtures/tp_review_gold.json(판례가 비교대상 적정성을 판단한 후보 12개). 여기서는 모델 없이
'정답 신호대로 판정했을 때 규칙 권고가 판례 결론과 맞는지'와 근거 대조·입력 검사를 본다. Solar 정확도는 eval/tp_review_eval.py.
"""
import json
import os

import pytest

from korean_tax_mcp import solar
from korean_tax_mcp import tp_review as T

GOLD = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "tp_review_gold.json"), encoding="utf-8"))["문항"]


@pytest.fixture(autouse=True)
def _host_ai(monkeypatch):
    monkeypatch.setattr(solar, "mode", lambda: "host_ai")


def _ideal(item):
    """정답 신호 중 모델 몫(문장 신호)을 원문 첫 문장 인용으로 채운 판정."""
    c = item["candidate"]
    quote = c["description"].split(".")[0]
    rows = [{"후보": c["name"], "신호": k, "판정": v, "이유": "정답 세트", "근거 문장": quote, "확신도": "높음"}
            for k, v in item["정답 신호"].items() if k in T.TEXT_SIGNALS]
    return {"판정": rows}


@pytest.mark.parametrize("item", GOLD, ids=[g["id"] for g in GOLD])
def test_rule_recommendation_matches_case_law(item):
    r = T.review(item["tested"], [item["candidate"]], judgments=_ideal(item))
    assert "error" not in r, r
    rec = r["후보별 권고"][0]
    assert rec["권고"] in item["허용 권고"], (item["id"], rec["권고"], rec["이유"])
    assert rec["권고"] == item["정답 권고"], (item["id"], rec["권고"], rec["이유"])
    got = {s["신호"]: s["판정"] for s in rec["신호"]}
    for k, v in item["정답 신호"].items():
        assert got.get(k) == v, (item["id"], k, got)


def test_numeric_signals_judged_by_tool_without_model():
    g = next(x for x in GOLD if x["id"] == "G01")
    r = T.review(g["tested"], [g["candidate"]], judgments={"판정": []})
    s = {x["신호"]: x for x in r["후보별 권고"][0]["신호"]}
    assert s["R3"]["판정"] == "다름" and s["R3"]["판정 주체"] == "도구(숫자)" and "관행 기본값" in s["R3"]["기준"]
    assert any(c["문서번호"] == "대법원-2024-두-54065" and c.get("링크") for c in s["R3"]["근거"]["판례"])
    assert any("시행규칙 제6조제1항제2호" in x for x in s["R3"]["근거"]["법령"]) and s["R3"]["근거"]["OECD"] and s["R3"]["근거"]["국세청 실무"]


def test_fabricated_quote_downgraded_to_unknown():
    g = next(x for x in GOLD if x["id"] == "G02")
    j = {"판정": [{"후보": g["candidate"]["name"], "신호": "R1", "판정": "다름", "이유": "x",
                 "근거 문장": "건강보조식품만 취급하는 회사이다", "확신도": "높음"}]}
    r = T.review(g["tested"], [g["candidate"]], judgments=j)
    s = {x["신호"]: x for x in r["후보별 권고"][0]["신호"]}
    assert s["R1"]["판정"] == "불명" and s["R1"]["원문 확인"].startswith("원문에 없음") and s["R1"]["확신도"] == "낮음"


def test_quote_from_tested_text_accepted_and_whitespace_ignored():
    g = next(x for x in GOLD if x["id"] == "G02")
    j = {"판정": [{"후보": g["candidate"]["name"], "신호": "R2", "판정": "다름", "이유": "x", "근거 문장": "다단계판매원에게  판매하는", "확신도": "보통"}]}
    s = {x["신호"]: x for x in T.review(g["tested"], [g["candidate"]], judgments=j)["후보별 권고"][0]["신호"]}
    assert s["R2"]["판정"] == "다름" and s["R2"]["원문 확인"] == "원문 일치"


def test_unrequested_signal_or_candidate_ignored():
    g = next(x for x in GOLD if x["id"] == "G01")
    j = {"판정": [{"후보": "없는 회사", "신호": "R1", "판정": "다름"}, {"후보": g["candidate"]["name"], "신호": "R3", "판정": "가까움"}]}
    r = T.review(g["tested"], [g["candidate"]], judgments=j)
    assert len(r["무시한 판정"]) == 2      # R3는 숫자로 도구가 판정했으므로 모델 판정을 받지 않음
    s = {x["신호"]: x for x in r["후보별 권고"][0]["신호"]}
    assert s["R3"]["판정"] == "다름"


def test_host_ai_step1_returns_package():
    g = next(x for x in GOLD if x["id"] == "G05")
    r = T.review(g["tested"], [g["candidate"]])
    assert r["mode"] == "host_ai" and r["단계"].startswith("1/2")
    assert set(r["판정할 신호"][g["candidate"]["name"]]) >= {"R1", "R2", "R3", "R4"}
    assert "글자 그대로" in r["판단 안내"] and "AI 생성" in r["판단 안내"]
    assert r["후보 원문"][0]["description"] == g["candidate"]["description"]


def test_missing_judgment_becomes_unknown_and_needs_review():
    g = next(x for x in GOLD if x["id"] == "G12")
    r = T.review(g["tested"], [g["candidate"]], judgments={"판정": []})
    rec = r["후보별 권고"][0]
    assert rec["권고"] == "사람 확인" and rec["확신도"] == "낮음"


def test_rules_override_and_validation():
    g = next(x for x in GOLD if x["id"] == "G10")
    j = _ideal(g)
    r = T.review(g["tested"], [g["candidate"]], judgments=j, rules={"ratio_high": 10})
    assert r["후보별 권고"][0]["권고"] == "포함" and r["기준값"]["ratio_high"]["값"] == 10
    assert "error" in T.review(g["tested"], [g["candidate"]], rules={"mix_max_diff": 0.1})
    assert "error" in T.review({"role": "유통"}, [g["candidate"]])
    assert "error" in T.review(g["tested"], [])
    assert "error" in T.review(g["tested"], [{"name": "a"}, {"name": "a"}])
    assert "error" in T.review(g["tested"], [{"name": "a", "advert": "많음"}])
    assert "error" in T.review(g["tested"], [{"name": f"c{i}"} for i in range(21)])


def test_group_checks_consistency_and_sample():
    t = {"role": "판매", "products": "화학 기초제품", "channel": "1차 도매"}
    cands = [{"name": "갑", "description": "직영 소매 매장을 운영하는 화학제품 판매업체"}, {"name": "을", "description": "화학 기초제품 1차 도매"}]
    j = {"판정": [{"후보": n, "신호": k, "판정": "가까움", "근거 문장": "화학", "확신도": "높음"} for n in ("갑", "을") for k in ("R1", "R2", "R3", "R4", "R12")]}
    r = T.review(t, cands, judgments=j, decisions=[{"name": "병", "reason": "직영 소매 매장 운영"}])
    checks = {c["검사"]: c["결과"] for c in r["묶음 검사"]}
    assert "갑" in checks["정성 선정 일관성"] and "표본" in checks["표본 수"] and "2023서9158" in checks["연도"]


def test_server_tool_registered():
    from korean_tax_mcp import server as S
    tools = {t.name for t in S.mcp._tool_manager.list_tools()} if hasattr(S.mcp, "_tool_manager") else None
    r = S.tp_comparability_review(GOLD[5]["tested"], [GOLD[5]["candidate"]], judgments=_ideal(GOLD[5]))
    assert r["후보별 권고"][0]["권고"] == "포함"
    if tools is not None:
        assert "tp_comparability_review" in tools


def test_labeled_multi_quote_checked_piece_by_piece():
    g = next(x for x in GOLD if x["id"] == "G05")
    n = g["candidate"]["name"]
    ok = {"후보": n, "신호": "R3", "판정": "다름", "근거 문장": "후보: TV 광고 등 마케팅을 직접 기획·집행한다.", "분석대상 근거": "마케팅 전략은 본사가 정함", "확신도": "높음"}
    note = {"후보": n, "신호": "R4", "판정": "다름", "근거 문장": "분석대상: (자체 브랜드 언급 없음) / 후보: 자체 브랜드를 보유하고", "확신도": "보통"}
    bad = {"후보": n, "신호": "R1", "판정": "다름", "근거 문장": "후보: 소형가전을 수입해 / 분석대상: 대형가전", "확신도": "높음"}
    s = {x["신호"]: x for x in T.review(g["tested"], [g["candidate"]], judgments={"판정": [ok, note, bad]})["후보별 권고"][0]["신호"]}
    assert s["R3"]["원문 확인"] == "원문 일치" and s["R4"]["원문 확인"] == "원문 일치"
    assert s["R1"]["판정"] == "불명"


def test_solar_called_in_small_chunks_and_failed_chunk_isolated(monkeypatch):
    """실제 공시 후보 10개를 한 번에 보내면 Solar 답이 잘려 전체가 실패했음(2026-11-17) — 묶음으로 나누고 실패한 묶음만 불명."""
    monkeypatch.setattr(solar, "mode", lambda: "solar_cloud")
    monkeypatch.setattr(solar, "where", lambda *a: "Solar(테스트)")
    t = {"role": "판매", "products": "화장품", "channel": "도매"}
    cands = [{"name": f"c{i}", "description": f"화장품 도매 {i}"} for i in range(7)]
    calls = []

    def fake(prompt, max_tokens=0, timeout=0):
        names = [c["name"] for c in cands if f"[{c['name']}]" in prompt]
        calls.append(names)
        if "c3" in names:
            raise ValueError("Expecting ',' delimiter")
        return {"판정": [{"후보": n, "신호": "R1", "판정": "가까움", "근거 문장": "화장품 도매", "확신도": "높음"} for n in names]}

    monkeypatch.setattr(solar, "chat_json", fake)
    r = T.review(t, cands)
    assert [len(c) for c in calls] == ([T.SOLAR_CHUNK] * 3 + [1]) * len(T.SIGNAL_GROUPS) and "error" not in r   # 신호 묶음마다, 실패한 후보 묶음은 한 번 다시
    assert sorted(k for g in T.SIGNAL_GROUPS for k in g) == sorted(T.TEXT_SIGNALS)
    assert set(r["판정 실패 후보"]["후보"]) == {"c3", "c4", "c5"}
    by = {x["후보"]: {s["신호"]: s for s in x["신호"]} for x in r["후보별 권고"]}
    assert by["c0"]["R1"]["판정"] == "가까움" and by["c3"]["R1"]["판정"] == "불명" and "Solar 판정 실패" in by["c3"]["R1"]["이유"]


def test_solar_all_chunks_failed_returns_error(monkeypatch):
    monkeypatch.setattr(solar, "mode", lambda: "solar_cloud")
    monkeypatch.setattr(solar, "chat_json", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad json")))
    r = T.review({"role": "판매"}, [{"name": "a", "description": "x"}])
    assert "error" in r and "모두" in r["error"]


def test_stitched_quote_partial_match_keeps_verdict_but_fabrication_still_unknown():
    g = next(x for x in GOLD if x["id"] == "G01")
    n = g["candidate"]["name"]
    stitched = {"후보": n, "신호": "R1", "판정": "다름", "확신도": "높음",
                "근거 문장": "생활용품·가전 등 약 50만 개 품목을 취급하는 종합 도매업체이다. 직영점을 운영하며 소매 판매도 한다.",
                "분석대상 근거": "침구청소기 단일 품목만 판매"}
    fake = {"후보": n, "신호": "R2", "판정": "다름", "확신도": "높음", "근거 문장": "백화점 명품관에서 고가 의류를 판다"}
    s = {x["신호"]: x for x in T.review(g["tested"], [g["candidate"]], judgments={"판정": [stitched, fake]})["후보별 권고"][0]["신호"]}
    assert s["R1"]["판정"] == "다름" and s["R1"]["원문 확인"].startswith("일부 일치") and s["R1"]["확신도"] == "보통"
    assert s["R2"]["판정"] == "불명"


def test_source_layers_cover_all_statutory_factors_and_resolve():
    """신호 근거 층(2026-11-17): 시행규칙 제6조① 분석요소 7개가 모두 신호로 덮이고, OECD 문단·판례 번호는 실제로 조회된다."""
    import re
    from korean_tax_mcp import oecd_tpg
    from korean_tax_mcp import tp_report
    m = T._DATA["분석요소 대응"]
    assert [k for k in m if k[0].isdigit()] == [f"{i}호" + k.split("호", 1)[1] for i, k in zip(range(1, 8), [k for k in m if k[0].isdigit()])]
    assert all(all(x in T.SIGNALS for x in v) for k, v in m.items() if k != "설명")
    cases = set(T._case_index())
    for sid, sig in T.SIGNALS.items():
        layers = sig.get("근거 층", {})
        assert layers.get("법령") or layers.get("OECD"), sid
        assert set(sig["판례"]) <= cases, (sid, set(sig["판례"]) - cases)
        for ref in layers.get("OECD", []):
            para = re.match(r"(\d+\.\d+)", ref).group(1)
            assert oecd_tpg.lookup(para).get("결과"), (sid, para)
        for ref in layers.get("법령", []):
            assert re.search(r"시행(령|규칙) 제\d+조", ref), (sid, ref)


def test_new_signals_requested_from_model_and_noncore():
    g = next(x for x in GOLD if x["id"] == "G06")
    r = T.review(g["tested"], [g["candidate"]])
    assert {"R15", "R16", "R17"} <= set(r["판정할 신호"][g["candidate"]["name"]])
    assert not any(T.SIGNALS[k]["핵심"] for k in ("R15", "R16", "R17"))
    assert "분석요소 대응" in r and "근거 층" in r["신호 설명"]["R16"]


def test_r12_scope_is_within_candidate_and_sent_to_model():
    """R12는 후보 자기 안의 부문 혼재만 — 업종 차이(R1)·제조/유통(R2)을 겹쳐 세지 않게 판정 범위로 알림."""
    scope = T.SIGNALS["R12"]["판정 범위"]
    assert "R1" in scope and "R2" in scope and "10%" in scope and "한 사업만" in scope
    g = next(x for x in GOLD if x["id"] == "G06")
    assert "한 사업만" in T._prompt(g["tested"], [g["candidate"]], {g["candidate"]["name"]: ["R12"]}, group=("R12",))


def test_quote_with_added_subject_keeps_verdict_but_rewritten_sentence_unknown():
    """근거 대조(2026-11-18): 원문 문장 앞에 '당사는'을 붙여 옮긴 인용은 판정을 지키고 확신도만 낮춘다. 새로 쓴 문장은 불명, 모델의 원래 판정을 남긴다.
    화장품 74곳 3번 측정에서 '원문에 없음'으로 낮춘 89건 중 44건이 앞의 경우, 12건이 뒤의 경우였다."""
    cand = {"name": "가", "description": "화장품 제조 및 도소매업을 주요 사업으로 영위하고 있습니다. 주식회사 가(이하 당사)는 2011년 설립되어 화장품 제조 및 판매를 주된 사업으로 영위하고 있는 중소기업으로서"}
    tested = {"role": "판매", "products": "해외 브랜드 화장품 완제품", "channel": "수입해 국내 도매"}
    added = {"후보": "가", "신호": "R2", "판정": "다름", "확신도": "높음", "근거 문장": "당사는 화장품 제조 및 도소매업을 주요 사업으로 영위하고 있습니다."}
    rewritten = {"후보": "가", "신호": "R1", "판정": "가까움", "확신도": "높음", "근거 문장": "당사의 주된 사업은 화장품 제조 및 판매입니다."}
    s = {x["신호"]: x for x in T.review(tested, [cand], judgments={"판정": [added, rewritten]})["후보별 권고"][0]["신호"]}
    assert s["R2"]["판정"] == "다름" and s["R2"]["원문 확인"].startswith("일부 일치") and s["R2"]["확신도"] == "보통" and "AI 원래 판정" not in s["R2"]
    assert s["R1"]["판정"] == "불명" and "새로 쓴 문장" in s["R1"]["원문 확인"] and s["R1"]["AI 원래 판정"] == "가까움"


def test_quote_of_tested_input_fields_accepted():
    """모델이 분석대상 입력 칸을 이름째 근거로 인용('limited_risk: true')해도 입력에 있는 값이면 원문 일치 — 없는 값이면 불명."""
    cand = {"name": "가", "description": "주요사업 내용 : 화장품 판매"}
    tested = {"role": "판매", "limited_risk": True, "products": "해외 브랜드 화장품 완제품", "channel": "수입해 국내 도매", "description": "제조·연구개발 없음, 자체 브랜드 없음"}
    def run(q):
        j = {"판정": [{"후보": "가", "신호": "R15", "판정": "다름", "확신도": "높음", "근거 문장": q}]}
        return next(x for x in T.review(tested, [cand], judgments=j)["후보별 권고"][0]["신호"] if x["신호"] == "R15")
    for q in ("limited_risk: true", "주요사업 내용 : 화장품 판매 / role: 판매, limited_risk: true, 제조·연구개발 없음, 자체 브랜드 없음", "분석대상 description: 제조·연구개발 없음, 자체 브랜드 없음"):
        r = run(q)
        assert r["판정"] == "다름" and r["원문 확인"] == "원문 일치", (q, r)
    r = run("limited_risk: false")
    assert r["판정"] == "불명" and r["AI 원래 판정"] == "다름"


def test_quote_of_question_or_other_candidate_is_unknown_with_reason():
    a = {"name": "가", "description": "주요사업 내용 : 화장품 판매"}
    b = {"name": "나", "description": "당사는 제조, 브랜드, 유통이라는 Total-Value Chain을 보유하고 있습니다."}
    tested = {"role": "판매", "limited_risk": True, "products": "해외 브랜드 화장품 완제품"}
    j = {"판정": [{"후보": "가", "신호": "R15", "판정": "다름", "확신도": "높음", "근거 문장": T.SIGNALS["R15"]["묻는 것"]},
                 {"후보": "가", "신호": "R2", "판정": "다름", "확신도": "높음", "근거 문장": "당사는 제조, 브랜드, 유통이라는 Total-Value Chain을 보유하고 있습니다."}]}
    s = {x["신호"]: x for x in T.review(tested, [a, b], judgments=j)["후보별 권고"][0]["신호"]}
    assert s["R15"]["판정"] == "불명" and "질문 문장" in s["R15"]["원문 확인"]
    assert s["R2"]["판정"] == "불명" and "다른 후보의 문장" in s["R2"]["원문 확인"]


def test_quote_with_ellipsis_checked_piece_by_piece():
    cand = {"name": "가", "description": "가는 화장품 판매사업을 전개하고 있는 화장품 전문기업으로서 1993년 설립되었으며 색조 브랜드 중심으로 다양한 브랜드를 전개하고 있습니다."}
    j = {"판정": [{"후보": "가", "신호": "R1", "판정": "가까움", "확신도": "높음", "근거 문장": "가는 화장품 판매사업을 전개하고 있는 화장품 전문기업으로서... 색조 브랜드 중심으로 다양한 브랜드를 전개하고 있습니다."}]}
    s = {x["신호"]: x for x in T.review({"role": "판매", "products": "화장품"}, [cand], judgments=j)["후보별 권고"][0]["신호"]}
    assert s["R1"]["판정"] == "가까움" and s["R1"]["원문 확인"] == "원문 일치"
