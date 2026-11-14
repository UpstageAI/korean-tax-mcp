"""가업상속공제 요건 안내(상속세 및 증여세법 제18조의2, 2022년까지 제18조제2항제1호, 시행령 제15조) — 상속개시일별 요건과 사실관계 대조. Claude 작성(2026-11-14).

세액을 계산하지 않는다. 상속개시일에 적용되는 문언(개정 부칙의 적용례·경과조치 반영)에 사실을 대어 요건별 판정과 근거 조문을 돌려준다.
조문 대조(국세법령정보시스템 연혁본): 법 2016.1.1.(법률 제13557호)·2017.1.1.(제14388호)·2018.1.1.(제15224호)·2019.1.1.(제16102호)·2020.1.1.(제16846호)·
2021.1.1.(제17654호)·2022.1.1.(제18591호)·2023.1.1.(제19195호)·2024.1.1.(제19932호)·2025.3.14.(제20777호)·2026.1.1.(제21219호) 시행본의 제18조·제18조의2·제72조의2와 부칙,
시행령 2016.2.5.(대통령령 제26960호)·2017.2.7.(제27835호)·2018.2.13.(제28638호)·2019.2.12.(제29533호) 시행본의 제15조와 부칙.
상속개시일별로 달라진 것(법):
  · 중견기업 매출액 기준: 2016년 '규모 확대로 중소기업에서 벗어난 기업'(직전 사업연도 매출액 3천억원 이상·상호출자제한기업집단 제외), 2017~2021년 직전 3개 연도 평균 3천억원 미만, 2022년 4천억원 미만, 2023년부터 5천억원 미만
  · 공제 한도: 2017년까지 200억원(15년 이상 300억원, 20년 이상 500억원), 2018~2022년 경영기간 10년 이상 200억원·20년 이상 300억원·30년 이상 500억원, 2023년부터 300억원·400억원·600억원
  · 중견기업 상속인의 상속세 납부능력 요건(가업상속재산 외 재산이 상속세액의 2배 초과면 배제): 2019.1.1. 이후 상속개시분
  · 사후관리 기간: 2019년까지 상속개시분 10년, 2020~2022년 7년, 2023년부터 5년. 2023.1.1. 당시 사후관리 중인 상속인에게도 5년 기준 적용(법률 제19195호 부칙 제7조제2항)
  · 가업용 자산 처분 기준: 2022년까지 20%(상속개시일부터 5년 이내 10%) 이상, 2023년부터 40% 이상. 2019.1.1. 이후 처분분부터 처분 비율만큼만 추징
  · 고용 유지: 2019년까지 각 연도 정규직 수 80%·전체 평균 100%(중견기업 120%), 2020~2022년 정규직 수와 총급여액 둘 다 미달해야 추징, 2023년부터 5년간 평균 90%(정규직 수·총급여액 둘 다 미달)
  · 조세포탈·회계부정 형 확정 시 공제 배제·추징: 2020.1.1. 이후 행위·상속개시분
  · 납부유예(제72조의2): 2023.1.1. 이후 상속개시분, 중소기업 가업으로 가업상속공제를 받지 않은 경우"""

from datetime import date, timedelta

DATE_MIN, DATE_MAX = date(2016, 1, 1), date(2026, 12, 31)
SIZES = ("중소기업", "중견기업", "일반")
EVENTS = ("가업용 자산 처분", "가업 미종사", "지분 감소", "고용 미달", "조세포탈·회계부정 형 확정")
_L, _D = "상속세 및 증여세법", "상속세 및 증여세법 시행령"
EOK = 100_000_000

