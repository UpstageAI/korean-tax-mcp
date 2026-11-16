"""이전가격 비교대상 후보 기능 유사성 검토 — AI가 신호별 판정·이유·근거 문장을 채우고, 도구가 근거를 대조해 권고를 낸다. 사람은 승인·수정만.

Claude 작성(2026-11-17). 판정 신호와 판례는 data/tp_review_signals.json(판례 본문 판단 부분과 대조).
- 숫자 신호(광고·연구개발·특수관계·규모·수출·재고)는 숫자가 양쪽에 있으면 도구가 기준값으로 판정한다(관행 기본값, rules로 바꿈).
- 문장 신호(품목·거래단계·사업부문, 숫자가 없을 때의 광고·연구개발)는 모델이 판정한다 — Solar 설정이 있으면 Solar, 없으면 사용자 AI(host_ai).
- 모델이 낸 근거 문장은 입력 원문에 그대로 있는지 대조하고, 없으면 판정을 '불명'으로 낮춘다(지어낸 근거 차단).
- 권고(포함·사람 확인·제외 후보)는 신호 판정에서 규칙으로 정한다 — 핵심 신호(품목·거래단계·마케팅·연구개발) 둘 이상이 다르면 제외 후보, 하나라도 다르면 사람 확인.
"""
import json
import os
import re

from . import solar
from . import tp_report as _tp

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "tp_review_signals.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)
SIGNALS = {s["id"]: s for s in _DATA["신호"]}
DEFAULT_RULES = {k: v["값"] for k, v in _DATA["숫자 기준"].items() if isinstance(v, dict)}
TEXT_SIGNALS = ("R1", "R2", "R3", "R4", "R8", "R12")       # 모델이 문장으로 판정할 수 있는 신호
CORE = tuple(k for k, s in SIGNALS.items() if s["핵심"])
VERDICTS = ("가까움", "다름", "불명")
CONF = ("높음", "보통", "낮음")
MAX_CANDIDATES = 20
_TESTED_KEYS = ("role", "limited_risk", "products", "channel", "description", "advert", "rnd", "related", "sales", "export", "inv")
_CAND_KEYS = ("name", "description", "sales_lines", "advert", "rnd", "related_sales", "related_purchase", "sales", "export", "inv", "calc")
_RATIO_KEYS = ("advert", "rnd", "related", "related_sales", "related_purchase", "sales", "export", "inv")


def _case_index():
    return {c["문서번호"]: c for v in _tp.cases()["쟁점"].values() for c in v["사례"]}


def _cases_for(sig, idx):
    out = []
    for no in SIGNALS[sig]["판례"]:
        c = idx.get(no)
        out.append({"문서번호": no, "결과": c["결과"], "링크": c.get("링크", "")} if c else {"문서번호": no})
    return out


def _norm(s):
    return re.sub(r"[\s\"'“”‘’·.,()\[\]]", "", str(s or ""))


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _validate(tested, candidates, rules):
    if not isinstance(tested, dict):
        return "tested는 객체여야 합니다(분석대상 — role, products, channel, description 등)"
    bad = [k for k in tested if k not in _TESTED_KEYS]
    if bad:
        return f"tested의 키 {bad} — 허용 키: {list(_TESTED_KEYS)}"
    if tested.get("role") not in (None, "판매", "제조", "용역"):
        return f"tested.role={tested.get('role')!r} — 허용값: 판매·제조·용역"
    if not isinstance(candidates, list) or not candidates:
        return "candidates에 후보를 1개 이상 넣으세요 — [{name, description, ...}]"
    if len(candidates) > MAX_CANDIDATES:
        return f"후보는 한 번에 {MAX_CANDIDATES}개까지 — 나눠서 부르세요"
    names = set()
    for i, c in enumerate(candidates):
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            return f"candidates[{i}]에 name이 필요합니다"
        bad = [k for k in c if k not in _CAND_KEYS]
        if bad:
            return f"candidates[{i}]의 키 {bad} — 허용 키: {list(_CAND_KEYS)}"
        if c["name"] in names:
            return f"후보 이름 {c['name']!r}이 겹칩니다 — 이름으로 판정을 맞추므로 서로 다르게"
        names.add(c["name"])
        for k in _RATIO_KEYS:
            if k in c and c[k] is not None and _num(c[k]) is None:
                return f"candidates[{i}].{k}는 숫자(비율은 0~1)여야 합니다"
    for k in _RATIO_KEYS:
        if k in tested and tested[k] is not None and _num(tested[k]) is None:
            return f"tested.{k}는 숫자(비율은 0~1)여야 합니다"
    bad = [k for k in (rules or {}) if k not in DEFAULT_RULES]
    if bad:
        return f"rules의 키 {bad} — 허용 키: {list(DEFAULT_RULES)}"
    return None


