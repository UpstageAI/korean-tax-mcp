"""OECD 이전가격지침 2022 문단 색인 조회. Claude 작성(2026-11-12).

출처: OECD (2022), OECD Transfer Pricing Guidelines for Multinational Enterprises and Tax Administrations 2022, OECD Publishing, Paris,
https://doi.org/10.1787/0e655865-en. © OECD 2022. OECD 이용약관(2024.7.1. 전 발간 자료: 출처를 밝히면 복제·배포·번안 가능, oecd.org/en/about/terms-conditions.html)에 따라
본문 제1장~제10장 문단 1,391개를 PDF에서 추출해 실었다(658쪽 전 쪽 추출, 부속서는 제외). 추출문이라 띄어쓰기·각주 표시가 어긋날 수 있으니 인용 전에 쪽 번호로 원문을 확인한다.
This is an adaptation of an original work by the OECD. The opinions expressed and arguments employed in this adaptation should not be reported as
representing the official views of the OECD or of its Member countries.
"""
import json
import os
import re

_PATH = os.path.join(os.path.dirname(__file__), "data", "oecd_tpg_2022.json")
_ROWS = None
CITATION = ("OECD (2022), OECD Transfer Pricing Guidelines for Multinational Enterprises and Tax Administrations 2022, "
            "OECD Publishing, Paris, https://doi.org/10.1787/0e655865-en")
STATUS = ("OECD 이전가격지침은 국내에서 법적 효력이 있는 규정이 아니다(대법원-2012-두-1969, 2012.5.24.; 서울고등법원-2010-누-25116 — 권고적 지침). "
          "다만 국조법령에 규정이 없거나 해석이 갈리는 대목에서 납세자·과세관청·심판례가 정상가격 원칙의 해석 자료로 든다(예: 조심-2025-서-3897, 조심-2012-중-3014). "
          "국조법령과 다르면 국조법령이 우선한다")
NOTE = "PDF 추출문(영문 원문) — 띄어쓰기·각주 번호가 어긋날 수 있음. 인용 전에 쪽 번호로 원문 확인. 부속서(사례·문서화 양식)는 색인에 없음"
CHAPTERS = {1: "The arm's length principle", 2: "Transfer pricing methods", 3: "Comparability analysis",
            4: "Administrative approaches to avoiding and resolving transfer pricing disputes", 5: "Documentation",
            6: "Special considerations for intangibles", 7: "Special considerations for intra-group services",
            8: "Cost contribution arrangements", 9: "Transfer pricing aspects of business restructurings",
            10: "Transfer pricing aspects of financial transactions"}
CHAPTERS_KO = {1: "정상가격 원칙", 2: "정상가격 산출방법", 3: "비교가능성 분석", 4: "분쟁 예방·해결 행정 절차", 5: "문서화", 6: "무형자산",
               7: "그룹 내 용역", 8: "원가분담약정", 9: "사업 구조조정", 10: "금융거래"}

