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
_TESTED_KEYS = ("role", "function", "limited_risk", "products", "channel", "description", "advert", "rnd", "related", "sales", "export", "inv")
_CAND_KEYS = ("name", "description", "sales_lines", "advert", "rnd", "related_sales", "related_purchase", "sales", "export", "inv", "calc", "production", "mix", "goods_merch_ratio", "industry_code")
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


# 비상장 후보 직접 제조 기준: 기계장치 취득원가(상각 전)가 매출의 3% 이상(2026-11-18 결정).
# 근거: 화장품 업종 비상장 33곳 실측에서 제조사·ODM은 4.1% 이상, 브랜드·유통사는 1.9% 이하로 2~4% 사이에 회사가 없었음.
# 장부가액(상각 후)은 쓰지 않음 — 상각은 원가 배분일 뿐 설비는 처분 전까지 남아 오래된 공장일수록 작게 읽힘.
MACHINERY_COST_TO_SALES = 0.03


def _cand_mfg(c):
    """후보가 직접 제조하는지 원문 낱말로(2026-11-18 결정) — 반환 (직접 제조|안 함|불명|언급 없음, 근거).
    외주·무공장·생산시설 없음 → 안 함, 공장·생산설비·CGMP·OEM·ODM 수탁 → 직접 제조, 둘 다면 불명,
    '제조 및 판매업 영위' 같은 사업 목적 문구만 있으면 불명(실제 제조인지 원문으로 알 수 없음 — 2차 자료로 확인), 제조 말이 없으면 언급 없음.
    2차 자료(후보 production: 사업보고서 '원재료 및 생산설비'의 외주 문장·생산능력 원문)가 있으면 먼저 쓴다 — 외주만 안 함, 생산능력만 직접 제조, 둘 다면 불명(2026-11-18). 비상장 감사보고서는 기계장치 계정이 없으면 안 함, 있으면 취득원가가 매출의 3% 이상 직접 제조·미만 또는 0원 안 함, 취득원가를 못 읽었으면 글 규칙으로."""
    pr = c.get("production")                            # 2차 자료: 사업보고서 '원재료 및 생산설비' 절의 단서(계산 MCP kr_comparable_candidates의 production) — 있으면 먼저 씀
    if isinstance(pr, dict):
        no_own = [str(x) for x in (pr.get("no_own_facility") or []) if str(x).strip()]
        own = [str(x) for x in (pr.get("own_production") or []) if str(x).strip()]
        if no_own and own:
            return "불명", f"[사업보고서 원재료 및 생산설비] 외주 문장과 생산능력·설비가 함께 있음(사업부문·자회사마다 다를 수 있음): {no_own[0][:80]} / {own[0][:80]}"
        if no_own:
            return "안 함", "[사업보고서 원재료 및 생산설비] " + no_own[0][:160]
        if own:
            return "직접 제조", "[사업보고서 원재료 및 생산설비] " + own[0][:160]
        if pr.get("machinery_account") == "없음":          # 비상장 감사보고서: 유형자산 주석에 기계장치·생산설비 계정이 없음(2026-11-18)
            return "안 함", "[감사보고서 유형자산 주석] " + str(pr.get("machinery_evidence") or "기계장치 계정 없음")[:160]
        mc, ratio = pr.get("machinery_cost"), pr.get("machinery_cost_to_sales")
        if pr.get("machinery_account") == "있음" and mc is not None:   # 기계장치 취득원가(상각 전)의 매출 대비 — 3% 기준(2026-11-18 결정)
            ev = f"[감사보고서] 기계장치 취득원가 {mc / 1e8:.2f}억 원" + (f", 매출 대비 {ratio * 100:.1f}%" if ratio is not None else "") + f" ({str(pr.get('machinery_cost_evidence') or '')[:80]})"
            if mc == 0:
                return "안 함", ev + " — 기계장치 없음(취득원가 표에 없음·처분)"
            if ratio is not None:
                return ("직접 제조", ev + f" — {MACHINERY_COST_TO_SALES:.0%} 이상") if ratio >= MACHINERY_COST_TO_SALES else ("안 함", ev + f" — {MACHINERY_COST_TO_SALES:.0%} 미만(소형 장비 수준)")
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



