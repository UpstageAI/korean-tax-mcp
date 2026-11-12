"""정상가격 검토 보고서 뼈대(개별기업보고서 목차)와 기능·위험 분석. Claude 작성(2026-11-12).

근거: 국조칙 별지 제13호서식(2026.3.20. 시행본), 시행령 제14조·제16조·제33조, 시행규칙 제6조(비교가능성·적합성 평가)·제7조(분석절차)·제10조(위험 분석).
정상가격을 산출하거나 거래가격이 정상가격인지 판정하지 않는다 — 회사가 낸 사실관계를 조문이 정한 틀에 맞춰 정리하고, 조문 문언에 맞는 방법·지표를 표시한다."""
import json
import os

from . import oecd_tpg as _tpg

_PATH = os.path.join(os.path.dirname(__file__), "data", "tp_report.json")
with open(_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)

FUNCTIONS = ("설계", "제조", "조립", "연구·개발", "용역", "구매", "유통", "마케팅", "광고", "운송", "재무", "관리")
RISKS = {"시장위험": "제조원가 및 제품가격 변동 등 시장의 불확실성에 따른 위험", "투자위험": "유형자산 투자·사용, 연구·개발 투자의 성공 여부 등에 따른 위험",
         "재무위험": "환율 및 이자율 변동 등에 따른 위험", "신용위험": "매출채권 회수 등과 관련된 위험"}
STEPS = ["분석대상 연도의 선정", "사업 환경 분석(산업, 경쟁, 규제 요소)", "특수관계 거래 분석(국내외 분석대상 당사자, 적합한 산출방법, 핵심 비교가능성 분석요소 식별)",
         "내부의 비교가능한 거래 자료 수집과 검토", "외부의 비교가능한 거래 자료 수집과 검토(상업용 데이터베이스 등)",
         "가장 합리적인 산출방법 선택과 재무 지표(거래순이익률 지표 포함) 선정", "비교가능한 거래의 선정", "합리적인 차이 조정(회계기준, 재무정보, 기능, 자산, 위험)",
         "수집된 자료의 해석 및 정상가격의 결정"]
QUESTIONS = {
    "재화·용역의 특성(시행규칙 제6조①1호)": ["재화: 물리적 특성, 품질·신뢰도, 공급 물량·시기는 어떤가", "무형자산: 사용허락인가 판매인가, 형태(특허·상표·노하우), 보호기간·정도, 기대편익은", "용역: 제공하는 용역의 특성과 범위는"],
    "사업활동의 기능(2호)": ["각 당사자가 수행하는 핵심 기능은 무엇인가 — " + "·".join(FUNCTIONS), "가격·물량·제품 구성·마케팅 예산을 누가 결정하는가"],
    "거래에 수반되는 위험(3호, 제10조)": ["경제적으로 중요한 위험은 무엇인가 — " + "·".join(RISKS), "계약상 그 위험을 누가 부담하는가",
                                "그 위험으로 생긴 이익·손실이 실제로 누구에게 귀속됐는가", "위험이 따르는 활동을 시작할지, 상황 변화에 어떻게 대응할지 누가 결정하는가(관리·통제)",
                                "누가 그 위험을 부담할 자금·비용·손실 감당 능력이 있는가(재정적 능력)"],
    "사용되는 자산(4호)": ["각 당사자가 쓰는 유형자산·무형자산은 무엇인가", "고유한 무형자산(상표권, 고유한 마케팅 조직, 기술)을 누가 갖고 있는가"],
    "계약 조건(5호)": ["책임·위험·기대편익이 계약서에 어떻게 배분돼 있는가", "계약서와 실제 행위가 다른 부분이 있는가(사실상의 계약관계)"],
    "경제 여건(6호)": ["시장의 지리적 위치·규모, 도매·소매 등 거래단계, 경쟁 정도는", "경기·제품 주기의 영향은"],
    "사업전략(7호)": ["시장 침투, 신제품 개발, 사업 다각화, 위험 회피 전략이 가격·이익에 영향을 줬는가", "그 영향이 여러 사업연도에 걸치는가(시행규칙 제9조 다년도 자료)"],
}


