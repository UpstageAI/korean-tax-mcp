"""1세대 1주택 양도소득세 비과세 요건 안내 — 양도일의 시행본과 개정 부칙으로 보유·거주기간, 일시적 2주택 처분기한, 고가주택 기준, 주요 특례를 판정한다. Claude 작성(2026-11-14).

세액을 계산하지 않는다(계산 MCP의 capital_gains_income·capital_gains_tax). 장기보유특별공제는 범위 밖.
대조한 원문(국세법령정보시스템 — 법제처 Open API 점검 중이라 이쪽으로 받음):
  · 소득세법 시행령 2026.10.1. 시행본(대통령령 제36737호 반영) 제152조의3, 제154조, 제155조, 제156조 전문과 조문별 개정 연혁 표시
  · 같은 시행본에 실린 2016~2026년 개정 부칙 전부(제26982호~제36737호) — 아래 적용 시기는 모두 부칙 문언
  · 국세청 해석·판례(국세법령정보시스템 문서 요지)
양도일·취득일에 따라 달라지는 것:
  · 거주요건: 취득 당시 조정대상지역 주택은 보유기간 중 거주 2년 — 2017.8.3. 이후 취득분으로 2017.9.19. 이후 양도분(시행령 2017.9.19. 개정 부칙 제2조). 2017.8.2. 이전 취득, 2017.8.2. 이전 계약금 지급(무주택 세대)은 종전 규정
  · 보유기간 기산: 2021.1.1.~2022.5.9. 양도분은 2주택 이상을 보유한 1세대가 다른 주택을 모두 처분한 뒤 1주택이 된 날부터(시행령 2019.2.12. 개정 제154조제5항, 부칙 제1조제3호). 2022.5.10. 이후 양도분부터 폐지(2022.5.31. 개정 부칙)
  · 일시적 2주택 처분기한(종전 주택과 신규 주택이 모두 조정대상지역): 2018.9.14. 이후 취득분은 2018.10.23. 이후 양도부터 2년 → 2019.12.17. 이후 취득분은 2020.2.11. 이후 양도부터 1년과 세대전원 전입 → 2022.5.10. 이후 양도분은 제2호 개정 → 2023.1.12. 이후 양도분은 3년 → 2026.8.4. 이후 취득분은 2026.10.1. 이후 양도부터 2년. 그 밖의 경우는 3년
  · 고가주택 기준: 양도가액 9억원 초과 → 12억원 초과(2021.12.8. 이후 양도분, 시행령 2022.2.15. 개정 부칙)
  · 혼인 합가 특례: 제155조제5항 개정(혼인한 날부터 10년)은 2024.11.12. 이후 양도분(2024.11.12. 개정 부칙)
  · 용도변경 양도: 매매계약 후 주택 외 용도로 바꿔 양도하면 매매계약일 현재로 판정 — 2025.2.28. 이후 매매계약분(2025.2.28. 개정 부칙)"""

import datetime as _dt

_L, _D = "소득세법", "소득세법 시행령"
D = _dt.date
DATE_MIN = D(2016, 1, 1)
SPECIALS = ("상속주택", "동거봉양", "혼인", "농어촌주택")
VERIFIED = ("소득세법 시행령 2026.10.1. 시행본(대통령령 제36737호 반영) 제152조의3·제154조·제155조·제156조 전문과 개정 연혁 표시, 같은 시행본의 2016~2026년 개정 부칙 — "
            "국세법령정보시스템 조회(2026-11-14). 2025년 이전 연말 시행본 전문과 소득세법(법률) 제88조·제89조 문언은 조회 장애로 대조하지 못함")

# 부칙 기준일
RES_ACQ = D(2017, 8, 3)        # 2017.9.19. 개정 부칙 제2조제2항 — 2017.8.2. 이전 취득·계약은 종전 규정
RES_TRANSFER = D(2017, 9, 19)  # 같은 부칙 제2조제1항·제2항제3호 — 시행 이후 양도분
FINAL_FROM, FINAL_TO = D(2021, 1, 1), D(2022, 5, 9)   # 제154조제5항(2019.2.12. 개정, 2021.1.1. 시행) ~ 2022.5.31. 개정 부칙(2022.5.10. 이후 양도분 폐지)
T2018, A2018 = D(2018, 10, 23), D(2018, 9, 14)        # 2018.10.23. 개정 부칙 제2조
T2020, A2020 = D(2020, 2, 11), D(2019, 12, 17)        # 2020.2.11. 개정 부칙
T2022 = D(2022, 5, 10)                                # 2022.5.31. 개정 부칙(제155조제1항제2호)
T2023 = D(2023, 1, 12)                                # 2023.2.28. 개정 부칙(제155조제1항)
T2026, A2026 = D(2026, 10, 1), D(2026, 8, 4)          # 2026.9.30. 개정 부칙
LUX_DATE = D(2021, 12, 8)                             # 2022.2.15. 개정 부칙(제156조 등 2021.12.8. 이후 양도분)
MARRIAGE_DATE = D(2024, 11, 12)                       # 2024.11.12. 개정 부칙(제155조제5항)
PARENT_DATE = D(2019, 2, 12)                          # 제155조제4항 마지막 실질 개정(2019.2.12.) — 그 전 문언 미확인