# R4 '다름'은 후보 원문에 연구개발·브랜드 서술이 있을 때만(근거 인용은 실행마다 달라 원문 전체로 봄)(2026-11-19 결정) — 화장품 후보 95곳 3번 판정에서 R4가 갈린 4곳 중
# 3곳이 '제조ㆍ판매업 영위'만 인용하고 연구소·브랜드 '보유 가능성'으로 다름을 냈음(제조 여부는 R2 몫). 남의 브랜드 상품을 파는 서술은 자체 브랜드가 아님.
_R4_EVID = re.compile(r"브랜드|연구|개발|특허|상표|기술|R&D|라이선스|로열티", re.I)
_R4_OTHERS = re.compile(r"\d+\s*여?\s*개(?:의)?\s*[^.]{0,15}브랜드|브랜드\s*(?:의\s*)?(?:상품|제품)(?:을|를)\s*(?:판매|취급|유통|공급|수입)")


# R2 '다름'도 같은 방식(2026-11-19 결정): 도구가 후보·분석대상 제조 여부를 같다고 정했으면, 모델의 '다름'은 후보 원문에 거래단계·판매채널 서술이 있을 때만.
# 화장품 95곳 3번 판정에서 제조 여부가 같은데 '화장품 제조, 판매'·'판매를 주요 사업'만 인용해 다름을 낸 칸이 실행마다 갈렸음(2곳).
_R2_CHANNEL = re.compile(r"도매|소매|직영|직접\s*판매|직판|온라인|쇼핑몰|자사몰|플랫폼|면세|유통\s*업체|유통\s*채널|대리점|총판|홈쇼핑|드럭\s*스토어|H&B|백화점|할인점|마트|편의점|수출|B2B|B2C|채널|방문\s*판매|다단계|(?:OEM|ODM)|매출처|거래처|리셀러|도·소매|도소매", re.I)


def _cand_evidence(quote, tested, pat, others=None):
    """근거 문장에서 분석대상 입력을 옮긴 조각을 빼고, 후보 쪽 조각에 pat 서술이 있는지 — 반환 (있음 여부, 후보 쪽 조각)."""
    tv = _tested_values(tested)
    cand = [p for p in _parts(quote) if not (_norm(p) and any(_norm(p) in v for v in tv)) and not _from_tested(p, tv)]
    txt = " ".join(cand)
    return bool(pat.search(others.sub(" ", txt) if others else txt)), txt


def _r4_cand_evidence(quote, tested):
    """R4: 후보 쪽 근거에 연구개발·자체 브랜드 서술이 있는지(남의 브랜드 상품 판매 서술은 뺌)."""
    return _cand_evidence(quote, tested, _R4_EVID, _R4_OTHERS)


# 깔때기(2026-11-19 결정): 0층 숫자 거르기 → 1층 기능 대분류 → 2층 세부 유형 → 3층 제품군(R1) → 4층 거래단계(R2) → 5층 그 밖.
# 끊는 선: 1층 다름 제외 / 2층(숫자 차이) 사람 확인 / 품목·거래단계·마케팅·연구개발(R1~R4) 가운데 둘 이상 다름 제외, 하나 사람 확인 / 5층은 제외 사유 아님(보고서에 차이만).
# 판례 정답 세트로 고친 두 곳(2026-11-19): 특수관계 거래 비중(R5)은 의존도만으로 특수관계가 아니어서(2009두24122) 0층 제외가 아니라 사람 확인,
# 마케팅·연구개발만 함께 달라도 제외된 사건(2024두54065)이 있어 '둘 이상 다름'은 3·4층만이 아니라 R1~R4로 센다.
MAJOR = {"A": "제조", "B": "유통", "C": "서비스", "D": "무형자산·플랫폼"}
_ROLE_MAJOR = {"판매": "B", "제조": "A", "용역": "C"}
LAYER2 = ("R3", "R5", "R7", "R14")     # 숫자 차이 — 광고·판촉(세부 유형: 전부 유통·제한위험 유통), 특수관계 거래 비중, 규모, 재고
LAYER5 = ("R8", "R12", "R15", "R16", "R17")


def _tested_major(tested):
    f = str(tested.get("function") or "").strip().upper()[:1]
    return f if f in MAJOR else _ROLE_MAJOR.get(tested.get("role"))


