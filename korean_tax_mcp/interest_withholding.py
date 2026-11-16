"""국외 지급 이자 원천징수 요건 안내 — 내국법인 등이 외국법인·비거주자에게 지급하는 이자(차입금 이자·채권 이자)와 이자로 잘못 처리하기 쉬운 지급보증수수료. Claude 작성(2026-11-16).

사실을 넣으면 조사 순서(소득 구분 → 국내원천 → 국내 세율 → 조약 제한세율 → 지방소득세 → 절차(실질귀속자·신청서·지급 시점·신고납부) → 세금부담 약정
→ 과소자본·정상이자율·소득 대비 과다이자)대로 요소별 판정·확인할 사실·근거·확신도를 돌려주고, 사실 → 0%·14%·20%·조약 제한세율·기타의 결정 경로를 붙인다.
세액은 계산하지 않는다(계산 MCP nonresident_withholding). 모르는 사실은 그 요소를 '확인 필요'로 두고 추정하지 않는다.

대조한 원문(조회일 2026-11-16, 조문 MCP 배포본 law_article·article_addenda·basic_rules·search_tax_rulings·get_tax_ruling):
  · 법인세법 제93조제1호 — 2016.1.25.·2026.1.2. 시행본(같은 문언). 제98조제1항 — 2018.1.1.(제3호 본문 20%·단서 채권 이자 14%), 2019.1.1.·2026.1.2.(제1호 가목 14%·나목 20%).
    제98조의6 — 2025.3.14.(제4항 경정청구), 2026.1.2.(제4항 세무서 제출 신설, 경정청구 제5항). 부칙 <제21217호, 2025.12.23.> 제1조·제13조. 제98조의7(2026.1.2.). 제73조제1항(2026.1.2.).
  · 법인세법 시행령 제137조(2026.10.1. — 지급시기 특례는 배당·기타소득·제4항 제93조제1호나목 이자뿐), 제138조의7(2016.6.23. 제6항, 2026.10.1. 전체). 법인세법 기본통칙 98-0…1~98-0…4(현행 고시본).
  · 소득세법 제119조제1호(2026.4.21.), 제156조제1항(2018.4.1.·2019.1.1.·2026.4.21.), 제156조의6(2026.4.21.). 소득세법 시행령 제45조(2026.5.22.).
  · 국제조세조정에 관한 법률 제22조제2항·제24조·제26조(2026.1.2.), 구 제14조제1항(2018.1.1.), 구 제15조의2(2019.1.1.), 부칙 <제17651호> 제2조·제6조.
  · 해석·판례(본문): 서면인터넷방문상담2팀-1656(2004.8.11.), 조심 2014광4612(2014.12.5.), 국업46017-135(2001.3.14.), 서이46017-10386(2002.3.5.), 서면인터넷방문상담2팀-1549(2005.9.27.).
    (요지): 서면법규과-881, 재국조46017-61(2000.4.20.), 국제세원관리담당관실-314(2009.6.16.), 서이46017-11059(2003.5.27.), 국총46017-133, 국심 2007서2298(2010.2.25.), 서울행정법원 2024구합56542(2025.9.11.).
royalty_withholding(2026-11-15 대조)에서 그대로 쓰는 것: 지방소득세 세율 특례 조문(2020.12.31.까지 구 국제조세조정에 관한 법률 제29조, 2021.1.1.부터 법인세법 제98조의7·소득세법 제156조의8),
  지방세법 제103조의52·제103조의18·제103조의29, 실질귀속자 증명서류(부칙 <제19193호> 제14조), 경정청구 기간·사유(_claim), 지급명세서 가산세·국제조세조정에 관한 법률 조문(_proc),
  소득세법 시행령 제207조의8, 부칙 <제21221호> 제10조, 국제조세조정에 관한 법률 제3조, 반기별 납부 '근거 없음', 국제세원관리담당관실-449(요지).
확신도: 확인함 = 원문을 읽고 확인 / 유추 = 확인한 원문에서 추론 / 근거 없음 = 찾아본 곳과 날짜를 적고 닫음(서면질의 대상) / 미확인 = 원문을 찾아보지 못함.
"""
from __future__ import annotations

import datetime as _dt

from . import royalty_withholding as R

OK, INFER, UNKNOWN, NOBASIS, NEED = R.OK, R.INFER, R.UNKNOWN, R.NOBASIS, R.NEED
AUTO = "자동 추출(조문 확인 필요)"
DATE_MIN, DATE_MAX = R.DATE_MIN, R.DATE_MAX
HO_RENUMBER_FROM = R.HO_RENUMBER_FROM      # 제98조제1항 이자: 2018.12.31.까지 제3호(단서 채권 이자 14%) → 2019.1.1.부터 제1호 가목·나목(법률 제16008호) — 세율 같음
FILING_DUTY_FROM = R.FILING_DUTY_FROM      # 제98조의6제4항 세무서 제출: 2026.1.1. 이후 제한세율 적용을 신청하는 경우부터(부칙 <제21217호> 제13조)
RATE_SPECIAL_FROM = R.RATE_SPECIAL_FROM    # 법인세법 제98조의7·소득세법 제156조의8(2021.1.1.) — 그 전 구 국제조세조정에 관한 법률 제29조
PROOF_DOC_FROM = R.PROOF_DOC_FROM          # 실질귀속자 증명서류: 2023.1.1. 이후 신청분
ICTCA_NEW_FROM = R.ICTCA_NEW_FROM          # 국제조세조정에 관한 법률 전부개정 — 2021.1.1. 이후 개시 과세연도분부터(부칙 <제17651호> 제2조)
EXCESS_INT_FROM = _dt.date(2019, 1, 1)     # 소득 대비 과다이자(구 제15조의2): 2019.1.1. 이후 개시하는 과세연도분부터(부칙 <제17651호> 제6조가 법률 제15221호 적용례를 옮김)
SEARCH_DAY = "2026-11-16"

KINDS = ("차입금 이자", "채권 이자", "지급보증수수료")
_KIND_EN = {"loan_interest": "차입금 이자", "loan interest": "차입금 이자", "interest": "차입금 이자", "bond_interest": "채권 이자", "bond interest": "채권 이자",
            "guarantee_fee": "지급보증수수료", "guarantee fee": "지급보증수수료"}
PAYERS = ("내국법인·거주자·국가 등", "외국법인·비거주자의 국내사업장", "국외 지급·국내사업장 손금 산입", "국외(국내사업장과 무관)")
_PAYER_EN = {"domestic": PAYERS[0], "korean_pe": PAYERS[1], "foreign_payer_pe_deductible": PAYERS[2], "foreign": PAYERS[3]}
_TYPE = {"법인": "법인", "corporation": "법인", "개인": "개인", "individual": "개인"}
_NET = {None: None, "없음": "없음", "none": "없음", "법인세": "법인세", "corporate_tax": "법인세", "소득세": "법인세", "income_tax": "법인세",
        "법인세+지방소득세": "법인세+지방소득세", "corporate_and_local_tax": "법인세+지방소득세", "소득세+지방소득세": "법인세+지방소득세", "income_and_local_tax": "법인세+지방소득세"}

GUARANTEE_RULINGS = [
    {"문서": "국업46017-135(2001.3.14.)", "사실": "국내사업장 없는 일본법인(주주)이 일본에서 지급보증, 내국법인은 외국계 은행 서울지점에서 외화 차입",
     "회신": "그 지급보증수수료는 국내원천소득에 해당하지 않음", "확신도": OK},
    {"문서": "서이46017-10386(2002.3.5.)", "사실": "제조업을 하는 국내사업장 없는 외국법인의 지급보증으로 국내 은행에서 차입(유사사례 재국조46017-184 인용)",
     "회신": "그 지급보증수수료는 기타소득(당시 법인세법 제93조제11호)", "확신도": OK},
    {"문서": "서면인터넷방문상담2팀-1549(2005.9.27.)", "사실": "금융업을 하며 같은 유형의 보증을 다른 회사에도 제공하는 미국 금융기관의 지급보증",
     "회신": "미국 금융기관의 사업소득 — 국내 고정사업장이 없으면 국내 과세 안 됨", "확신도": OK},
    {"문서": "서면법규과-881", "사실": "국외 신종자본증권 발행 때 국내사업장 없는 외국법인이 국외에서 투자자에게 풋옵션을 주고 받는 보증 수수료",
     "회신": "법인세법 제93조의 국내원천소득에 해당하지 않음", "확신도": "확인함(요지만)"},
]

BO_RULINGS = [
    {"문서": "서이46017-11059(2003.5.27.)", "요지": "이자·배당의 수익적소유자가 따로 있으면 그 수익적소유자의 거주지국과의 조세조약 제한세율을 적용", "확신도": "확인함(요지만)"},
    {"문서": "재국조46017-61(2000.4.20.)", "요지": "이자소득의 실질적 소유자와 형식적 소유자가 다르면 수익적 소유자를 귀속자로 보아 조약을 적용", "확신도": "확인함(요지만)"},
    {"문서": "국제세원관리담당관실-314(2009.6.16.)", "요지": "실질귀속자는 거래의 실질 내용 등을 종합해 사실판단", "확신도": "확인함(요지만)"},
    {"문서": "국총46017-133", "요지": "아일랜드 법인이 내국법인에 대한 자금 대여로 받는 소득에 실질적 처분권을 가지면 수익적 소유자", "확신도": "확인함(요지만)"},
    {"문서": "국심 2007서2298(2010.2.25.)", "요지": "아일랜드 법인을 이자소득의 수익적 소유자로 보아 조약상 비과세를 적용할 수 있는지가 쟁점이 된 사건", "확신도": "확인함(요지만)"},
    {"문서": "서울행정법원 2024구합56542(2025.9.11.)", "요지": "원고는 수익적 소유자 및 실질귀속자에 해당한다고 볼 수 없음", "확신도": "확인함(요지만)"},
]