_RULINGS = [
    {"문서번호": "기준-2020-법령해석재산-0102", "주제": "일시적 2주택",
     "내용": "조정대상지역 종전 주택 보유 중 2018.9.13. 이전에 조정대상지역 신규 분양권 매매계약·계약금 지급 → 2018.10.23. 개정 부칙 제2조제2항에 따라 처분기한 3년(회신 전문 확인)"},
    {"문서번호": "대구지방법원-2024-구합-23544(대구고등법원-2025-누-10153 같은 취지)", "주제": "일시적 2주택",
     "내용": "2019.12.17. 이후 취득 신규 주택은 취득일부터 1년 이내 세대전원 이사·전입신고가 요건 — 해외파견은 예외 사유가 아님(요지)"},
    {"문서번호": "대법원-2024-두-65645(심리불속행, 대구고등법원-2024-누-11892)", "주제": "보유기간",
     "내용": "2021.1.1. 이후 3주택 중 1주택을 양도해 일시적 2주택이 된 경우 보유기간은 직전 주택 양도일부터 기산(구 제154조제5항 단서, 요지)"},
    {"문서번호": "대법원-2024-두-55426", "주제": "일시적 2주택",
     "내용": "2주택 보유 1세대가 신규 주택을 취득해 3주택이 되었다가 1주택을 처분해 2주택이 된 경우는 일시적 2주택 비과세 대상이 아님(요지)"},
    {"문서번호": "기획재정부 재산세제과-906(2024.7.31.)", "주제": "일시적 2주택",
     "내용": "일시적 2주택 특례(제155조제1항)와 일시적 1주택·1조합원입주권(제156조의2제3항)·1분양권(제156조의3제2항·제3항) 특례는 중복 적용 불가(요지)"},
    {"문서번호": "대법원-2026-두-30005(심리불속행, 대구고등법원-2025-누-10195)", "주제": "1세대",
     "내용": "배우자는 사실상 동거·생계 여부를 묻지 않고 1세대를 구성 — 법률상 배우자가 있으면 부부관계가 파탄되어도 배우자 없는 경우의 예외(구 시행령 제152조의3 등)는 적용 안 됨(요지)"},
    {"문서번호": "대법원-2023-두-53799", "주제": "상속주택",
     "내용": "상속주택 특례(제155조제2항)는 원칙적으로 상속개시 당시 상속인과 피상속인이 1세대이면 적용되지 않음(요지)"},
    {"문서번호": "기준-2024-법규재산-0061(2026.8.20.)", "주제": "동거봉양",
     "내용": "동거봉양 합가일부터 10년 이내 자녀 소유 주택 양도 시 거주주택 특례의 거주요건 적용 관계(요지)"},
]


def _add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:      # 2월 29일
        return d.replace(year=d.year + n, day=28)


def _date(v, name, 문제):
    if v is None:
        return None
    try:
        return D.fromisoformat(str(v))
    except ValueError:
        문제.append(f"{name}={v!r} — YYYY-MM-DD")
        return None


def _years_ok(start, end, n):
    """start 다음 날부터 기산(초일불산입)해 end에 n년이 찼는지. n년이 되는 날은 start의 n년 뒤 같은 날."""
    return end >= _add_years(start, n)