def outline(section="", keyword=""):
    items = _DATA["항목"]
    s = "".join(str(section or "").split())
    if s:
        ar = lambda v: v.replace("Ⅰ", "1").replace("Ⅱ", "2").replace("Ⅲ", "3").replace("III", "3").replace("II", "2").replace("I", "1")
        s = ar(s)
        items = [x for x in items if ar(x["번호"]) == s or ar(x["번호"]).startswith(s + "-")]
        if not items:
            return {"error": f"section={section!r} — 'Ⅰ'·'Ⅱ'·'Ⅲ' 또는 'Ⅱ-7'(숫자 '2-7'도 됨)"}
    k = "".join(str(keyword or "").split())
    if k:
        items = [x for x in items if k in "".join((x["제목"] + x["작성방법"] + " ".join(x["준비할 사실·자료"])).split())]
    out = {"항목": items, "전체건수": len(items), "분석절차": {"순서": STEPS, "근거": "시행규칙 제7조①(더 합리적인 분석절차가 있으면 그 절차를 쓸 수 있음 — ②)", "OECD 지침 문단": "3.4"},
           "제출 의무": _DATA["제출 의무"], "확인 시행본": _DATA["확인 시행본"],
           "한계": ["목차와 작성방법은 서식 원문을 옮긴 것 — 내용을 채우는 사실과 수치는 회사 자료로", "이 도구는 정상가격을 산출하지 않고 거래가격이 정상가격인지 판정하지 않는다",
                  "관련 결정례는 검색으로 확인한 제목·요지 — 본문은 get_tax_ruling·get_tribunal_decision으로 확인"],
           "다음 단계": ["기능·위험 분석은 transfer_pricing_far", "지침 문단 전문은 oecd_tp_guidelines(paragraph=...)", "산출방법·거래 유형 특칙은 transfer_pricing_guide"]}
    return out


def _risk_allocation(r, parties):
    """시행규칙 제10조 2호~4호: 계약상 부담자 → 손익이 실제 귀속된 자와 다르면 실제 귀속자 → 그 자가 관리·통제 기능이나 재정적 능력이 없으면 둘을 갖춘 자."""
    name = r.get("위험")
    contract, actual = r.get("계약상"), r.get("손익귀속")
    control = r.get("관리통제") or []
    capacity = r.get("재정능력") or []
    control = [control] if isinstance(control, str) else list(control)
    capacity = [capacity] if isinstance(capacity, str) else list(capacity)
    trail = []
    if not contract and not actual:
        return {"위험": name, "부담자": None, "결론": "확인 필요 — 계약상 부담자와 손익 귀속자가 모두 비어 있음", "근거": "시행규칙 제10조2호·3호"}
    bearer = contract
    trail.append(f"계약상 부담자: {contract or '정해지지 않음'}(2호)")
    if actual and actual != contract:
        bearer = actual
        trail.append(f"이익·손실이 실제로 {actual}에 귀속 — 계약과 다르면 실제 귀속자가 부담하는 것으로 봄(4호 가목)")
    elif actual:
        trail.append(f"이익·손실도 {actual}에 귀속(3호 가목)")
    else:
        trail.append("손익 귀속자를 입력하지 않음 — 계약상 부담자로 진행(3호 가목 확인 필요)")
    has_control, has_capacity = bearer in control, bearer in capacity
    if not control and not capacity:
        return {"위험": name, "부담자": bearer, "결론": f"{bearer} 부담 — 다만 관리·통제 기능과 재정적 능력을 입력하지 않아 최종 결정(4호 나목)은 확인 필요", "경로": trail, "근거": "시행규칙 제10조"}
    if has_control and has_capacity:
        trail.append(f"{bearer}: 위험을 관리·통제하고 부담할 재정적 능력이 있음(3호 나목·다목)")
        diff = bool(contract and bearer != contract)
        return {"위험": name, "부담자": bearer, "결론": f"{bearer} 부담" + ("(계약상 부담자와 다름 — 실제 손익 귀속 기준)" if diff else ""),
                **({"재배분": True} if diff else {}), "경로": trail, "근거": "시행규칙 제10조4호"}
    both = [p for p in parties if p in control and p in capacity]
    lack = "·".join(x for x, ok in (("관리·통제 기능", has_control), ("재정적 능력", has_capacity)) if not ok)
    if len(both) == 1:
        trail.append(f"{bearer}: {lack} 없음 → 실제로 관리·통제 기능을 하고 재정적 능력을 가진 쪽({both[0]})이 부담하는 것으로 봄(4호 나목)")
        return {"위험": name, "부담자": both[0], "결론": f"{both[0]} 부담(계약·손익 귀속과 달리 재배분)", "재배분": True, "경로": trail, "근거": "시행규칙 제10조4호 나목"}
    trail.append(f"{bearer}: {lack} 없음. 관리·통제 기능과 재정적 능력을 모두 갖춘 당사자가 " + ("없음" if not both else "둘 이상") + " — 사실관계 보완 필요")
    return {"위험": name, "부담자": None, "결론": "확인 필요", "경로": trail, "근거": "시행규칙 제10조4호 나목"}