DECISION_TREE = [
    "Q1 무엇에 대한 대가인가 — 지급보증수수료: 이자 아님(국내원천 아님·기타소득·사업소득으로 회신이 갈림, 사실에 따라 소득 구분) [기타] / "
    "국가·지방자치단체·내국법인이 발행한 채권의 이자: 국내 세율 14% / 그 밖의 차입금 이자(비영업대금 포함): 국내 세율 20% → Q2",
    "Q2 국내원천인가 — 지급자가 내국법인·거주자·국가 등 또는 외국법인·비거주자의 국내사업장(가목), 또는 국외 지급자가 국내사업장 손금에 넣는 이자(나목)면 국내원천. "
    "거주자·내국법인의 국외사업장이 직접 빌린 차입금의 이자는 제외(단서) → 아니면 0% / 맞으면 Q3",
    "Q3 수취인의 국내사업장과 실질 관련되거나 귀속되는가 — 예: 제98조(소득세법 제156조) 원천징수 대상 아님, 국내사업장 소득으로 과세 [기타] / 아니오 → Q4",
    "Q4 수취인이 실질귀속자이고, 제한세율 적용신청서를 지급 전에 받았고(받은 지 3년 이내·내용 변동 없음), 조약에 이자 조문이 있는가 — 아니오: 국내 세율(14%·20%) + 지방소득세 → 5년 내 경정청구 / 예 → Q5",
    "Q5 조약 제한세율 — 대상조세에 지방소득세(주민세)가 있으면 제한세율이 법인세+지방소득세 합계 상한, 없으면 지방소득세(원천징수세액의 10%)는 따로. "
    "특수관계로 정상 이자를 넘는 부분은 조약 이자 조문(특수관계 항)의 제한세율 밖",
    "Q6 언제 떼는가 — 지급할 때. 미지급 계상만으로는 의무 없음(국외 지급자의 나목 이자만 지급시기 의제). 원본 전입은 근거 없음(두 결과 제시). 면제받아 지급하지 않으면 의무 없음(조심 2014광4612)",
    "Q7 순액 지급 약정인가 — 과세표준 = 약정액 ÷ (1 − 원천징수세율). 지방소득세까지 지급자가 부담할 때 세율에 지방소득세를 더하는 것은 유추",
    "Q8 국외지배주주·국외특수관계인 차입인가 — 과소자본(2배), 소득 대비 과다이자(30%, 2019.1.1. 이후 개시 과세연도), 정상이자율 → 계산 MCP로 금액, 손금불산입·소득처분은 법인세 신고에서",
]


def _no_basis():
    return [
        "원본 전입(지급하지 않은 이자를 원금에 더함)을 제98조제1항의 '지급'으로 보는지: 근거 없음 — 국세법령정보시스템 해석·판례 검색('외국법인 차입금 이자 원본 전입 원천징수', "
        f"'외국법인 미지급 이자 원금 가산 원천징수 시기', '외국법인 미지급이자 원천징수 시기 지급의제', {SEARCH_DAY}), 서면질의 필요. 문언: 법인세법 제98조제1항·소득세법 제156조제1항은 '그 지급을 할 때', "
        "법인세법 시행령 제137조의 지급시기 특례는 배당·기타소득·제93조제1호나목 이자뿐. 거주자 이자의 수입시기(소득세법 시행령 제45조)는 예금 이자에만 '원본에 전입된 날'(제4호나목)을, 비영업대금의 이익에는 "
        "'약정에 의한 이자지급일'(제9호의2)을 적음 — 외국법인 원천징수 시기 조문이 아님. '전입일에 지급한 것으로 보아 원천징수'와 '실제 현금 지급(원리금 상환) 때 원천징수' 두 결과를 함께 보여 줌",
        "순액 약정에서 지급자가 지방소득세까지 부담할 때 역산 세율에 지방소득세를 더하는지: 기본통칙 98-0…2는 '원천징수세율'만 적음 — 지방소득세를 넣는 산식은 유추"
        "(royalty_withholding 조사: 국이22601-403 회신은 '국내세법에 의한 제세에는 주민세도 포함'까지만 — 계산 MCP nonresident_withholding의 payer_bears_local_tax도 '유추'로 표시)",
        "반기별 납부 승인·지정을 받은 자가 외국법인·비거주자 국내원천소득 원천징수세액을 반기별로 낼 수 있는지: 직접 답한 해석례 근거 없음(royalty_withholding 조사, 2026-11-15, 서면질의 필요) — "
        "다음 달 10일로 내면 어느 쪽으로도 기한을 지킴",
        "송금 계좌가 수취인 아닌 제3자(계열 재무법인 등) 명의라는 사실만으로 실질귀속자가 바뀌는지: 직접 답한 해석례를 찾지 못함 — 국세법령정보시스템 검색"
        f"('이자 수익적 소유자 도관 백투백 대여 실질귀속자 조세조약', {SEARCH_DAY}). 받은 이자를 넘길 법적·계약상 의무가 있는지 등 사실판단(국제세원관리담당관실-314)",
    ]


UNVERIFIED = [
    "제한세율 적용신청서 '제출된 날부터 3년 이내'의 마지막 날 계산(초일 산입 여부) — 3년이 되는 같은 날짜에 지급하면 '확인 필요'로 둠",
    "국내사업장에 귀속되는 이자에 제98조 대신 다른 원천징수 규정(법인세법 제73조 등)이 적용되는지 — 제73조제1항(2026.1.2.)은 내국법인에 지급하는 이자 규정이고 외국법인 국내사업장 언급은 읽지 못함",
    "외국법인의 국채·통화안정증권 이자 과세특례(법인세법 제93조의3) — 조회하지 않음",
    "2019~2020 과세연도의 과소자본과 소득 대비 과다이자 동시 적용 순서 조문 — 2021.1.1. 이후 개시 과세연도의 제26조만 읽음",
    "소득세법 제119조제1호의 2016~2025 시행본 문언(2026.4.21. 시행본만 대조 — 법인세법 제93조제1호는 2016·2026 같음)",
    "원 단위 절사(계산 MCP가 다룸)",
]

LIMITS = [
    "사실 판단(실질귀속자, 정상이자율, 지급보증의 성격, 원본 전입이 지급인지)은 하지 않고 입력값을 그대로 씀 — 모르는 사실은 '확인 필요'로 둠",
    "조약 세율·요건은 조약 원문 자동 추출값(treaty_withholding_rates) — 의정서·교환각서가 고쳤을 수 있어 tax_treaty로 조문을 읽어야 함. 이 도구는 조약 세율표를 따로 갖지 않음",
    "지급일로 나눈 것: 국내 세율의 호(2018.12.31.까지 제98조제1항제3호·소득세법 제156조제1항제3호, 2019.1.1.부터 제1호 가목·나목), 지방소득세 세율 특례 조문(2021.1.1.), "
    "실질귀속자 증명서류(2023.1.1. 이후 신청분), 신청서 세무서 제출 의무(2026.1.1. 이후 신청분), 경정청구 항 번호·기간",
    "과소자본·소득 대비 과다이자·정상가격 조문은 과세연도 개시일 기준인데 이 도구는 지급일이 속한 해로 나눔(사업연도가 역년이 아니면 개시일로 다시 확인)",
    "세액·과세표준·가산세·손금불산입액은 계산하지 않음 — 계산 MCP nonresident_withholding·withholding_late_payment_penalty·thin_capitalization·arm_length_range. 소득 대비 과다이자는 계산 MCP 전용 도구가 없음(korean-tax-calc-mcp 0.58.1 기준)",
    "지급보증수수료는 이자가 아니라는 것과 회신이 갈리는 지점만 안내 — 사용료·기타소득 원천징수 요건은 다루지 않음(사용료는 royalty_withholding_guide)",
    "수취인이 개인(비거주자)이면 소득세법 제119조제1호·제156조·제156조의6·제156조의8로 안내 — 개인의 거주자 판정은 residency_check",
]


def _verified():
    return ("법인세법 제93조제1호(20160125·20260102), 제98조제1항(20180101·20190101·20260102), 제98조의6(20250314·20260102)·부칙 <제21217호> 제1조·제13조, 제98조의7(20260102), 제73조제1항(20260102), "
            "법인세법 시행령 제137조(20261001)·제138조의7(20160623 제6항·20261001), 법인세법 기본통칙 98-0…1~4(현행), 소득세법 제119조제1호(20260421)·제156조제1항(20180401·20190101·20260421)·제156조의6(20260421), "
            "소득세법 시행령 제45조(20260522), 국제조세조정에 관한 법률 제22조제2항·제24조·제26조(20260102)·구 제14조제1항(20180101)·구 제15조의2(20190101)·부칙 <제17651호> 제2조·제6조 — 조회일 2026-11-16. "
            "지방소득세 특례·지방세법·실질귀속자 증명서류·경정청구·지급명세서·국제조세조정에 관한 법률 구 제4조·제7조는 royalty_withholding의 2016~2026 대조(2026-11-15)를 그대로 씀")


def _arts(d, ind):
    """지급일·수취인 → 인용 조문. 절차·특례·지방세는 사용료 도구의 대조 결과를 쓰고 이자 조문만 바꾼다."""
    A = dict(R._arts(d, ind))
    L, wh, src = ("소득세법", "제156조", "제119조") if ind else ("법인세법", "제98조", "제93조")
    A["원천 조"] = f"{L} {src}제1호"
    if d >= HO_RENUMBER_FROM:
        A["세율 호"], A["채권 목"], A["일반 목"] = f"{L} {wh}제1항제1호", f"{L} {wh}제1항제1호가목", f"{L} {wh}제1항제1호나목"
    else:
        A["세율 호"], A["채권 목"], A["일반 목"] = f"{L} {wh}제1항제3호", f"{L} {wh}제1항제3호 단서", f"{L} {wh}제1항제3호 본문"
    return A