def deadline_years(transfer, new_acq, both_adjusted, new_contract=None):
    """일시적 2주택 처분기한(년)과 근거, 전입요건 여부. both_adjusted는 신규 주택 취득일 현재 종전 주택과 신규 주택이 모두 조정대상지역인지."""
    e = min(x for x in (new_acq, new_contract) if x is not None)   # 계약금 지급일이 기준일 이전이면 종전 규정(각 부칙 제2항제2호)
    if not both_adjusted:
        return 3, False, f"{_D} 제155조제1항 — 조정대상지역에서 조정대상지역으로 갈아탄 경우가 아니면 신규 주택 취득일부터 3년"
    if transfer < T2018:
        return 3, False, f"{_D} 제155조제1항(2018.10.23. 개정 전) — 3년. 조정대상지역 단축 규정은 2018.10.23. 이후 양도분부터(개정 부칙 제2조제1항)"
    if transfer >= T2026:
        if e >= A2026:
            return 2, False, f"{_D} 제155조제1항제1호(2026.9.30. 개정, 2026.10.1. 시행) — 2026.8.4. 이후 조정대상지역 신규 주택 취득분(개정 부칙 제2조제1항)"
        return 3, False, f"{_D} 제155조제1항(종전) — 2026.8.3. 이전 신규 주택 취득·계약분은 종전 규정 3년(2026.9.30. 개정 부칙 제2조제2항)"
    if transfer >= T2023:
        return 3, False, f"{_D} 제155조제1항(2023.2.28. 개정) — 2023.1.12. 이후 양도분은 조정대상지역 여부와 관계없이 3년(개정 부칙 제2조)"
    if e < A2018:
        return 3, False, f"{_D} 제155조제1항 — 2018.9.13. 이전 신규 주택 취득·계약분은 종전 규정 3년(2018.10.23. 개정 부칙 제2조제2항, 기준-2020-법령해석재산-0102)"
    if transfer >= T2022:
        return 2, False, (f"{_D} 제155조제1항제2호(2022.5.31. 개정) — 2022.5.10. 이후 종전 주택 양도분(개정 부칙). 기간 2년·전입요건 삭제는 개정 문언을 대조하지 못함(미확인) — "
                          "2018.9.14. 이후 취득분의 2018.10.23. 개정 기간과 같은 2년으로 안내")
    if transfer >= T2020 and e >= A2020:
        return 1, True, f"{_D} 제155조제1항(2020.2.11. 개정) — 2019.12.17. 이후 조정대상지역 신규 주택 취득분: 1년 이내 종전 주택 양도와 세대전원 전입(개정 부칙, 대구지방법원-2024-구합-23544)"
    return 2, False, f"{_D} 제155조제1항(2018.10.23. 개정) — 2018.9.14. 이후 조정대상지역 신규 주택 취득분 2년" + (" (2019.12.16. 이전 취득·계약분은 2020.2.11. 개정 부칙 제2항으로 종전 규정)" if transfer >= T2020 else "")