# 국조법령 ↔ 지침 문단 대응(문단은 그 주제가 시작되는 곳과 범위 — 2026-11-12 문단 본문으로 대조)
CROSSWALK = [
    {"주제": "정상가격 원칙·조세조약 특수관계기업 조항", "국내": "국조법 제7조, 조세조약 제9조", "문단": "1.6-1.15"},
    {"주제": "비교가능성 분석요소(계약조건·기능·재화·경제 여건·사업전략)", "국내": "시행령 제14조②, 시행규칙 제6조", "문단": "1.33-1.39"},
    {"주제": "기능 분석(수행 기능·사용 자산·부담 위험)", "국내": "시행규칙 제6조, 시행령 제16조①", "문단": "1.51-1.55"},
    {"주제": "위험 분석 여섯 단계", "국내": "시행규칙 제10조", "문단": "1.56-1.106", "핵심": "1.60"},
    {"주제": "사업전략(시장 침투 등)", "국내": "시행규칙 제6조", "문단": "1.134-1.138"},
    {"주제": "거래의 실질 파악·거래 부인과 재구성", "국내": "국조법 제8조②③, 시행령 제16조", "문단": "1.139-1.148", "핵심": "1.142"},
    {"주제": "손실이 계속되는 경우", "국내": "(국조법령에 직접 규정 없음)", "문단": "1.149-1.151"},
    {"주제": "가장 합리적인 방법 선택", "국내": "국조법 제8조①, 시행령 제14조①", "문단": "2.1-2.12", "핵심": "2.2"},
    {"주제": "비교가능 제3자 가격방법", "국내": "국조법 제8조①1호, 시행령 제5조", "문단": "2.14-2.26"},
    {"주제": "재판매가격방법", "국내": "국조법 제8조①2호, 시행령 제6조", "문단": "2.27-2.44"},
    {"주제": "원가가산방법", "국내": "국조법 제8조①3호, 시행령 제7조", "문단": "2.45-2.61"},
    {"주제": "거래순이익률방법(이익지표 선택·분석 대상 당사자)", "국내": "국조법 제8조①4호, 시행령 제8조", "문단": "2.64-2.113", "핵심": "2.65"},
    {"주제": "이익분할방법", "국내": "국조법 제8조①5호, 시행령 제9조", "문단": "2.114-2.187"},
    {"주제": "비교가능성 분석 절차(아홉 단계)", "국내": "시행령 제15조①, 시행규칙 제7조", "문단": "3.1-3.8", "핵심": "3.4"},
    {"주제": "개별 거래 통합평가", "국내": "시행령 제15조②, 시행규칙 제8조", "문단": "3.9-3.12"},
    {"주제": "비교가능성 차이 조정", "국내": "시행령 제15조④", "문단": "3.47-3.54"},
    {"주제": "정상가격 범위·사분위 범위·범위 안의 지점", "국내": "시행령 제15조⑤⑥", "문단": "3.55-3.62", "핵심": "3.57"},
    {"주제": "극단값·손실 비교대상", "국내": "시행령 제15조⑦", "문단": "3.63-3.66"},
    {"주제": "다년도 자료", "국내": "시행령 제15조③, 시행규칙 제9조", "문단": "3.75-3.79"},
    {"주제": "보상조정(신고 전 납세자 조정)", "국내": "국조법 제6조", "문단": "4.38-4.39"},
    {"주제": "2차 조정(소득처분에 해당)", "국내": "국조법 제13조", "문단": "4.68-4.78"},
    {"주제": "문서화(통합기업보고서·개별기업보고서·국가별보고서)", "국내": "국조법 제16조, 시행령 제33조~제35조, 시행규칙 별지 제13호", "문단": "5.16-5.26"},
    {"주제": "무형자산(개발·향상·유지·보호·활용 기능)", "국내": "시행령 제13조", "문단": "6.32-6.72"},
    {"주제": "용역이 실제 제공됐는지(편익 기준·주주활동·중복)", "국내": "시행령 제12조⑦", "문단": "7.6-7.18"},
    {"주제": "저부가가치 용역 간이 방법(원가 + 5%)", "국내": "시행령 제12조②③, 시행규칙 제4조", "문단": "7.43-7.65", "핵심": "7.61"},
    {"주제": "원가분담약정", "국내": "국조법 제9조, 시행령 제17조", "문단": "8.1-8.53"},
    {"주제": "금전대차 — 거래 실질 파악·신용등급", "국내": "시행령 제11조①", "문단": "10.4-10.13, 10.51-10.87"},
    {"주제": "금전대차 — 정상이자율 산출(비교가능 제3자 가격·자금조달원가·신용부도스왑·경제 모형)", "국내": "시행령 제11조②, 시행규칙 제3조", "문단": "10.88-10.108"},
    {"주제": "지급보증", "국내": "시행령 제12조④⑤, 시행규칙 제5조", "문단": "10.154-10.188", "핵심": "10.170"},
]
# 평소 쓰는 말 → 지침의 영어 표현
KO_TERMS = {
    "비교가능성": ["comparability"], "기능분석": ["functional analysis"], "기능": ["functions"], "위험": ["risk"], "사분위": ["interquartile"],
    "정상가격범위": ["arm's length range"], "범위": ["range"], "중위값": ["median"], "재판매": ["resale price"], "원가가산": ["cost plus"],
    "거래순이익률": ["transactional net margin"], "이익분할": ["profit split"], "분석대상당사자": ["tested party"], "검증대상": ["tested party"],
    "다년도": ["multiple year"], "통합평가": ["evaluated together", "aggregat"], "차이조정": ["comparability adjustment"], "운전자본": ["working capital"],
    "손실": ["loss"], "저부가가치": ["low value-adding"], "용역": ["services"], "주주활동": ["shareholder activit"], "중복": ["duplicat"],
    "대여": ["loan"], "이자율": ["interest rate"], "신용등급": ["credit rating"], "지급보증": ["guarantee"], "무형자산": ["intangible"],
    "마케팅무형자산": ["marketing intangible"], "문서화": ["documentation"], "개별기업보고서": ["local file"], "통합기업보고서": ["master file"],
    "판매법인": ["distributor"], "유통업자": ["distributor"], "시장침투": ["market penetration"], "지역적이점": ["location savings"],
    "재구성": ["disregard", "recognis"], "원가분담": ["cost contribution"], "2차조정": ["secondary adjustment"], "보상조정": ["compensating adjustment"],
    "대응조정": ["corresponding adjustment"], "베리비율": ["berry ratio"], "수수료": ["fee", "commission"], "계약제조": ["contract manufactur"],
}


def _rows():
    global _ROWS
    if _ROWS is None:
        with open(_PATH, encoding="utf-8") as f:
            _ROWS = [{"문단": r[0], "쪽": r[1], "절": r[2], "본문": r[3], "_ch": int(r[0].split(".")[0]), "_no": int(r[0].split(".")[1])} for r in json.load(f)]
    return _ROWS


def _pub(r, full=True, width=320):
    out = {"문단": r["문단"], "장": f"Chapter {r['_ch']} — {CHAPTERS_KO[r['_ch']]}", "절": r["절"], "쪽": r["쪽"]}
    out["본문" if full else "발췌"] = r["본문"] if full else (r["본문"][:width] + ("…" if len(r["본문"]) > width else ""))
    return out