_RULINGS = [   # 국세법령정보시스템 문서 본문(요지·회신)을 확인한 것만
    {"문서번호": "기준-2021-법령해석재산-0014(2022.1.11.)·기준-2020-법규재산-0216(2022.1.7.)", "주제": "지분 보유",
     "내용": "기획재정부 조세법령운용과-10(2022.1.5.) 인용 — 피상속인이 직접 10년 이상 보유하지 않은 주식도 다른 요건을 갖추면 가업상속공제 대상. 이 해석은 예규 생산일 이후 결정·경정분부터 적용(전문 확인)"},
    {"문서번호": "조심-2020-서-8289(2021.12.6.)", "주제": "지분 보유",
     "내용": "'피상속인이 상속재산인 해당 주식을 10년 이상 계속 보유할 것'은 가업상속공제 요건이 아님(대법원 2021.8.26. 선고 2021두38741 판결과 같은 뜻, 요지 확인)"},
    {"문서번호": "법규과-1088(2014.10.14.)", "주제": "지분 보유",
     "내용": "피상속인 등의 지분율 판정 때 상법상 의결권 없는 우선주는 발행주식총수와 보유 주식수에서 빼고, 가업상속재산에도 해당하지 않음(전문 확인)"},
    {"문서번호": "서면-2016-상속증여-5107(2016.9.30.)", "주제": "대표이사",
     "내용": "상속개시일 현재 피상속인이 대표이사가 아니어도 영위기간의 50% 이상, 소급 10년 중 5년 이상, 10년 이상(승계 요건) 중 하나의 기간을 재직했으면 적용(요지 확인)"},
    {"문서번호": "서면-2017-법령해석재산-1278(2018.10.16.)", "주제": "상속인",
     "내용": "2016.2.5. 이후 상속개시분부터 1개 가업을 공동상속받아도 적용. 대표이사 취임 요건에는 공동·각자 대표이사, 상속개시 전 대표이사 취임도 포함(전문 확인)"},
    {"문서번호": "서면-2019-법규재산-2914(2022.5.31.)", "주제": "대표이사",
     "내용": "유한책임회사 출자지분도 '주식등'에 포함되고 업무집행자를 대표이사로 봄(전문 확인)"},
    {"문서번호": "서면-2022-법규재산-0547(2023.3.15.)", "주제": "사후관리",
     "내용": "상속개시 전부터 정규직이던 가업상속인은 기준고용인원에는 포함, 기준총급여액에서는 제외. 대표자가 된 날이 속하는 달부터 정규직근로자 수에서 빠짐(전문 확인)"},
    {"문서번호": "서면-2021-법규재산-6258(2023.9.5.)", "주제": "사후관리",
     "내용": "기획재정부 재산세제과-1039(2023.9.4.) 인용 — 사후관리 위반으로 추징세액을 신고할 때 연부연납 적용 가능(전문 확인)"},
]


def _d(s):
    if isinstance(s, date):
        return s
    y, m, d = (int(x) for x in str(s).strip().replace(".", "-").split("-")[:3])
    return date(y, m, d)


def _add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:      # 2월 29일
        return d.replace(year=d.year + n, day=28)


def _years_between(a, b):
    return (b - a).days / 365.2425


def era(d):
    """상속개시일 → 법 문언 구간."""
    if d < date(2017, 1, 1):
        return "2016"
    if d < date(2018, 1, 1):
        return "2017"
    if d < date(2022, 1, 1):
        return "2018-2021"
    if d < date(2023, 1, 1):
        return "2022"
    return "2023-"


def article(d):
    """가업상속공제 조문 위치(2022.12.31. 개정으로 제18조의2 신설)."""
    return f"{_L} 제18조의2제1항" if d >= date(2023, 1, 1) else f"{_L} 제18조제2항제1호"


def revenue_rule(d):
    """(기준 설명, 매출액 상한(원) | None, 근거). 중견기업(2016년은 규모 확대 기업) 매출액 기준."""
    a = article(d)
    if d < date(2017, 1, 1):
        return ("규모 확대 등으로 중소기업에 해당하지 않게 된 기업 — 상속이 개시되는 사업연도의 직전 사업연도 매출액이 3천억원 이상인 기업과 상호출자제한기업집단 내 기업은 제외",
                3000 * EOK, f"{a}(법률 제13557호, 2016.1.1. 시행)")
    if d < date(2022, 1, 1):
        return ("중견기업 — 상속이 개시되는 과세기간·사업연도의 직전 3개 과세기간·사업연도 매출액 평균이 3천억원 이상이면 제외", 3000 * EOK,
                f"{a}(2017.1.1. 시행 법률 제14388호부터)")
    if d < date(2023, 1, 1):
        return ("중견기업 — 직전 3개 과세기간·사업연도 매출액 평균이 4천억원 이상이면 제외", 4000 * EOK, f"{a}(법률 제18591호, 2022.1.1. 시행)")
    return ("중견기업 — 직전 3개 과세기간·사업연도 매출액 평균이 5천억원 이상이면 제외", 5000 * EOK, f"{a}(법률 제19195호, 2023.1.1. 시행)")


def limit_table(d):
    """[(경영기간 하한(년), 한도(원))], 근거."""
    a = article(d)
    if d < date(2018, 1, 1):
        return [(10, 200 * EOK), (15, 300 * EOK), (20, 500 * EOK)], f"{a} 단서(2017년까지 상속개시분)"
    if d < date(2023, 1, 1):
        return [(10, 200 * EOK), (20, 300 * EOK), (30, 500 * EOK)], f"{a} 가목~다목(법률 제15224호, 2018.1.1. 이후 상속개시분)"
    return [(10, 300 * EOK), (20, 400 * EOK), (30, 600 * EOK)], f"{a} 제1호~제3호(법률 제19195호, 2023.1.1. 이후 상속개시분)"