def _requirements(t):
    lux = 1_200_000_000 if t >= LUX_DATE else 900_000_000
    r = [
        {"요건": "1세대", "내용": "거주자와 그 배우자, 같은 주소에서 생계를 같이하는 가족으로 구성. 배우자는 동거·생계 여부를 묻지 않음(대법원-2026-두-30005). 배우자가 없어도 1세대로 보는 경우 — 30세 이상, 배우자의 사망·이혼, "
                                     "소득(부령으로 정하는 소득)이 기준 중위소득을 12개월로 환산한 금액의 100분의 40 수준 이상으로 독립 생계 유지 가능(미성년자 제외, 예외 있음)",
         "근거": f"{_L} 제88조제6호, {_D} 제152조의3(2017.2.3. 신설) — 법 문언과 2017.2.3. 전 규정·소득 기준의 연도별 문언은 미확인"},
        {"요건": "1주택", "내용": "양도일 현재 국내에 1주택(주택 수는 세대원 전원 기준. 겸용주택은 주택 연면적이 더 크면 전부 주택, 다가구주택은 구분 양도하지 않으면 단독주택). 2025.2.28. 이후 매매계약 후 주택 외 용도로 바꿔 양도하면 매매계약일 현재로 판정",
         "근거": f"{_D} 제154조제1항·제3항, 제155조제15항, 2025.2.28. 개정 부칙"},
        {"요건": "보유기간", "내용": "2년 이상(비거주자가 3년 이상 보유·거주한 상태로 거주자로 전환하면 3년, 그 기간 통산). 기간은 취득일부터 양도일까지(법 제95조제4항). "
                                    + ("2주택 이상을 보유한 1세대가 다른 주택을 모두 처분(2021.2.17. 이후 증여·용도변경 포함)했으면 1주택이 된 날부터 기산" if FINAL_FROM <= t <= FINAL_TO else
                                       "2022.5.10. 이후 양도분은 다른 주택 처분일 기산 규정이 없음(2022.5.31. 개정)" if t > FINAL_TO else "다른 주택 처분일 기산 규정(2021.1.1. 시행) 전"),
         "근거": f"{_D} 제154조제1항·제5항·제8항" + (", 2019.2.12. 개정 부칙 제1조제3호, 2021.2.17. 개정 부칙" if FINAL_FROM <= t <= FINAL_TO else ", 2022.5.31. 개정 부칙" if t > FINAL_TO else "")},
        {"요건": "거주기간", "내용": ("취득 당시 조정대상지역 주택은 보유기간 중 거주 2년 이상(주민등록 전입일~전출일). 2017.8.2. 이전 취득, 2017.8.2. 이전 계약금 지급(계약금 지급일 현재 무주택 세대), "
                                    "조정대상지역 공고일 이전 계약금 지급(무주택 세대 — 제154조제1항제5호)은 거주요건 없음" if t >= RES_TRANSFER else
                                    "2017.9.19. 전 양도분은 거주요건 없음(2017.9.19. 개정 부칙 제2조)"),
         "근거": f"{_D} 제154조제1항·제2항·제6항, 2017.9.19. 개정 부칙 제2조"},
        {"요건": "보유·거주기간 예외", "내용": "건설임대·공공매입임대주택 임차일부터 5년 이상 거주, 수용, 해외이주·1년 이상 국외 취학·근무로 세대전원 출국(출국일부터 2년 이내 양도), 1년 이상 거주 후 취학·근무·질병 등 부득이한 사유는 보유·거주기간 제한 없음",
         "근거": f"{_D} 제154조제1항제1호~제3호"},
        {"요건": "고가주택", "내용": f"양도 당시 실지거래가액 합계액이 {lux // 100_000_000}억원을 넘으면 비과세에서 제외되고 넘는 부분 양도차익에 과세(같으면 비과세). 일부 지분 양도도 전체 가액으로 판정"
                                    + (" — 2021.12.8. 이후 양도분 12억원" if t >= LUX_DATE else " — 2021.12.8. 이후 양도분부터 12억원"),
         "근거": f"{_L} 제89조제1항제3호, {_D} 제156조제1항" + (", 2022.2.15. 개정 부칙" if t >= LUX_DATE else "")},
        {"요건": "일시적 2주택", "내용": "종전 주택 취득일부터 1년 이상 지난 후 신규 주택을 취득하고 처분기한 이내 종전 주택을 양도하면 1주택으로 봄(수용·임대주택·부득이한 사유는 1년 요건 없음). "
                                       "처분기한은 양도일·신규 주택 취득일·조정대상지역 여부로 다름(new_house_acquisition_date로 판정)",
         "근거": f"{_D} 제155조제1항"},
    ]
    return r


def _residence_days(periods, 문제):
    spans = []
    for i, p in enumerate(periods or []):
        if not isinstance(p, dict):
            문제.append(f"residence_periods[{i}] — {{from, to}} 형식")
            continue
        a, b = _date(p.get("from"), f"residence_periods[{i}].from", 문제), _date(p.get("to"), f"residence_periods[{i}].to", 문제)
        if a and b:
            if b < a:
                문제.append(f"residence_periods[{i}] — to가 from보다 앞섬")
            else:
                spans.append((a, b))
    return spans