def _treaty(country, lookup):
    """조약 조회 결과 → 이자 조문만. lookup(country) → ntis.withholding_rates(country, '이자') 형식."""
    if not country:
        return {"상태": "미입력"}
    T = {"상태": "조회 안 함", "국가": country}
    if lookup is None:
        return T
    try:
        r = lookup(country)
    except Exception as e:      # 연결 실패 등 — 추정하지 않고 상태만 남김
        T["상태"], T["오류"] = "조회 실패", str(e)[:200]
        return T
    if not isinstance(r, dict) or r.get("error"):
        if isinstance(r, dict) and "체결국" in r:
            T["상태"] = "체결국 아님"
        else:
            T["상태"], T["오류"] = "조회 실패", (str(r.get("error", ""))[:200] if isinstance(r, dict) else "")
        return T
    item = next((x for x in r.get("제한세율") or [] if x.get("소득") == "이자"), {}) or {}
    T.update({"상태": "조회함", "국가": r.get("국가", country), "발효일": r.get("발효일"), "링크": r.get("링크"), "조문": item.get("조문"),
              "세율": item.get("세율") or [], "요건": [c for c in item.get("요건·기타") or [] if c.get("구분")], "개정 문서": item.get("개정 문서 언급") or []})
    lt = r.get("지방소득세") or {}
    T["지방세 포함"], T["지방세 근거"] = lt.get("대상조세 포함"), lt.get("근거")
    T["특수관계 항"] = next((c["조항"] for c in T["요건"] if c["구분"].startswith("특수관계")), None)
    T["고정사업장 항"] = next((c["조항"] for c in T["요건"] if c["구분"].startswith("고정사업장")), None)
    T["혜택 배제"] = [c["조항"] for c in T["요건"] if c["구분"].startswith("혜택 배제")]
    return T


def _rates(cap, covered, dom, A):
    """제한세율과 국내 세율(14·20%) → 본세율·지방소득세율·합계. 지방소득세 포함 조약은 국내 세율에 지방소득세를 반영한 세율(×1.1)과 비교(제98조의7제1항제2호)."""
    tk = A["세율 키"]
    if covered is None:
        return {tk: None, "지방소득세율(%)": NEED, "합계(%)": NEED, "제한세율(%)": cap}
    if covered:
        tot = min(cap, round(dom * 1.1, 4))
        return {tk: round(tot / 1.1, 4), "지방소득세율(%)": round(tot / 11, 4), "합계(%)": tot, "지방소득세": f"제한세율 안에 포함({A['특례2']})"}
    main = min(cap, dom)
    return {tk: main, "지방소득세율(%)": round(main * 0.1, 4), "합계(%)": round(main * 1.1, 4), "지방소득세": f"제한세율과 따로({A['특례1']}, {A['지방세']})"}


def _domestic(dom, A):
    tk = A["세율 키"]
    return {tk: dom, "지방소득세율(%)": round(dom * 0.1, 4), "합계(%)": round(dom * 1.1, 4)}


def _fmt(v):
    return R._fmt(v)


def _app_status(d, app_d, before, changed):
    """신청서 상태 → (상태, 설명). 상태: 유효 | 지급 뒤 수령 | 3년 경과 | 경계일 | 변동 | 모름 | 없음."""
    if app_d is not None:
        if app_d > d:
            return "지급 뒤 수령", f"신청서를 {app_d.isoformat()}에 받아 지급일({d.isoformat()}) 뒤 — '해당 국내원천소득을 지급받기 전까지' 제출 요건을 못 갖춤"
        try:
            ann = app_d.replace(year=app_d.year + 3)
        except ValueError:          # 2월 29일
            ann = app_d.replace(year=app_d.year + 3, day=28)
        if d > ann:
            return "3년 경과", f"신청서 제출일 {app_d.isoformat()}부터 3년이 지난 뒤의 지급 — 다시 내지 않아도 되는 기간(제출된 날부터 3년 이내)이 지남, 지급 전에 새 신청서를 받아야 함"
        if d == ann:
            return "경계일", f"지급일이 신청서 제출일 {app_d.isoformat()}의 3년 뒤 같은 날 — '제출된 날부터 3년 이내'의 마지막 날 계산(초일 산입 여부)을 확인하지 못함(미확인)"
        if changed:
            return "변동", "신청서 내용에 변동이 있음 — 변동사유가 생긴 날 이후 최초로 지급받기 전까지 변동 내용을 다시 제출해야 함"
        return "유효", f"신청서를 {app_d.isoformat()}에 받아 지급 전이고 3년 이내"
    if before is True:
        return ("변동", "신청서 내용에 변동이 있음 — 변동사유가 생긴 날 이후 최초로 지급받기 전까지 변동 내용을 다시 제출해야 함") if changed else ("유효", "지급 전에 신청서를 받았다고 입력(받은 날을 주면 3년 경과도 판정)")
    if before is False:
        return "없음", "지급 전에 신청서를 받지 못했다고 입력"
    return "모름", ""


