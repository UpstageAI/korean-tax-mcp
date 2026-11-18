"""이전가격 비교대상 후보 기능 유사성 검토 — AI가 신호별 판정·이유·근거 문장을 채우고, 도구가 근거를 대조해 권고를 낸다. 사람은 승인·수정만.

Claude 작성(2026-11-17). 판정 신호와 판례는 data/tp_review_signals.json(판례 본문 판단 부분과 대조).
- 숫자 신호(광고·연구개발·특수관계·규모·수출·재고)는 숫자가 양쪽에 있으면 도구가 기준값으로 판정한다(관행 기본값, rules로 바꿈).
- 문장 신호(품목·거래단계·사업부문, 숫자가 없을 때의 광고·연구개발)는 모델이 판정한다 — Solar 설정이 있으면 Solar, 없으면 사용자 AI(host_ai).
- 모델이 낸 근거 문장은 입력 원문(후보 설명·매출 구성, 분석대상 입력 칸)과 대조한다. 원문 문장에 주어를 붙이거나 줄여 옮긴 것은 판정을 두고 확신도만 낮추고, 새로 쓴 문장·질문 문장·다른 후보 문장이면 판정을 '불명'으로 낮추며 모델의 원래 판정을 'AI 원래 판정'에 남긴다(지어낸 근거 차단).
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
TEXT_SIGNALS = ("R1", "R2", "R3", "R4", "R8", "R12", "R15", "R16", "R17")       # 모델이 문장으로 판정할 수 있는 신호
CORE = tuple(k for k, s in SIGNALS.items() if s["핵심"])
VERDICTS = ("가까움", "다름", "불명")
CONF = ("높음", "보통", "낮음")
MAX_CANDIDATES = 20
SOLAR_CHUNK = 3            # Solar 한 번에 판정할 후보 수 — 10개(문장 신호 60개)면 답이 1만 자를 넘어 JSON이 잘렸음(2026-11-17 실제 공시 46개)
SOLAR_MAX_TOKENS = 6000
SIGNAL_GROUPS = (("R1", "R2", "R3", "R4"), ("R8", "R12", "R15", "R16", "R17"))   # Solar에 따로 물을 신호 묶음(핵심 / 나머지)
_TESTED_KEYS = ("role", "limited_risk", "products", "channel", "description", "advert", "rnd", "related", "sales", "export", "inv")
_CAND_KEYS = ("name", "description", "sales_lines", "advert", "rnd", "related_sales", "related_purchase", "sales", "export", "inv", "calc")
_RATIO_KEYS = ("advert", "rnd", "related", "related_sales", "related_purchase", "sales", "export", "inv")


def _case_index():
    """판례 번호 → 사례(심급이 있는 사건의 원심·앞 단계 심판은 '관련 문서'에서, 결과는 본 사건 것)."""
    idx = {}
    for v in _tp.cases()["쟁점"].values():
        for c in v["사례"]:
            idx.setdefault(c["문서번호"], c)
            for r in c.get("관련 문서", []):
                idx.setdefault(r["문서번호"], {"문서번호": r["문서번호"], "결과": f"{c['결과']}({c['문서번호']}의 관련 심급)", "링크": r.get("링크", "")})
    return idx


def _cases_for(sig, idx):
    out = []
    for no in SIGNALS[sig]["판례"]:
        c = idx.get(no)
        out.append({"문서번호": no, "결과": c["결과"], "링크": c.get("링크", "")} if c else {"문서번호": no})
    return out


def _norm(s):
    return re.sub(r"[\s\"'“”‘’·.,()\[\]*]", "", str(s or ""))


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




_R2_NOT_MFG = re.compile(r"외주|위탁\s*생산|무공장|시설\s*없이|공장[^.。]{0,15}(?:보유하고\s*있지\s*(?:않|아니)|보유하지\s*(?:않|아니)|없)|(?:OEM|ODM)[\s/·]*(?:OEM|ODM)?\s*업체(?:를|에|와)|협력\s*업체를\s*통해|아웃소싱")
_R2_MFG = re.compile(r"(?:OEM|ODM)\s*제조|공장|생산\s*설비|생산\s*시설|생산\s*능력|CGMP|제조소|생산\s*라인|자체\s*생산|(?:OEM|ODM)[\s/·]*(?:OEM|ODM)?\s*(?:기업|전문|사업|방식으로\s*제조)")


def _snip(t, m):
    return t[max(0, m.start() - 20):m.end() + 20].strip()


_R2_PURPOSE = re.compile(r"제조\s*(?:및|와|·|ㆍ|,)\s*(?:판매|도소매|도매|유통|공급|수출입)|제조\s*판매|제조업(?!체에)|제조를\s*(?:주된|주요)")


def _cand_mfg(c):
    """후보가 직접 제조하는지 원문 낱말로(2026-11-18 결정) — 반환 (직접 제조|안 함|불명|언급 없음, 근거).
    외주·무공장·생산시설 없음 → 안 함, 공장·생산설비·CGMP·OEM·ODM 수탁 → 직접 제조, 둘 다면 불명,
    '제조 및 판매업 영위' 같은 사업 목적 문구만 있으면 불명(실제 제조인지 원문으로 알 수 없음 — 2차 자료로 확인), 제조 말이 없으면 언급 없음."""
    t = _cand_text(c)
    out_m = _R2_NOT_MFG.search(t)
    rest = _R2_NOT_MFG.sub(" ", t)
    in_m = _R2_MFG.search(rest)
    if out_m and in_m:
        return "불명", _snip(t, out_m) + " / " + _snip(rest, in_m)
    if out_m:
        return "안 함", _snip(t, out_m)
    if in_m:
        return "직접 제조", _snip(rest, in_m)
    pm = _R2_PURPOSE.search(t)
    if pm:
        return "불명", _snip(t, pm)
    return "언급 없음", ""


def _instruction():
    return ("후보마다 '판정할 신호'만 판정한다. 근거 문장은 입력 원문(후보 description·sales_lines, 분석대상 products·channel·description)에서 "
            "글자 그대로 옮긴다(요약·번역 금지) — 후보 원문은 '근거 문장', 분석대상 원문은 '분석대상 근거'에 나눠 적는다. 원문에 근거가 없으면 판정을 '불명'으로 하고 근거 문장은 비운다. 업종 코드가 같다는 것만으로 '가까움'이라 하지 않는다. "
            "신호마다 '판정 범위'만 본다 — 한 가지 차이를 여러 신호에 겹쳐 '다름'으로 세지 않는다(예: 자체 브랜드는 R4, 제조사인지는 R2이고 R1 품목은 제품군만). "
            "확신이 없으면 '불명' 또는 확신도 '낮음'. 판정 결과를 judgments로 넣어 이 도구를 다시 부르면 근거 대조와 권고가 붙는다. "
            "결과를 사용자에게 보여 줄 때 AI 생성임을 표시하세요.")


def _prompt(tested, cands, targets, group=TEXT_SIGNALS):
    sig_lines = "\n".join(f"- {k} {SIGNALS[k]['이름']}: {SIGNALS[k]['묻는 것']} [판정 범위] {SIGNALS[k].get('판정 범위', '')}" for k in group)
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


def _parts(quote):
    """근거 문장을 대조 단위(글 그대로)로 — ' / '로 이은 여러 인용, 줄임표('...')로 건너뛴 인용, '분석대상:'·'후보:' 같은 머리말, 괄호 속 메모('(언급 없음)')는 떼어 냄."""
    out = []
    for part in (x for seg in re.split(r"\s/\s|\||\n|\.{2,}|…", str(quote or "")) for x in re.split(r"(?<=다\.)\s*", seg)):
        part = re.sub(r"^\s*(?:\[[^\]]*\]|분석대상|후보(?:\s*[^:：]{0,20})?)\s*[:：]\s*", "", part.strip())
        if not part or re.fullmatch(r"[(（].*[)）]", part):
            continue
        if _norm(part):
            out.append(part)
    return out


def _pieces(quote):
    return [_norm(p) for p in _parts(quote)]


TESTED_TEXT_KEYS = ("products", "channel", "description")
TESTED_FLAG_KEYS = ("role", "limited_risk")   # 문장이 아닌 입력 칸 — 모델이 'limited_risk: true'처럼 칸 이름째 근거로 인용함(2026-11-17 측정: 낮춘 89건 중 24건)
_TESTED_KEY_RE = re.compile(r"(?:분석대상\s*)?\b(?:" + "|".join(TESTED_FLAG_KEYS + TESTED_TEXT_KEYS) + r")\b\s*[:：=]?\s*")


def _tested_values(tested):
    """분석대상 입력 칸의 값(대조용) — 문장 칸과 role·limited_risk."""
    vals = [_norm(tested.get(k)) for k in TESTED_TEXT_KEYS]
    vals += [_norm(str(tested.get(k)).lower()) for k in TESTED_FLAG_KEYS if tested.get(k) is not None]
    return [v for v in vals if v]


def _from_tested(part, tested_vals):
    """근거 조각이 분석대상 입력을 옮긴 것인지 — 칸 이름('limited_risk: true')과 쉼표로 이어 붙인 값들을 나눠, 조각마다 입력 값 안에 있어야 함."""
    if not _TESTED_KEY_RE.search(part):
        return False
    chunks = [_norm(c.lower()) for seg in _TESTED_KEY_RE.split(part) for c in re.split(r"[,;，]", seg)]
    chunks = [c for c in chunks if c and c != "분석대상"]
    return bool(chunks) and all(any(c in v for v in tested_vals) for c in chunks)


def _ordered_cover(piece, src):
    """조각 글자 가운데 원문과 같은 순서로 4자 이상 이어서 겹치는 부분의 비율 — 원문 문장에 주어를 붙이거나 일부를 줄여 옮긴 것은 높고, 낱말만 겹치는 다른 문장은 낮음."""
    from difflib import SequenceMatcher
    if not piece or not src:
        return 0.0
    return sum(b.size for b in SequenceMatcher(None, piece, src, autojunk=False).get_matching_blocks() if b.size >= 4) / len(piece)


def _bigram_cover(piece, srcs):
    """원문에 없는 조각이 원문 말을 줄이거나 이어 쓴 것인지 — 글자 2개 묶음이 원문에 있는 비율."""
    grams = [piece[i:i + 2] for i in range(len(piece) - 1)]
    return sum(any(g in s_ for s_ in srcs) for g in grams) / len(grams) if grams else 0.0


QUOTE_FUZZY_MIN_LEN = 10  # 이보다 짧은 조각은 원문과 글자 그대로 같아야 함(짧으면 우연히 겹침)
QUOTE_COVER_MIN = 0.7     # 분석대상 입력을 줄여 쓴 조각은 글자 2개 묶음 70% 이상이 입력에 있으면 '일부 일치'(사용자가 넣은 글이라 느슨하게). 같은 비율로 질문 글과 겹치면 질문 문장을 근거로 댄 것으로 봄
QUOTE_NEAR_MIN = 0.8      # 원문에 그대로 없는 조각은 글자의 80% 이상이 원문과 같은 순서로 이어 겹쳐야 '일부 일치' — 2026-11-18 화장품 74곳 측정: 주어만 붙인 인용은 0.88 이상, 새로 쓴 문장은 0.68 이하, 다른 회사 문장이 통과한 비율 0.16%(54/33,763)


def _cand_text(c):
    return f"{c.get('description', '')} {' '.join(map(str, c.get('sales_lines') or []))}"


def _cand_src(c):
    return _norm(_cand_text(c))


RISK_WORDS = re.compile(r"재고|반품|가격\s*변동|채권|대손|위험|리스크|보증|위탁|손실|클레임")    # R15 '다름·가까움'은 후보 근거에 이런 위험 서술이 있을 때만(2026-11-18 결정)
SEGMENT_WORDS = re.compile(r"부문|임대업|임대\s*사업|지주|[가-힣]+사업\s*(?:과|및|,|·)\s*[가-힣]+사업")  # R12 — 다른 사업·부문 서술이 보이면 모델 판정을 그대로 둠


def _ask_src():
    """모델에 준 질문 글(신호 이름·묻는 것·판정 범위) — 이것을 근거로 대면 근거가 아님."""
    return _norm(" ".join(f"{v['이름']} {v['묻는 것']} {v.get('판정 범위', '')}" for v in SIGNALS.values()))


def _verify(j, tested, cand_by, targets):
    """모델 판정 검증 — 후보·신호가 요청한 것인지, 근거 문장이 원문에 그대로 있는지. 반환 {후보: {신호: row}}, 무시한 항목 목록"""
    out, dropped = {}, []
    tested_src = _norm(" ".join(str(tested.get(k, "")) for k in TESTED_TEXT_KEYS))
    tested_vals = _tested_values(tested)
    for r in (j or {}).get("판정", []) if isinstance(j, dict) else []:
        if not isinstance(r, dict):
            continue
        name, sig = r.get("후보"), r.get("신호")
        if name not in cand_by or sig not in targets.get(name, ()):
            dropped.append(f"{name}·{sig}: 요청하지 않은 후보·신호")
            continue
        v = model_v = r.get("판정") if r.get("판정") in VERDICTS else "불명"
        conf = r.get("확신도") if r.get("확신도") in CONF else "낮음"
        quote = " / ".join(str(r.get(k) or "").strip() for k in ("근거 문장", "분석대상 근거") if str(r.get(k) or "").strip())
        src = _cand_src(cand_by[name])
        exact = near = 0
        bad = []                                         # 원문에서 온 것이 아닌 조각과 그 까닭
        cand_parts = []                                  # 후보 원문에서 온 조각(R15 위험 서술 검사용)
        for part in _parts(quote):
            p = _norm(part)
            if p in src or p in tested_src or _from_tested(part, tested_vals):
                exact += 1
                if p in src:
                    cand_parts.append(part)
            elif len(p) >= QUOTE_FUZZY_MIN_LEN and (_ordered_cover(p, src) >= QUOTE_NEAR_MIN or _bigram_cover(p, (tested_src,)) >= QUOTE_COVER_MIN):
                near += 1                                # 원문 문장 앞에 '당사는'을 붙이거나 줄여 옮김 — 판정은 그대로, 확신도만 낮춤(2026-11-17 측정: 낮춘 89건 중 58건이 이 경우였음)
                if _ordered_cover(p, src) >= QUOTE_NEAR_MIN:
                    cand_parts.append(part)
            elif any(len(p) >= QUOTE_FUZZY_MIN_LEN and p in _cand_src(o) for n_, o in cand_by.items() if n_ != name):
                bad.append("다른 후보의 문장")
            elif len(p) >= QUOTE_FUZZY_MIN_LEN and _bigram_cover(p, (_ask_src(),)) >= QUOTE_COVER_MIN:
                bad.append("질문 문장을 근거로 댐")
            else:
                bad.append("원문에 없는 말·새로 쓴 문장")
        row_extra = {}
        if bad:
            check = f"원문에 없음({'·'.join(sorted(set(bad)))}) — 판정을 불명으로 낮춤"
            if v != "불명":
                row_extra["AI 원래 판정"] = model_v      # 낮추기 전 판정 — 흔들림 원인을 다시 묻지 않고 가릴 수 있게 남김
            v, conf = "불명", "낮음"
        elif near:
            check = f"일부 일치 — 원문을 고쳐 옮긴 조각 {near}개(주어 붙임·줄임), 확신도 한 단계 낮춤"
            conf = {"높음": "보통", "보통": "낮음"}.get(conf, "낮음")
        elif exact:
            check = "원문 일치"
        elif quote:
            check = "원문에 없음(대조할 문장이 없음) — 판정을 불명으로 낮춤"
            if v != "불명":
                row_extra["AI 원래 판정"] = model_v
            v, conf = "불명", "낮음"
        else:
            check = "근거 문장 없음"
            if v != "불명":
                conf = "낮음"
        if sig == "R15" and v != "불명" and not RISK_WORDS.search(" ".join(cand_parts)):
            row_extra.setdefault("AI 원래 판정", model_v)    # 위험 서술 없이 '제조사라 위험을 질 것'처럼 미룬 판정 — 실행마다 갈렸음(2026-11-18 측정: R15 갈린 후보 17곳 → 1곳)
            check += " · 후보 근거에 위험 서술(재고·반품·가격변동·채권) 없음 — R15는 불명(제조·유통 차이는 R2 몫)"
            v, conf = "불명", "낮음"
        elif sig == "R12" and model_v == "불명" and _cand_text(cand_by[name]).strip() and not SEGMENT_WORDS.search(_cand_text(cand_by[name])):
            row_extra["AI 원래 판정"] = model_v              # 다른 사업 서술이 없으면 한 사업만 하는 회사(판정 범위 규칙) — 모델이 실행마다 가까움·불명을 오갔음(R12 갈린 후보 15곳 → 7곳)
            check += " · 다른 사업·부문 서술 없음 — 한 사업만 하는 회사로 봄(가까움)"
            v, conf = "가까움", "보통"
        out.setdefault(name, {})[sig] = {"판정": v, "이유": str(r.get("이유", ""))[:400], "근거 문장": quote[:400], "원문 확인": check,
                                         "확신도": conf, "판정 주체": "AI(문장)", **row_extra}
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
            "신호 설명": {k: {"이름": SIGNALS[k]["이름"], "묻는 것": SIGNALS[k]["묻는 것"], **({"판정 범위": SIGNALS[k]["판정 범위"]} if SIGNALS[k].get("판정 범위") else {}),
                         "근거 층": {**SIGNALS[k].get("근거 층", {}), "판례": SIGNALS[k]["판례"]}} for k in _signals_for(role)},
            "분석요소 대응": _DATA["분석요소 대응"], "근거 확인": _DATA["근거 확인"],
            "기준값": {k: {"값": R[k], "성격": _DATA["숫자 기준"][k]["성격"], "뜻": _DATA["숫자 기준"][k]["뜻"]} for k in DEFAULT_RULES}}

    mode = solar.mode()
    if judgments is None and mode == "host_ai" and any(targets.values()):
        return {**base, "mode": "host_ai", "단계": "1/2 — 사용자 AI가 문장 신호를 판정해 judgments로 다시 부르기",
                "판정할 신호": targets, "숫자 판정(도구)": {n: v for n, v in numeric.items() if v},
                "후보 원문": [{"name": c["name"], "description": str(c.get("description", ""))[:1500], "sales_lines": c.get("sales_lines", [])} for c in candidates],
                "판정 형식": _schema(), "판단 안내": _instruction(),
                "주의": "AI 판정과 도구 권고는 검토 보조 — 사람이 승인·수정"}
    dropped, failed = [], {}
    if judgments is not None:
        judged, dropped = _verify(judgments, tested, cand_by, targets)
        who = "사용자 AI"
    elif any(targets.values()):
        judged, failed = {}, {}
        todo = [c for c in candidates if targets[c["name"]]]
        for group in SIGNAL_GROUPS:                       # 신호를 한 번에 다 물으면 판정 범위가 섞임(품목에 브랜드·제조를 겹쳐 셈) — 핵심 신호와 나머지를 따로 물음
            tg = {n: [k for k in v if k in group] for n, v in targets.items()}
            gtodo = [c for c in todo if tg[c["name"]]]
            for i in range(0, len(gtodo), SOLAR_CHUNK):   # 후보가 많으면 답이 길어져 JSON이 잘림 — 묶음을 작게 나눠 부르고, 실패한 묶음만 불명
                part = gtodo[i:i + SOLAR_CHUNK]
                for attempt in range(2):                  # Solar가 가끔 깨진 JSON을 냄 — 한 번 다시 부름
                    try:
                        j, d = _verify(solar.chat_json(_prompt(tested, part, tg, group), max_tokens=SOLAR_MAX_TOKENS), tested, cand_by, tg)
                        for n, rows_ in j.items():
                            judged.setdefault(n, {}).update(rows_)
                        dropped += d
                        for c in part:
                            failed.pop((c["name"], group), None)
                        break
                    except Exception as e:
                        for c in part:
                            failed[(c["name"], group)] = f"{type(e).__name__}: {str(e)[:120]}"
        failed = {n: msg for (n, _g), msg in failed.items()}
        if failed and len(failed) == len(todo):
            return {"error": f"Solar 판정 실패(후보 {len(failed)}개 모두): {next(iter(failed.values()))} — Solar 설정을 빼면 사용자 AI가 판정하는 방식(host_ai)으로 돌아감"}
        who = solar.where()
    else:
        judged, who = {}, "없음(숫자만)"

    results = []
    for c in candidates:
        n = c["name"]
        rows = {**numeric[n], **judged.get(n, {})}
        for k in targets[n]:
            rows.setdefault(k, {"판정": "불명", "이유": f"Solar 판정 실패 — {failed[n]}" if n in failed else "판정이 오지 않음",
                                "근거 문장": "", "원문 확인": "판정 없음", "확신도": "낮음", "판정 주체": "없음"})
        if "R2" in targets[n]:                            # R2 제조 여부만 원문 낱말로 도구가 정함(2026-11-18) — 같은 '제조 및 판매업 영위' 한 줄을 모델이 실행마다 다르게 읽었음(R2 갈린 17곳 중 13곳)
            cm, ev = _cand_mfg(c)
            tm = {"판매": "안 함", "제조": "직접 제조"}.get(role, "불명")
            ai = rows.get("R2", {}).get("판정")
            tool = None
            if "불명" not in (tm,) and cm in ("직접 제조", "안 함") and cm != tm:
                tool = ("다름", f"제조 {cm} vs 분석대상 {tm}")
            elif cm == "불명" and tm != "불명":
                tool = ("불명", "후보가 실제로 제조하는지 원문으로 알 수 없음(사업 목적 문구만 있거나 외주·자체 생산이 섞여 있음) — 생산설비·판매경로 자료로 2차 확인")
            if tool:
                rows["R2"] = {"판정": tool[0], "이유": tool[1], "근거 문장": ev, "원문 확인": "원문 낱말로 도구가 판정", "확신도": "보통" if tool[0] != "불명" else "낮음",
                              "판정 주체": "도구(원문 낱말)", "사실": {"후보 제조": cm, "분석대상 제조": tm}, **({"AI 판정": ai} if ai else {})}
            elif "R2" in rows:
                rows["R2"] = {**rows["R2"], "사실": {"후보 제조": cm, "분석대상 제조": tm}}
        rec, why = _recommend(rows)
        sig_rows = []
        for k in sorted(rows, key=lambda x: int(x[1:])):
            r = rows[k]
            sig_rows.append({"신호": k, "이름": SIGNALS[k]["이름"], **r, "조정 가능": SIGNALS[k]["조정 가능"],
                             **({"근거": {**SIGNALS[k].get("근거 층", {}), "판례": _cases_for(k, idx)}, "볼 포인트": SIGNALS[k]["볼 포인트"]} if r["판정"] != "가까움" else {})})
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
    if failed:
        out["판정 실패 후보"] = {"후보": list(failed), "안내": "이 후보들은 문장 신호가 불명으로 남음 — 같은 후보만 다시 부르거나 사용자 AI로 판정(judgments)"}
    if judged:
        out["AI 생성 표시"] = (f"이 결과의 문장 판정은 생성형 AI({who})가 작성했습니다. 근거 문장은 원문과 대조했고, 원문에 없으면 불명으로 낮췄습니다."
                            if judgments is None else "문장 판정은 사용자 AI가 작성했습니다. 근거 문장은 원문과 대조했고, 원문에 없으면 불명으로 낮췄습니다. 사용자에게 보여 줄 때 AI 생성임을 표시하세요.")
    return out