def guide(transfer_date=None, acquisition_date=None, adjusted_area_at_acquisition=None, residence_periods=None, contract_date=None, homeless_at_contract=None,
          contract_before_designation=None, transfer_price=None, other_houses_disposed_date=None, new_house_acquisition_date=None, new_house_contract_date=None,
          both_adjusted_at_new_acquisition=None, moved_in_date=None, special=None, special_date=None):
    if transfer_date is None:
        return {"양도일별 변화": [x.strip() for x in __doc__.split("양도일·취득일에 따라 달라지는 것:")[1].strip().split("\n")],
                "입력": "transfer_date(2016-01-01 이후)를 주면 그 양도일의 요건과 사실관계 판정", "특례 구분": list(SPECIALS), "확인 시행본": VERIFIED}
    문제 = []
    t = _date(transfer_date, "transfer_date", 문제)
    if t and t < DATE_MIN:
        문제.append("transfer_date — 2016-01-01 이후 양도분만")
    acq = _date(acquisition_date, "acquisition_date", 문제)
    cd = _date(contract_date, "contract_date", 문제)
    od = _date(other_houses_disposed_date, "other_houses_disposed_date", 문제)
    na = _date(new_house_acquisition_date, "new_house_acquisition_date", 문제)
    nc = _date(new_house_contract_date, "new_house_contract_date", 문제)
    mi = _date(moved_in_date, "moved_in_date", 문제)
    sd = _date(special_date, "special_date", 문제)
    spans = _residence_days(residence_periods, 문제)
    for k, v in (("adjusted_area_at_acquisition", adjusted_area_at_acquisition), ("homeless_at_contract", homeless_at_contract),
                 ("contract_before_designation", contract_before_designation), ("both_adjusted_at_new_acquisition", both_adjusted_at_new_acquisition)):
        if v is not None and not isinstance(v, bool):
            문제.append(f"{k}={v!r} — true | false")
    if transfer_price is not None and (isinstance(transfer_price, bool) or not isinstance(transfer_price, (int, float)) or transfer_price < 0):
        문제.append(f"transfer_price={transfer_price!r} — 0 이상의 금액(원)")
    if special is not None and special not in SPECIALS:
        문제.append(f"special={special!r} — {' | '.join(SPECIALS)}")
    if t and acq and acq > t:
        문제.append("acquisition_date가 transfer_date보다 뒤")
    if na and acq and na < acq:
        문제.append("new_house_acquisition_date가 종전 주택 acquisition_date보다 앞섬 — 양도하는 주택이 먼저 취득한 종전 주택이어야 일시적 2주택")
    if 문제:
        return {"error": "입력 확인 필요", "문제": 문제}

    out = {"양도일": t.isoformat(), "요건": _requirements(t)}
    판정 = []

    # 보유기간
    start, start_why = acq, "취득일"
    if acq and od and od > acq:
        if FINAL_FROM <= t <= FINAL_TO:
            start, start_why = od, "다른 주택을 모두 처분해 1주택이 된 날(2021.1.1.~2022.5.9. 양도분, 구 제154조제5항 단서)"
        else:
            판정.append({"항목": "보유기간 기산일", "판정": "해당 없음", "사유": "다른 주택 처분일부터 기산하는 규정은 2021.1.1.~2022.5.9. 양도분에만 적용 — 취득일부터 기산",
                       "근거": f"{_D} 제154조제5항, 2019.2.12. 개정 부칙 제1조제3호, 2022.5.31. 개정 부칙"})
    if start:
        ok = _years_ok(start, t, 2)
        until = _add_years(start, 2)
        판정.append({"항목": "보유기간 2년", "판정": "충족" if ok else "미충족",
                   "사유": f"{start_why} {start} → 양도일 {t}. 2년이 되는 날 {until}(초일불산입)" + ("" if ok else " — 일시적 2주택이어도 양도하는 종전 주택은 이 요건을 갖춰야 함")
                           + (". 다른 주택을 처분한 뒤 1주택이 된 경우 — 대법원-2024-두-65645" if start is od else ""),
                   "근거": f"{_D} 제154조제1항·제5항, {_L} 제95조제4항"})
    elif od and FINAL_FROM <= t <= FINAL_TO:
        pass
    elif FINAL_FROM <= t <= FINAL_TO:
        판정.append({"항목": "보유기간 기산일", "판정": "확인 필요", "사유": "2021.1.1.~2022.5.9. 양도분 — 2주택 이상을 보유하다 다른 주택을 처분했다면 그 날(other_houses_disposed_date)부터 기산",
                   "근거": f"{_D} 제154조제5항(2019.2.12. 개정)"})

    # 거주기간
    if acq and adjusted_area_at_acquisition is not None:
        basis = f"{_D} 제154조제1항, 2017.9.19. 개정 부칙 제2조"
        if not adjusted_area_at_acquisition:
            판정.append({"항목": "거주기간 2년", "판정": "해당 없음", "사유": "취득 당시 조정대상지역이 아님", "근거": basis})
        elif t < RES_TRANSFER:
            판정.append({"항목": "거주기간 2년", "판정": "해당 없음", "사유": "2017.9.19. 전 양도분 — 거주요건 신설 전(2017.8.3. 이후 취득해 그 전에 양도한 주택도 종전 규정, 부칙 제2조제2항제3호)", "근거": basis})
        elif acq < RES_ACQ:
            판정.append({"항목": "거주기간 2년", "판정": "해당 없음", "사유": f"{acq} 취득 — 2017.8.2. 이전 취득 주택은 종전 규정(부칙 제2조제2항제1호)", "근거": basis})
        elif cd and cd < RES_ACQ and homeless_at_contract:
            판정.append({"항목": "거주기간 2년", "판정": "해당 없음", "사유": f"{cd} 계약금 지급, 계약금 지급일 현재 무주택 세대 — 2017.8.2. 이전 계약분은 종전 규정(부칙 제2조제2항제2호)", "근거": basis})
        elif contract_before_designation and homeless_at_contract:
            판정.append({"항목": "거주기간 2년", "판정": "해당 없음", "사유": "조정대상지역 공고일 이전 매매계약·계약금 지급(증빙 확인), 계약금 지급일 현재 무주택 세대 — 거주기간 제한 없음",
                       "근거": f"{_D} 제154조제1항 단서·제5호(현행 문언, 신설 시기 미확인)"})
        else:
            pend = []
            if cd and cd < RES_ACQ and homeless_at_contract is None:
                pend.append("2017.8.2. 이전 계약금 지급 — 계약금 지급일 현재 무주택 세대였는지(homeless_at_contract) 확인하면 종전 규정")
            if contract_before_designation and homeless_at_contract is None:
                pend.append("공고일 이전 계약 — 계약금 지급일 현재 무주택 세대였는지(homeless_at_contract) 확인하면 거주요건 없음(제154조제1항제5호)")
            if not spans:
                pend.append("거주 기간(residence_periods: 주민등록 전입일~전출일) 확인")
            if pend:
                판정.append({"항목": "거주기간 2년", "판정": "확인 필요", "사유": "취득 당시 조정대상지역(2017.8.3. 이후 취득) — 보유기간 중 2년 거주 필요. " + "; ".join(pend), "근거": basis})
            else:
                판정.append(_residence(spans, acq, t, basis))
    elif acq and adjusted_area_at_acquisition is None and t >= RES_TRANSFER and acq >= RES_ACQ:
        판정.append({"항목": "거주기간 2년", "판정": "확인 필요", "사유": "취득 당시 조정대상지역이면 보유기간 중 2년 거주 필요 — adjusted_area_at_acquisition 확인", "근거": f"{_D} 제154조제1항"})

    # 일시적 2주택
    if na:
        if both_adjusted_at_new_acquisition is None and na >= A2018 and T2018 <= t < T2023 or (both_adjusted_at_new_acquisition is None and na >= A2026 and t >= T2026):
            판정.append({"항목": "일시적 2주택 — 처분기한", "판정": "확인 필요", "사유": "신규 주택 취득일 현재 종전 주택과 신규 주택이 모두 조정대상지역이면 처분기한이 짧아짐 — both_adjusted_at_new_acquisition 확인",
                       "근거": f"{_D} 제155조제1항"})
        else:
            판정.extend(_temporary(t, acq, na, nc, bool(both_adjusted_at_new_acquisition), mi))

    # 고가주택
    if transfer_price is not None:
        lux = 1_200_000_000 if t >= LUX_DATE else 900_000_000
        over = transfer_price > lux
        판정.append({"항목": "고가주택", "판정": "고가주택" if over else "해당 없음",
                   "사유": f"양도가액 {transfer_price:,.0f}원 — 기준 {lux:,}원" + (" 초과: 비과세 요건을 갖춰도 기준 초과분 양도차익에 과세(계산 MCP capital_gains_income)" if over else " 이하(같으면 비과세)")
                           + (" (2021.12.8. 이후 양도분 12억원)" if t >= LUX_DATE else " (2021.12.7. 이전 양도분 9억원)"),
                   "근거": f"{_L} 제89조제1항제3호, {_D} 제156조, 2022.2.15. 개정 부칙"})

    if special:
        판정.append(_special(special, t, acq, sd))

    if 판정:
        out["판정"] = 판정
    out["한계"] = [
        "보유·거주기간은 초일불산입으로 n년이 되는 날(취득일의 n년 뒤 같은 날) 이후 양도면 충족으로 계산. 여러 번 나눠 거주하면 날짜를 합산(730일 미만 미충족, 731일 이상 충족, 그 사이는 확인 필요)",
        "2025년 이전 연말 시행본의 전문과 소득세법(법률) 제88조·제89조 문언은 국세법령정보시스템 조회 장애로 대조하지 못함(미확인) — 적용 시기는 현행 시행본에 실린 개정 부칙 문언으로 나눔. "
        "2022.5.10.~2023.1.11. 양도분 일시적 2주택 기간(2년)과 전입요건 삭제, 2020.2.11. 개정의 전입요건 예외(기존 임차인 등), 2019.2.12. 전 동거봉양·2024.11.12. 전 혼인 합가 기간, "
        "제154조제1항제5호의 신설 시기, 2021.1.1.~2022.5.9. 제154조제5항의 정확한 문언은 미확인",
        "다루지 않는 특례: 공동상속주택 소수지분(제155조제3항), 문화유산주택(제6항), 부득이한 사유로 취득한 수도권 밖 주택(제8항), 수도권 밖 이전 기관 종사자(제16항), 장기임대주택·장기어린이집과 거주주택(제20항~), "
        "조합원입주권·분양권과 주택(제156조의2·제156조의3), 상생임대주택(제155조의3), 대체주택·재건축 관련 특례, 농어촌주택은 요건 안내만",
        "1세대 구성(생계를 같이하는 가족인지)과 주택 해당 여부(오피스텔 등 사실상 주거용), 조정대상지역 지정 여부는 사실 판단 — 입력값으로 봄. 조정대상지역 지정·해제 고시는 국토교통부 공고로 확인",
        "세액·장기보유특별공제는 계산하지 않음 — 계산 MCP의 capital_gains_income(고가주택 안분 포함)·capital_gains_tax",
    ]
    out["관련 해석"] = _RULINGS
    out["다음 단계"] = (f"원문: law_article(law_name='{_D}', article='154', as_of=양도일) · 제155조·제156조 · 부칙: article_addenda · 해석: search_tax_rulings('일시적 2주택 처분기한') · "
                    "세액: 계산 MCP capital_gains_income → capital_gains_tax")
    out["확인 시행본"] = VERIFIED
    return out