def _numeric(tested, cand, R):
    """양쪽 숫자가 있을 때만 도구가 판정. 반환 {신호: {판정, 이유, 기준}}"""
    out = {}

    def put(sig, verdict, why, key):
        out[sig] = {"판정": verdict, "이유": why, "기준": f"{key}={R[key]}(관행 기본값 — 법령 숫자 아님)", "판정 주체": "도구(숫자)"}

    for sig, key, tol in (("R3", "advert", "advert_abs_tol"), ("R4", "rnd", "rnd_abs_tol"), ("R8", "export", "export_abs_tol")):
        t, c = _num(tested.get(key)), _num(cand.get(key))
        if t is not None and c is not None:
            d = abs(c - t)
            put(sig, "다름" if d > R[tol] else "가까움", f"분석대상 {t:.1%} vs 후보 {c:.1%}(차이 {d:.1%}p)", tol)
    rs, rp = _num(cand.get("related_sales")), _num(cand.get("related_purchase"))
    if rs is not None or rp is not None:
        hi = max(x for x in (rs, rp) if x is not None)
        parts = ", ".join(f"{n} {v:.1%}" for n, v in (("특수관계 매출", rs), ("특수관계 매입", rp)) if v is not None)
        put("R5", "다름" if hi >= R["related_review"] else "가까움", parts + " — 거래 비중만으로 법정 특수관계는 아님", "related_review")
    t, c = _num(tested.get("sales")), _num(cand.get("sales"))
    if t and c and t > 0 and c > 0:
        m = c / t
        put("R7", "다름" if m > R["size_ratio"] or m < 1 / R["size_ratio"] else "가까움", f"후보 매출이 분석대상의 {m:.2f}배", "size_ratio")
    t, c = _num(tested.get("inv")), _num(cand.get("inv"))
    if t is not None and c is not None and t > 0:
        m = c / t
        put("R14", "다름" if m < R["ratio_low"] or m > R["ratio_high"] else "가까움", f"재고/매출 분석대상 {t:.1%} vs 후보 {c:.1%}({m:.2f}배)", "ratio_low")
    return out


def _signals_for(role):
    return [k for k, s in SIGNALS.items() if role is None or role in s["역할"]]


def _model_targets(tested, cand, numeric, role):
    return [k for k in TEXT_SIGNALS if k in _signals_for(role) and k not in numeric]


def _schema():
    return {"판정": [{"후보": "후보 name 그대로", "신호": "R1 등", "판정": "가까움|다름|불명", "이유": "1~2문장",
                    "근거 문장": "후보 description·sales_lines에서 글자 그대로 옮긴 한 문장 — 없으면 빈 값",
                    "분석대상 근거": "분석대상 products·channel·description에서 글자 그대로 옮긴 말(선택)", "확신도": "높음|보통|낮음"}]}


