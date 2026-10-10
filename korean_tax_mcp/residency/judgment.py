"""residency_check — 3단계 거주자·비거주자 판정 로직 (rules.md 기반, 외부 호출 없음).

판례 데이터는 korean_tax_mcp/data/residency/rules.md 에서 추출했다.
6-4절(찾지 못함/추정) 판례는 인용하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .models import (
    AddrJudgment, DualStatus, ResidenceJudgment, Stage1Overall,
    TreatyOutcome, TreatyStage,
)

# ─────────────────────────────────────────────────────────────────────────────
# 판례 DB  (rules.md 6-1~6-3에서 추출. 6-4는 인용 금지)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Precedent:
    case_no: str          # 예: "2015두1243"
    court: str            # 예: "대법원"
    date: str             # 선고일
    case_name: str        # 사건명
    conclusion: str       # 결론 (거주자 / 비거주자 / 법리 확인 등)
    facts: str            # 사실관계 요약
    holding: str          # 판결요지·판단근거 요약
    keywords: tuple[str, ...] = ()  # 매칭용 키워드 (사실관계 핵심어)
    misc: str = ""        # 비고 (파견 vs 현지채용 등 실무 포인트)


CASES: list[Precedent] = [
    # 6-1-1
    Precedent(
        case_no="2015두1243", court="대법원", date="2016.02.18.",
        case_name="종합소득세등부과처분취소",
        conclusion="거주자",
        facts="원고는 해외(SPC·지주회사) 실질적 경영자. 과세관청이 CFC 유보소득 배당간주 규정으로 국내 거주자로 보아 종합소득세 부과.",
        holding="국내 생계를 같이하는 가족 있음, 국내에서 그룹 전체 업무 통제·주요 의사결정, 주된 경영활동을 국내 수행 필요, 국내 경영·사회활동에 필요한 자산 국내 보유 → 국내 거주자 인정(상고기각).",
        keywords=("해외 법인", "SPC", "지주회사", "국내 경영 통제", "국내 자산", "국내 가족",
                  "경영활동 국내 수행", "CFC"),
        misc=""),
    # 6-1-2
    Precedent(
        case_no="2016두37584", court="대법원", date="2016.08.17.",
        case_name="종합소득세부과처분취소",
        conclusion="거주자 (한·사우디 조세조약 tie-break 적용 후에도 국내 거주자)",
        facts="원고는 2003년 사우디 건설회사 설립·대표이사. 국내 건설사 하도급 공사 수행. 과세관청이 2007~2010 급여 등 종합소득세 약 23억 부과. 원고는 사우디 거주자 주장.",
        holding="연평균 국내 체류 188일로 사우디 체류보다 김, 국내 주민등록 유지, 부부 주요 재산(부동산 등) 국내 소재·사우디 유형자산 거의 없음, 사우디 법인 주요 계약·의사결정 원고 국내 체류 중 이루어짐, 사우디 소득 대부분 국내 송금해 생활비 사용 → '인적·경제적 관계의 중심지'가 대한민국.",
        keywords=("해외 건설회사", "사우디", "연평균 체류 188일", "국내 주민등록", "주요 재산 국내",
                  "소득 국내 송금", "인적·경제 중심지 국내", "조세조약 tie-break"),
        misc=""),
    # 6-1-3 (이중거주자 증명책임 법리)
    Precedent(
        case_no="2014두13959", court="대법원", date="2015.02.26.",
        case_name="양도소득세등부과처분취소",
        conclusion="거주자 (법리 확인)",
        facts="공개 자료로 구체적 사실관계 확인 안 됨.",
        holding="이중거주자 해당 사실과 조세조약 적용 사실에 대한 증명책임은 이를 주장하는 납세의무자에게 있다 — 이후 다수 판례·논문에서 인용되는 핵심 법리.",
        keywords=("이중거주자", "증명책임", "납세의무자", "조세조약 적용", "증명책임 납세의무자"),
        misc=""),
    # 6-2-1 (1심 거주자→최종 비거주자 번복; 인용 시 반드시 상급심 결과 함께 언급)
    Precedent(
        case_no="2016구합69079", court="서울행정법원", date="2018년경",
        case_name="종합소득세등부과처분취소",
        conclusion="1심 거주자 → 상급심(서울고등법원 2021누72583)·대법원 최종 비거주자로 번복",
        facts="원고 S모 회장(동남아 I국 그룹 운영, 한·I국 양국 생활 근거지). 과세관청 약 1,000억 원대 부과. 원고는 I국 거주자(비거주자) 주장.",
        holding="1심: 국내 여러 기업 회장 근로소득, 국내 이자·배당·임대소득, 스스로 거주자 전제로 종소세 신고·납부, 국내 가족행사·동창회 활동 → 국내 거주자 판단. 상급심: '중대한 이해관계의 중심지'가 I국 → 비거주자, 과세처분 취소.",
        keywords=("그룹 회장", "해외 그룹 운영", "양국 생활 근거지", "국내 근로소득", "국내 자산·소득",
                  "중대한 이해관계 중심지", "상급심 번복"),
        misc="⚠️ 최종 확정은 비거주자. 인용 시 반드시 상급심 결과(비거주자) 함께 언급."),
    # 6-2-2 (법리 확인, 사실관계 미확정 → 사실관계는 인용하지 않음)
    Precedent(
        case_no="2017두59352", court="대법원", date="2017.12.07.",
        case_name="(미확인)",
        conclusion="법리 확인 (사실관계 미확정)",
        facts="사실관계 상충 정보로 신뢰도 있게 확정하지 못함.",
        holding="'중대한 이해관계의 중심지' 판단 시 양국의 사업규모, 양국에서 얻은 소득 규모, 양국 체류일수 등을 비교해야 한다 — 후속 판례(2018두60847 등)·조세심판원 결정례에서 반복 인용.",
        keywords=("중대한 이해관계 중심지", "사업규모 비교", "소득 규모 비교", "체류일수 비교"),
        misc="⚠️ 사실관계 미확정 — 판결요지만 인용, 개별 사실관계는 인용하지 않음."),
    # 6-3-1 ★ 리딩케이스
    Precedent(
        case_no="2018두60847", court="대법원", date="2019.03.14.",
        case_name="종합소득세부과처분취소",
        conclusion="비거주자 (한일조세협약 tie-break 적용 → 일본 거주자)",
        facts="원고는 프로축구 선수, 고교 졸업 후 일본 구단 장기(3년, 2012~2014) 계약. 일본 구단 제공 주거에서 생활, 국내에는 국가대표 소집 시만 일시 체류. 일본 급여 일본 신고·납부.",
        holding="원고는 한일 양국법상 이중거주자. 한일조세협약 tie-break 결과 '인적·경제적 관계가 일본에 더 밀접' → 일본 거주자. 항구적 주거 개념 명확화(소유·임차 불문, 단기체류용 아닌 계속 사용 가능한 주거). 양국 모두 항구적 주거 인정 → 다음 단계 '중대한 이해관계 중심지' 적용. 고교 졸업 후 일본만 선수 생활, 일본 구단이 가족 거주지 제공, 소득 대부분 일본 발생, 국내 체류는 국가대표 소집 시 비정기 체류에 불과.",
        keywords=("프로축구", "일본 구단", "장기 계약", "일본 주거", "일본 소득", "국내 체류 비정기",
                  "국가대표 소집", "항구적 주거", "이중거주자", "조세조약 tie-break"),
        misc="리딩케이스. '가족 국내 거주 = 국내 거주자' 경직 관행 탈피, 본인 독립적 경제활동·생활근거지 중심 판단 명확화."),
    # 6-3-2
    Precedent(
        case_no="2018두128", court="대법원", date="2018.12.13.",
        case_name="종합소득세부과처분취소",
        conclusion="비거주자 (일부 기간: 1999~2000)",
        facts="원고는 홍콩 법인·BVI 기지회사 통해 사업. 1999~2000년 귀속분: 가족과 함께 미국에 항구적 주거 두고 생활, 국내 체류는 사업 목적 일시 체류로 인정.",
        holding="한미조세협약 제3조 제2항(e) 거소 기준 적용 → 1999~2000년은 미국 거주자(한국 비거주자). 가족(배우자·자녀)과 미국 거주, 항구적 주거 미국, 국내 체류는 사업 목적 일시 체류.",
        keywords=("미국 가족 거주", "항구적 주거 미국", "사업 목적 일시 체류", "한미조세협약",
                  "비거주자 일부 기간"),
        misc="나머지 쟁점은 실질과세 원칙·부과제척기간 관련."),
    # 6-3-3
    Precedent(
        case_no="2015두52050", court="대법원", date="2016.01.28.",
        case_name="양도소득세부과처분취소",
        conclusion="비거주자 (절차법적 쟁점 중심)",
        facts="원고는 미국 영주권자, 배우자·자녀 모두 미국 거주, 국내 생계 가족 없음. 2008년 국내 법인 등기이사 재직하며 국내 활동 있었음. 국내 부동산 자산 미보유, 국내 근로소득 3개월분(약 210만 원)에 불과. 2008.1. 저축은행 주식 약 105억 원 양도 후 미신고.",
        holding="국내 체류일수 2007년 143일·2008년 187일(2개 과세기간 합산 330일 미만), 배우자·자녀 미국 거주·국내 생계 가족 없음, 국내 부동산 등 자산 미보유, 국내 근로소득 3개월분 → '1년 이상 국내 거주 필요 직업'으로 보기 어려움 → 비거주자. (절차법: 비거주자 주식양도소득은 원천징수 대상, 원천징수의무자 미징수 시 과세관청 직접 부과 불가.)",
        keywords=("미국 영주권", "가족 미국 거주", "국내 가족 없음", "국내 자산 없음", "체류 143일 187일",
                  "국내 근로소득 3개월", "183일 미만", "국내 직업 183일 불필요"),
        misc="핵심 의의는 절차법(원천징수의 완납적 효력)."),
    # 6-3-4 (파견 vs 현지채용 분기 포인트)
    Precedent(
        case_no="2010두15056", court="대법원", date="2011.04.28.",
        case_name="양도소득세경정청구거부처분취소",
        conclusion="비거주자",
        facts="원고는 2006.4.15. 미국 출국 후 계속 거주. 미국 현지법인 Senior Director로 근무, 2006.5. 후 미국 급여소득 신고·납부. 배우자와 함께 출국(국내 별도 가족 없음), 2006.5. 미국 첫째 자녀 출생. 2007.9. 영주권 신청, 2009.4. 취득.",
        holding="계속하여 1년 이상 국외 거주를 통상 필요로 하는 직업 → 비거주자(원심 유지). 2006년 출국 후 계속 거주·장기 체류 의사, 미국 현지법인 Senior Director로서 1년 이상 국외 거주 통상 필요 직업, 배우자 동반 출국·자녀 미국 출생, 미국 급여소득 신고·납부, 영주권 취득으로 계속적 국외 거주 의사 뒷받침, 국내 방문 빈도·체류기간 짧음.",
        keywords=("미국 현지법인", "Senior Director", "가족 동반 출국", "영주권", "국내 방문 빈도 낮음",
                  "1년 이상 국외 거주 필요 직업", "장기 체류 의사", "비거주자"),
        misc="⚠️ 실무 포인트: 원고가 '파견'이 아니라 소외 회사 퇴직 후 미국 현지법인에 '새로 채용'되어 §3 특례 미적용. 파견 vs 현지채용 구분 핵심 사례."),
    # 6-3-5
    Precedent(
        case_no="2014두6869", court="대법원", date="2014.08.20.",
        case_name="(미확인)",
        conclusion="거주자 (체류일수 중심)",
        facts="공개 자료로 구체적 사실관계 확인 안 됨.",
        holding="국내 체류일 2년간 540일 → 주소와 같이 밀접한 일반적 생활관계 형성 안 됐어도 국내에 상당기간 거주 장소(거소) 둔 것, 2과세기간 거쳐 1년 이상 → 구 소득세법 제1조 제1항 제1호 거주자. '주소 수준 생활관계 없어도 거소 1년 이상이면 거주자'.",
        keywords=("체류일수 540일", "2년", "2과세기간 183일", "거소 1년 이상", "주소 생활관계 불필요"),
        misc=""),
    # 6-3-6
    Precedent(
        case_no="2010두28946", court="대법원", date="2011.04.14.",
        case_name="(미확인)",
        conclusion="이중거주자 과세 (심리불속행 상고기각)",
        facts="공개 자료로 구체적 사실관계 확인 안 됨.",
        holding="원심 요지: 국외 임대소득, 국내 금융소득, 거주지 국내/국외인 경우 조세협약에 따라 인적·경제적 관계 가장 밀접한 체약국 거주자로 간주.",
        keywords=("국외 임대소득", "국내 금융소득", "조세조약", "인적·경제 관계", "이중거주자"),
        misc="심리불속행 상고기각 — 원심 요지 수준 참고."),
    # 6-3-7
    Precedent(
        case_no="2010두22719", court="대법원", date="2011.01.27.",
        case_name="(미확인)",
        conclusion="거주자 판정 기준(법리)",
        facts="공개 자료로 구체적 사실관계 확인 안 됨.",
        holding="거주자 판정은 가족·직업·소득·자산·거주 근거지 등 객관적 생활실체로 판단한다는 취지.",
        keywords=("가족", "직업", "소득", "자산", "거주 근거지", "객관적 생활실체"),
        misc="유렉스 요약 수준. 세부 사실관계 별도 확인 필요."),
]

# ─────────────────────────────────────────────────────────────────────────────
# 6-4절: 인용하지 않을 판례 (규칙으로 명시)
# ─────────────────────────────────────────────────────────────────────────────
DISABLED_CASE_NO = frozenset({"2018두71798", "2010두8171"})

# ─────────────────────────────────────────────────────────────────────────────
# 키워드 매칭 점수
# ─────────────────────────────────────────────────────────────────────────────
def _keyword_score(p: Precedent, query: str) -> int:
    """사실관계 키워드 기반 유사도 점수 (들어맞는 키워드 수)."""
    q = query.lower()
    return sum(1 for kw in p.keywords if kw.lower() in q)


def find_similar_cases(query: str, top: int = 3) -> list[Precedent]:
    """입력 사실 요약(query)에서 키워드 매칭으로 유사 판례 상위 top건을 반환.

    6-4절(찾지 못함/추정) 판례는 제외한다.
    """
    ranked: list[tuple[int, Precedent]] = []
    for p in CASES:
        if p.case_no in DISABLED_CASE_NO:
            continue
        s = _keyword_score(p, query)
        if s > 0:
            ranked.append((s, p))
    ranked.sort(key=lambda x: (-x[0], tuple(-ord(c) for c in x[1].date)))
    return [p for _, p in ranked[:top]]


# ─────────────────────────────────────────────────────────────────────────────
# 체류일수 계산 (시행령 §4①: 입국 다음날 ~ 출국일)
# ─────────────────────────────────────────────────────────────────────────────
from datetime import date, timedelta

def _parse_d(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def calc_stay_days(entry_dates: list[str] | None, exit_dates: list[str] | None,
                   temporary_exit_days: int = 0) -> int:
    """입국 다음날~출국일 규칙으로 국내 체류일수를 계산한다.

    entry_dates와 exit_dates는 1:1 대응(같은 인덱스끼리 한 번의 출입국).
    일시 출국 기간(temporary_exit_days)은 §4②에 따라 국내 거소로 간주하여 합산.
    """
    if not entry_dates:
        return 0
    total = 0
    for i, ed in enumerate(entry_dates):
        ex = exit_dates[i] if exit_dates and i < len(exit_dates) else None
        e = _parse_d(ed)
        x = _parse_d(ex) if ex else date.today()
        # 입국 다음날 ~ 출국일 (출국일 포함)
        stay = (x - (e + timedelta(days=1))).days + 1
        if stay > 0:
            total += stay
    total += temporary_exit_days
    return total


# ─────────────────────────────────────────────────────────────────────────────
# 1단계 — 소득세법상 거주자 판정
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Stage1Result:
    addr_judgment: AddrJudgment                    # 주소 판정
    addr_reason: str                               # 주소 판단 근거 서술
    addr_article: str                              # 근거 조문 (예: "시행령 제2조 ①")
    residence_judgment: ResidenceJudgment          # 거소 판정
    residence_days: int                            # 계산/입력 체류일수
    residence_reason: str
    residence_article: str
    dispatch_special: bool                         # §3 파견 특례 적용
    dispatch_reason: str
    overall: Stage1Overall
    overall_reason: str
    pending_items: list[str]                       # 판단 보류 시 추가 확인 사항


def stage1(inp: "ResidencyInput") -> Stage1Result:
    """1단계: 소득세법§1의2 + 시행령§2(①③④)·§3·§4로 거주자/비거주자/판단보류."""
    pending: list[str] = []

    # ── 1. 주소 판정 (시행령 §2) ──────────────────────────────────────────
    has_family = inp.family_in_korea
    has_assets = inp.domestic_assets
    job_183 = inp.job_needs_183_days
    biz_activity = inp.domestic_business_activity

    # §2④: 국내 주소 없는 것으로 간주 요건 (전부 충족 필요)
    # 외국 국적/영주권 + 국내 생계 가족 없음 + 직업·자산상 재입국하여 주로 국내 거주 인정 안 됨
    # → '직업 및 자산상태에 비추어 다시 입국하여 주로 국내에 거주하리라고 인정되지 않는 때'에 해당 방향
    section4_condition = (
        (inp.foreign_nationality or inp.foreign_permanent_residency)
        and not has_family
        and not job_183
        and not biz_activity
    )
    # 국내 자산이 있을 경우 §2④ 적용 여부를 더 신중히 판단해야 한다
    # (자산이 생계 기반인지 단순 보유인지, 다른 생활관계 요소와 종합 판단).
    # 자산이 있다고 해서 §2④ 적용을 자동 배제하지 않는다.
    if has_assets:
        pending.append(
            "국내 자산이 있어 시행령 §2④ '직업 및 자산상태에 비추어 다시 입국하여 주로 국내에 거주하리라고 인정되지 않는 때' "
            "해당 여부를 자산 성격·규모, 다른 생활관계 요소와 종합 판단할 필요가 있음"
        )

    if section4_condition:
        addr = "주소 없음"
        addr_reason = (
            f"외국 국적/영주권을 가지고 있고(국내 생계 가족 없고, "
            f"직업·자산상태에 비추어 다시 입국하여 주로 국내에 거주하리라고 인정되지 않음) → "
            f"소득세법 시행령 제2조 제4항에 따라 국내에 주소가 없는 것으로 본다."
        )
        addr_article = "시행령 제2조 ④"
    elif job_183:
        # §2③1 → 주소 간주
        addr = "주소 있음"
        addr_reason = (
            f"국내에 계속하여 183일 이상 거주할 것을 통상 필요로 하는 직업을 가진 때 → "
            f"소득세법 시행령 제2조 제3항 제1호에 따라 국내에 주소를 가진 것으로 본다."
        )
        addr_article = "시행령 제2조 ③ 제1호"
    elif has_family and (biz_activity or has_assets):
        # §2③2 → 주소 간주 (국내 가족 + 직업·자산상 183일 이상 거주 인정)
        addr = "주소 있음"
        addr_reason = (
            f"국내에 생계를 같이하는 가족이 있고, 그 직업 및 자산상태에 비추어 "
            f"계속하여 183일 이상 국내에 거주할 것으로 인정되는 때 → "
            f"소득세법 시행령 제2조 제3항 제2호에 따라 국내에 주소를 가진 것으로 본다."
        )
        addr_article = "시행령 제2조 ③ 제2호"
    elif has_family or has_assets or biz_activity:
        addr = "주소 있음"
        addr_reason = (
            f"국내에 생계를 같이하는 가족({('있음' if has_family else '없음')}), "
            f"국내 소재 자산({('있음' if has_assets else '없음')}), "
            f"국내 경제활동({('있음' if biz_activity else '없음')}) 등 "
            f"생활관계의 객관적 사실을 종합 → 소득세법 제1조의2 및 시행령 제2조 제1항에 따라 "
            f"국내에 주소를 둔 것으로 본다."
        )
        addr_article = "소득세법 제1조의2 ① / 시행령 제2조 ①"
    else:
        # 가족·자산·직업·경제활동 모두 국내 부재 → §2① 생활관계 종합 판단으로 주소 없음 방향
        # (§2④ 외국 국적/영주권 요건이 없어도 생활관계 객관적 사실이 모두 국내 부재인 경우)
        addr = "주소 없음"
        addr_reason = (
            "국내 생계를 같이하는 가족 없음, 국내 소재 자산 없음, "
            "183일 이상 국내 거주를 통상 필요로 하는 직업 아님, 국내 경제활동 없음 → "
            "생활관계의 객관적 사실이 모두 국내에 부재하므로 소득세법 제1조의2 및 "
            "시행령 제2조 제1항 종합 판단 시 국내에 주소를 두지 않은 것으로 본다."
        )
        addr_article = "소득세법 제1조의2 ① / 시행령 제2조 ①"

    # ── 2. 거소 판정 (시행령 §4) ──────────────────────────────────────────
    stay_days = calc_stay_days(inp.entry_dates, inp.exit_dates, inp.temporary_exit_days)
    if inp.domestic_stay_days is not None and inp.entry_dates is None:
        # 직접 입력한 체류일수 사용 (entry_dates 미제공 시)
        stay_days = inp.domestic_stay_days

    if inp.entry_dates is not None:
        stay_basis = f"출입국 날짜로 계산한 체류일수(입국 다음날~출국일, 일시 출국 {inp.temporary_exit_days}일 포함)"
    else:
        stay_basis = f"입력된 국내 체류일수 {stay_days}일"

    if stay_days >= 183:
        res = "183일 이상 거소"
        res_reason = (
            f"{stay_basis} → 183일 이상이므로 소득세법 시행령 제4조 제3항에 따라 "
            f"국내에 183일 이상 거소를 둔 것으로 본다."
        )
        res_article = "시행령 제4조 ③"
    elif stay_days == 0 and inp.domestic_stay_days is None and inp.entry_dates is None:
        res = "판단 보류"
        res_reason = "체류일수 정보 없음 — 출입국 기록 확보 후 183일 여부 확인 필요."
        res_article = "시행령 제4조 ①·③ (판단 보류)"
        pending.append("출입국 기록(직전연도 1.1.~12.31.) 확보 필요")
    else:
        res = "183일 미만 거소"
        res_reason = (
            f"{stay_basis} → 183일 미만이므로 시행령 제4조 제3항의 183일 이상 거소 요건 미충족. "
            f"2과세기간 계속 183일(시행령 §4③2호) 해당 여부도 함께 확인 필요."
        )
        res_article = "시행령 제4조 ①·③ 제1호 (2과세기간 계속 183일 §4③2호 별도 확인)"
        if inp.entry_dates is None and inp.domestic_stay_days is None:
            pending.append("2과세기간(예: 직전전연도+직전연도) 합산 체류일수 확인 필요 (시행령 §4③2호)")

    # ── 3. 파견 특례 (시행령 §3) ──────────────────────────────────────────
    dispatch = False
    dispatch_reason = ""
    if inp.dispatched_by_korean_company and not inp.local_hire_not_dispatch:
        dispatch = True
        dispatch_reason = (
            "내국법인(100% 출자 해외현지법인 포함) 등에 파견된 임직원 또는 "
            "국외에서 근무하는 공무원은 소득세법 시행령 제3조에 따라 거주자로 본다. "
            "※ 파견 vs 현지채용 구별: 퇴직 후 현지 신규 채용된 경우는 §3 미적용 "
            "(대법원 2010두15056 참조)."
        )
    elif inp.local_hire_not_dispatch:
        dispatch_reason = (
            "해외 현지법인에 '파견'이 아니라 퇴직 후 현지 채용된 경우 → "
            "시행령 제3조 특례 미적용(대법원 2010두15056)."
        )
        pending.append("파견 vs 현지채용 구분 확인 — 현지법인 설립 경위, 고용 승계 여부 등")

    if inp.public_official_overseas:
        dispatch = True
        dispatch_reason = (
            "공무원은 소득세법 시행령 제3조에 따라 거주자로 본다."
        )

    # ── 4. 1단계 종합 ─────────────────────────────────────────────────────
    if dispatch:
        overall = "거주자"
        overall_reason = (
            f"파견 특례(시행령 제3조) 적용 대상 → 국내 주소·거소 판단과 관계없이 거주자로 본다. "
            f"({dispatch_reason})"
        )
    elif addr == "주소 있음" or res == "183일 이상 거소":
        overall = "거주자"
        parts = []
        if addr == "주소 있음":
            parts.append(addr_reason)
        if res == "183일 이상 거소":
            parts.append(res_reason)
        overall_reason = " / ".join(parts) + (
            " → 소득세법 제1조의2 제1항에 따라 거주자에 해당한다."
        )
    elif addr == "주소 없음" and res == "183일 미만 거소":
        overall = "비거주자"
        overall_reason = (
            f"국내 주소 없고(시행령 제2조 {addr_article.split()[-1] if addr_article else '④'}), "
            f"183일 이상 거소도 아님 → 거주자가 아니므로 비거주자에 해당한다."
        )
    else:
        overall = "판단 보류"
        overall_reason = (
            f"주소 판단({addr}), 거소 판단({res})이 모두 명확하지 않아 "
            f"소득세법 제1조의2상 거주자 여부를 단정할 수 없다."
        )
        if addr == "판단 보류":
            pending.append("주소 판정을 위한 생활관계 추가 자료 필요")
        if res == "판단 보류":
            pending.append("체류일수 확정 필요")

    return Stage1Result(
        addr_judgment=addr, addr_reason=addr_reason, addr_article=addr_article,
        residence_judgment=res, residence_days=stay_days, residence_reason=res_reason,
        residence_article=res_article,
        dispatch_special=dispatch, dispatch_reason=dispatch_reason,
        overall=overall, overall_reason=overall_reason, pending_items=pending,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2단계 — 이중거주자 여부
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Stage2Result:
    dual: DualStatus
    reason: str
    burden_of_proof: str          # 증명책임 안내


def stage2(inp: "ResidencyInput", s1: Stage1Result) -> Stage2Result:
    """2단계: 국내 거주자인데 상대국에서도 거주자인 경우 이중거주자."""
    if s1.overall != "거주자":
        return Stage2Result(
            dual="이중거주자 아님",
            reason="1단계에서 비거주자로 판정되었으므로 이중거주자 검토 대상이 아니다.",
            burden_of_proof="(해당 없음)",
        )

    if not inp.treaty_country:
        # 상대국 이름이 없어도 상대국 거주자 여부가 명시되어 있으면 이중거주자 검토 대상으로 본다
        # (미체결국 시나리오: 상대국 이름은 없으나 상대국 거주자임이 분명한 경우 등)
        if inp.treaty_country_is_resident:
            reason = (
                "국내 세법상 거주자에 해당하고(1단계), 상대국 측에서도 거주자로 취급됨이 확인되나 "
                "상대국 이름이 명시되지 않아 조세조약 체결 여부를 확인할 수 없다. "
                f"상대국 국내법상 거주자 근거로 기재된 내용: {inp.treaty_country_resident_desc}. "
                "조세조약 체결국인지 확인되기 전까지는 이중거주자 해소가 안 되어 양국 과세 가능성이 있다."
            )
            return Stage2Result(dual="이중거주자", reason=reason,
                                burden_of_proof="납세의무자에게 증명책임 있음 (대법원 2006두3964, 2014두13959)")
        return Stage2Result(
            dual="확인 필요",
            reason="상대국 정보가 없어 이중거주자 해당 여부를 판단할 수 없다. 상대국 이름과 상대국 거주자 여부를 입력하면 2단계 판단을 진행한다.",
            burden_of_proof="(상대국 정보 필요)",
        )

    if not inp.treaty_country_is_resident:
        return Stage2Result(
            dual="이중거주자 아님",
            reason=(f"국내 거주자에 해당하나, 상대국({inp.treaty_country}) 국내법상 거주자로 취급되지 않으므로 "
                    f"이중거주자에 해당하지 않는다."),
            burden_of_proof="(해당 없음)",
        )

    # 국내 거주자 + 상대국 거주자 → 이중거주자
    reason = (
        f"국내 세법상 거주자에 해당하고(1단계), 상대국({inp.treaty_country}) 국내법상으로도 "
        f"거주자로 취급되므로({inp.treaty_country_resident_desc}) 이중거주자에 해당한다. "
        f"어느 국가의 거주자로 취급될지는 조세조약상 거주지국 결정 기준(Tie-break)에 따라 결정되며, "
        f"이중거주자 해당 사실과 조세조약 적용 사실에 대한 **증명책임은 이를 주장하는 납세의무자**에게 있다 "
        f"(대법원 2006두3964, 대법원 2014두13959)."
    )
    return Stage2Result(dual="이중거주자", reason=reason,
                        burden_of_proof="납세의무자에게 증명책임 있음 (대법원 2006두3964, 2014두13959)")


# ─────────────────────────────────────────────────────────────────────────────
# 3단계 — 조세조약 tie-break (이중거주자인 경우)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Stage3Result:
    treaty_concluded: bool
    tie_break_applied: bool
    decisive_stage: TreatyStage | None   # 결정된 단계
    outcome: TreatyOutcome
    reason: str
    article_note: str                  # 조문 번호/근거 안내
    pending_items: list[str]


def stage3(inp: "ResidencyInput", s1: Stage1Result, s2: Stage2Result,
           treaty_info: dict | None) -> Stage3Result:
    """3단계: 이중거주자면 조약 tie-break로 최종 거주지국 결정."""
    pending: list[str] = []

    if s2.dual != "이중거주자":
        if s2.dual == "이중거주자 아님":
            return Stage3Result(
                treaty_concluded=bool(inp.treaty_country),
                tie_break_applied=False,
                decisive_stage=None,
                outcome="한국 거주자" if s1.overall == "거주자" else "상대국 거주자",
                reason="이중거주자가 아니므로 조세조약 tie-break 적용 없이 1단계 판정이 최종 거주지국 결정이다.",
                article_note="(tie-break 미적용)",
                pending_items=[],
            )
        # 확인 필요 → 3단계도 보류
        return Stage3Result(
            treaty_concluded=bool(inp.treaty_country),
            tie_break_applied=False,
            decisive_stage=None,
            outcome="판정 보류",
            reason="이중거주자 여부가 확인 필요 상태이므로 tie-break 적용을 진행하는 대신 2단계 확인 후 다시 판단한다.",
            article_note="(상대국 정보 필요)",
            pending_items=["상대국 이름·상대국 거주자 여부 입력 필요"],
        )

    country = inp.treaty_country
    # treaty_info의 source가 실제 NTIS 조회 성공인 경우에만 체결국으로 본다.
    # treaty_info가 없으면 treaty_country가 있어도 체결 여부 미확인 → 미체결국 처리.
    # (network 실패도 미체결국과 동일하게 tie-break 미적용. 체결국 목록은 tax_treaty로만 확인 가능.)
    treaty_concluded = bool(treaty_info and treaty_info.get("source") == "tax_treaty (실제 NTIS 조회)")

    if not treaty_concluded:
        return Stage3Result(
            treaty_concluded=False,
            tie_break_applied=False,
            decisive_stage=None,
            outcome="양국 과세(미체결국)",
            reason=(f"상대국이 주어지지 않아 조세조약 체결 여부를 확인할 수 없다. "
                    f"상대국 이름(treaty_country)을 입력하면 treaty_treaty 도구로 체결 여부를 확인한다. "
                    f"체결국이 아니면 이중거주자 지위를 해소할 수 없어 양국에서 각각 자국법에 따라 과세된다."),
            article_note="(조세조약 미체결 — treaty_country 미입력)",
            pending_items=["상대국 이름(treaty_country) 입력 필요"],
        )

    # tie-break 순차 적용
    ph = inp.permanent_home
    covi = inp.center_of_vital_interests
    hab = inp.habitual_abode
    nat = inp.nationality

    applied_stage: TreatyStage | None = None
    outcome: TreatyOutcome = "판정 보류"
    reason_lines: list[str] = []

    # ① 항구적 주거
    if ph == "국내만":
        applied_stage = "항구적 주거"
        outcome = "한국 거주자"
        reason_lines.append(
            "① 항구적 주거: 국내에만 항구적 주거가 있으므로(한국 거주자) 이 단계에서 결정.")
    elif ph == "국외만":
        applied_stage = "항구적 주거"
        outcome = "상대국 거주자"
        reason_lines.append(
            f"① 항구적 주거: 국외({country})에만 항구적 주거가 있으므로(상대국 거주자) 이 단계에서 결정.")
    elif ph == "양쪽":
        reason_lines.append(
            "① 항구적 주거: 국내와 국외 양쪽에 항구적 주거가 있어 이 단계로는 결정되지 않음 → 다음 단계로.")
    elif ph == "없음":
        reason_lines.append(
            "① 항구적 주거: 어느 쪽에도 항구적 주거가 없다고 볼 여지가 있어 이 단계로는 결정되지 않음 → 다음 단계로.")
    else:
        reason_lines.append("① 항구적 주거: 정보 부족으로 판단 보류.")

    # ② 중대한 이해관계의 중심지
    if applied_stage is None:
        covi_map = {
            "국내": ("한국 거주자", "② 중대한 이해관계의 중심지: 가족·사회관계·직업·재산관리장소 등을 종합할 때 국내 쪽으로 인적·경제적 관계가 더 밀접하다고 볼 수 있어 이 단계에서 결정."),
            "국외": (f"상대국({country}) 거주자",
                     f"② 중대한 이해관계의 중심지: 양 체약국 중 {country} 쪽으로 인적·경제적 관계가 더 밀접하다고 볼 수 있어 이 단계에서 결정."),
            "판단 보류": (None, "② 중대한 이해관계의 중심지: 양국 사업규모·소득규모·체류일수 등 비교 자료 부족하여 판단 보류 → 다음 단계로."),
        }
        nxt, txt = covi_map.get(covi, (None, "② 중대한 이해관계의 중심지: 정보 부족으로 판단 보류."))
        if nxt:
            applied_stage = "중대한 이해관계의 중심지"
            outcome = nxt
        reason_lines.append(txt)
        if covi == "판단 보류":
            pending.append("양국의 사업규모·소득규모·체류일수 비교 자료 확보 후 중대한 이해관계 중심지 재판정 필요")

    # ③ 일상적 거소
    if applied_stage is None:
        hab_map = {
            "국내": ("한국 거주자", "③ 일상적 거소: 국내가 일상적 거소이므로 이 단계에서 결정."),
            "국외": (f"상대국({country}) 거주자", f"③ 일상적 거소: {country}가 일상적 거소이므로 이 단계에서 결정."),
            "양쪽": (None, "③ 일상적 거소: 국내·국외 양쪽 → 이 단계로는 결정되지 않음 → 다음 단계로."),
            "판단 보류": (None, "③ 일상적 거소: 정보 부족 → 다음 단계로."),
        }
        nxt, txt = hab_map.get(hab, (None, "③ 일상적 거소: 정보 부족."))
        if nxt:
            applied_stage = "일상적 거소"
            outcome = nxt
        reason_lines.append(txt)
        if hab == "판단 보류":
            pending.append("일상적 거소 국내/국외 판단을 위한 체류 패턴 상세 확인 필요")

    # ④ 국적
    if applied_stage is None:
        nat_map = {
            "대한민국": ("한국 거주자", "④ 국적: 대한민국 국적이므로 이 단계에서 한국 거주자로 결정."),
            "외국": (f"상대국({country}) 거주자", f"④ 국적: 외국({country} 추정) 국적이므로 이 단계에서 상대국 거주자로 결정."),
            "복수국적": (None, "④ 국적: 복수국적 → 이 단계로는 결정되지 않음 → 다음 단계로."),
            "미입력": (None, "④ 국적: 국적 미입력 → 이 단계로 결정되지 않으며, 국적 확인 필요 → 다음 단계로."),
        }
        nxt, txt = nat_map.get(nat, (None, "④ 국적: 정보 부족."))
        if nxt:
            applied_stage = "국적"
            outcome = nxt
        else:
            # nationality 미입력 등 4단계에서 결정되지 않은 경우: 4단계까지 적용, 결정 단계는 '국적'
            # ⑤ 상호합의로 넘어가지 않고 여기서 판정 보류
            applied_stage = "국적"
            outcome = "판정 보류"
        reason_lines.append(txt)
        if nat == "미입력":
            pending.append("국적 확인 필요 (조세조약 tie-break 4단계 적용을 위해 국적 정보 필요)")
            pending.append("상호합의(조약 제3조②(e)) 검토 — 전 단계에서 결정되지 않은 경우")

    # ⑤ 상호합의
    if applied_stage is None:
        applied_stage = "상호합의"
        outcome = "판정 보류"
        reason_lines.append(
            "⑤ 상호합의: 앞의 모든 기준으로도 결정되지 않은 경우 상호합의 절차에 따른다. "
            "상호합의 결과는 아직 확정되지 않았으므로 현재 단계에서는 판정이 보류된다.")

    treaty_note = ""
    if treaty_info and "article_text" in treaty_info:
        at = treaty_info["article_text"]
        treaty_note = (
            f"조세조약({country}) 거주지국 결정 조항 원문(발췌): {at[:300]}{'…' if len(at) > 300 else ''}"
        )
    elif country:
        treaty_note = f"조세조약({country}) 거주자 조문·tie-break 원문 확인이 필요하다 (tax_treaty 도구로 조회)."

    return Stage3Result(
        treaty_concluded=treaty_concluded,
        tie_break_applied=True,
        decisive_stage=applied_stage,
        outcome=outcome,
        reason=" ".join(reason_lines),
        article_note=treaty_note,
        pending_items=pending,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 최종 조립
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResidencyResult:
    input_digest: str            # 입력 요약
    stage1: Stage1Result
    stage2: Stage2Result
    stage3: Stage3Result
    final_outcome: Literal["거주자", "비거주자", "이중거주자(조세조약 적용 필요)", "판정 보류", "양국 과세(미체결국)"]
    final_reason: str
    legal_principle: str        # 법리 명시 (92누11695 등)
    similar_cases: list[Precedent]
    conflicting_points: list[str]   # 판단이 갈리는 지점·추가 확인 사항
    treaty_info: dict | None


def run_check(inp: "ResidencyInput", treaty_info: dict | None = None) -> ResidencyResult:
    """residency_check 전체 실행: 1→2→3단계 + 판례 매칭 + 법리 명시."""
    s1 = stage1(inp)
    s2 = stage2(inp, s1)
    s3 = stage3(inp, s1, s2, treaty_info)

    # 판례 매칭 (입력 사실 종합 키워드 + 체크 항목·판정 결과 번역)
    def _kw() -> list[str]:
        k: list[str] = []
        # 체크 항목 → 판례 keywords 어휘
        if inp.family_in_korea:
            k.append("국내 가족")
        elif not inp.family_in_korea and inp.family_desc:
            k.append("가족 국외")
        if inp.domestic_assets:
            k.append("국내 자산")
        if inp.domestic_business_activity:
            k.append("경영활동 국내 수행")
        if inp.foreign_permanent_residency:
            k.append("영주권")
        if inp.dispatched_by_korean_company and not inp.local_hire_not_dispatch:
            k.append("해외 파견")
        elif inp.public_official_overseas:
            k.append("해외 파견")
        # 판정 결과 → 판례 keywords 어휘
        if s1.residence_judgment == "183일 이상 거소":
            k.append("183일 이상 거소")
        elif s1.residence_judgment == "183일 미만 거소":
            k.append("183일 미만")
        if s2.dual == "이중거주자":
            k.extend(["이중거주자", "조세조약 tie-break", "증명책임"])
        if s3.decisive_stage:
            k.append(s3.decisive_stage)
        return k

    query = " ".join([
        *(_kw()),
        str(inp.family_desc or ""),
        str(inp.asset_desc or ""),
        str(inp.economic_activity_desc or ""),
        str(inp.overseas_job_desc or ""),
        str(inp.foreign_nationality_desc or ""),
        f"체류 {s1.residence_days}일",
        str(inp.treaty_country or ""),
    ])
    # 6-4절 제외하고 상위 3건
    cases = find_similar_cases(query, top=3)

    # 법리 명시
    legal_principle = (
        "국내에서의 생활관계로만 판단한다(국내외 생활관계 비교가 아님). "
        "근거: 대법원 1993.05.27. 선고 92누11695 판결. "
        "주소는 국내에서 생계를 같이하는 가족 및 국내에 소재하는 자산의 유무 등 생활관계의 객관적 사실에 따라 판정한다(소득세법 시행령 제2조 제1항)."
    )

    # 판단이 갈리는 지점·추가 확인 사항
    conflicting: list[str] = []
    conflicting.extend(s1.pending_items)
    conflicting.extend(s3.pending_items)
    if s2.dual == "이중거주자":
        conflicting.append(
            "이중거주자에 해당하므로 조세조약 tie-break 결과에 따라 최종 거주지국이 달라질 수 있다. "
            "항구적 주거·양쪽 인정 여부, 중대한 이해관계의 중심지 비교 자료가 결론을 바꿀 수 있는 지점이다."
        )
    if s1.overall == "거주자" and s1.addr_judgment == "주소 있음" and s1.residence_judgment == "183일 미만 거소":
        conflicting.append(
            "주소는 인정되나 183일 이상 거소는 아닌 경우 — 주소 판정 근거가 §2③(각 호)에 해당하는지, "
            "또는 §2① 종합 판단인지에 따라 근거 조문 표현이 달라질 수 있다."
        )

    # 최종 결과
    # "판정 보류"는 1단계 사실이 모자랄 때(모두 비어 있음)와 3단계 tie-break가 끝까지 '판단 보류'일 때만.
    # 3단계 결과가 나왔으면 그 결과를 최종 판정에 그대로 반영한다.
    if s3.outcome == "양국 과세(미체결국)":
        final_outcome: Literal["거주자", "비거주자", "이중거주자(조세조약 적용 필요)", "판정 보류", "양국 과세(미체결국)"]
        final_outcome = "양국 과세(미체결국)"
        final_reason = (
            f"1단계: {s1.overall}(주소 {s1.addr_judgment}, 거소 {s1.residence_judgment}). "
            f"2단계: 이중거주자. "
            f"3단계: {inp.treaty_country}는 조세조약 미체결(또는 체결 미확인)국으로 tie-break 적용 불가 → "
            f"양국 과세. 국내법상 한국 거주자로서 한국 과세, 상대국법상 상대국 거주자로서 상대국 과세."
        )
    elif s1.overall == "거주자" and s3.outcome == "한국 거주자":
        final_outcome = "거주자"
        if s1.dispatch_special:
            final_reason = (
                f"1단계 거주자(소득세법 시행령 제3조(해외현지법인 등의 임직원 등에 대한 거주자 판정)에 따라 "
                f"국내 주소·거소 판단과 관계없이 거주자로 봄 — {s1.dispatch_reason}). "
                f"상대국 거주자로 이중거주자에 해당하나, 조세조약 tie-break 결과 {s3.decisive_stage} 단계에서 "
                f"한국 거주자로 결정 → 최종 거주자."
            )
        else:
            final_reason = (
                f"1단계 거주자(주소 {s1.addr_judgment}, 거소 {s1.residence_judgment}). "
                f"상대국 거주자로 이중거주자에 해당하나, 조세조약 tie-break 결과 {s3.decisive_stage} 단계에서 "
                f"한국 거주자로 결정 → 최종 거주자."
            )
    elif s1.overall == "거주자" and s3.outcome.startswith("상대국"):
        # tie-break 결과 상대국 거주자 → 조약상 비거주자로 취급 (3-3).
        # s3.outcome 예: "상대국(미국) 거주자"
        final_outcome = "비거주자"
        final_reason = (
            f"1단계 국내 거주자이나, 상대국과 이중거주자에 해당하고 조세조약 tie-break 결과 "
            f"{s3.decisive_stage} 단계에서 상대국 거주자로 결정 → 조약상 비거주자로 취급."
            f" 근거: {s3.article_note}"
        )
    elif s1.overall == "비거주자":
        final_outcome = "비거주자"
        final_reason = (
            f"1단계 비거주자(주소 {s1.addr_judgment}, 거소 {s1.residence_judgment}) → "
            f"조세조약 검토 없이 비거주자로 판정."
        )
    elif s1.overall == "거주자" and s2.dual in ("이중거주자 아님", "확인 필요"):
        # 1단계 거주자이고 이중거주자가 아니거나 확인 필요 → 조약 검토 없이 거주자로 최종 판정.
        # 상대국도 거주자로 볼 여지가 있으면 treaty_country 입력 안내 추가 (3-1, 3-2)
        note = ""
        if s2.dual == "확인 필요":
            note = " 상대국도 거주자로 보면 treaty_country 입력 후 조약 검토를 진행하세요."
        final_outcome = "거주자"
        final_reason = (
            f"1단계 거주자(주소 {s1.addr_judgment}, 거소 {s1.residence_judgment}). "
            f"상대국 정보가 없거나 상대국이 거주자가 아니므로 이중거주자에 해당하지 않아 "
            f"조세조약 tie-break 없이 국내법상 거주자로 판정.{note}"
        )
    elif s1.overall == "판단 보류":
        # 1단계 자체가 판단 보류 → 최종 판정 보류 (3단계는 의미 없음)
        final_outcome = "판정 보류"
        final_reason = (
            f"1단계에서 주소·거소·파견 등 사실관계가 충분하지 않아 거주자 여부를 단정할 수 없다. "
            f"추가 자료 확보 후 재검토 필요."
        )
    elif s3.outcome == "판정 보류":
        # 1단계 거주자 + 2단계 이중거주자 → 3단계 tie-break가 보류된 경우만 판정 보류
        final_outcome = "판정 보류"
        final_reason = (
            f"1단계 거주자, 이중거주자에 해당하나 조세조약 tie-break 결과가 보류되어 "
            f"최종 거주지국을 결정할 수 없다. 추가 자료 확보 후 재검토 필요."
        )
    else:
        final_outcome = "판정 보류"
        final_reason = f"종합 판정 보류: 1단계 {s1.overall}, 2단계 {s2.dual}, 3단계 {s3.outcome}."

    return ResidencyResult(
        input_digest=input_digest(inp),
        stage1=s1, stage2=s2, stage3=s3,
        final_outcome=final_outcome, final_reason=final_reason,
        legal_principle=legal_principle,
        similar_cases=cases,
        conflicting_points=conflicting,
        treaty_info=treaty_info,
    )


def input_digest(inp: "ResidencyInput") -> str:
    """입력 요약을 한 문단으로 반환."""
    lines = [
        f"판정 연도: {inp.judgment_year} (직전연도 {inp.judgment_year - 1}년 출입국 기준)",
        f"국내 체류일수: {inp.domestic_stay_days or calc_stay_days(inp.entry_dates, inp.exit_dates, inp.temporary_exit_days)}일"
        + (f" (입국 다음날~출국일 계산, 일시 출국 {inp.temporary_exit_days}일 포함)"
           if inp.entry_dates else ""),
        f"국내 생계 가족: {'있음' if inp.family_in_korea else '없음'}" + (f" — {inp.family_desc}" if inp.family_desc else ""),
        f"국내 자산: {'있음' if inp.domestic_assets else '없음'}" + (f" — {inp.asset_desc}" if inp.asset_desc else ""),
        f"183일 거주 필요 직업: {'예' if inp.job_needs_183_days else '아니오'}",
        f"국내 경제활동: {'있음' if inp.domestic_business_activity else '없음'}" + (f" — {inp.economic_activity_desc}" if inp.economic_activity_desc else ""),
        f"외국 국적/영주권: {'있음' if (inp.foreign_nationality or inp.foreign_permanent_residency) else '없음'}"
        + (f" — {inp.foreign_nationality_desc}" if inp.foreign_nationality_desc else ""),
        f"파견/현지채용: " + (
            "내국법인 파견(§3 적용 대상)" if inp.dispatched_by_korean_company and not inp.local_hire_not_dispatch
            else "현지 채용(§3 미적용)" if inp.local_hire_not_dispatch
            else "해당 없음"),
        f"상대국: '{inp.treaty_country}'" + (f", 상대국 거주자: {'예' if inp.treaty_country_is_resident else '아니오'}"
                                               if inp.treaty_country else ""),
        f"항구적 주거: {inp.permanent_home}",
        f"중대한 이해관계 중심지: {inp.center_of_vital_interests}",
        f"일상적 거소: {inp.habitual_abode}",
        f"국적: {inp.nationality}",
    ]
    if inp.notes:
        lines.append(f"기타: {inp.notes}")
    return "\n".join(lines)