def _residence(spans, acq, t, basis):
    if len(spans) == 1:
        a, b = spans[0]
        ok = _years_ok(a, min(b, t), 2)
        return {"항목": "거주기간 2년", "판정": "충족" if ok else "미충족", "사유": f"전입 {a} ~ 전출 {b} — 2년이 되는 날 {_add_years(a, 2)}(초일불산입)", "근거": basis}
    days = sum((min(b, t) - a).days for a, b in spans)
    res = "충족" if days >= 731 else "미충족" if days < 730 else "확인 필요"
    return {"항목": "거주기간 2년", "판정": res, "사유": f"거주 {len(spans)}회 합산 {days}일 — 2년(730~731일) 기준" + (" — 경계라 날짜 계산 확인" if res == "확인 필요" else ""), "근거": basis}


def _temporary(t, acq, na, nc, both, mi):
    out = []
    basis = f"{_D} 제155조제1항"
    if acq:
        ok = na > _add_years(acq, 1)
        same = na == _add_years(acq, 1)
        out.append({"항목": "일시적 2주택 — 종전 주택 취득 후 1년", "판정": "충족" if ok else ("확인 필요" if same else "미충족"),
                    "사유": f"종전 주택 취득 {acq} → 신규 주택 취득 {na}" + (" — 1년이 되는 날 신규 취득이라 '1년 이상이 지난 후'인지 확인" if same else "")
                            + ("" if ok or same else ". 수용·건설임대주택·부득이한 사유(제154조제1항제1호·제2호가목·제3호)는 이 요건 없음"),
                    "근거": basis})
    if na > t:
        out.append({"항목": "일시적 2주택 — 처분기한", "판정": "해당 없음", "사유": "신규 주택을 종전 주택 양도일 뒤에 취득 — 양도일 현재 1주택", "근거": basis})
        return out
    yrs, move_in, why = deadline_years(t, na, both, nc)
    until = _add_years(na, yrs)
    ok = t <= until
    out.append({"항목": "일시적 2주택 — 처분기한", "판정": "충족" if ok else "미충족", "사유": f"신규 주택 취득 {na}부터 {yrs}년 이내({until}까지) 종전 주택 양도 — 양도일 {t}", "처분기한(년)": yrs, "근거": why})
    if move_in:
        b = f"{_D} 제155조제1항(2020.2.11. 개정), 대구지방법원-2024-구합-23544"
        if mi is None:
            out.append({"항목": "일시적 2주택 — 신규 주택 전입", "판정": "확인 필요", "사유": "신규 주택 취득일부터 1년 이내 세대전원 이사·전입신고(moved_in_date) 확인. 기존 임차인이 있는 경우 등 예외 문언은 미확인", "근거": b})
        else:
            lim = _add_years(na, 1)
            out.append({"항목": "일시적 2주택 — 신규 주택 전입", "판정": "충족" if mi <= lim else "미충족", "사유": f"전입 {mi} — 기한 {lim}", "근거": b})
    return out