def _cand_major(c):
    """후보 기능 대분류 — 반환 (A|B|C|D|혼합|판단불가, 근거). 매출 구성(계산 MCP mix_*, 커버리지 0.8~1.2)이 있으면 그것,
    없으면 재화 원가·재고의 상품 비율(goods_merch_ratio): 0.5 이상 B, 미만 A. 판정은 숫자로만 — 사업 설명 글은 보지 않는다."""
    m = c.get("mix") if isinstance(c.get("mix"), dict) else {}
    cov = _num(m.get("coverage"))
    if m and cov is not None and 0.8 <= cov <= 1.2:
        sh = {"A": _num(m.get("product")) or 0, "B": _num(m.get("merchandise")) or 0, "C": _num(m.get("service")) or 0,
              "D": (_num(m.get("sw_license")) or 0) + (_num(m.get("platform_fee")) or 0)}
        k = max(sh, key=sh.get)
        ev = "[매출 구성] " + ", ".join(f"{MAJOR[x]} {v:.0%}" for x, v in sh.items() if v)
        if sh[k] >= 0.5:
            return k, ev
        if sh["A"] + sh["B"] >= 0.5 and sh["C"] + sh["D"] < 0.5 and _num(c.get("goods_merch_ratio")) is not None:
            pass                                          # 재화 매출이 큰데 제품·상품이 반반 — 원가·재고 비율로 가름
        else:
            return "혼합", ev + " — 어느 하나도 50% 미만"
    g = _num(c.get("goods_merch_ratio"))
    if g is not None:
        return ("B" if g >= 0.5 else "A"), f"[매출원가·재고] 상품 비율 {g:.0%}(상품 ÷ 상품·제품) — 매출 구성을 못 읽어 대신 씀"
    return "판단불가", "매출 구성·매출원가·재고 구성을 모두 못 읽음"


def _cand_subtype(c, major):
    if major != "A":
        return MAJOR.get(major, major)
    cm, ev = _cand_mfg(c)
    return {"직접 제조": "제조 — 직접(공장 있음)", "안 함": "제조 — 위탁 브랜드(공장 없이 외주)"}.get(cm, "제조 — 방식 불명"), ev


def _funnel_pre(tested, c, numeric):
    """0~2층 — 반환 {'층', '결과'(제외|사람 확인|통과), '사유', '대분류', '세부'}. 문장 판정(3층 이후) 전에 숫자로만."""
    tm = _tested_major(tested)
    if "mix" not in c and "goods_merch_ratio" not in c:      # 1층 숫자 자료를 넘기지 않은 호출(사업 설명만) — 1층은 건너뜀
        d2 = [k for k in LAYER2 if numeric.get(k, {}).get("판정") == "다름"]
        return {"층": 2, "결과": "사람 확인" if d2 else "통과", "사유": ("숫자 차이 — " + "; ".join(f"{SIGNALS[k]['이름']}: {numeric[k]['이유']}" for k in d2)) if d2 else "",
                "대분류": "자료 없음", "대분류 근거": "mix·goods_merch_ratio를 넘기지 않아 1층(기능 대분류)을 건너뜀"}
    cm, ev = _cand_major(c)
    sub = _cand_subtype(c, cm)
    sub_name, sub_ev = (sub if isinstance(sub, tuple) else (sub, ""))
    info = {"대분류": cm, "대분류 근거": ev, "세부": sub_name, **({"세부 근거": sub_ev} if sub_ev else {})}
    if tm and cm in MAJOR and cm != tm:
        return {"층": 1, "결과": "제외", "사유": f"1층 기능 대분류 다름 — 후보 {sub_name}, 분석대상 {MAJOR[tm]}", **info}
    if cm in ("혼합", "판단불가"):
        return {"층": 1, "결과": "사람 확인", "사유": f"1층 기능 대분류 {cm} — {ev}", **info}
    d2 = [k for k in LAYER2 if numeric.get(k, {}).get("판정") == "다름"]
    if d2:
        return {"층": 2, "결과": "사람 확인", "사유": "2층 숫자 차이 — " + "; ".join(f"{SIGNALS[k]['이름']}: {numeric[k]['이유']}" for k in d2), **info}
    return {"층": 2, "결과": "통과", "사유": "", **info}

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