def _parse_ids(spec):
    ids = []
    for part in re.split(r"[,\s]+", str(spec).strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,3})(?:\s*[-~–]\s*(?:(\d{1,2})\.)?(\d{1,3}))?", part)
        if not m:
            raise ValueError(f"문단 '{part}' — '2.14' 또는 '3.55-3.62' 형식")
        ch, a = int(m.group(1)), int(m.group(2))
        b = int(m.group(4)) if m.group(4) else a
        if m.group(3) and int(m.group(3)) != ch:
            raise ValueError(f"문단 범위 '{part}' — 같은 장 안에서만")
        ids += [(ch, n) for n in range(a, b + 1)]
    return ids


def lookup(paragraph, limit=12):
    try:
        want = _parse_ids(paragraph)
    except ValueError as e:
        return {"error": str(e)}
    by = {(r["_ch"], r["_no"]): r for r in _rows()}
    found = [by[k] for k in want if k in by]
    missing = [f"{c}.{n}" for c, n in want if (c, n) not in by]
    out = {"문단 수": len(found), "결과": [_pub(r) for r in found[:limit]], "출처": CITATION, "지위": STATUS, "주의": NOTE}
    if len(found) > limit:
        out["더 있음"] = f"{len(found)}개 중 {limit}개만 실음 — 나머지: {found[limit]['문단']}부터 {found[-1]['문단']}까지 범위를 나눠 다시 조회"
    if missing:
        out["없는 문단"] = missing
    return out


def search(keyword, chapter=None, n=6):
    words = []
    for w in str(keyword).split():
        key = "".join(w.split())
        words.append([x.lower() for x in KO_TERMS.get(key, [w])])
    if not words:
        return {"error": "keyword — 찾을 말(영어, 또는 표에 있는 한국어: " + "·".join(list(KO_TERMS)[:12]) + " …)"}
    hits = []
    for r in _rows():
        if chapter and r["_ch"] != chapter:
            continue
        text = (r["절"] + " " + r["본문"]).lower()
        score = 0
        for cands in words:
            c = max(text.count(x) for x in cands)
            if c == 0:
                score = 0; break
            score += c + (3 if any(x in r["절"].lower() for x in cands) else 0)
        if score:
            hits.append((score, r))
    hits.sort(key=lambda t: (-t[0], t[1]["_ch"], t[1]["_no"]))
    out = {"전체건수": len(hits), "결과": [_pub(r, full=False) for _, r in hits[:n]], "검색어": [" | ".join(c) for c in words],
           "출처": CITATION, "지위": STATUS, "주의": NOTE, "다음 단계": "문단 전문은 paragraph='문단 번호'로 조회"}
    if not hits:
        out["안내"] = "지침은 영문 — 영어 표현으로 찾거나 crosswalk(국내 조문 대응표)에서 문단을 고른다"
    return out


def chapters():
    rows = _rows()
    out = []
    for ch in sorted(CHAPTERS):
        xs = [r for r in rows if r["_ch"] == ch]
        secs = []
        for r in xs:
            if r["절"] and (not secs or secs[-1]["절"] != r["절"]):
                secs.append({"절": r["절"], "시작 문단": r["문단"]})
        out.append({"장": ch, "제목": CHAPTERS[ch], "한국어": CHAPTERS_KO[ch], "문단": f"{xs[0]['문단']}-{xs[-1]['문단']}", "쪽": f"{xs[0]['쪽']}-{xs[-1]['쪽']}", "절 수": len(secs)})
    return {"장": out, "출처": CITATION, "지위": STATUS, "주의": NOTE}


def sections(chapter):
    xs = [r for r in _rows() if r["_ch"] == chapter]
    if not xs:
        return {"error": f"chapter={chapter!r} — 1~10"}
    secs = []
    for r in xs:
        if r["절"] and (not secs or secs[-1]["절"] != r["절"]):
            secs.append({"절": r["절"], "시작 문단": r["문단"], "쪽": r["쪽"]})
    return {"장": chapter, "제목": CHAPTERS[chapter], "한국어": CHAPTERS_KO[chapter], "절": secs, "출처": CITATION, "주의": NOTE}


def crosswalk(keyword=""):
    k = "".join(str(keyword or "").split())
    rows = [r for r in CROSSWALK if not k or k in "".join((r["주제"] + r["국내"]).split())]
    return {"대응표": rows, "전체건수": len(rows), "출처": CITATION, "지위": STATUS,
            "주의": "문단 범위는 그 주제를 다루는 곳 — 국조법령 문언과 지침 내용이 같다는 뜻이 아니다. 차이가 있으면 국조법령이 우선"}


def pointers(topic_words):
    """transfer_pricing 안내표에서 쓰는 보조 — 주제어가 든 대응표 행의 문단 범위."""
    out = []
    for r in CROSSWALK:
        if any(w in r["주제"] for w in topic_words):
            out.append({"주제": r["주제"], "문단": r["문단"], **({"핵심": r["핵심"]} if "핵심" in r else {})})
    return out