def _special(kind, t, acq, sd):
    if kind == "상속주택":
        b = f"{_D} 제155조제2항, 대법원-2023-두-53799"
        if sd is None or acq is None:
            return {"항목": "상속주택 특례", "판정": "확인 필요", "사유": "상속주택과 일반주택을 1개씩 보유한 1세대가 일반주택을 양도하면 1주택으로 봄 — 일반주택은 상속개시 당시 보유한 주택이어야 함(상속개시일 special_date, 일반주택 취득일 acquisition_date)", "근거": b}
        ok = acq <= sd
        return {"항목": "상속주택 특례", "판정": "충족" if ok else "대상 아님",
                "사유": (f"일반주택 {acq} 취득, 상속개시 {sd} — 상속개시 당시 보유한 일반주택" if ok else f"일반주택을 상속개시({sd}) 뒤에 취득 — 특례 대상 아님")
                        + ". 상속개시일부터 소급해 2년 이내 피상속인에게서 증여받은 주택(2018.2.13. 이후 증여분), 상속개시 당시 동일세대(동거봉양 합가 예외)는 별도 확인",
                "근거": b + ", 2018.2.13. 개정 부칙"}
    if kind == "동거봉양":
        b = f"{_D} 제155조제4항"
        if sd is None:
            return {"항목": "동거봉양 합가 특례", "판정": "확인 필요", "사유": "1주택 보유 60세 이상 직계존속(배우자의 직계존속 포함, 한 사람만 60세 이상이어도 됨, 요양급여 대상 60세 미만 포함)과 합가한 날(special_date)부터 10년 이내 먼저 양도하는 주택", "근거": b}
        if t < PARENT_DATE:
            return {"항목": "동거봉양 합가 특례", "판정": "확인 필요", "사유": f"합가 {sd} — 2019.2.12. 전 양도분은 그 당시 문언(기간·대상)을 대조하지 못함(미확인)", "근거": b + "(2018.2.13.·2019.2.12. 개정)"}
        lim = _add_years(sd, 10)
        return {"항목": "동거봉양 합가 특례", "판정": "충족" if t <= lim else "미충족", "사유": f"합가 {sd}부터 10년 이내({lim}까지) 먼저 양도하는 주택 — 직계존속 나이·주택 보유 요건은 별도 확인", "근거": b}
    if kind == "혼인":
        b = f"{_D} 제155조제5항"
        if sd is None:
            return {"항목": "혼인 합가 특례", "판정": "확인 필요", "사유": "각각 1주택을 보유한 사람끼리 혼인(또는 1주택 보유 직계존속을 동거봉양하는 무주택자가 1주택자와 혼인)한 날(special_date)부터 10년 이내 먼저 양도하는 주택", "근거": b}
        if t < MARRIAGE_DATE:
            return {"항목": "혼인 합가 특례", "판정": "확인 필요", "사유": f"혼인 {sd} — 2024.11.12. 전 양도분은 개정 전 제155조제5항의 기간이 적용(개정 부칙). 개정 전 문언은 대조하지 못함(미확인)", "근거": b + ", 2024.11.12. 개정 부칙"}
        lim = _add_years(sd, 10)
        return {"항목": "혼인 합가 특례", "판정": "충족" if t <= lim else "미충족", "사유": f"혼인 {sd}부터 10년 이내({lim}까지) 먼저 양도하는 주택(2024.11.12. 이후 양도분)", "근거": b + ", 2024.11.12. 개정 부칙"}
    return {"항목": "농어촌주택 특례", "판정": "확인 필요",
            "사유": "수도권 밖 읍(도시지역 제외)·면 지역의 상속주택(피상속인이 취득 후 5년 이상 거주), 이농주택(이농인이 5년 이상 거주), 귀농주택(취득일부터 5년 이내 일반주택 양도)과 일반주택을 1개씩 보유하고 일반주택을 양도하면 1주택으로 봄. "
                    "귀농주택 요건(제10항~제12항)과 특례적용신고서 제출(제13항)은 원문 확인",
            "근거": f"{_D} 제155조제7항~제14항"}