# R1 취급 품목 — 제품군을 원문 낱말로 도구가 먼저 정함(2026-11-18 결정). 6번 판정에서 R1이 갈린 28곳 중 약 25곳은
# 모델이 제조·ODM·자체 브랜드를 품목에 끌어들이거나('다름') '화장품'이라고만 적혀 세부를 몰라 '불명'으로 흔들렸음 — 판정 범위 밖.
# 업종 팩(2026-11-19 결정: 업종별 지식은 깔때기 3·4층에만) — data/tp_packs/*.json. 분석대상 품목·설명에 같은 제품군 낱말이 처음 걸리는 팩을 씀.
# 화장품은 후보 원문 실측으로 손으로 만든 목록, 컴퓨터는 한국표준산업분류 해설서 예시 품목에서 만든 목록(bench_ksic/make_pack.py).
_PACK_ORDER = ("cosmetics", "computer", "pharma")
_PACK_DIR = os.path.join(os.path.dirname(__file__), "data", "tp_packs")


def _words_re(words):
    return "|".join(r"\s*".join(map(re.escape, w.replace(" ", ""))) for w in sorted(set(words), key=lambda w: -len(w.replace(" ", ""))))


def _load_pack(pid):
    with open(os.path.join(_PACK_DIR, f"{pid}.json"), encoding="utf-8") as f:
        p = json.load(f)
    rx = p.get("정규식") or {"같은 제품군": _words_re(x["낱말"] for x in p["같은 제품군"]),
                           "다른 제품군": _words_re(w for w, _code in p["다른 제품군"])}
    return {"id": p["id"], "제품군": p["제품군"], "출처": p["출처"], "업종코드": p["업종코드"],
            "same": re.compile(rx["같은 제품군"]), "other": re.compile(rx["다른 제품군"])}


PACKS = [_load_pack(p) for p in _PACK_ORDER]
_R1_HOLDING = re.compile(r"순수\s*지주\s*회사|지주\s*사업을\s*중점")


def _pack_for(tested):
    tt = f"{tested.get('products', '')} {tested.get('description', '')}"
    return next((p for p in PACKS if p["same"].search(tt)), None)


def _code_rel(code, pack_codes):
    """후보 DART 등록 업종코드와 팩 업종코드의 관계 — 같음(팩 코드이거나 그 아래)·넓음(팩 코드의 상위, 판단 못 함)·다름·None(코드 없음)."""
    c = re.sub(r"\D", "", str(code or ""))
    if not c:
        return None, ""
    if any(c.startswith(p) for p in pack_codes):
        return "같음", c
    if any(p.startswith(c) for p in pack_codes):
        return "넓음", c
    return "다름", c


CODE_CONFLICT = "업종코드 오등록 의심"


def _cand_product(c, tested):
    """후보 제품군을 원문 낱말과 DART 등록 업종코드로 — 반환 (가까움|다름|불명, 근거) 또는 None(모델에 맡김).
    순수 지주회사 → 다름. 같은 제품군 사업부문의 매출 비중 50% 이상 → 가까움.
    원문 낱말: 분석대상 제품군 낱말만 있으면 가까움, 다른 제품군 낱말만 있으면 다름(2026-11-19).
    업종코드 교차 확인(2026-11-19 승미님 결정 — 표현이 회사마다 달라 낱말 목록을 늘리지 않고 숫자 코드를 같이 봄):
      원문과 코드가 같은 쪽 → 그대로, 원문과 코드가 엇갈림 → 불명 + '업종코드 오등록 의심'(사람 확인),
      원문에 어느 제품군 낱말도 없으면 코드가 다름 → 다름, 코드가 같거나 넓으면 모델에 — 코드만으로 '가까움'은 주지 않음
      (고침용 자료에서 코드만으로 가까움 7건 중 2건이 다른 사업 — 한의원 컨설팅, 화장용 브러시. 코드만으로 다름 2건은 맞음).
    제조·ODM·자체 브랜드·수입 여부는 보지 않는다(R2·R4 몫). 다른 제품군이 섞이고 비중을 모르면 None."""
    pk = _pack_for(tested)
    if not pk:
        return None
    grp, pat = pk["제품군"], pk["same"].pattern
    t = _cand_text(c)
    hm = _R1_HOLDING.search(t)
    if hm:
        return "다름", "순수 지주회사 — 직접 파는 물건이 없음: " + _snip(t, hm)
    for m in re.finditer(r"(?:" + pat + r")\s*(?:사업\s*부문|사업부|사업|부문)[^%]{0,80}?(\d{1,3}(?:\.\d+)?)\s*%", t):
        if 50 <= float(m.group(1)) <= 100:
            return "가까움", f"{grp} 사업부문 매출 비중 {m.group(1)}%: " + _snip(t, m)
    gm = pk["same"].search(t)
    om = pk["other"].search(t)
    rel, code = _code_rel(c.get("industry_code"), pk["업종코드"])
    ctag = f"업종코드 {code}" if code else ""
    if gm and not om:
        if rel == "다름":
            return "불명", f"{CODE_CONFLICT} — 원문은 {grp}인데 등록 {ctag}는 {grp} 업종({', '.join(pk['업종코드'])})이 아님: " + _snip(t, gm)
        return "가까움", f"후보 원문의 제품군이 {grp}뿐(다른 제품군 낱말 없음, 업종 팩 {pk['id']}{', ' + ctag + ' ' + rel if rel else ''}): " + _snip(t, gm)
    if om and not gm:
        if rel == "같음":
            return "불명", f"{CODE_CONFLICT} — 등록 {ctag}는 {grp} 업종인데 원문에는 다른 제품군 '{om.group(0)}'만: " + _snip(t, om)
        return "다름", f"후보 원문에 {grp} 낱말이 없고 다른 제품군 '{om.group(0)}'(업종 팩 {pk['id']}{', ' + ctag + ' ' + rel if rel else ''}): " + _snip(t, om)
    if not gm and not om and rel == "다름":
        return "다름", f"원문에 제품군 낱말이 없고 등록 {ctag}가 {grp} 업종({', '.join(pk['업종코드'])})이 아님"
    return None


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