def deduction_limit(d, years_managed):
    """피상속인 계속 경영기간에 따른 공제 한도(원). 10년 미만이면 None(가업 아님)."""
    if years_managed is None or years_managed < 10:
        return None
    table, _ = limit_table(d)
    return [lim for lo, lim in table if years_managed >= lo][-1]


def decree_note(d):
    """시행령 제15조 원문 대조 범위 밖이면 붙일 주의 문구."""
    if d < date(2020, 1, 1):
        return ""
    if d < date(2023, 1, 1):
        return " — 2019.2.12. 시행본 문언 기준(2020년 이후 시행령 개정 여부 미확인)"
    return " — 2023.1.1. 이후 상속개시분은 시행령 원문 미확인"


def shareholding_rule(d):
    """(지분율(비상장), 지분율(상장), 보유기간 문언, 근거). 시행령 제15조제3항제1호가목."""
    if d < date(2017, 2, 7):
        return 50, 30, None, f"{_D} 제15조제3항제1호가목(대통령령 제26960호 시행본) — '계속하여 보유'만 있고 기간 문언 없음"
    if d < date(2023, 1, 1):
        return 50, 30, 10, f"{_D} 제15조제3항제1호가목(대통령령 제27835호, 2017.2.7. 이후 상속개시분부터 '10년 이상 계속하여 보유')" + decree_note(d)
    return None, None, 10, f"{_D} 제15조제3항제1호가목 — 2023.1.1. 이후 상속개시분의 지분율은 미확인(2023.2.28. 개정 시행령 원문을 받지 못함)"


def post_rules(regime):
    """사후관리 구간별 규칙. regime: '10년' | '7년' | '5년'."""
    if regime == "5년":
        return {"기간": 5, "자산": "가업용 자산의 40% 이상 처분", "자산 기준": (40, 40),
                "고용": "상속개시일부터 5년간 정규직 근로자 수 전체 평균과 총급여액 전체 평균이 모두 상속개시 직전 2개 연도 평균의 90%에 미달",
                "근거": f"{_L} 제18조의2제5항"}
    if regime == "7년":
        return {"기간": 7, "자산": "가업용 자산의 20%(상속개시일부터 5년 이내는 10%) 이상 처분", "자산 기준": (10, 20),
                "고용": "각 연도 정규직 근로자 수 평균이 기준고용인원의 80% 미달이면서 총급여액도 기준총급여액의 80% 미달, 또는 7년간 정규직 수 전체 평균과 총급여액 전체 평균이 모두 기준에 미달",
                "근거": f"{_L} 제18조제6항(법률 제16846호, 2020.1.1. 이후 상속개시분)"}
    return {"기간": 10, "자산": "가업용 자산의 20%(상속개시일부터 5년 이내는 10%) 이상 처분", "자산 기준": (10, 20),
            "고용": "각 연도 정규직 근로자 수 평균이 기준고용인원의 80% 미달, 또는 10년간 정규직 수 전체 평균이 기준고용인원의 100%(중견기업 120%) 미달",
            "근거": f"{_L} 제18조제6항(2016년 시행본은 제5항)"}


def regime_for(d, assessed_before_2023=None, today=None):
    """상속개시일과 2023.1.1. 전 추징 여부 → (적용 사후관리 구간, 설명)."""
    if d >= date(2023, 1, 1):
        return "5년", "2023.1.1. 이후 상속개시분 — 제18조의2제5항(5년)"
    old = "10년" if d < date(2020, 1, 1) else "7년"
    old_why = ("2020.1.1. 전 상속개시분은 사후관리 기간 10년(법률 제16846호 부칙 제11조)" if old == "10년"
               else "2020~2022년 상속개시분은 7년(법률 제16846호)")
    if assessed_before_2023:
        return old, old_why + ". 2023.1.1. 전에 이미 상속세·이자상당액이 부과되어 종전 규정 적용(법률 제19195호 부칙 제7조제2항제3호)"
    note = (old_why + ". 다만 2023.1.1. 당시 사후관리 기간이 지나지 않았고 그 전에 추징되지 않았으면 제18조의2제5항(5년, 자산 40%, 고용 90%)을 적용"
            "(법률 제19195호 부칙 제7조제2항). 종전 고용 기준(제18조제6항제1호마목)이 더 유리하면 그 기준 적용(같은 조 제3항)")
    return "5년", note


def _verdict(ok):
    return {True: "충족", False: "미충족", None: "확인 필요"}[ok]