def _instruction():
    return ("후보마다 '판정할 신호'만 판정한다. 근거 문장은 입력 원문(후보 description·sales_lines, 분석대상 products·channel·description)에서 "
            "글자 그대로 옮긴다(요약·번역 금지) — 후보 원문은 '근거 문장', 분석대상 원문은 '분석대상 근거'에 나눠 적는다. 원문에 근거가 없으면 판정을 '불명'으로 하고 근거 문장은 비운다. 업종 코드가 같다는 것만으로 '가까움'이라 하지 않는다. "
            "확신이 없으면 '불명' 또는 확신도 '낮음'. 판정 결과를 judgments로 넣어 이 도구를 다시 부르면 근거 대조와 권고가 붙는다. "
            "결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요.")


def _prompt(tested, cands, targets):
    sig_lines = "\n".join(f"- {k} {SIGNALS[k]['이름']}: {SIGNALS[k]['묻는 것']}" for k in TEXT_SIGNALS)
    cand_lines = "\n".join(
        f"[{c['name']}] 판정할 신호: {','.join(targets[c['name']]) or '없음'}\n  description: {str(c.get('description', ''))[:1500]}\n  sales_lines: {c.get('sales_lines', [])}"
        for c in cands)
    tested_txt = json.dumps({k: tested.get(k) for k in ("role", "limited_risk", "products", "channel", "description") if tested.get(k) is not None}, ensure_ascii=False)
    return f"""이전가격 비교대상 후보의 기능 유사성을 신호별로 판정한다. {_DATA['종합 법리']}
[신호]
{sig_lines}
[분석대상] {tested_txt[:1500]}
[후보]
{cand_lines}
규칙: {_instruction()}
JSON: {json.dumps(_schema(), ensure_ascii=False)}"""


def _pieces(quote):
    """근거 문장을 대조 단위로 — ' / '로 이은 여러 인용, '분석대상:'·'후보:' 같은 머리말, 괄호 속 메모('(언급 없음)')는 떼어 냄."""
    out = []
    for part in re.split(r"\s/\s|\||\n", str(quote or "")):
        part = re.sub(r"^\s*(?:\[[^\]]*\]|분석대상|후보(?:\s*[^:：]{0,20})?)\s*[:：]\s*", "", part.strip())
        if not part or re.fullmatch(r"[(（].*[)）]", part):
            continue
        n = _norm(part)
        if n:
            out.append(n)
    return out


def _verify(j, tested, cand_by, targets):
    """모델 판정 검증 — 후보·신호가 요청한 것인지, 근거 문장이 원문에 그대로 있는지. 반환 {후보: {신호: row}}, 무시한 항목 목록"""
    out, dropped = {}, []
    tested_src = _norm(" ".join(str(tested.get(k, "")) for k in ("products", "channel", "description")))
    for r in (j or {}).get("판정", []) if isinstance(j, dict) else []:
        if not isinstance(r, dict):
            continue
        name, sig = r.get("후보"), r.get("신호")
        if name not in cand_by or sig not in targets.get(name, ()):
            dropped.append(f"{name}·{sig}: 요청하지 않은 후보·신호")
            continue
        v = r.get("판정") if r.get("판정") in VERDICTS else "불명"
        conf = r.get("확신도") if r.get("확신도") in CONF else "낮음"
        quote = " / ".join(str(r.get(k) or "").strip() for k in ("근거 문장", "분석대상 근거") if str(r.get(k) or "").strip())
        c = cand_by[name]
        src = _norm(f"{c.get('description', '')} {' '.join(map(str, c.get('sales_lines') or []))}")
        pieces = _pieces(quote)
        if pieces and all(p in src or p in tested_src for p in pieces):
            check = "원문 일치"
        elif quote:
            check = "원문에 없음 — 판정을 불명으로 낮춤"
            v, conf = "불명", "낮음"
        else:
            check = "근거 문장 없음"
            if v != "불명":
                conf = "낮음"
        out.setdefault(name, {})[sig] = {"판정": v, "이유": str(r.get("이유", ""))[:400], "근거 문장": quote[:400], "원문 확인": check,
                                         "확신도": conf, "판정 주체": "AI(문장)"}
    return out, dropped