def _recommend(rows, pre=None):
    """깔때기 끊는 선(2026-11-19 승미님 결정, 판례 정답 세트로 보정). pre는 0~2층 결과."""
    pre = pre or {"층": 2, "결과": "통과", "사유": ""}
    if pre["결과"] == "제외":
        return "제외 후보", pre["사유"]
    core_diff = [k for k in CORE if rows.get(k, {}).get("판정") == "다름"]
    if len(core_diff) >= 2:
        return "제외 후보", f"핵심 신호 {', '.join(core_diff)}가 함께 다름 — 판례상 품목·거래단계·기능이 함께 다르고 조정이 없으면 비교가능성이 부정됨(대법원 2012두23341, 수원고법 2023누16871)"
    why = [pre["사유"]] if pre["결과"] == "사람 확인" else []
    if core_diff:
        why.append(f"{SIGNALS[core_diff[0]]['이름']}({core_diff[0]})만 다름 — 차이 하나만으로 제외된 사례는 없음, 조정 가능 여부와 이익률 영향을 사람이 확인")
    unk = [k for k in CORE if rows.get(k, {}).get("판정") == "불명"]
    core_here = [k for k in CORE if k in rows]
    if not why and core_here and len(unk) >= min(3, len(core_here)):
        why.append(f"핵심 신호 {len(core_here)}개 중 불명 {len(unk)}개({', '.join(unk)}) — 자료를 더 확보해 판정")
    elif not why and "R1" in unk and "R2" in unk:            # 품목·거래단계를 둘 다 모르면 포함하지 않음(2026-11-19 측정: 둘 다 불명인 후보가 '포함'으로 나옴)
        why.append("품목(R1)과 거래단계(R2)가 모두 불명 — 자료를 더 확보해 판정")
    if not why and CODE_CONFLICT in str(rows.get("R1", {}).get("이유", "")):   # 품목 원문과 업종코드가 엇갈리면 포함하지 않음(2026-11-19)
        why.append("품목(R1) 원문과 DART 등록 업종코드가 엇갈림 — 업종코드 오등록 여부를 사람이 확인")
    d5 = [k for k in LAYER5 if rows.get(k, {}).get("판정") == "다름"]
    tail = f" · {', '.join(d5)} 차이는 제외 사유가 아님 — 보고서에 차이와 조정 여부를 적음" if d5 else ""
    if why:
        return "사람 확인", " / ".join(why) + tail
    return "포함", "다른 신호가 없음(핵심 신호 불명 2개 이하)" + tail + " — 거래단계·시장·계약 조건은 사람이 최종 확인"


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
    pre = {c["name"]: _funnel_pre(tested, c, numeric[c["name"]]) for c in candidates}
    targets = {c["name"]: ([] if pre[c["name"]]["결과"] == "제외" else _model_targets(tested, c, numeric[c["name"]], role)) for c in candidates}   # 0·1층에서 제외되면 문장 판정을 묻지 않음
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
        if "R1" in targets[n]:                            # R1 제품군은 원문 낱말로 도구가 먼저 정함(2026-11-18) — 못 정하면 모델 판정 그대로
            tool = _cand_product(c, tested)
            if tool:
                ai = rows.get("R1", {}).get("판정")
                rows["R1"] = {"판정": tool[0], "이유": tool[1], "근거 문장": tool[1].split(": ", 1)[-1], "원문 확인": "원문 낱말로 도구가 판정",
                              "확신도": "보통", "판정 주체": "도구(원문 낱말)", **({"AI 판정": ai} if ai else {})}
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
        r2 = rows.get("R2", {})
        f2 = r2.get("사실") or {}
        if (r2.get("판정") == "다름" and "AI" in str(r2.get("판정 주체", "")) and f2.get("후보 제조") == f2.get("분석대상 제조")
                and f2.get("후보 제조") in ("안 함", "직접 제조") and not _R2_CHANNEL.search(_cand_text(c))):
            rows["R2"] = {**r2, "판정": "불명", "확신도": "낮음", "AI 판정": "다름",
                          "이유": f"제조 여부는 후보·분석대상 모두 '{f2.get('후보 제조')}'(도구 확인)이고 후보 원문에 거래단계·판매채널 서술이 없음 — AI 이유: " + str(r2.get("이유", ""))[:120],
                          "원문 확인": "후보 원문에 거래단계·판매채널 서술 없음 — 불명으로 낮춤"}
        r4 = rows.get("R4", {})
        if "R4" in targets[n] and r4.get("판정") == "다름" and "AI" in str(r4.get("판정 주체", "")):
            if not _R4_EVID.search(_R4_OTHERS.sub(" ", _cand_text(c))):   # 근거 인용은 실행마다 다르게 고름 — 후보 원문 전체로 봄
                rows["R4"] = {**r4, "판정": "불명", "확신도": "낮음", "AI 판정": "다름",
                              "이유": "후보 원문에 연구개발·자체 브랜드 서술이 없음(제조·판매업 영위나 남의 브랜드 상품 판매만으로 추정하지 않음) — AI 이유: " + str(r4.get("이유", ""))[:120],
                              "원문 확인": "후보 원문에 연구개발·브랜드 서술 없음 — 불명으로 낮춤"}
        rec, why = _recommend(rows, pre[n])
        sig_rows = []
        for k in sorted(rows, key=lambda x: int(x[1:])):
            r = rows[k]
            sig_rows.append({"신호": k, "이름": SIGNALS[k]["이름"], **r, "조정 가능": SIGNALS[k]["조정 가능"],
                             **({"근거": {**SIGNALS[k].get("근거 층", {}), "판례": _cases_for(k, idx)}, "볼 포인트": SIGNALS[k]["볼 포인트"]} if r["판정"] != "가까움" else {})})
        results.append({"후보": n, "권고": rec, "이유": why, "확신도": _confidence(rows), "깔때기": pre[n], "신호": sig_rows,
                        "사람이 볼 것": [f"{s['신호']} {s['이름']}: {s['볼 포인트']}" for s in sig_rows if s["판정"] != "가까움"][:5]})
    order = {"제외 후보": 0, "사람 확인": 1, "포함": 2}
    results.sort(key=lambda r: order[r["권고"]])
    out = {**base, "mode": mode if judgments is None else "host_ai", "판정 주체": who,
           "집계": {k: sum(r["권고"] == k for r in results) for k in order},
           "후보별 권고": results, "묶음 검사": _group_checks(tested, candidates, results, decisions),
           "업종 팩": ({"id": pk["id"], "제품군": pk["제품군"], "업종코드": pk["업종코드"], "출처": pk["출처"]} if (pk := _pack_for(tested))
                     else "없음 — 분석대상 품목에 맞는 업종 팩이 없어 품목(R1)은 모델 판정만 씀(지금 팩: " + ", ".join(p["제품군"] for p in PACKS) + ")"),
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