def far(parties=None, risks=None, facts=None, tested_party=""):
    """parties: {이름: {기능: [...], 자산: [...], 고유무형자산: bool}} / risks: [{위험, 계약상, 손익귀속, 관리통제, 재정능력}] /
    facts: {internal_comparable, tested_resells_to_third_parties, tested_processing_or_manufacturing, tested_bears_inventory, intermediate_goods_or_services,
            asset_intensive, both_unique_intangibles}"""
    if not parties:
        return {"질문지": QUESTIONS, "위험 분석 순서": ["경제적으로 중요한 위험의 식별", "계약 조건에 따라 부담하는 위험의 결정", "위험에 관한 기능 분석(손익의 실제 귀속, 관리·통제 기능, 재정적 능력)",
                                              "결과를 종합해 위험 재배분(계약과 실제가 다르면 실제, 관리·통제나 재정적 능력이 없으면 그것을 갖춘 당사자)"],
                "입력 형식": {"parties": "{이름: {기능: [..], 자산: [..], 고유무형자산: true|false}} — 기능은 " + "·".join(FUNCTIONS) + " 중에서(다른 말도 됨)",
                          "risks": "[{위험, 계약상, 손익귀속, 관리통제: [이름], 재정능력: [이름]}] — 위험은 " + "·".join(RISKS) + " 또는 구체적인 이름",
                          "facts": "{internal_comparable, tested_resells_to_third_parties, tested_processing_or_manufacturing, tested_bears_inventory, intermediate_goods_or_services, asset_intensive, both_unique_intangibles} — 값은 true/false",
                          "tested_party": "분석대상 당사자로 보려는 쪽의 이름(선택)"},
                "근거": "시행규칙 제6조①·제10조, 시행령 제16조①", "OECD 지침 문단": "1.33-1.39, 1.51-1.55, 1.56-1.106(1.60 여섯 단계)",
                "보고서 항목": "개별기업보고서 Ⅱ-7(비교가능성 및 기능 분석)"}
    if not isinstance(parties, dict) or len(parties) < 2:
        return {"error": "parties — 거래 당사자 둘 이상 {이름: {기능: [..], 자산: [..], 고유무형자산: bool}}"}
    names = list(parties)
    facts = facts or {}
    allowed = ("internal_comparable", "tested_resells_to_third_parties", "tested_processing_or_manufacturing", "tested_bears_inventory",
               "intermediate_goods_or_services", "asset_intensive", "both_unique_intangibles")
    bad = [k for k in facts if k not in allowed]
    if bad:
        return {"error": f"facts의 키 {bad} — 허용 키: {list(allowed)}"}
    문제 = []
    for i, r in enumerate(risks or []):
        for key in ("계약상", "손익귀속"):
            if r.get(key) and r[key] not in names:
                문제.append(f"risks[{i}].{key}={r[key]!r} — parties의 이름({names}) 중 하나")
        for key in ("관리통제", "재정능력"):
            v = r.get(key) or []
            for x in ([v] if isinstance(v, str) else v):
                if x not in names:
                    문제.append(f"risks[{i}].{key}의 {x!r} — parties의 이름({names}) 중 하나")
    if tested_party and tested_party not in names:
        문제.append(f"tested_party={tested_party!r} — parties의 이름({names}) 중 하나")
    if 문제:
        return {"error": "입력 확인 필요", "문제": 문제}

    alloc = [_risk_allocation(r, names) for r in (risks or [])]
    table = {}
    for n in names:
        p = parties[n] or {}
        table[n] = {"기능": list(p.get("기능") or []), "자산": list(p.get("자산") or []), "고유무형자산": bool(p.get("고유무형자산")),
                    "부담 위험": [a["위험"] for a in alloc if a["부담자"] == n]}
    # 분석대상 당사자: 국조법령은 선정 기준을 따로 두지 않고(서식 Ⅱ-9가 선정 이유를 요구) 지침 3.18이 덜 복잡한 기능 분석을 가진 쪽을 든다
    def weight(n):
        t = table[n]
        return (1 if t["고유무형자산"] else 0, len(t["부담 위험"]), len(t["기능"]))
    ranked = sorted(names, key=weight)
    cand = ranked[0] if weight(ranked[0]) != weight(ranked[1]) else None
    tested = {"후보": cand, "이유": (f"고유한 무형자산·부담 위험·수행 기능이 가장 적은 쪽: {cand} — 지침 3.18은 방법을 가장 신뢰성 있게 적용할 수 있고 신뢰할 만한 비교대상을 찾을 수 있는 쪽, "
                                 "대개 기능 분석이 덜 복잡한 쪽을 분석대상으로 든다" if cand else "양쪽의 무형자산·위험·기능 수가 같아 후보를 고르지 못함 — 사실관계를 더 나눠 입력"),
              "근거": "시행규칙 제7조①3호(국내외 분석대상 당사자 분석), 개별기업보고서 Ⅱ-9(선정 이유 기재) — 선정 기준 자체는 국조법령에 없음", "OECD 지침 문단": "3.18-3.19",
              "관련 결정례": ["서울행정법원-2021-구합-69158(2023.11.10.) — 분석대상 당사자를 해외 생산법인으로 선정한 것이 위법하지 않다고 본 사례"]}
    if tested_party:
        tested["입력한 분석대상"] = tested_party
        if cand and cand != tested_party:
            tested["주의"] = f"입력한 분석대상({tested_party})이 후보({cand})와 다름 — 선정 이유를 보고서 Ⅱ-9에 따로 밝혀야 함"
    tp = tested_party or cand

    def yn(key):
        return facts.get(key)
    fit = []
    def add(method, basis, cond, ok_text, no_text, extra=None):
        row = {"방법": method, "근거": basis}
        if cond is None:
            row["적합성"] = "확인 필요"; row["이유"] = "관련 사실을 입력하지 않음"
        else:
            row["적합성"] = "문언상 맞음" if cond else "문언상 맞지 않음"; row["이유"] = ok_text if cond else no_text
        if extra: row["주의"] = extra
        fit.append(row)
    add("비교가능 제3자 가격방법", "시행규칙 제6조②1호", yn("internal_comparable"), "특수관계 없는 자와의 같은·유사 거래 가격이 있음 — 거래 시기·시장·조건·무형자산 사용 차이를 합리적으로 조정할 수 있어야 함",
        "비교할 독립 거래 가격이 없음")
    rs, pm = yn("tested_resells_to_third_parties"), yn("tested_processing_or_manufacturing")
    add("재판매가격방법", "시행규칙 제6조②2호", None if rs is None or pm is None else (rs and not pm),
        "분석대상 당사자가 중요한 가공·제조기능 없이 판매 — 재화의 특성보다 기능상 동질성을 우선 고려", "분석대상 당사자가 제3자에게 재판매하지 않거나 중요한 가공·제조기능을 수행",
        "분석대상 당사자가 고유한 무형자산(상표권, 고유한 마케팅 조직)을 쓰면 그 차이를 합리적으로 조정할 수 있어야 함" if tp and table[tp]["고유무형자산"] else None)
    add("원가가산방법", "시행규칙 제6조②3호", yn("intermediate_goods_or_services"), "특수관계인 간에 반제품 등 중간재가 거래되거나 용역이 제공됨 — 총이익이 원가와 관련성이 높고 같은 회계기준으로 측정될 수 있어야 함",
        "중간재 거래나 용역 제공이 아님")
    fit.append({"방법": "거래순이익률방법", "근거": "시행규칙 제6조②4호·③", "적합성": "지표로 판단",
                "이유": "거래순이익률 지표와 영업활동의 상관관계가 높은지로 평가 — 아래 '거래순이익률 지표' 참조",
                "주의": "다른 방법보다 더 엄격하게 특수관계 거래와 비교가능 거래의 유사성이 확보되거나 차이가 합리적으로 조정될 수 있어야 함"})
    add("이익분할방법", "시행규칙 제6조②5호", yn("both_unique_intangibles"), "양쪽이 특수한 무형자산 형성에 관여하는 등 고도로 통합된 기능을 수행", "양쪽이 함께 특수한 무형자산을 형성하는 구조가 아님")
    # 거래순이익률 지표(시행규칙 제6조③)
    ind = []
    if rs:
        ind.append({"지표": "매출액에 대한 거래순이익의 비율", "이유": "특수관계인에게서 구매한 제품을 독립된 제3자에게 재판매 — 판매장려금·매출할인·외환손익은 분석대상과 비교대상에 같은 회계기준 적용", "근거": "시행규칙 제6조③1호"})
    if rs and yn("tested_bears_inventory") is False:
        ind.append({"지표": "영업비용에 대한 매출 총이익의 비율", "이유": "분석대상 당사자가 재고 부담 없이 단순 판매활동(단순 중개 등)", "근거": "시행규칙 제6조③4호", "OECD 지침 문단": "2.106-2.108"})
    if yn("intermediate_goods_or_services"):
        ind.append({"지표": "매출원가 및 영업비용에 대한 거래순이익의 비율", "이유": "거래순이익과 매출원가·영업비용의 관련성이 높은 경우(제조·용역)", "근거": "시행규칙 제6조③3호"})
    if yn("asset_intensive"):
        ind.append({"지표": "자산에 대한 거래순이익의 비율", "이유": "유형자산 집약적 제조활동 등 거래순이익과 자산의 관련성이 큰 경우", "근거": "시행규칙 제6조③2호"})
    realloc = [a for a in alloc if a.get("재배분")]
    쟁점 = []
    for a in realloc:
        쟁점.append(f"{a['위험']}: 계약상 부담자와 다른 쪽({a['부담자']})이 부담하는 것으로 정리됨 — 계약서와 실제 의사결정·자금 부담·손익 귀속을 맞추거나 차이를 설명할 자료 필요")
    for a in alloc:
        if a["부담자"] is None:
            쟁점.append(f"{a['위험']}: 부담자를 정하지 못함 — {a['결론']}")
    if tp and rs and yn("tested_bears_inventory") is False and any("재고" in str(x) for x in table[tp]["부담 위험"]):
        쟁점.append(f"{tp}: 재고 부담 없는 단순 판매로 입력했는데 위험 분석에서는 재고 관련 위험을 부담 — 둘 중 하나를 바로잡아야 영업비용 대비 매출 총이익 지표(시행규칙 제6조③4호)를 쓸 수 있음")
    return {"당사자별 기능·자산·위험": table, "위험 분석": alloc, "분석대상 당사자": tested, "산출방법 적합성": fit,
            **({"거래순이익률 지표": ind} if ind else {}), **({"쟁점": 쟁점} if 쟁점 else {}),
            "보고서 항목": {"Ⅱ-7": "당사자별 기능·자산·위험, 위험 분석", "Ⅱ-8": "산출방법 적합성, 거래순이익률 지표", "Ⅱ-9": "분석대상 당사자"},
            "근거": "시행규칙 제6조①②③·제10조, 시행령 제14조②③·제16조①", "OECD 지침": {"문단": _tpg.pointers(["기능 분석", "위험 분석", "비교가능성 분석요소"]), "지위": _tpg.STATUS},
            "한계": ["입력한 사실을 조문의 틀로 정리한 것 — 사실 자체가 맞는지, 비교대상과 얼마나 비슷한지는 판단하지 않는다",
                   "'문언상 맞음'은 시행규칙 제6조②의 적합성 평가 문언에 맞는다는 뜻 — 가장 합리적인 방법인지는 시행령 제14조① 다섯 기준(비교가능성, 자료 확보, 가정, 결함의 영향, 적합성)으로 판단",
                   "정상가격을 산출하지 않고 거래가격이 정상가격인지 판정하지 않는다"]}