def guide(inheritance_date=None, company_size=None, avg_revenue=None, prior_year_revenue=None, cross_shareholding_group=None, listed=None,
          years_managed=None, decedent_share_pct=None, share_holding_years=None, ceo_ratio=None, ceo_years=None, ceo_years_in_last10=None,
          heir_succeeded_ceo=None, decedent_age_at_death=None, unavoidable_death=None, heir_age=None, heir_years_in_business=None,
          heir_officer_by_deadline=None, heir_ceo_within_2y=None, spouse_qualifies=None, business_property_value=None,
          other_property_exceeds_twice_tax=None, assessed_before_2023=None, post_events=None):
    문제 = []
    if inheritance_date is None:
        return {"상속개시일별 변화": [x.strip(" ·") for x in __doc__.split("상속개시일별로 달라진 것(법):")[1].strip().split("\n")],
                "입력": "inheritance_date(2016-01-01~2026-12-31)를 주면 그 상속개시일의 요건과 사실관계 판정",
                "기업 구분": list(SIZES), "사후관리 사유": list(EVENTS), "확인 시행본": _CHECKED}
    try:
        d = _d(inheritance_date)
    except Exception:
        return {"error": "입력 확인 필요", "문제": [f"inheritance_date={inheritance_date!r} — YYYY-MM-DD"]}
    if not DATE_MIN <= d <= DATE_MAX:
        문제.append(f"inheritance_date={inheritance_date!r} — 2016-01-01~2026-12-31")
    if company_size is not None and company_size not in SIZES:
        문제.append(f"company_size={company_size!r} — {' | '.join(SIZES)}")
    for i, e in enumerate(post_events or []):
        if not isinstance(e, dict) or e.get("event") not in EVENTS:
            문제.append(f"post_events[{i}].event — {' | '.join(EVENTS)}")
        elif e.get("date"):
            try:
                _d(e["date"])
            except Exception:
                문제.append(f"post_events[{i}].date — YYYY-MM-DD")
    for k, v in (("avg_revenue", avg_revenue), ("prior_year_revenue", prior_year_revenue), ("years_managed", years_managed), ("decedent_share_pct", decedent_share_pct),
                 ("share_holding_years", share_holding_years), ("heir_age", heir_age), ("business_property_value", business_property_value)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            문제.append(f"{k}={v!r} — 0 이상의 숫자")
    if 문제:
        return {"error": "입력 확인 필요", "문제": 문제}

    art = article(d)
    rev_text, rev_cap, rev_basis = revenue_rule(d)
    table, lim_basis = limit_table(d)
    pct, pct_listed, hold_years, hold_basis = shareholding_rule(d)
    regime, regime_why = regime_for(d, assessed_before_2023)
    pr = post_rules(regime)
    d15 = f"{_D} 제15조"
    lim_text = ", ".join(f"{lo}년 이상 {lim // EOK:,}억원" for lo, lim in table)

    요건 = [
        {"구분": "가업", "요건": "중소기업 또는 중견기업", "내용": ("중소기업(조세특례제한법 제5조제1항의 중소기업, 작물재배업·축산업·어업 주업 제외) 또는 " + rev_text if d < date(2017, 2, 7)
                                                  else "중소기업(별표 업종을 주된 사업으로, 조세특례제한법 시행령 제2조제1항제1호·제3호 충족, 자산총액 5천억원 미만) 또는 " + rev_text
                                                  + "(별표 업종, 조세특례제한법 시행령 제9조제4항제1호·제3호 충족). 상속개시일이 속하는 과세기간·사업연도의 직전 과세기간·사업연도 말 현재로 판단" + decree_note(d)),
         "근거": f"{art}, {d15}제1항·제2항"},
        {"구분": "가업", "요건": "피상속인이 10년 이상 계속 경영", "내용": "피상속인이 10년 이상 계속하여 경영한 기업", "근거": art},
        {"구분": "피상속인", "요건": "최대주주등으로서 지분 보유",
         "내용": (f"최대주주등으로서 특수관계인과 합해 발행주식총수등의 {pct}%(상장법인 {pct_listed}%) 이상을 " + (f"{hold_years}년 이상 " if hold_years else "") + "계속 보유"
                if pct else "최대주주등으로서 특수관계인과 합해 일정 지분 이상을 10년 이상 계속 보유 — 2023.1.1. 이후 상속개시분의 지분율은 미확인"), "근거": hold_basis},
        {"구분": "피상속인", "요건": "대표이사등 재직",
         "내용": "가업 영위기간 중 다음 중 하나의 기간을 대표이사(개인사업자는 대표자)로 재직: 영위기간의 50% 이상, 10년 이상(상속인이 대표이사직을 승계해 상속개시일까지 계속 재직한 경우), 상속개시일부터 소급해 10년 중 5년 이상"
                + decree_note(d), "근거": f"{d15}제3항제1호나목"},
        {"구분": "상속인", "요건": "나이·종사·취임",
         "내용": "상속개시일 현재 18세 이상, 상속개시일 전 2년 이상 직접 가업에 종사(피상속인이 65세 전에 사망하거나 천재지변·인재 등 부득이한 사유로 사망하면 예외), "
                 "상속세 신고기한까지 임원 취임 및 신고기한부터 2년 이내 대표이사등 취임. 상속인의 배우자가 요건을 갖추면 상속인이 갖춘 것으로 봄"
                + decree_note(d), "근거": f"{d15}제3항제2호"},
        {"구분": "공제액", "요건": "가업상속 재산가액(한도 있음)",
         "내용": f"가업상속 재산가액에 상당하는 금액을 공제. 한도는 피상속인 계속 경영기간별 {lim_text}. 법인 가업은 주식등 가액 중 사업무관자산 비율만큼 뺀 금액, 개인 가업은 사업용 자산가액에서 담보 채무를 뺀 금액",
         "근거": f"{lim_basis}, {d15}제5항"},
    ]
    cap_basis = (f"{_L} 제18조의2제2항" if d >= date(2023, 1, 1) else f"{_L} 제18조제3항") + f", {d15}제6항·제7항(2019 시행본)"
    if d >= date(2019, 1, 1):
        요건.append({"구분": "가업", "요건": "중견기업 상속인의 납부능력",
                   "내용": "중견기업이면 가업상속인의 가업상속재산 외 상속재산 가액이 그 상속인이 납부할 상속세액의 2배(시행령 문언 '100분의 200', 2019 시행본)를 넘으면 공제 배제",
                   "근거": cap_basis})
    if d >= date(2020, 1, 1):
        요건.append({"구분": "공제 배제", "요건": "조세포탈·회계부정",
                   "내용": f"피상속인 또는 상속인이 가업 경영과 관련해 상속개시일 전 10년 이내 또는 상속개시일부터 {7 if d < date(2023, 1, 1) else 5}년 이내 행위로 조세포탈(조세범 처벌법 제3조제1항) 또는 회계부정(외부감사법 제39조제1항) 징역형·일정 벌금형이 확정되면 결정 전 확정 시 배제, 공제 후 확정 시 추징",
                   "근거": (f"{_L} 제18조의2제8항" if d >= date(2023, 1, 1) else f"{_L} 제18조제9항") + "(법률 제16846호 부칙 제4조: 2020.1.1. 이후 행위·상속개시분)"})
    요건.append({"구분": "사후관리", "요건": f"상속개시일부터 {pr['기간']}년",
               "내용": f"정당한 사유 없이 다음 중 하나에 해당하면 공제액에 기간별 추징률을 곱한 금액을 상속세 과세가액에 산입하고 이자상당액 가산: {pr['자산']}, 상속인이 가업에 종사하지 않게 된 경우(대표이사 미종사, 주된 업종 변경, 1년 이상 휴업·폐업 포함), "
                       f"주식등을 상속받은 상속인의 지분 감소(물납 등 예외), {pr['고용']}. 적용 구간: {regime_why}",
               "근거": pr["근거"] + f", {d15}(정당한 사유·가업 미종사·지분 감소의 범위)"})
    if d >= date(2023, 1, 1):
        요건.append({"구분": "납부유예", "요건": "가업상속공제 대신 납부유예(개요)",
                   "내용": "중소기업 가업을 상속받고 가업상속공제를 받지 않은 경우(영농상속공제를 받으면 받은 것으로 봄) 담보를 제공하고 신청하면 납부유예 허가 가능. 가업용 자산 40% 이상 처분(개인 가업), 가업 미종사, 지분 감소, "
                           "5년간 고용 평균 70% 미달(정규직 수·총급여액 모두), 상속인 사망 시 유예 세액과 이자상당액 징수",
                   "근거": f"{_L} 제72조의2(법률 제19195호, 2023.1.1. 이후 상속개시분 — 부칙 제2조)"})

    out = {"상속개시일": d.isoformat(), "조문": art, "요건": 요건}
    판정 = []
    # 가업 규모
    if company_size is not None:
        if company_size == "일반":
            판정.append({"항목": "기업 규모", "판정": "미충족", "사유": "중소기업·중견기업이 아니면 가업이 아님", "근거": f"{art}, {d15}제1항·제2항"})
        elif company_size == "중소기업":
            판정.append({"항목": "기업 규모", "판정": "충족", "사유": "중소기업(업종·독립성·자산총액 요건 충족을 전제)", "근거": f"{d15}제1항"})
        else:
            rev = prior_year_revenue if d < date(2017, 1, 1) else avg_revenue
            which = "직전 사업연도 매출액" if d < date(2017, 1, 1) else "직전 3개 과세기간·사업연도 매출액 평균"
            if rev is None:
                ok, why = None, f"{which}을 주면 {rev_cap // EOK:,}억원 기준으로 판정"
            elif rev >= rev_cap:
                ok, why = False, f"{which} {rev / EOK:,.0f}억원 ≥ {rev_cap // EOK:,}억원 — 가업에서 제외"
            else:
                ok, why = True, f"{which} {rev / EOK:,.0f}억원 < {rev_cap // EOK:,}억원"
            if ok and d < date(2017, 1, 1) and cross_shareholding_group:
                ok, why = False, "상호출자제한기업집단 내 기업은 제외(2016년 시행본)"
            elif ok and d < date(2017, 1, 1) and cross_shareholding_group is None:
                why += ". 상호출자제한기업집단 내 기업이 아닌 경우(cross_shareholding_group)"
            판정.append({"항목": "기업 규모·매출액", "판정": _verdict(ok), "사유": why, "근거": rev_basis})
    # 경영기간과 한도
    if years_managed is not None:
        lim = deduction_limit(d, years_managed)
        판정.append({"항목": "피상속인 계속 경영기간", "판정": "충족" if lim else "미충족",
                   "사유": (f"{years_managed}년 — 공제 한도 {lim // EOK:,}억원" if lim else f"{years_managed}년 — 10년 미만이면 가업이 아님"), "근거": lim_basis})
        if lim and business_property_value is not None:
            ded = min(business_property_value, lim)
            out["공제액(한도 적용)"] = {"가업상속 재산가액": business_property_value, "한도": lim, "공제액": ded,
                                   "주의": "가업상속 재산가액은 시행령 제15조제5항(사업무관자산 제외)으로 계산한 금액을 넣어야 함. 상속세 계산은 하지 않음"}
    # 지분
    if decedent_share_pct is not None or share_holding_years is not None:
        need = pct_listed if listed else pct
        if need is None:
            ok, why = None, "2023.1.1. 이후 상속개시분의 지분율 기준은 시행령 원문 미확인 — law_article(law_name='상속세 및 증여세법 시행령', article='제15조', as_of=상속개시일)"
        else:
            bad = []
            if decedent_share_pct is not None and decedent_share_pct < need:
                bad.append(f"지분 {decedent_share_pct}% < {need}%")
            if hold_years and share_holding_years is not None and share_holding_years < hold_years:
                bad.append(f"보유 {share_holding_years}년 < {hold_years}년")
            if bad:
                ok, why = False, ", ".join(bad)
            elif decedent_share_pct is None or (hold_years and share_holding_years is None):
                ok, why = None, "지분율과 보유기간을 모두 주어야 판정"
            else:
                ok, why = True, f"지분 {decedent_share_pct}% ≥ {need}%" + (f", 보유 {share_holding_years}년 ≥ {hold_years}년" if hold_years else " (2017.2.7. 전 상속개시분은 보유기간 문언 없음 — 해석 확인)")
            if hold_years:
                why += ". 10년 보유는 최대주주등 지분율 요건이고, 피상속인이 10년 미만 보유한 개별 주식도 공제 대상(기획재정부 조세법령운용과-10, 2022.1.5.)"
        판정.append({"항목": "피상속인 지분", "판정": _verdict(ok), "사유": why + ("" if listed is not None else " — 상장 여부(listed)를 주지 않아 비상장 기준"), "근거": hold_basis})
    # 대표이사 재직
    if any(x is not None for x in (ceo_ratio, ceo_years, ceo_years_in_last10)):
        hits = []
        if ceo_ratio is not None and ceo_ratio >= 0.5:
            hits.append(f"영위기간의 {ceo_ratio:.0%} 재직(50% 이상)")
        if ceo_years is not None and ceo_years >= 10:
            if heir_succeeded_ceo:
                hits.append(f"{ceo_years}년 재직 + 상속인이 대표이사직 승계 후 계속 재직")
        if ceo_years_in_last10 is not None and ceo_years_in_last10 >= 5:
            hits.append(f"상속개시일부터 소급해 10년 중 {ceo_years_in_last10}년 재직(5년 이상)")
        pending = ceo_years is not None and ceo_years >= 10 and heir_succeeded_ceo is None
        ok = True if hits else (None if pending or d >= date(2023, 1, 1) else False)
        why = "; ".join(hits) if hits else ("10년 이상 재직은 상속인이 대표이사직을 승계해 계속 재직한 경우만 — heir_succeeded_ceo 확인" if pending else "세 가지 재직기간 요건 중 어느 것도 충족하지 않음")
        why += decree_note(d)
        판정.append({"항목": "피상속인 대표이사 재직", "판정": _verdict(ok), "사유": why, "근거": f"{d15}제3항제1호나목"})
    # 상속인
    if any(x is not None for x in (heir_age, heir_years_in_business, heir_officer_by_deadline, heir_ceo_within_2y)):
        bad, unknown = [], []
        if heir_age is None:
            unknown.append("나이")
        elif heir_age < 18:
            bad.append(f"상속개시일 현재 {heir_age}세(18세 미만)")
        exempt = (decedent_age_at_death is not None and decedent_age_at_death < 65) or bool(unavoidable_death)
        if heir_years_in_business is None:
            if not exempt:
                unknown.append("가업 종사 기간")
        elif heir_years_in_business < 2 and not exempt:
            bad.append(f"상속개시일 전 가업 종사 {heir_years_in_business}년(2년 미만)")
        if heir_officer_by_deadline is False:
            bad.append("상속세 신고기한까지 임원으로 취임하지 않음")
        elif heir_officer_by_deadline is None:
            unknown.append("신고기한까지 임원 취임")
        if heir_ceo_within_2y is False:
            bad.append("신고기한부터 2년 이내 대표이사등으로 취임하지 않음")
        elif heir_ceo_within_2y is None:
            unknown.append("2년 이내 대표이사 취임")
        if bad and spouse_qualifies:
            ok, why = True, "상속인은 미충족이나 배우자가 요건을 모두 갖춰 상속인이 갖춘 것으로 봄(" + "; ".join(bad) + ")"
        elif bad:
            ok, why = False, "; ".join(bad) + ("" if spouse_qualifies is not None else " — 배우자가 요건을 갖추면 충족으로 봄(spouse_qualifies)")
        elif unknown:
            ok, why = None, "확인할 사실: " + ", ".join(unknown)
        else:
            ok, why = True, "나이·종사·임원 취임·대표이사 취임 요건 충족" + (" (피상속인 65세 전 사망 또는 부득이한 사망으로 2년 종사 요건 예외)" if exempt and (heir_years_in_business or 0) < 2 else "")
        why += decree_note(d)
        if d >= date(2023, 1, 1):
            if ok is False:
                ok = None
        판정.append({"항목": "상속인 요건", "판정": _verdict(ok), "사유": why, "근거": f"{d15}제3항제2호"})
    if company_size == "중견기업" and d >= date(2019, 1, 1) and other_property_exceeds_twice_tax is not None:
        판정.append({"항목": "중견기업 납부능력", "판정": "미충족" if other_property_exceeds_twice_tax else "충족",
                   "사유": "가업상속재산 외 상속재산이 상속세액의 2배 초과 — 공제 배제" if other_property_exceeds_twice_tax else "가업상속재산 외 상속재산이 상속세액의 2배 이하",
                   "근거": cap_basis})
    # 사후관리
    for i, e in enumerate(post_events or []):
        ev = e["event"]
        when = _d(e["date"]) if e.get("date") else None
        end = _add_years(d, pr["기간"])
        within = None if when is None else (d <= when < end)
        just = e.get("justified")
        name = f"사후관리 — {ev}" + (f"({when.isoformat()})" if when else "")
        if ev == "조세포탈·회계부정 형 확정":
            if d < date(2020, 1, 1):
                판정.append({"항목": name, "판정": "해당 없음", "사유": "2020.1.1. 전 상속개시분에는 이 규정이 없음(법률 제16846호 부칙 제4조)", "근거": f"{_L} 제18조제9항"})
            else:
                판정.append({"항목": name, "판정": "추징 사유", "사유": "결정 전 확정이면 공제 배제, 공제 후 상속인의 형 확정이면 공제액 전액을 과세가액에 산입하고 이자상당액 가산. 행위 시기가 상속개시일 전 10년~상속개시 후 사후관리 기간 이내인지 확인",
                           "근거": f"{_L} " + ("제18조의2제8항" if d >= date(2023, 1, 1) or regime == "5년" else "제18조제9항")})
            continue
        if within is False:
            판정.append({"항목": name, "판정": "해당 없음", "사유": f"사후관리 기간(상속개시일부터 {pr['기간']}년, {end.isoformat()} 전까지) 밖", "근거": pr["근거"]})
            continue
        if just:
            판정.append({"항목": name, "판정": "해당 없음(정당한 사유)", "사유": "시행령 제15조의 정당한 사유(수용·조직변경·병역·질병, 상장요건, 회생 출자전환 등)에 해당한다고 입력함 — 해당 호 문언 확인",
                       "근거": f"{d15}(정당한 사유)"})
            continue
        res, why = "추징 사유", ""
        if ev == "가업용 자산 처분":
            ratio = e.get("ratio")
            lo, hi = pr["자산 기준"]
            if ratio is None:
                res, why = "확인 필요", f"처분 비율(ratio, %)을 주면 판정 — 기준: {pr['자산']}"
            else:
                need = lo if (when and when < _add_years(d, 5)) else hi
                if when is None and lo != hi:
                    need = lo
                if ratio >= need:
                    why = f"처분 비율 {ratio}% ≥ {need}% — 공제액 × 처분 비율 × 기간별 추징률" + ("" if regime == "5년" or (when and when >= date(2019, 1, 1)) else "(2019.1.1. 전 처분분은 처분 비율을 곱하지 않음)")
                else:
                    res, why = "해당 없음", f"처분 비율 {ratio}% < {need}%"
        elif ev == "가업 미종사":
            why = "상속인(배우자 요건 적용 시 배우자)이 대표이사등으로 종사하지 않거나, 주된 업종 변경(허용 범위 밖), 1년 이상 휴업·폐업 — 공제액 × 기간별 추징률"
        elif ev == "지분 감소":
            why = "상속받은 주식등 처분, 유상증자 실권, 특수관계인 처분으로 최대주주등에서 벗어남 등 — 물납으로 줄었더라도 최대주주등이어야 함"
        elif ev == "고용 미달":
            emp = e.get("employment_ratio")
            pay = e.get("payroll_ratio")
            if regime == "5년":
                thr = 90
                if emp is None or pay is None:
                    res, why = "확인 필요", "5년간 정규직 수 평균 비율(employment_ratio, %)과 총급여액 평균 비율(payroll_ratio, %)을 모두 주면 판정 — 둘 다 90% 미달이어야 추징"
                elif emp < thr and pay < thr:
                    why = f"정규직 수 {emp}%·총급여액 {pay}% 모두 90% 미달"
                else:
                    res, why = "해당 없음", f"정규직 수 {emp}%·총급여액 {pay}% 중 하나 이상이 90% 이상"
                if d < date(2023, 1, 1) and res == "추징 사유":
                    why += ". 종전 제18조제6항제1호마목 기준이 더 유리하면 그 기준 적용(법률 제19195호 부칙 제7조제3항)"
            else:
                res, why = "확인 필요", f"종전 기준: {pr['고용']}"
        판정.append({"항목": name, "판정": res, "사유": why, "근거": pr["근거"]})
    if 판정:
        out["판정"] = 판정
    out["사후관리 적용"] = {"구간": regime, "설명": regime_why, "기간 종료": _add_years(d, pr["기간"]).isoformat()}
    out["한계"] = [
        "상속개시일에 적용되는 문언과 부칙 기준. 중소기업·중견기업 해당 여부(업종·독립성·자산총액), 가업상속 재산가액(사업무관자산), 정당한 사유는 사실 판단이라 입력을 전제로만 판정",
        "시행령 제15조는 2016.2.5.·2017.2.7.·2018.2.13.·2019.2.12. 시행본만 원문 대조함. 2020년 이후 시행령(특히 2023.2.28. 개정)의 지분율·대표이사·상속인 요건·업종 변경 허용 범위·기간별 추징률은 미확인 — 원문으로 확인",
        "2017.1.1.~2017.2.6. 상속개시분은 법은 중견기업 기준, 시행령은 2016 시행본(보유기간 문언 없음)이 적용되는 구간 — 해석 확인",
        "기간별 추징률·이자상당액·납부유예 금액은 계산하지 않음. 상속세 계산은 계산 MCP",
        "영농상속공제(제18조의3)와 조세특례제한법 가업승계 증여세 과세특례(제30조의6)·창업자금 과세특례(제30조의5)는 다루지 않음",
    ]
    out["관련 해석"] = list(_RULINGS)
    out["다음 단계"] = (f"원문: law_article(law_name='{_L}', article='{'제18조의2' if d >= date(2023, 1, 1) else '제18조'}', as_of='{d.isoformat()}') · "
                     f"시행령 제15조(as_of 상속개시일) · 부칙: article_addenda · 해석: search_tax_rulings('가업상속공제 사후관리')")
    out["확인 시행본"] = _CHECKED
    return out


_CHECKED = ("법: 2016.1.1.·2017.1.1.·2018.1.1.·2019.1.1.·2020.1.1.·2021.1.1.·2022.1.1.·2023.1.1.·2024.1.1.·2025.3.14.·2026.1.1. 시행본(제18조·제18조의2·제72조의2)과 개정 부칙. "
            "시행령: 2016.2.5.·2017.2.7.·2018.2.13.·2019.2.12. 시행본 제15조(국세법령정보시스템 연혁본)")