def _recommend(rows):
    diff = [k for k, r in rows.items() if r["판정"] == "다름"]
    unk = [k for k, r in rows.items() if r["판정"] == "불명" and k in CORE]
    core_diff = [k for k in diff if k in CORE]
    if len(core_diff) >= 2:
        return "제외 후보", f"핵심 신호 {', '.join(core_diff)}가 함께 다름 — 판례상 품목·거래단계·기능이 함께 다르고 조정이 없으면 비교가능성이 부정됨(대법원 2012두23341, 수원고법 2023누16871)"
    if diff:
        adj = [k for k in diff if SIGNALS[k]["조정 가능"]]
        why = f"{', '.join(diff)} 다름 — 차이 하나만으로 제외된 사례는 없음. 조정 가능 여부와 영업이익률 영향을 사람이 확인"
        if adj:
            why += f"({', '.join(adj)}는 판례상 조정할 수 있는 차이에 가까움)"
        return "사람 확인", why
    core_here = [k for k in CORE if k in rows]
    if core_here and len(unk) >= min(3, len(core_here)):
        return "사람 확인", f"핵심 신호 {len(core_here)}개 중 불명 {len(unk)}개({', '.join(unk)}) — 자료를 더 확보해 판정"
    return "포함", "다른 신호가 없음(핵심 신호 불명 2개 이하) — 거래단계·시장·계약 조건은 사람이 최종 확인"


def _confidence(rows):
    if not rows:
        return "낮음"
    confs = [r.get("확신도", "높음") for r in rows.values()]
    if "낮음" in confs or sum(r["판정"] == "불명" for r in rows.values()) >= 2:
        return "낮음"
    return "보통" if "보통" in confs else "높음"


def _group_checks(tested, cands, results, decisions):
    out = []
    inc = [r for r in results if r["권고"] == "포함"]
    if len(inc) < 5:
        out.append({"검사": "표본 수", "결과": f"포함 권고 {len(inc)}개 — 표본이 적으면 편차 원인을 분석(조심 2017서2666)"})
    if decisions:
        reasons = {d.get("name"): str(d.get("reason", "")) for d in decisions if isinstance(d, dict)}
        kept = [r["후보"] for r in results if r["후보"] not in reasons]
        for n, why in reasons.items():
            words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", why) if len(w) >= 2][:6]
            hits = [k for k in kept if any(w in str(next((c.get("description", "") for c in cands if c["name"] == k), "")) for w in words)]
            if hits:
                out.append({"검사": "정성 선정 일관성", "결과": f"'{n}'을 뺀 사유({why[:60]})의 낱말이 남긴 후보 {hits}의 설명에도 있음 — 같은 잣대인지 확인(수원고법 2023누16871)"})
    out.append({"검사": "연도", "결과": "후보는 사업연도별로 판정 — 다른 연도에 선정되지 않았다는 이유로 빼지 않음(조심 2023서9158)"})
    return out