def _decide(kind, F, T, d, A, app):
    """결정 경로 → {결론, 구분, 세율…, 경로, 전제, 막힌 사실?, 가능한 결과?}"""
    path, premise, blocked = [], [], []
    tk = A["세율 키"]
    zero = {tk: 0.0, "지방소득세율(%)": 0.0, "합계(%)": 0.0}

    def out(concl, cat, **kw):
        return {"결론": concl, "구분": cat, **kw, "경로": path, "전제": premise}

    if kind is None:
        return out(f"{NEED} — 지급 대상(payment_kind: 차입금 이자·채권 이자·지급보증수수료)을 넣어야 결정 경로를 탐", NEED)
    if kind == "지급보증수수료":
        path.append("Q1 지급보증수수료 — 금전 대여의 대가가 아니라 보증의 대가: 이자(법인세법 제93조제1호·소득세법 제119조제1호)로 원천징수하지 않음")
        path.append("소득 구분은 회신이 갈림 — 국내원천소득 아님(국업46017-135), 기타소득(서이46017-10386), 사업소득(서면인터넷방문상담2팀-1549): 보증인의 업종, 보증 장소, 대주가 국내 은행인지 외국 은행 국내지점인지에 따라")
        return out("기타 — 이자 아님. 소득 구분(국내원천 아님·기타소득·사업소득)을 사실로 정한 뒤 그 소득의 원천징수 요건을 따로 확인", "기타(이자 아님)",
                   **{"가능한 결과": ["국내원천소득 아님 → 원천징수 없음(국업46017-135와 같은 사실)", "기타소득 → 국내법 기타소득 세율, 조약의 기타소득 조항 확인(서이46017-10386과 같은 사실)",
                                  "사업소득 → 수취인의 국내 고정사업장이 없으면 국내 과세 안 됨(서면인터넷방문상담2팀-1549와 같은 사실)"]})
    dom = 14.0 if kind == "채권 이자" else 20.0
    path.append(f"Q1 {kind} → 국내원천 이자소득({A['원천 조']}) — 국내 세율 {_fmt(dom)}%({A['채권 목'] if kind == '채권 이자' else A['일반 목']})")
    if kind == "채권 이자":
        premise.append("국가·지방자치단체·내국법인이 발행한 채권의 이자일 것 — 그 밖의 채권·대여금 이자는 20%")

    # Q2 국내원천
    payer, branch = F["payer"], F["branch"]
    if branch:
        path.append(f"Q2 거주자·내국법인의 국외사업장을 위해 그 국외사업장이 직접 빌린 차입금의 이자 → 국내원천에서 제외({A['원천 조']} 단서)")
        return out("0% — 국내원천 이자소득 아님(국외사업장이 직접 차용한 차입금의 이자)", "0%", **zero)
    if payer is None:
        blocked.append("지급자 구분(payer_type)")
        path.append("Q2 지급자가 누구인지 모름 — 국내원천 판정 보류")
    elif payer == PAYERS[3]:
        path.append(f"Q2 국외 지급자이고 국내사업장 손금과 무관 → {A['원천 조']} 가목·나목 어디에도 해당하지 않음")
        return out("0% — 국내원천 이자소득 아님", "0%", **zero)
    else:
        mok = "나목" if payer == PAYERS[2] else "가목"
        path.append(f"Q2 국내원천({A['원천 조']} {mok})")
    if branch is None:
        premise.append("거주자·내국법인의 국외사업장이 직접 빌린 차입금의 이자가 아닐 것(for_overseas_branch 미입력)")

    # Q3 국내사업장 귀속
    pe = F["pe"]
    if pe:
        path.append(f"Q3 수취인의 국내사업장과 실질 관련되거나 귀속 → {A['징수 조']}은 국내사업장과 실질 관련되지 않거나 귀속되지 않는 소득만 원천징수"
                    + (f"; 조약 {T['고정사업장 항']}도 제한세율 대신 사업소득 조항" if T.get("고정사업장 항") else ""))
        return out(f"기타 — {A['징수 조']} 원천징수 대상 아님(국내사업장 소득으로 과세). 다른 원천징수 규정이 적용되는지는 미확인", "기타")
    if pe is None:
        premise.append("채권이 수취인의 국내사업장과 실질 관련되지 않을 것(attributable_to_korean_pe 미입력)")

    # Q4 조약 적용 요건
    st = T.get("상태")
    if st == "미입력":
        blocked.append("수취인 거주지국(recipient_country)")
    elif st == "체결국 아님":
        path.append(f"Q4 '{T['국가']}'는 조세조약 체결국 목록에 없음 → 제한세율 없음")
        if blocked:
            return out(f"{NEED} — {', '.join(blocked)}", NEED, **{"막힌 사실": blocked, "가능한 결과": [f"국내원천이면 {_fmt(dom)}% + 지방 {_fmt(dom / 10)}%", "국내원천이 아니면 0%"]})
        return out(f"{_fmt(dom)}% + 지방소득세 {_fmt(dom / 10)}% = {_fmt(dom * 1.1)}% — 조세조약 없음({A['세율 호']})", f"{_fmt(dom)}%", **_domestic(dom, A))
    elif st != "조회함":
        blocked.append("조약 이자 조문 조회(treaty_withholding_rates·tax_treaty)")
    elif not T.get("조문"):
        blocked.append("조약 이자 조문(자동 추출에서 찾지 못함 — tax_treaty로 확인)")
    bo, (ast, adesc) = F["bo"], app
    if bo is False or ast in ("없음", "지급 뒤 수령", "3년 경과"):
        why = "실질귀속자를 확인하지 못함" if bo is False else adesc
        path.append(f"Q4 {why} → 제한세율을 적용하지 않고 국내 세율로 원천징수({A['절차 조']}제3항)")
        cp, cperiod, _ = R._claim(d, A)
        path.append(f"사후에 서류를 갖추면 경정청구({A['절차 조']}{cp}) — 기간: {cperiod}")
        if blocked and any("지급자" in b for b in blocked):
            return out(f"{NEED} — {', '.join(blocked)}", NEED, **{"막힌 사실": blocked, "가능한 결과": [f"국내원천이면 {_fmt(dom)}% + 지방 {_fmt(dom / 10)}%(제한세율 요건 못 갖춤)", "국내원천이 아니면 0%"]})
        return out(f"{_fmt(dom)}% + 지방소득세 {_fmt(dom / 10)}% = {_fmt(dom * 1.1)}% — {why}", f"{_fmt(dom)}%", **_domestic(dom, A))
    if ast in ("모름",):
        blocked.append("제한세율 적용신청서를 지급 전에 받았는지(application_before_payment 또는 application_date)")
    elif ast in ("경계일", "변동"):
        blocked.append(f"신청서 — {adesc}")
    if bo is None:
        blocked.append("수취인이 실질귀속자인지(beneficial_owner_confirmed)")
    if bo and ast == "유효":
        path.append(f"Q4 실질귀속자 확인 + 지급 전 제한세율 적용신청서(3년 이내) → 제한세율 적용({A['절차 조']}제1항, {A['절차 영']}제1항·제6항)")
    if F["pass_through"]:
        blocked.append("수익적 소유자(받은 이자를 넘길 의무가 있다고 입력 — 백투백, 사실판단)")
        premise.append("받은 이자를 다른 법인에 넘길 의무(백투백)가 있다고 입력 — 조약상 수익적 소유자인지 사실판단, 아니면 실제 귀속자의 거주지국 조약을 적용(서이46017-11059)")
    if F["remitted"]:
        premise.append("송금 계좌가 제3자 명의 — 계좌만으로 귀속이 바뀐다고 읽을 회신은 없음(근거 없음), 그 제3자가 이자를 처분하는지 확인")
    if T.get("혜택 배제"):
        premise.append(f"조약의 혜택 배제 조항({', '.join(T['혜택 배제'])})에 해당하지 않을 것")

    # Q5 세율
    covered = T.get("지방세 포함")
    vals = sorted({x.get("세율(%)") for x in T.get("세율") or [] if x.get("세율(%)") is not None})
    cap = vals[0] if len(vals) == 1 else None
    art = f"{T.get('국가', '')} 조세조약 {T.get('조문') or ''}".strip()
    if st == "조회함" and T.get("조문"):
        path.append(f"Q5 {art}: " + (f"{_fmt(cap)}%" if cap is not None else ("세율 " + ", ".join(f"{_fmt(v)}%" for v in vals) + "로 갈림" if vals else "세율 추출 못 함")) + f" [{AUTO}]")
    if F["related"]:
        premise.append("이자가 정상이자율 범위 안일 것 — 특수관계로 정상 이자를 넘는 부분은 조약 이자 조문의 제한세율 밖"
                       + (f"({art.split(' 조세조약')[0]} 조세조약 {T['특수관계 항']})" if T.get("특수관계 항") else "(조약 이자 조문의 특수관계 항 — tax_treaty로 확인)"))
    elif F["related"] is None:
        premise.append("특수관계 지급이면 정상 이자 초과분은 제한세율 밖(related_party 미입력)")
    if blocked:
        poss = []
        if cap is not None:
            rt = _rates(cap, covered, dom, A)
            poss.append(f"요건 충족 시 제한세율 {_fmt(cap)}%" + ("" if covered is None else f"(지방소득세 포함 합계 {_fmt(rt['합계(%)'])}%)"))
        poss.append(f"신청서 미수령·실질귀속자 미확인 시 {_fmt(dom)}% + 지방 {_fmt(dom / 10)}%")
        return out(f"{NEED} — {', '.join(blocked)}", NEED, **{"막힌 사실": blocked, "가능한 결과": poss})
    if cap is None:
        return out(f"{NEED} — 조약 이자 세율이 " + (", ".join(f"{_fmt(v)}%" for v in vals) + "로 갈림(수취인·채권 종류별) — 각 세율의 근거 문장을 treaty_withholding_rates로 확인" if vals else "추출되지 않음 — tax_treaty로 조문 확인"),
                   NEED, **({"가능한 결과": [f"{_fmt(v)}%" for v in vals]} if vals else {}))
    rt = _rates(cap, covered, dom, A)
    if covered:
        concl = f"{_fmt(rt['합계(%)'])}%(지방소득세 포함 상한) — {A['세목']} {_fmt(rt[tk])}% + 지방소득세 {_fmt(rt['지방소득세율(%)'])}%"
    elif covered is False:
        concl = f"{_fmt(rt[tk])}% + 지방소득세 {_fmt(rt['지방소득세율(%)'])}% = {_fmt(rt['합계(%)'])}%"
    else:
        concl = f"{_fmt(cap)}%(조약 제한세율) — 지방소득세를 제한세율에 넣는지 {NEED}(조약 대상조세 확인)"
    return out(f"{concl} — {art}", f"{_fmt(cap)}%", **rt, **{"세율 확신도": AUTO})


def _overview():
    return {"요소": ["소득 구분", "국내원천", "국내 세율", "조약 제한세율", "지방소득세", "절차 — 실질귀속자", "절차 — 제한세율 적용신청서", "절차 — 원천징수 시기",
                   "절차 — 신고·납부", "세금부담 약정", "과소자본·정상이자율·과다이자"],
            "지급일별로 달라지는 것": [
                "2018.12.31. 이전 지급: 국내 세율 근거가 법인세법 제98조제1항제3호(본문 20%, 단서 채권 이자 14%)·소득세법 제156조제1항제3호 — 2019.1.1.부터 제1호 가목(14%)·나목(20%), 세율 같음",
                "2020.12.31. 이전 지급: 지방소득세를 제한세율에 넣는지의 세율 특례가 구 국제조세조정에 관한 법률 제29조 — 2021.1.1.부터 법인세법 제98조의7·소득세법 제156조의8",
                "2023.1.1. 이후 신청분: 제한세율 적용신청서와 함께 실질귀속자임을 증명하는 서류",
                "2026.1.1. 이후 제한세율 적용 신청분: 원천징수의무자가 신청서등을 지급일이 속하는 연도의 다음 연도 2월 말일까지 세무서에 제출(법인세법 제98조의6제4항, 2025.12.23. 신설, 부칙 <제21217호> 제13조) — 경정청구는 제5항으로 이동",
                "과세연도 기준: 소득 대비 과다이자 손금불산입은 2019.1.1. 이후 개시하는 과세연도부터(구 국제조세조정에 관한 법률 제15조의2 → 2021년부터 제24조), 과소자본은 2020년까지 구 제14조·2021년부터 제22조",
            ],
            "입력": {"payment_kind": list(KINDS), "payer_type": list(PAYERS), "recipient_type": ["법인", "개인"], "net_of_tax": ["없음", "법인세", "법인세+지방소득세"]},
            "결정 트리": DECISION_TREE,
            "안내": "payment_date(2016-01-01~2026-12-31)와 사실을 넣으면 요소별 판정과 결정 경로를 돌려줍니다. 모르는 사실은 비워 두면 그 요소가 '확인 필요'로 나옵니다.",
            "근거 없음": _no_basis(), "미확인": UNVERIFIED, "한계": LIMITS, "확인 시행본": _verified()}


# ── 영문 키(lang="en") — 본문 글은 한국어 그대로(호스트 AI가 번역) ──
_EN_KEYS = {
    "지급일": "payment_date", "수취인": "recipient", "거주지국": "residence_country", "구분": "type", "지급 대상": "payment_kind", "지급자": "payer",
    "결정": "decision", "결론": "conclusion", "법인세율(%)": "corporate_tax_rate_pct", "소득세율(%)": "income_tax_rate_pct", "지방소득세율(%)": "local_income_tax_rate_pct",
    "합계(%)": "total_rate_pct", "제한세율(%)": "treaty_cap_pct", "지방소득세": "local_income_tax", "경로": "path", "전제": "premises", "막힌 사실": "blocking_facts",
    "가능한 결과": "possible_outcomes", "세율 확신도": "rate_confidence", "원천징수 시점": "withholding_timing", "순액 약정 반영": "gross_up", "과세표준": "tax_base",
    "판정": "judgments", "항목": "item", "사유": "reason", "근거": "basis", "확신도": "confidence", "확인할 사실": "facts_to_check", "결정 트리": "decision_tree",
    "다음에 부를 도구": "next_tools", "계산 다음 단계": "next_calculation", "도구": "tool", "용도": "purpose", "인자": "arguments", "근거 없음": "no_basis",
    "미확인": "unverified", "한계": "limits", "확인 시행본": "verified_versions", "기준일 주의": "as_of_warning", "조약 조회": "treaty_lookup",
    "지급보증수수료 회신": "guarantee_fee_rulings", "실질귀속자 해석": "beneficial_owner_rulings", "문서": "document", "사실": "facts", "회신": "reply", "요지": "summary",
    "요소": "elements", "지급일별로 달라지는 것": "changes_by_payment_date", "입력": "inputs", "안내": "guidance",
    "순액 기준 실효 세율(%)": "effective_rate_on_net_pct",
}
_EN_VALUES = {OK: "verified", INFER: "inferred", UNKNOWN: "unverified", NOBASIS: "no_basis", NEED: "to_confirm", AUTO: "auto-extracted (check the treaty text)",
              "확인함(요지만)": "verified (summary only)", "외국법인": "foreign corporation", "비거주자(개인)": "nonresident individual"}


