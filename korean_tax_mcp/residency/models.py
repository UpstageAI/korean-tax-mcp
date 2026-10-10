"""residency_check 입력·출력 pydantic 모델."""
from typing import Literal
from pydantic import BaseModel, Field


# ── 분류 상수 ──────────────────────────────────────────────────────────────
AddrJudgment = Literal["주소 있음", "주소 없음", "판단 보류"]
ResidenceJudgment = Literal["183일 이상 거소", "183일 미만 거소", "판단 보류"]
Stage1Overall = Literal["거주자", "비거주자", "판단 보류"]
DualStatus = Literal["이중거주자", "이중거주자 아님", "확인 필요"]
TreatyStage = Literal["항구적 주거", "중대한 이해관계의 중심지", "일상적 거소", "국적", "상호합의", "미적용"]
TreatyOutcome = Literal["한국 거주자", "상대국 거주자", "양국 과세(미체결국)", "판정 보류"]


# ── 입력 모델 ──────────────────────────────────────────────────────────────
class ResidencyInput(BaseModel):
    """비거주자·거주자 판정 입력 데이터.

    판정 연도, 국내 체류 정보, 국내 생활관계(가족·자산·직업), 해외 측 정보
    (국적·영주권·파견·상대국·조세조약)를 담는다.
    """

    judgment_year: int = Field(..., description="판정 대상 연도 (소득 지급 연도). 예: 2026")
    # 국내 체류
    domestic_stay_days: int | None = Field(
        None, description="직전연도(판정 연도-1) 국내 체류일수. 직접 입력한 값.", ge=0)
    entry_dates: list[str] | None = Field(
        None, description="입국 날짜 목록(YYYY-MM-DD). 제공 시 입국 다음날~출국일로 체류일수 자동 계산.")
    exit_dates: list[str] | None = Field(
        None, description="출국 날짜 목록(YYYY-MM-DD). entry_dates와 1:1 대응.")
    temporary_exit_days: int = Field(
        0, description="관광·질병 치료 등 명백히 일시적인 출국 기간 합계(일). 시행령 §4②에 따라 국내 거소로 간주.", ge=0)
    temporary_exit_reason: str = Field(
        "", description="일시적 출국 사유 (예: '관광 5일, 치료 3일').")
    # 국내 생활관계
    family_in_korea: bool = Field(
        False, description="국내에 생계를 같이하는 가족이 있는지 여부.")
    family_desc: str = Field(
        "", description="국내 가족 상황 설명 (예: '배우자·자녀 2명 서울 거주, 자녀 국내 학교 재학').")
    domestic_assets: bool = Field(
        False, description="국내 부동산·예금·사업용 자산 등 국내 소재 자산이 있는지 여부.")
    asset_desc: str = Field(
        "", description="국내 자산 요약 (예: '서울 아파트 자가(부부 공동명의), 국내 증권사 주식, 성남 상가 임대').")
    job_needs_183_days: bool = Field(
        False, description="국내 183일 이상 거주를 통상 필요로 하는 직업인지 여부 (시행령 §2③1).")
    domestic_business_activity: bool = Field(
        False, description="국내 사업·경영 활동, 국내 사업자등록, 국내 근로소득 등 국내 경제활동 유무.")
    economic_activity_desc: str = Field(
        "", description="경제활동 요약 (예: '국내 A건설 자문·임원 근로소득, 국내 C컨설팅 사업, 국내 B법인 배당').")
    # 해외 측
    foreign_nationality: bool = Field(False, description="외국 국적이 있는지 여부.")
    foreign_permanent_residency: bool = Field(
        False, description="외국 영주권 또는 그에 준하는 장기체류자격을 얻었는지 여부 (시행령 §2④).")
    foreign_nationality_desc: str = Field(
        "", description="외국 국적·영주권 상세 (예: '미국 국적, 2015년 미국 영주권 취득').")
    dispatched_by_korean_company: bool = Field(
        False, description="내국법인(100% 출자 현지법인 포함) 파견 여부 (시행령 §3 특례 적용 대상).")
    local_hire_not_dispatch: bool = Field(
        False, description="해외 현지법인에 '파견'이 아니라 퇴직 후 현지 채용된 경우 (§3 미적용, 대법원 2010두15056 구조).")
    dispatch_desc: str = Field(
        "", description="파견/현지채용 상세 (예: 'S국 현지법인에 2018년 파견' 또는 '미국 현지법인에 퇴직 후 Senior Director로 신규 채용').")
    public_official_overseas: bool = Field(
        False, description="공무원으로서 국외 근무 중인지 여부 (시행령 §3 특례 적용 대상).")
    overseas_job_desc: str = Field(
        "", description="해외 근무 형태 종합 설명.")
    # 상대국·조세조약
    treaty_country: str = Field(
        "", description="상대국 이름(한글). 예: '미국', '일본', '사우디아라비아'. 모르면 빈 문자열.")
    treaty_country_is_resident: bool = Field(
        False, description="상대국 국내법상 거주자로 취급되는지 여부.")
    treaty_country_resident_desc: str = Field(
        "", description="상대국 거주자 근거 (예: '미국 영주권자로서 미국 세법 거주지 테스트 충족').")
    permanent_home: Literal["국내만", "국외만", "양쪽", "없음"] = Field(
        "없음", description="항구적 주거 소재. 단기체류용이 아닌 계속 사용 가능한 주거 (소유·임차 무관).")
    permanent_home_desc: str = Field(
        "", description="항구적 주거 상세 (예: '국내: 서울 아파트 자가(부부 공동), 국외: S국 아파트 임차(실사용 낮음)').")
    center_of_vital_interests: Literal["국내", "국외", "판단 보류"] = Field(
        "판단 보류", description="중대한 이해관계의 중심지(판례상 양국 사업규모·소득규모·체류일수 등 비교).")
    habitual_abode: Literal["국내", "국외", "양쪽", "판단 보류"] = Field(
        "판단 보류", description="일상적 거소.")
    nationality: Literal["대한민국", "외국", "복수국적", "미입력"] = Field(
        "미입력", description=" 국적 (조약 tie-break 4단계). 미입력 시 4단계 보류 → 판정 보류.")
    # 기타
    notes: str = Field("", description="추가 참고사항.")