def review(tested, candidates, judgments=None, rules=None, decisions=None):
    err = _validate(tested, candidates, rules)
    if err:
        return {"error": err}
    R = {**DEFAULT_RULES, **(rules or {})}
    role = tested.get("role")
    idx = _case_index()
    cand_by = {c["name"]: c for c in candidates}
    numeric = {c["name"]: _numeric(tested, c, R) for c in candidates}
    targets = {c["name"]: _model_targets(tested, c, numeric[c["name"]], role) for c in candidates}
    base = {"입력": {"역할": role or "판매·제조(지정 안 함)", "후보 수": len(candidates)},
            "신호 설명": {k: {"이름": SIGNALS[k]["이름"], "묻는 것": SIGNALS[k]["묻는 것"]} for k in _signals_for(role)},
            "기준값": {k: {"값": R[k], "성격": _DATA["숫자 기준"][k]["성격"], "뜻": _DATA["숫자 기준"][k]["뜻"]} for k in DEFAULT_RULES}}

    mode = solar.mode()
    if judgments is None and mode == "host_ai" and any(targets.values()):
        return {**base, "mode": "host_ai", "단계": "1/2 — 사용자 AI가 문장 신호를 판정해 judgments로 다시 부르기",
                "판정할 신호": targets, "숫자 판정(도구)": {n: v for n, v in numeric.items() if v},
                "후보 원문": [{"name": c["name"], "description": str(c.get("description", ""))[:1500], "sales_lines": c.get("sales_lines", [])} for c in candidates],
                "판정 형식": _schema(), "판단 안내": _instruction(),
                "주의": "AI 판정과 도구 권고는 검토 보조 — 사람이 승인·수정"}
    dropped = []
    if judgments is not None:
        judged, dropped = _verify(judgments, tested, cand_by, targets)
        who = "사용자 AI"
    elif any(targets.values()):
        try:
            judged, dropped = _verify(solar.chat_json(_prompt(tested, candidates, targets), max_tokens=4000), tested, cand_by, targets)
        except Exception as e:
            return {"error": f"Solar 판정 실패: {e} — Solar 설정을 빼면 사용자 AI가 판정하는 방식(host_ai)으로 돌아감"}
        who = solar.where()
    else:
        judged, who = {}, "없음(숫자만)"

    results = []
    for c in candidates:
        n = c["name"]
        rows = {**numeric[n], **judged.get(n, {})}
        for k in targets[n]:
            rows.setdefault(k, {"판정": "불명", "이유": "판정이 오지 않음", "근거 문장": "", "원문 확인": "판정 없음", "확신도": "낮음", "판정 주체": "없음"})
        rec, why = _recommend(rows)
        sig_rows = []
        for k in sorted(rows, key=lambda x: int(x[1:])):
            r = rows[k]
            sig_rows.append({"신호": k, "이름": SIGNALS[k]["이름"], **r, "조정 가능": SIGNALS[k]["조정 가능"],
                             **({"판례": _cases_for(k, idx), "볼 포인트": SIGNALS[k]["볼 포인트"]} if r["판정"] != "가까움" else {})})
        results.append({"후보": n, "권고": rec, "이유": why, "확신도": _confidence(rows), "신호": sig_rows,
                        "사람이 볼 것": [f"{s['신호']} {s['이름']}: {s['볼 포인트']}" for s in sig_rows if s["판정"] != "가까움"][:5]})
    order = {"제외 후보": 0, "사람 확인": 1, "포함": 2}
    results.sort(key=lambda r: order[r["권고"]])
    out = {**base, "mode": mode if judgments is None else "host_ai", "판정 주체": who,
           "집계": {k: sum(r["권고"] == k for r in results) for k in order},
           "후보별 권고": results, "묶음 검사": _group_checks(tested, candidates, results, decisions),
           "승인 안내": "권고·판정마다 근거 문장과 판례가 붙어 있다 — 사람은 승인하거나 판정·권고를 고쳐 사유를 남긴다. 제외로 확정한 후보와 사유는 decisions로 넘기면 남긴 후보와 같은 잣대인지 대조한다.",
           "계산 다음 단계": "확정한 후보로 계산 MCP tp_comparable_screen → arm_length_range(정상가격 범위)",
           "주의": "AI 판정과 도구 권고는 검토 보조 — 정상가격이나 비교가능성을 확정하지 않는다. 판례는 tp_cases.json 본문 대조분, 인용 전에 get_tax_ruling으로 본문 확인"}
    if dropped:
        out["무시한 판정"] = dropped[:20]
    if judged:
        out["AI 생성 표시"] = (f"이 결과의 문장 판정은 생성형 AI({who})가 작성했습니다. 근거 문장은 원문과 대조했고, 원문에 없으면 불명으로 낮췄습니다."
                            if judgments is None else "문장 판정은 사용자 AI가 작성했습니다. 근거 문장은 원문과 대조했고, 원문에 없으면 불명으로 낮췄습니다. 사용자에게 보여 줄 때 AI 생성임을 표시하세요.")
    return out