def _en(o):
    if isinstance(o, dict):
        return {_EN_KEYS.get(k, k): _en(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_en(v) for v in o]
    if isinstance(o, str):
        return _EN_VALUES.get(o, o)
    return o


def guide(payment_date=None, recipient_country=None, recipient_type="법인", payment_kind=None, payer_type=None, for_overseas_branch=None,
          attributable_to_korean_pe=None, beneficial_owner_confirmed=None, application_before_payment=None, application_date=None,
          application_changed=None, related_party=None, net_of_tax=None, accrued_unpaid=None, capitalized_to_principal=None, interest_waived=None,
          remitted_to_third_party=None, pass_through_obligation=None, treaty_lookup=None, english=False):
    r = _guide(payment_date, recipient_country, recipient_type, payment_kind, payer_type, for_overseas_branch, attributable_to_korean_pe,
               beneficial_owner_confirmed, application_before_payment, application_date, application_changed, related_party, net_of_tax,
               accrued_unpaid, capitalized_to_principal, interest_waived, remitted_to_third_party, pass_through_obligation, treaty_lookup)
    return _en(r) if english and "error" not in r else r


def _guide(payment_date, recipient_country, recipient_type, payment_kind, payer_type, for_overseas_branch, attributable_to_korean_pe,
           beneficial_owner_confirmed, application_before_payment, application_date, application_changed, related_party, net_of_tax,
           accrued_unpaid, capitalized_to_principal, interest_waived, remitted_to_third_party, pass_through_obligation, treaty_lookup):
    if payment_date is None:
        return _overview()
    try:
        d = R._date(payment_date)
    except (ValueError, TypeError):
        return {"error": "payment_date는 YYYY-MM-DD"}
    if not DATE_MIN <= d <= DATE_MAX:
        return {"error": "payment_date는 2016-01-01~2026-12-31(2027.1.1. 시행 예정 개정은 반영하지 않음)"}
    if recipient_type not in _TYPE:
        return {"error": "recipient_type은 법인 | 개인"}
    ind = _TYPE[recipient_type] == "개인"
    kind = None
    if payment_kind is not None:
        kind = _KIND_EN.get(str(payment_kind).strip().lower(), payment_kind)
        if kind not in KINDS:
            return {"error": f"payment_kind 값은 {' | '.join(KINDS)}"}
    payer = None
    if payer_type is not None:
        payer = _PAYER_EN.get(str(payer_type).strip().lower(), payer_type)
        if payer not in PAYERS:
            return {"error": f"payer_type 값은 {' | '.join(PAYERS)}"}
    if net_of_tax not in _NET:
        return {"error": "net_of_tax는 없음 | 법인세 | 법인세+지방소득세"}
    net = _NET[net_of_tax]
    app_d = None
    if application_date:
        try:
            app_d = R._date(application_date)
        except (ValueError, TypeError):
            return {"error": "application_date는 YYYY-MM-DD"}

    A = _arts(d, ind)
    PR = R._proc(d, ind)
    tk, tax, who = A["세율 키"], A["세목"], ("비거주자(개인)" if ind else "외국법인")
    T = _treaty(recipient_country, treaty_lookup)
    covered = T.get("지방세 포함")
    app = _app_status(d, app_d, application_before_payment, application_changed)
    F = {"payer": payer, "branch": for_overseas_branch, "pe": attributable_to_korean_pe, "bo": beneficial_owner_confirmed, "related": related_party,
         "pass_through": pass_through_obligation, "remitted": remitted_to_third_party}
    J, check = [], []
    j = R._j
    P = A["절차 조"]

    # ── 1. 소득 구분 ──
    src_basis = f"{A['원천 조']}" + ("" if ind else ", 소득세법 제16조제1항")
    if kind is None:
        J.append(j("소득 구분", NEED, "지급 대상(payment_kind: 차입금 이자·채권 이자·지급보증수수료)을 넣어야 구분 — 지급보증수수료·보증료처럼 금전 대여의 대가가 아닌 것은 이자로 원천징수하지 않음",
                   src_basis, OK))
        check.append("계약서상 대가의 성격(대여금 이자인지, 보증·약정·주선 수수료인지), 이자율·계산 기준")
    elif kind == "지급보증수수료":
        J.append(j("소득 구분", "이자 아님 — 소득 구분 확인 필요",
                   "지급보증수수료는 금전 대여의 대가가 아니어서 국내원천 이자소득이 아님 — 이자 세율(14%·20%)이나 조약 이자 세율로 원천징수하면 틀림. "
                   "국세청 회신은 사실에 따라 갈림: " + "; ".join(f"{x['문서']} — {x['사실']}: {x['회신']}" for x in GUARANTEE_RULINGS)
                   + ". 회신 당시 조문(구 법인세법 제93조제11호 등)이라 현행 조문 대응은 law_article(법인세법, 제93조, as_of)로 확인",
                   "국업46017-135, 서이46017-10386, 서면인터넷방문상담2팀-1549, 서면법규과-881", OK))
        check.append("보증인의 업종(금융업인지), 보증을 한 장소, 대주가 국내 은행인지 외국 은행 국내지점인지, 보증인의 국내사업장 유무")
    else:
        J.append(j("소득 구분", "국내원천 이자소득(국내원천 판정 전제)" if kind == "차입금 이자" else "채권 이자",
                   f"{A['원천 조']}: 소득세법 제16조제1항의 이자소득(같은 항 제7호 제외)과 그 밖의 대금의 이자 및 신탁의 이익. "
                   + ("국가·지방자치단체·내국법인이 발행한 채권에서 생기는 이자는 14%, 그 밖의 이자(차입금 이자·비영업대금의 이익 포함)는 20%. "
                      "참고: 내국법인에 지급하는 비영업대금의 이익은 25%(법인세법 제73조제1항 단서)이나 외국법인 지급분은 제98조제1항의 이자 세율"),
                   src_basis + ", 법인세법 제73조제1항", OK))

    # ── 2. 국내원천 ──
    if kind != "지급보증수수료":
        gamok = ("가목 — 국가, 지방자치단체, 거주자, 내국법인 또는 외국법인의 국내사업장이나 비거주자의 국내사업장으로부터 받는 소득; 나목 — 외국법인·비거주자로부터 받는 소득으로서 그 지급자의 국내사업장과 실질적으로 관련하여 "
                 "그 국내사업장의 소득금액 계산 때 손금·필요경비에 넣는 것. 단서 — 거주자·내국법인의 국외사업장을 위해 그 국외사업장이 직접 차용한 차입금의 이자는 제외(2016·2026 시행본 같음)")
        if for_overseas_branch:
            J.append(j("국내원천", "국내원천소득 아님", "국외사업장이 직접 빌린 차입금의 이자 — " + gamok, f"{A['원천 조']} 단서", OK))
        elif payer is None:
            J.append(j("국내원천", NEED, "지급자 구분(payer_type)을 넣어야 판정 — " + gamok, A["원천 조"], OK))
            check.append("지급자가 내국법인·거주자인지, 외국법인 국내사업장인지, 국외 본점이 지급하고 국내사업장이 손금에 넣는지")
        elif payer == PAYERS[3]:
            J.append(j("국내원천", "국내원천소득 아님", "국외 지급자이고 국내사업장 손금과 무관 — " + gamok, A["원천 조"], OK))
        else:
            J.append(j("국내원천", "국내원천소득", ("가목" if payer != PAYERS[2] else "나목") + f"에 해당({payer}). " + gamok, A["원천 조"], OK))
            if for_overseas_branch is None:
                check.append("차입금이 거주자·내국법인의 국외사업장이 직접 빌린 것인지(단서 제외)")
        if attributable_to_korean_pe is None:
            check.append("수취인이 국내에 사업장을 두고 그 채권이 국내사업장과 실질 관련되는지")
        elif attributable_to_korean_pe:
            J.append(j("국내원천(국내사업장 귀속)", "원천징수 대상 아님",
                       f"{A['징수 조']}은 국내사업장과 실질적으로 관련되지 않거나 귀속되지 않는 소득(국내사업장 없는 자에게 지급하는 금액 포함)만 원천징수 — 국내사업장 소득으로 과세. 다른 원천징수 규정의 적용은 미확인",
                       A["징수 조"], OK))

    # ── 3. 국내 세율 ──
    if kind != "지급보증수수료":
        renum = ("" if d >= HO_RENUMBER_FROM else
                 f" 2018.12.31.까지 시행본은 제3호(제93조제1호·제2호·제8호·제10호의 소득 100분의 20, 단서 채권 이자 100분의 14)이고 2019.1.1. 시행본부터 제1호 가목·나목 — 세율은 같고 호 번호만 다름")
        J.append(j("국내 세율", "14%" if kind == "채권 이자" else ("20%" if kind else "14% 또는 20%"),
                   "국내원천 이자소득: 국가·지방자치단체·내국법인이 발행하는 채권에서 발생하는 이자소득은 지급금액의 100분의 14, 그 밖의 이자소득은 100분의 20. 지급할 때 원천징수." + renum,
                   (A["채권 목"] if kind == "채권 이자" else A["일반 목"] if kind else A["세율 호"]), OK))

    # ── 4. 조약 제한세율 ──
    st = T.get("상태")
    if kind == "지급보증수수료":
        pass
    elif st == "미입력":
        J.append(j("조약 제한세율", NEED, "수취인 거주지국(recipient_country)을 넣어야 조약을 확인", "", OK))
        check.append("수취인의 거주지국과 그 나라와의 조세조약 유무")
    elif st == "체결국 아님":
        J.append(j("조약 제한세율", "조약 없음", f"'{T['국가']}'는 조세조약 체결국 목록에서 찾지 못함 — 국내 세율 적용. 나라 이름 표기를 tax_treaty로 다시 확인", "국세법령정보시스템 조세조약 목록", AUTO))
    elif st == "조회함" and T.get("조문"):
        rates = "; ".join(f"{_fmt(x.get('세율(%)'))}% {x.get('항', '')} — {(x.get('근거') or '')[:200]}" for x in T["세율"]) or "세율을 추출하지 못함"
        conds = "; ".join(f"{c['구분']}({c['조항']})" for c in T["요건"]) or "추출된 요건 없음"
        vals = {x.get("세율(%)") for x in T["세율"]}
        J.append(j("조약 제한세율", f"{_fmt(T['세율'][0]['세율(%)'])}%(자동 추출)" if len(vals) == 1 else NEED,
                   f"{T['국가']} 조세조약 {T['조문']}(발효 {T.get('발효일')}) 자동 추출 — 세율: {rates}. 요건: {conds}. "
                   "제한세율은 수익적 소유자가 상대국 거주자일 때. 채권이 수취인의 국내 고정사업장과 실질 관련되면 제한세율 대신 사업소득 조항. "
                   + (f"특수관계 항({T['특수관계 항']}): 특수관계로 정상 이자를 넘는 부분에는 이 조문이 적용되지 않고 각국 법에 따라 과세 — 초과분은 국내 세율. " if T.get("특수관계 항") else "특수관계 초과분 항은 tax_treaty로 확인. ")
                   + (f"개정 문서 언급: {', '.join(x.strip() for x in T['개정 문서'])}. " if T.get("개정 문서") else "")
                   + f"적용 전에 tax_treaty(country='{T['국가']}', article='{T['조문']}')로 조문을 읽을 것",
                   f"{T['국가']} 조세조약 {T['조문']}", AUTO))
        if related_party and T.get("특수관계 항"):
            check.append("특수관계 차입 이자율이 정상이자율 범위인지(비교 대상 대출 견적·신용등급·만기·통화) — 초과분은 조약 제한세율 밖")
    elif st == "조회함":
        J.append(j("조약 제한세율", NEED, f"{T['국가']} 조세조약에서 이자 조문을 자동 추출하지 못함 — tax_treaty(country='{T['국가']}', keyword='이자')로 조문 확인", "", UNKNOWN))
    else:
        J.append(j("조약 제한세율", NEED, f"조약 원문을 조회하지 못함({st}{': ' + T['오류'] if T.get('오류') else ''}) — treaty_withholding_rates(country='{T['국가']}', income='이자')와 tax_treaty로 확인", "", UNKNOWN))

    # ── 5. 지방소득세 ──
    if kind != "지급보증수수료":
        lt_old = "" if d >= RATE_SPECIAL_FROM else " 2020.12.31.까지는 이 세율 특례가 구 국제조세조정에 관한 법률 제29조에 있었고 2021.1.1.부터 " + ("소득세법 제156조의8" if ind else "법인세법 제98조의7") + "(내용 같음)."
        if st == "조회함" and covered is True:
            J.append(j("지방소득세", "제한세율 안에 포함",
                       f"{T['국가']} 조세조약 대상조세에 한국 지방소득세(주민세)가 있음(자동 추출: {T.get('지방세 근거')}) — 제한세율과 '국내 세율에 원천징수 {tax}의 100분의 10을 반영한 세율' 중 낮은 세율. "
                       f"예: 제한세율 15%면 {tax} 15/11·지방소득세 1.5/11로 나눠 합계 15%. 제한세율에 지방소득세 10%를 더 얹어 떼면 상한을 넘음." + lt_old,
                       f"{A['특례2']}, {A['지방세']}", AUTO))
        elif st == "조회함" and covered is False:
            J.append(j("지방소득세", f"제한세율과 따로 — 원천징수 {tax}의 10%",
                       f"{T['국가']} 조세조약 대상조세의 한국 측 조세에 지방소득세가 없음(자동 추출: {T.get('지방세 근거')}) — 제한세율과 국내 세율 중 낮은 세율이 {tax}분이고 그 100분의 10을 지방소득세로 특별징수." + lt_old,
                       f"{A['특례1']}, {A['지방세']}", AUTO))
        else:
            J.append(j("지방소득세", NEED, f"조약의 대상조세에 한국 지방소득세(주민세)가 있는지에 따라 제한세율에 포함되는지 갈림 — tax_treaty(country, keyword='대상조세')로 확인. 조약이 없으면 원천징수 {tax}의 10%를 따로 특별징수." + lt_old,
                       f"{A['특례']}, {A['지방세']}", OK))

    # ── 6. 절차 — 실질귀속자 ──
    bo_txt = "; ".join(f"{x['문서']}: {x['요지']}" for x in BO_RULINGS)
    if kind != "지급보증수수료":
        if beneficial_owner_confirmed is None or remitted_to_third_party or pass_through_obligation:
            extra = []
            if remitted_to_third_party:
                extra.append("송금 계좌가 수취인 아닌 제3자 명의라고 입력 — 계좌가 다르다는 사실만으로 귀속이 바뀐다고 읽을 회신은 찾지 못함(근거 없음, " + SEARCH_DAY + "). "
                             "그 제3자가 이자를 자기 것으로 처분하는지, 계약상 채권자가 누구인지 확인")
            if pass_through_obligation:
                extra.append("받은 이자를 다른 법인에 그대로(또는 마진만 남기고) 넘길 의무가 있다고 입력(백투백) — 조약상 수익적 소유자인지 사실판단. 수익적 소유자가 따로 있으면 그 거주지국 조약 세율을 적용하고 "
                             "그 실질귀속자에게서 신청서등을 받아야 함")
            J.append(j("절차 — 실질귀속자", NEED if beneficial_owner_confirmed is None or pass_through_obligation else "확인 필요(송금 계좌)",
                       "수취인이 국내원천소득의 실질귀속자여야 제한세율 적용 — 판정은 하지 않음. " + " ".join(extra) + " 해석·판례: " + bo_txt,
                       f"{P}제1항·제3항, 국제조세조정에 관한 법률 제3조, " + ", ".join(x["문서"].split("(")[0] for x in BO_RULINGS[:4]), OK))
            check.append("이자 수취 계좌 명의, 대주가 받은 이자를 다른 계열사에 넘길 계약상 의무(백투백 조달·지급 지시서), 대주의 자금 원천과 위험 부담, 실질귀속자 증명 서류")
        elif beneficial_owner_confirmed:
            J.append(j("절차 — 실질귀속자", "충족", "수취인이 실질귀속자라고 입력", f"{P}제1항", OK))
        else:
            J.append(j("절차 — 실질귀속자", "제한세율 적용 불가", f"실질귀속자를 파악할 수 없으면 제한세율을 적용하지 않고 {A['징수 조']} 각 호의 금액을 원천징수 — 실제 귀속자의 거주지국 조약을 따로 검토. 해석: " + bo_txt,
                       f"{P}제3항, {A['절차 영']}제7항", OK))

    # ── 7. 절차 — 제한세율 적용신청서 ──
    proof = d >= PROOF_DOC_FROM
    docs = ("제한세율 적용신청서와 실질귀속자임을 증명하는 서류(2023.1.1. 이후 신청분부터 — " + A["부칙 증명"] + ")" if proof
            else "제한세율 적용신청서(실질귀속자임을 증명하는 서류는 2023.1.1. 이후 신청분부터 — " + A["부칙 증명"] + ")")
    rule = (f"실질귀속자가 {docs}를 '해당 국내원천소득을 지급받기 전까지' 원천징수의무자에게 제출. 제출된 날부터 3년 이내에는 다시 내지 않아도 되나 내용에 변동이 있으면 변동사유가 생긴 날 이후 최초로 지급받기 전까지 "
            "변동 내용을 제출(3년 규정은 2016.6.23.·2026.10.1. 시행본에서 같음). 원천징수의무자는 납부기한 다음 날부터 5년간 보관")
    ast, adesc = app
    if kind == "지급보증수수료":
        pass
    elif ast == "모름":
        J.append(j("절차 — 제한세율 적용신청서", NEED, rule + ". 못 받으면 국내 세율로 원천징수", f"{P}제1항·제3항, {A['절차 영']}제1항·제6항·제8항", OK))
        check.append("신청서를 받은 날과 지급일의 선후, 받은 지 3년이 지났는지, 그 뒤 수취인·조약 조항·세율 등 내용 변동이 있었는지")
    elif ast == "유효":
        J.append(j("절차 — 제한세율 적용신청서", "충족", adesc + ". " + rule, f"{P}제1항, {A['절차 영']}제1항·제6항·제8항", OK))
    elif ast == "경계일":
        J.append(j("절차 — 제한세율 적용신청서", NEED, adesc + ". " + rule, f"{A['절차 영']}제6항", UNKNOWN))
    elif ast == "변동":
        J.append(j("절차 — 제한세율 적용신청서", NEED, adesc + " — 변동 내용을 다시 받지 않았으면 제한세율 적용 요건을 못 갖춘 것으로 읽힘(유추). " + rule, f"{A['절차 영']}제6항·제7항", INFER))
        check.append("변동 내용을 담은 신청서를 그 지급 전에 다시 받았는지")
    else:
        J.append(j("절차 — 제한세율 적용신청서", f"제한세율 적용 불가 → 국내 세율",
                   adesc + f". 신청서등을 제출받지 못하면 제한세율을 적용하지 않고 {A['징수 조']} 각 호의 금액(이자 14%·20%)을 원천징수. " + rule,
                   f"{P}제3항, {A['절차 영']}제1항·제6항·제7항제1호", OK))
    if kind != "지급보증수수료":
        cp, cperiod, ccause = R._claim(d, A)
        J.append(j("절차 — 경정청구", "5년 이내 가능" if (ast in ("없음", "지급 뒤 수령", "3년 경과") or beneficial_owner_confirmed is False) else "해당 시 5년 이내",
                   f"{ccause} 실질귀속자 또는 원천징수의무자가 원천징수의무자의 납세지 관할 세무서장에게 경정청구 — 기간: {cperiod}. 세무서장은 6개월 이내 경정 또는 통지. "
                   f"국내 세율로 원천징수한 뒤 서류를 갖추면 제한세율과의 차액 환급 청구. 근거 항은 이 지급일 시행본 기준 {cp}"
                   + (" — 2026년부터 제4항은 신청서 세무서 제출 의무" if d >= FILING_DUTY_FROM else " — 2026.1.1.부터 제5항(제4항은 신청서 세무서 제출 의무)"),
                   f"{P}{cp}", OK))
        duty = f"{P}제4항(2025.12.23. 신설), {A['부칙 제출']}"
        if d >= FILING_DUTY_FROM:
            if app_d is not None and app_d < FILING_DUTY_FROM:
                J.append(j("절차 — 신청서 세무서 제출", "의무 없음으로 읽힘", f"신청서를 {app_d.isoformat()}에 받음 — 제4항은 2026.1.1. 이후 제한세율 적용을 신청하는 경우부터. 그 전에 받아 둔 신청서(3년 이내)에는 제출 의무가 없다고 읽힘", duty, INFER))
            elif ast in ("유효", "변동", "경계일"):
                J.append(j("절차 — 신청서 세무서 제출", "제출 의무" if app_d is not None else NEED,
                           f"원천징수의무자는 제출받은 신청서등을 납세지 관할 세무서장에게 지급일이 속하는 연도의 다음 연도 2월 말일({d.year + 1}년 2월 말일)까지 제출(휴업·폐업 시 그 날이 속하는 달의 다음다음 달 말일). "
                           "2026.1.1. 이후 제한세율 적용을 신청하는 경우부터" + ("" if app_d is not None else " — 신청서를 받은 날(application_date)이 2026.1.1. 전이면 의무가 없다고 읽힘(유추)"), duty, OK))
            else:
                J.append(j("절차 — 신청서 세무서 제출", "해당 시 제출", f"2026.1.1. 이후 신청서등을 받으면 지급일이 속하는 연도의 다음 연도 2월 말일({d.year + 1}년 2월 말일)까지 세무서에 제출", duty, OK))
        else:
            J.append(j("절차 — 신청서 세무서 제출", "해당 없음", f"신청서를 세무서에 내는 의무({P}제4항)는 2026.1.1. 이후 신청분부터 — 이 지급일에는 보관 의무만({A['절차 영']}제8항)", duty, OK))

    # ── 8. 절차 — 원천징수 시기 ──
    timing = None
    if kind != "지급보증수수료":
        wh = f"{A['징수 조']}('그 지급을 할 때')"
        if interest_waived:
            timing = "원천징수 의무 없음(면제)"
            J.append(j("절차 — 원천징수 시기", "원천징수 의무 성립 안 함(이자 면제)",
                       "미지급 이자를 대주가 면제해 실제로 지급하지 않았으면 원천징수 의무가 성립하지 않는다고 본 결정 — 외국법인 대주가 출자전환 합의로 미지급 이자를 면제한 사안(조심 2014광4612, 2014.12.5., 본문 확인). "
                       "면제이익의 법인세 과세는 별도", f"{wh}, 조심 2014광4612", OK))
        elif capitalized_to_principal:
            timing = "근거 없음 — 원본 전입일 또는 실제 지급일"
            J.append(j("절차 — 원천징수 시기", "근거 없음 — 두 결과",
                       _no_basis()[0] + ". 비교: 면제로 지급하지 않은 이자는 원천징수 의무 없음(조심 2014광4612) — 원본 전입은 면제가 아니라 원금으로 바뀌어 남는 점이 다름",
                       f"{wh}, 법인세법 시행령 제137조, 소득세법 시행령 제45조제4호·제9호의2", NOBASIS))
            check.append("원본 전입 약정 문언(이자 지급에 갈음하는지, 연체이자 대신인지), 전입 뒤 원금 상환 일정, 전입분을 원천징수·지급명세서에 넣었는지")
        elif accrued_unpaid:
            if payer == PAYERS[2]:
                timing = "지급시기 의제 — 지급자의 과세표준 신고기한 종료일"
                J.append(j("절차 — 원천징수 시기", "지급시기 의제(나목 이자)", "국외 지급자가 국내사업장 손금에 넣는 나목 이자는 그 지급자의 해당 사업연도(과세기간) 과세표준 신고기한 종료일(연장하면 연장 기한)을 지급시기로 봄",
                           "법인세법 시행령 제137조제4항", OK))
            else:
                timing = "실제 지급일"
                J.append(j("절차 — 원천징수 시기", "아직 원천징수 의무 없음(실제 지급 때)",
                           "원천징수는 '그 지급을 할 때'. 법인세법 시행령 제137조의 지급시기 특례는 배당소득·기타소득·제93조제1호나목 이자에만 있고 내국법인 등이 지급하는 가목 이자에는 없음(2026.10.1. 시행본). "
                           "미지급 이자로 장부에 올리기만 한 단계에서는 의무가 생기지 않음 — 비거주자 사안 회신: 국내사업장이 없는 비거주자에게 지급하는 이자의 원천징수시기는 실제 지급하는 때"
                           "(서면인터넷방문상담2팀-1656, 2004.8.11., 본문 — 유사 사례 국이46524-497 인용). 실제 지급한 날이 속하는 달의 다음 달 10일까지 납부",
                           f"{wh}, 법인세법 시행령 제137조, 서면인터넷방문상담2팀-1656", OK))
                check.append("미지급 이자를 모회사 채권과 상계·차감 정산하거나 원금에 더한 사실이 있는지")
        else:
            timing = "지급할 때"
    if kind != "지급보증수수료":
        J.append(j("절차 — 신고·납부", "다음 달 10일까지",
                   f"지급할 때 원천징수해 원천징수한 날이 속하는 달의 다음 달 10일까지 납부(지방소득세도 같은 기한에 관할 지방자치단체 — 지방세법 제103조의52제2항·제103조의29제3항 준용{'' if not ind else ', 개인은 제103조의18'}). "
                   f"반기별 납부는 근거 없음 — {_no_basis()[2]}. "
                   f"지급명세서는 지급일이 속하는 연도의 다음 연도 2월 말일({d.year + 1}년 2월 말일)까지 제출. 늦게 내면 {PR['가산세 이름']} — 금액은 계산 MCP withholding_late_payment_penalty(국세 tax='national', 지방소득세 tax='local')",
                   f"{A['징수 조']}, {A['지급명세서']}, 지방세법 제103조의52제2항, 국세기본법 제47조의5제1항", OK))

    # ── 9. 세금부담 약정 ──
    tbase = "법인세법 기본통칙 98-0…2"
    if kind == "지급보증수수료":
        pass
    elif net is None:
        J.append(j("세금부담 약정", NEED, "계약이 '국내 세법에 의한 제세를 공제한 금액을 지급'하도록 되어 있으면 과세표준 = 지급하기로 약정한 금액 ÷ (1 − 원천징수세율). 누가 한국 원천세를 부담하는지, 지방소득세까지 부담하는지 확인", tbase, OK))
        check.append("계약서의 세금 조항(gross-up·tax indemnity — 지급자가 원천세를 부담하는지, 지방소득세 포함 여부), 정산서 금액이 총액인지 순액인지")
    elif net == "없음":
        J.append(j("세금부담 약정", "해당 없음", "총액 지급(세액을 떼고 송금) — 지급금액이 과세표준", tbase, OK))
    elif net == "법인세":
        J.append(j("세금부담 약정", "과세표준 역산",
                   f"지급자가 {tax}를 부담하는 순액 약정 — 과세표준 = 약정한 금액 ÷ (1 − 원천징수세율). 예(지어낸 값): 국내 세율 20%, 약정 순액 5천만 원 → 과세표준 62,500,000원, {tax} 12,500,000원, 지방소득세 1,250,000원. "
                   "순액에 세율을 곱해 세액을 구하면 과세표준이 작게 잡혀 덜 뗌. 원 단위 절사는 계산 MCP가 다룸", tbase, OK))
    else:
        J.append(j("세금부담 약정", "과세표준 역산(지방소득세 포함 산식은 유추)",
                   f"지급자가 {tax}와 지방소득세를 모두 부담 — 세율에 지방소득세분을 더해 역산: 예(지어낸 값) 국내 세율 20%면 약정 순액 5천만 원 ÷ (1 − 0.22) → 과세표준 64,102,564원. "
                   f"통칙 98-0…2는 '원천징수세율'만 적어 지방소득세를 넣는 산식은 유추 — {_no_basis()[1]}. 지방소득세가 제한세율 안에 들어가는 조약이면 역산 세율은 합계 상한 하나(유추)",
                   tbase, INFER))

    # ── 10. 과소자본·정상이자율·과다이자 ──
    if kind != "지급보증수수료":
        newlaw = d >= ICTCA_NEW_FROM
        tc = ("국제조세조정에 관한 법률 제22조제2항: 국외지배주주로부터 차입한 금액, 국외지배주주의 특수관계인으로부터 차입한 금액, 국외지배주주의 지급보증(담보 제공 등 포함)으로 제3자에게서 차입한 금액의 합이 "
              "그 국외지배주주 출자금액의 2배를 넘으면 초과분 이자는 손금불산입, 배당 또는 기타사외유출로 처분" if newlaw else
              "구 국제조세조정에 관한 법률 제14조제1항(2020.12.31. 이전 개시 과세연도 — 2021년부터 제22조, 법률 제17651호 부칙 제2조): 국외지배주주(특수관계인 포함) 차입금과 그 지급보증에 의한 제3자 차입금이 "
              "출자금액의 2배를 넘으면 초과분 이자 손금불산입, 배당 또는 기타사외유출 처분")
        if d >= ICTCA_NEW_FROM:
            ex = ("제24조: 국외특수관계인 차입금의 순이자비용이 조정소득금액(감가상각비와 순이자비용을 빼기 전 소득금액)의 30%를 넘으면 초과분 손금불산입·기타사외유출, 금융업 등 제외, 이자율이 높은 것부터. "
                  "제26조제1항: 제22조와 제24조가 함께 적용되면 손금불산입액이 큰 쪽 하나만(같으면 제22조)")
        elif d >= EXCESS_INT_FROM:
            ex = ("구 제15조의2(2019.1.1. 이후 개시 과세연도 — 부칙 <제17651호> 제6조): 순이자비용이 조정소득금액의 100분의 30을 넘으면 초과분 손금불산입·기타사외유출, 높은 이자율부터. "
                  "과소자본과의 적용 순서 조문은 이 도구가 읽지 못함(미확인)")
        else:
            ex = "소득 대비 과다이자 손금불산입은 2019.1.1. 이후 개시하는 과세연도부터라 이 지급일이 속한 과세연도(역년 전제)에는 없음"
        tp = (f"정상이자율: 국외특수관계인과의 금전대차 이자율이 정상가격과 다르면 정상가격으로 과세조정({PR['과세조정 조']}). 조약 이자 조문의 특수관계 항 — 정상 이자 초과분은 제한세율 밖. "
              "과소자본으로 배당 처분된 금액은 배당 원천징수 대상이고 이미 이자로 원천징수한 세액은 상계조정(국제세원관리담당관실-449, 2009.8.31. — royalty_withholding 조사의 요지)")
        body = " / ".join([tc, ex, tp]) + ". 손금불산입액·처분 금액은 사업연도 종료일 기준 적수로 계산 — 계산 MCP로 넘김(계산 다음 단계)"
        basis = (("국제조세조정에 관한 법률 제22조·제24조·제26조" if newlaw else "구 국제조세조정에 관한 법률 제14조" + ("·제15조의2" if d >= EXCESS_INT_FROM else "")) + f", {PR['과세조정 조']}")
        if related_party is None:
            J.append(j("과소자본·정상이자율·과다이자", NEED, "수취인이 국외지배주주·국외특수관계인인지 넣어야 판정. 특수관계이면: " + body, basis, OK))
            check.append("대주가 국외지배주주(지분 50% 이상 등)·국외특수관계인인지, 그 지급보증으로 빌린 제3자 차입금이 있는지")
        elif related_party:
            J.append(j("과소자본·정상이자율·과다이자", "검토 대상", body, basis, OK))
            check.append("국외지배주주 출자금액(납입자본과 순자산 중 큰 쪽 등 시행령 기준), 국외지배주주·특수관계인 차입금과 그 지급보증 차입금의 적수, 차입금별 이자율, 정상이자율 비교 자료, 조정소득금액(감가상각비·순이자비용)")
        else:
            J.append(j("과소자본·정상이자율·과다이자", "해당 없음(특수관계 아님 전제)", "특수관계가 아니라고 입력 — 다만 국외지배주주의 지급보증으로 빌린 제3자 차입금도 과소자본 대상(" + ("제22조제2항제3호" if newlaw else "구 제14조제1항") + ")", basis, OK))

    # ── 결정 ──
    dec = _decide(kind, F, T, d, A, app)
    if timing:
        dec["원천징수 시점"] = timing
    if net in ("법인세", "법인세+지방소득세") and isinstance(dec.get(tk), (int, float)) and dec[tk] > 0:
        r = dec[tk] / 100
        lt = dec["지방소득세율(%)"] / 100 if isinstance(dec.get("지방소득세율(%)"), (int, float)) else 0
        if net == "법인세":
            dec["순액 약정 반영"] = {"과세표준": f"약정액 ÷ (1 − {round(r, 6):g})", "순액 기준 실효 세율(%)": round(r / (1 - r) * 100, 2), "확신도": OK}
        else:
            dec["순액 약정 반영"] = {"과세표준": f"약정액 ÷ (1 − {round(r + lt, 6):g})", "순액 기준 실효 세율(%)": round((r + lt) / (1 - r - lt) * 100, 2), "확신도": INFER}

    # ── 다음에 부를 도구 · 계산 다음 단계 ──
    cname = T.get("국가") or "상대국"
    nxt = []
    calc = []
    if kind == "지급보증수수료":
        nxt.append("search_tax_rulings(query='외국법인 지급보증수수료 국내원천소득')·get_tax_ruling으로 사실이 같은 회신을 찾아 소득 구분을 정함")
        nxt.append(f"tax_treaty(country='{cname}', keyword='기타소득')·(keyword='사업소득')로 조약 조항 확인")
        calc.append({"도구": "계산 MCP nonresident_withholding", "용도": "소득 구분을 정한 뒤 그 소득으로 계산 — '이자'로 넣으면 이자 세율로 계산되므로 넣지 않음",
                     "인자": {"income_kind": "기타 또는 사업소득 구분 후", "recipient_type": "개인" if ind else "법인", "residence_country": cname, "year": d.year}})
    else:
        args = {"income_kind": "이자", "amount": "지급액(원)", "recipient_type": "개인" if ind else "법인", "residence_country": cname, "year": d.year}
        if kind == "채권 이자":
            args["bond_interest"] = True
        if dec.get("구분", "").endswith("%") and dec["구분"] not in ("0%", "14%", "20%") and T.get("세율"):
            args["treaty_rate"] = round(float(dec["구분"].rstrip("%")) / 100, 6)
            if covered is not None:
                args["treaty_includes_local_tax"] = bool(covered)
        if net in ("법인세", "법인세+지방소득세"):
            args["net_of_tax"] = True
            if net == "법인세+지방소득세":
                args["payer_bears_local_tax"] = True
        if related_party:
            args["related_party"] = True
        calc.append({"도구": "계산 MCP nonresident_withholding", "용도": "원천징수 법인세(소득세)·지방소득세" + ("·순액 약정 역산" if net in ("법인세", "법인세+지방소득세") else ""), "인자": args})
        calc.append({"도구": "계산 MCP withholding_late_payment_penalty", "용도": "늦게·적게 낸 원천세의 납부지연가산세 — 국세 tax='national', 지방소득세 tax='local'",
                     "인자": {"unpaid_tax": "미납 세액(원)", "due": "원천징수한 날이 속하는 달의 다음 달 10일", "until": "납부일 또는 납부고지일", "accrued_on": "지급일"}})
        if related_party is not False:
            calc.append({"도구": "계산 MCP thin_capitalization", "용도": "과소자본 초과 차입금·손금불산입 이자·배당 처분분 원천징수 재계산",
                         "인자": {"equity": "국외지배주주 출자금액(원)", "borrowings": "국외지배주주 관련 차입금 적수 기준 금액(원)", "total_interest": "그 차입금 이자(원)", "year": d.year,
                                "recipient_residence_country": cname, "recipient_type": "개인" if ind else "법인"}})
            calc.append({"도구": "계산 MCP arm_length_range", "용도": "특수관계 차입 이자율이 비교 이자율 범위 안인지(정상이자율)", "인자": {"comparables": "비교 대상 이자율 목록(소수)"}})
        nxt.append(f"treaty_withholding_rates(country='{cname}', income='이자')로 세율별 근거 문장과 요건(고정사업장·특수관계·원천 규칙·혜택 배제) 확인")
        nxt.append(f"tax_treaty(country='{cname}', article='{T.get('조문') or '이자 조문'}')로 조문 전체와 개정 의정서 확인")
        if related_party is not False:
            nxt.append("transfer_pricing_guide(transaction='금전대차')로 정상이자율 산출방법 확인")
    nxt.append(f"law_article(law_name='{A['법']}', article='{'제156조' if ind else '제98조'}', as_of='{d.strftime('%Y%m%d')}')·article_addenda로 지급일 시행본과 적용례 확인")
    nxt.append("서면 메모가 필요하면 tax_memo_guide로 구성과 인용 규칙을 받은 뒤 작성하고 verify_citations로 인용 확인")

    out = {"지급일": d.isoformat(), "수취인": {"거주지국": T.get("국가") or NEED, "구분": who}, "지급 대상": kind or NEED, "지급자": payer or NEED,
           "결정": dec, "판정": J, "확인할 사실": list(dict.fromkeys(check)), "결정 트리": DECISION_TREE,
           "다음에 부를 도구": nxt, "계산 다음 단계": calc, "근거 없음": _no_basis(), "미확인": UNVERIFIED, "한계": LIMITS, "확인 시행본": _verified()}
    if kind == "지급보증수수료":
        out["지급보증수수료 회신"] = GUARANTEE_RULINGS
    if pass_through_obligation or remitted_to_third_party or beneficial_owner_confirmed is False:
        out["실질귀속자 해석"] = BO_RULINGS
    if d.year < 2026:
        out["기준일 주의"] = (f"지급일({d.isoformat()}) 시행본으로 나눈 것: 국내 세율의 호({A['세율 호']}), 지방소득세 세율 특례 조문({A['특례']}), 실질귀속자 증명서류, 신청서 세무서 제출, 경정청구 항. "
                         "기본통칙은 현행 고시본 기준. 소득세법 제119조제1호는 2026.4.21. 시행본만 대조 — 개인 수취인의 2025년 이전 지급분은 law_article(as_of)로 확인")
    if st in ("조회 실패", "조회 안 함") and T.get("국가"):
        out["조약 조회"] = f"{st}" + (f": {T['오류']}" if T.get("오류") else "") + " — 조약 부분은 '확인 필요'"
    elif T.get("링크"):
        out["조약 조회"] = f"{T['국가']} 조세조약 원문 조회함(발효 {T.get('발효일')}) — {T['링크']}"
    return out
