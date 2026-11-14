"""사업소득 요건 안내 — 과세기간(2016~2026)별 사업소득 범위, 비과세, 주택임대소득 과세 방식과 간주임대료, 기장 의무, 성실신고확인 대상, 추계(기준경비율·단순경비율) 적용 대상, 사업용계좌·현금영수증 의무를 판정한다. Claude 작성(2026-11-14).

세액을 계산하지 않는다(계산 MCP의 estimated_business_income·housing_rental_income·housing_deemed_rent_income·income_tax).
대조한 원문(국세법령정보시스템 시행본 전문·부칙 — 법제처 Open API 점검 중이라 이쪽으로 받음, 원자료 raw_inc_business/):
  · 소득세법 2016.1.1.·2017.1.1.·2018.1.1.·2019.1.1.·2020.1.1.·2021.1.1.·2022.1.1.·2023.1.1.·2024.1.1.·2025.1.1.·2026.4.21. 시행본 제12조·제14조·제19조·제25조·제64조의2·제70조·제70조의2·제80조·제160조·제160조의5·제162조의3과 2026.4.21. 시행본에 실린 개정 부칙
  · 소득세법 시행령 2016.12.5.·2017.11.21.·2018.10.23.·2019.12.31.·2020.12.10.·2021.7.1.·2022.10.27.·2023.10.1.·2024.11.12.·2025.10.1.·2026.10.1. 시행본 제8조의2·제9조~제9조의5·제53조·제122조의2·제132조·제133조·제143조·제208조와 2026.10.1. 시행본에 실린 개정 부칙
과세기간에 따라 달라지는 것:
  · 1주택 주택임대 비과세의 고가주택 기준: 기준시가 9억원 초과 → 12억원 초과(2023.1.1. 이후 발생 소득, 법 2022.12.31. 개정 부칙 제2조·제11조)
  · 주택임대수입금액 2천만원 이하 비과세: 2018년 과세기간까지(법 제12조제2호나목 괄호, 2016.12.20. 개정으로 2016년 → 2018년 연장)
  · 2천만원 이하 분리과세(필요경비율 등록임대주택 60%·그 밖 50%, 다른 종합소득금액 2천만원 이하면 400만원·200만원 공제): 2019년 과세기간부터(법 2014.12.23. 개정 부칙 제1조·제4조, 2016.12.20. 개정)
  · 간주임대료 주택 수에서 빼는 소형주택: 2016년 85㎡·기준시가 3억원 이하 → 2017~2018년 60㎡·3억원 이하 → 2019~2026년 40㎡·2억원 이하(법 제25조제1항, 2016.12.20.·2018.12.31.·2021.12.8.·2023.12.31. 개정)
  · 간주임대료 2주택 기준(기준시가 12억원 초과 주택 2채, 보증금 합계 12억원 초과): 2026년 과세기간부터(법 2023.12.31. 개정 부칙 제1조제1호와 경과조치, 시행령 제53조제1항 2025.2.28. 신설·2026.1.1. 시행)
  · 성실신고확인대상 수입금액: 2017년까지 20억원·10억원·5억원 → 2018년부터 15억원·7억5천만원·5억원(시행령 2018.2.13. 개정 부칙 제2조제1항). 사업용 유형자산 양도 수입금액 제외는 2019년 과세기간 신고분부터(2020.2.11. 개정 부칙 — 시행 이후 제출하는 성실신고확인서)
  · 복식부기 판정의 직전 수입금액에서 사업용 유형자산 양도 수입금액 제외: 2020년 과세기간부터(시행령 2020.2.11. 개정 부칙)
  · 단순경비율: 계속사업자도 해당 과세기간 수입금액이 복식부기 기준 이상이면 제외 — 2019년 과세기간부터(시행령 2018.2.13. 개정 부칙 제13조). 인적용역 수리·기타 개인서비스업 3천600만원 기준 — 2023년 과세기간부터(2023.2.28. 개정 부칙)
  · 조림기간 5년 이상 임목 벌채·양도 비과세: 연 600만원 → 연 3천만원(2026.1.1. 이후 발생 소득, 법 2025.12.23. 개정 부칙 제2조)
  · 어로어업 비과세(소득금액 5천만원 이하): 2020년부터(법 제12조제2호사목 2019.12.31. 신설, 시행령 제9조의5 2020.2.11. 신설), 양식어업 추가: 2024년부터(법 2023.12.31. 개정 부칙 제2조제1항) — 그 전에는 어로·양어(2019년까지)·양어(2020~2023년)가 농어가부업소득 범위
  · 복식부기의무자 사업용 유형자산 양도소득을 사업소득에 포함: 2018년 과세기간부터(법 제19조제1항제20호, 2017.12.19. 개정 부칙 제2조)"""

_L, _D = "소득세법", "소득세법 시행령"
YEARS = range(2016, 2027)
VERIFIED = ("소득세법 2016.1.1.~2025.1.1.(각 연초)·2026.4.21. 시행본 전문과 개정 부칙, 소득세법 시행령 2016.12.5.·2017.11.21.·2018.10.23.·2019.12.31.·2020.12.10.·2021.7.1.·"
            "2022.10.27.·2023.10.1.·2024.11.12.·2025.10.1.·2026.10.1. 시행본 전문과 개정 부칙 — 국세법령정보시스템 조회(2026-11-14). 소득세법 시행규칙, 별표 3의2·3의3 업종표, "
            "조세특례제한법은 대조하지 않음")

# 업종 → (복식부기·성실신고·단순경비율 업종 구분(시행령 제208조제5항제2호 가·나·다목), 법 제19조제1항 호)
GROUPS = {
    "농업·임업·어업": ("가", "1"), "작물재배업": ("가", "1"), "광업": ("가", "2"), "도매·소매업": ("가", "7"), "부동산매매업": ("가", "12"),
    "비주거용 건물 건설업": ("가", "6"), "그 밖의 사업": ("가", "21"),
    "제조업": ("나", "3"), "숙박·음식점업": ("나", "9"), "전기·가스·증기·공기조절 공급업": ("나", "4"), "수도·하수·폐기물처리·원료재생업": ("나", "5"),
    "건설업": ("나", "6"), "주거용 건물 개발·공급업": ("나", "6·12"), "운수·창고업": ("나", "8"), "정보통신업": ("나", "10"), "금융·보험업": ("나", "11"), "상품중개업": ("나", "7"),
    "부동산임대업": ("다", "12"), "부동산업(매매업 제외)": ("다", "12"), "전문·과학·기술서비스업": ("다", "13"), "사업시설관리·사업지원·임대서비스업": ("다", "14"),
    "교육서비스업": ("다", "15"), "보건업·사회복지서비스업": ("다", "16"), "예술·스포츠·여가 관련 서비스업": ("다", "17"), "협회·단체": ("다", "18"),
    "수리·기타 개인서비스업": ("다", "18"), "수리·기타 개인서비스업(인적용역)": ("다", "18"), "가구내 고용활동": ("다", "19"),
}
# 비과세 업종(법 제12조제2호) — 한도를 넘으면 과세되는 업종 구분
EXEMPT = {"논·밭 임대(작물 생산)": None, "농어가부업": "가", "전통주 제조": "나", "조림(임목 벌채·양도)": "가", "연근해·내수면어업": "가", "양식어업": "가"}
NOT_BUSINESS = ("곡물·식량작물 재배업",)
INDUSTRIES = tuple(GROUPS) + tuple(EXEMPT) + NOT_BUSINESS

BOOK = {"가": 300_000_000, "나": 150_000_000, "다": 75_000_000}          # 시행령 제208조제5항제2호 — 2016~2026 같음
SIMPLE = {"가": 60_000_000, "나": 36_000_000, "다": 24_000_000}          # 시행령 제143조제4항제2호 — 2016~2026 같음
GROUP_NAME = {"가": "가목(농업·임업·어업, 광업, 도매·소매업, 부동산매매업 등)", "나": "나목(제조업, 숙박·음식점업, 건설업, 운수·창고업, 정보통신업, 금융·보험업 등)",
              "다": "다목(부동산임대업, 부동산업, 전문·과학·기술서비스업, 교육, 보건, 수리·기타 개인서비스업 등)"}


def faithful(y):
    """시행령 제133조제1항 — 성실신고확인대상 수입금액(이상)."""
    if y >= 2018:
        return {"가": 1_500_000_000, "나": 750_000_000, "다": 500_000_000}, f"{_D} 제133조제1항(2018.2.13. 개정 — 개정 부칙 제2조제1항: 시행일이 속하는 과세기간 소득분부터)"
    return {"가": 2_000_000_000, "나": 1_000_000_000, "다": 500_000_000}, f"{_D} 제133조제1항(2018.2.13. 개정 전)"


def one_house_cap(y):
    return 1_200_000_000 if y >= 2023 else 900_000_000


def small_house(y):
    """법 제25조제1항 괄호 — 간주임대료 주택 수에서 빼는 소형주택 기준."""
    if y == 2016:
        return "주거전용면적 1호(세대)당 85㎡ 이하이고 해당 과세기간 기준시가 3억원 이하", f"{_L} 제25조제1항(2014.1.1. 개정 — 2016.12.31.까지)"
    if y <= 2018:
        return "주거전용면적 1호(세대)당 60㎡ 이하이고 해당 과세기간 기준시가 3억원 이하", f"{_L} 제25조제1항(2016.12.20. 개정 — 2018.12.31.까지)"
    until = "2021.12.31." if y <= 2021 else "2023.12.31." if y <= 2023 else "2026.12.31."
    amend = "2018.12.31." if y <= 2021 else "2021.12.8." if y <= 2023 else "2023.12.31."
    return "주거전용면적 1호(세대)당 40㎡ 이하이고 해당 과세기간 기준시가 2억원 이하", f"{_L} 제25조제1항({amend} 개정 — {until}까지)"


_RULINGS = [
    {"문서번호": "사전-2016-법령해석소득-0360", "주제": "1주택 비과세", "내용": "겸용주택의 기준시가(당시 9억원) 초과 여부는 주택 부분(주택부수토지 포함)만으로 판단(요지·질의 확인)"},
    {"문서번호": "법규과-562(2010.4.2.)", "주제": "1주택 비과세", "내용": "비과세 주택임대소득의 주택 수에 국외 소재 주택을 포함하고 고가주택 기준은 국외주택에도 적용(요지·질의 확인, 2008년 전 시행령 대상)"},
    {"문서번호": "서면-2025-소득-3140(2026.2.20.)", "주제": "간주임대료", "내용": "40㎡ 이하·기준시가 2억원 이하 소형주택은 제12조제2호나목 비과세 판단의 주택 수에는 포함하되 제25조제1항 간주임대료는 계산하지 않음(요지·질의 확인)"},
    {"문서번호": "서면-2024-소득-1229(2024.5.7.)", "주제": "성실신고확인", "내용": "공동사업장은 1거주자로 보아 그 수입금액으로 판단하고, 단독사업장은 단독사업장 수입금액 합계로 따로 판단(관련 사례 소득세과-296 같은 취지, 질의 확인)"},
    {"문서번호": "사전-2020-법령해석소득-0473(2020.6.12.)", "주제": "성실신고확인", "내용": "성실신고확인대상 판단의 수입금액에 「보조금 관리에 관한 법률」 등에 따른 보조금을 포함(요지·질의 확인)"},
    {"문서번호": "소득세과-1068(2011.12.21.)", "주제": "단순경비율·기장", "내용": "직전연도 수입금액이 있으면 '해당 과세기간에 신규로 사업을 개시한 사업자'가 아니고 직전연도 수입금액으로 판단(요지·질의 확인)"},
    {"문서번호": "사전-2020-법령해석소득-0124(2020.4.3.)", "주제": "기장", "내용": "비과세 농어가부업소득의 수입금액은 직전·해당 과세기간 수입금액에 넣지 않음(요지 — 본문 조회 실패)"},
    {"문서번호": "서면-2025-법규소득-2393(2025.9.16.)", "주제": "분리과세 등록임대주택", "내용": "민간임대주택법에 따라 계산한 임대료 등 증가율(환산보증금)이 5%를 넘지 않으면 시행령 제122조의2 특례 적용 가능(요지 — 본문 조회 실패)"},
    {"문서번호": "기준-2020-법령해석소득-0004(2020.6.18.)", "주제": "분리과세 등록임대주택", "내용": "시행령 제122조의2제1항 요건을 갖추지 못한 국외주택 임대에는 제64조의2제2항 단서(60%·400만원) 적용 안 됨(요지 — 본문 조회 실패)"},
]


def _num(v, name, 문제, allow_none=True):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        문제.append(f"{name}={v!r} — 0 이상의 수")
        return None
    return v


def _won(v):
    return f"{v:,.0f}원"


def _scope(y, ind):
    """법 제19조 — 사업소득 범위."""
    if ind in NOT_BUSINESS:
        return {"항목": "사업소득 범위", "판정": "사업소득 아님", "사유": "작물재배업 중 곡물 및 기타 식량작물 재배업은 사업소득의 농업에서 제외(소득세가 과세되는 소득 종류에 없음)",
                "근거": f"{_L} 제19조제1항제1호 괄호"}
    if ind == "논·밭 임대(작물 생산)":
        return {"항목": "사업소득 범위", "판정": "사업소득(비과세)", "사유": "논·밭을 작물 생산에 이용하게 해서 생기는 소득 — 사업소득 중 비과세", "근거": f"{_L} 제12조제2호가목"}
    g = GROUPS.get(ind) or (EXEMPT[ind], "1" if ind != "전통주 제조" else "3")
    ho = g[1]
    note = ""
    if ind in ("부동산임대업", "사업시설관리·사업지원·임대서비스업"):
        note = " 2018년까지는 '부동산업 및 임대업'(제12호), 2019년부터 부동산업(제12호)과 임대서비스업(제14호)으로 나뉨(2018.12.31. 개정 — 한국표준산업분류 개정 반영)."
    if ind == "주거용 건물 개발·공급업":
        note = " 한국표준산업분류로 건설업(제6호) 또는 부동산업(제12호) 중 어디에 속하는지 확인."
    r = f"법 제19조제1항제{ho}호 업종에서 생기는 소득.{note} 사업의 범위는 이 법에 특별한 규정이 없으면 한국표준산업분류에 따름(제19조제3항)."
    if y >= 2018:
        r += " 복식부기의무자가 차량·운반구 등 사업용 유형자산을 양도해 생긴 소득(양도소득 대상 부동산 제외)도 사업소득(제20호, 2018년 과세기간부터)."
    if y >= 2019:
        r += " 제21조제1항제8호의2 기타소득으로 원천징수하거나 확정신고한 경우는 사업소득에서 제외(제19조제1항 단서, 2019년부터)."
    return {"항목": "사업소득 범위", "판정": "사업소득", "사유": r, "근거": f"{_L} 제19조제1항·제3항" + (", 2017.12.19. 개정 부칙 제2조" if y >= 2018 else "")}


def _exempt(y, ind, revenue_curr, exempt_income):
    """법 제12조제2호 가·다~사목과 시행령 제9조~제9조의5."""
    out = []
    if ind == "작물재배업":
        b = f"{_L} 제12조제2호바목, {_D} 제9조의4"
        if revenue_curr is None:
            out.append({"항목": "작물재배업 비과세", "판정": "확인 필요", "사유": "해당 과세기간 작물재배업 수입금액 합계 10억원 이하이면 비과세 — revenue_curr 입력", "근거": b})
        else:
            ok = revenue_curr <= 1_000_000_000
            out.append({"항목": "작물재배업 비과세", "판정": "비과세" if ok else "확인 필요",
                        "사유": f"수입금액 {_won(revenue_curr)} — 10억원 " + ("이하" if ok else "초과: 비과세 범위 계산(소득 계산은 시행규칙)은 원문 확인 — 시행규칙 미대조"), "근거": b})
        return out
    if ind not in EXEMPT or ind == "논·밭 임대(작물 생산)":
        return out
    if ind == "농어가부업":
        cap, b = 30_000_000, f"{_L} 제12조제2호다목, {_D} 제9조제1항(2016.2.17. 개정 반영 시행본부터 연 3천만원)"
        what = "농·어민의 축산·고공품 제조·민박·음식물 판매·특산물 제조·전통차 제조 등" + (" ·어로·양어" if y <= 2019 else " ·양어" if y <= 2023 else "") + " 소득. 별표 1 농가부업규모 축산은 금액과 관계없이 비과세"
    elif ind == "전통주 제조":
        cap, b = 12_000_000, f"{_L} 제12조제2호라목, {_D} 제9조의2"
        what = "수도권 밖 읍·면 지역에서 전통주 등을 제조해 생긴 소득"
    elif ind == "조림(임목 벌채·양도)":
        cap = 30_000_000 if y >= 2026 else 6_000_000
        b = f"{_L} 제12조제2호마목" + (", 2025.12.23. 개정 부칙 제2조, " if y >= 2026 else ", ") + f"{_D} 제9조의3"
        what = "조림기간 5년 이상인 임지의 임목 벌채·양도 소득" + (" (2026.1.1. 이후 발생 소득 연 3천만원)" if y >= 2026 else " (2025년까지 연 600만원)")
    else:  # 연근해·내수면어업, 양식어업
        if y < 2020 or (ind == "양식어업" and y < 2024):
            prior = "농어가부업소득(어로·양어)" if y <= 2019 else "농어가부업소득(양어)"
            return [{"항목": f"{ind} 비과세", "판정": "확인 필요",
                     "사유": f"{y}년에는 제12조제2호사목 " + ("신설 전(2020년부터)" if y < 2020 else "에 양식어업이 없음(2024년부터)") + f" — {prior} 범위에서 연 3천만원 한도로 판단(ind='농어가부업')",
                     "근거": f"{_D} 제9조제1항" + ("(2020.2.11. 개정 전)" if y <= 2019 else "(2024.2.29. 개정 전)")}]
        cap, b = 50_000_000, f"{_L} 제12조제2호사목, {_D} 제9조의5" + (", 2023.12.31. 개정 부칙 제2조제1항" if ind == "양식어업" else "")
        what = "한국표준산업분류의 연근해어업·내수면어업" + ("·양식어업" if y >= 2024 else "") + " 소득"
    if exempt_income is None:
        return [{"항목": f"{ind} 비과세", "판정": "확인 필요", "사유": f"{what} — 소득금액 합계 연 {_won(cap)} 이하이면 비과세(exempt_income 입력)", "근거": b}]
    ok = exempt_income <= cap
    return [{"항목": f"{ind} 비과세", "판정": "비과세" if ok else "확인 필요",
             "사유": f"{what} — 소득금액 {_won(exempt_income)}, 한도 연 {_won(cap)} " + ("이하" if ok else "초과: 한도를 넘는 부분만 과세하는지 전부 과세하는지는 원문·해석 확인"), "근거": b}]


def _housing(y, house_count, house_prices, overseas_house, small_house_count, deposit_total, rental_revenue, registered_rental, other_income):
    out = []
    b12 = f"{_L} 제12조제2호나목, {_D} 제8조의2"
    cap = one_house_cap(y)
    taxable = None
    # 1. 비과세
    if house_count is not None:
        if house_count == 1:
            p = house_prices[0] if house_prices else None
            if overseas_house:
                taxable = True
                out.append({"항목": "주택임대 — 1주택 비과세", "판정": "과세", "사유": "국외에 있는 주택의 임대소득은 1주택이어도 비과세에서 제외", "근거": b12})
            elif p is None:
                out.append({"항목": "주택임대 — 1주택 비과세", "판정": "확인 필요", "사유": f"1주택 — 기준시가가 {_won(cap)}를 넘으면 과세(house_prices 입력). 과세기간 종료일(양도하면 양도일) 기준", "근거": b12})
            else:
                taxable = p > cap
                out.append({"항목": "주택임대 — 1주택 비과세", "판정": "과세" if taxable else "비과세",
                            "사유": f"기준시가 {_won(p)} — 기준 {_won(cap)} " + ("초과" if taxable else "이하(같으면 비과세)") + " (과세기간 종료일 또는 양도일 기준, 시행령 제8조의2제5항). "
                                    + ("2023.1.1. 이후 발생 소득 12억원" if y >= 2023 else "2022년까지 9억원 — 2023년부터 12억원"),
                            "근거": b12 + (", 법 2022.12.31. 개정 부칙 제2조·제11조" if y >= 2022 else "")})
        elif house_count == 0:
            out.append({"항목": "주택임대 — 주택 수", "판정": "해당 없음", "사유": "주택 0채 — 주택임대소득 판정 없음", "근거": b12})
        else:
            taxable = True
            out.append({"항목": "주택임대 — 1주택 비과세", "판정": "해당 없음", "사유": f"{house_count}주택 — 1주택 비과세 대상 아님(주택 수는 본인·배우자 합산, 다가구주택은 1주택, 공동소유는 최대지분자"
                        + (" — 2020년부터 소수지분자도 임대수입 연 600만원 이상이거나 기준시가 " + ("12억원" if y >= 2023 else "9억원") + " 초과 주택 지분 30% 초과면 포함" if y >= 2020 else "") + ")",
                        "근거": f"{_D} 제8조의2제3항" + (", 2020.2.11. 개정 부칙" if y >= 2020 else "")})
    # 2. 수입금액 2천만원 기준
    if rental_revenue is not None and (taxable or house_count is None):
        if y <= 2018:
            if rental_revenue <= 20_000_000:
                out.append({"항목": "주택임대 — 2천만원 이하", "판정": "비과세",
                            "사유": f"주택임대수입금액 {_won(rental_revenue)} — 2018년 과세기간까지는 주거용 건물 임대업 수입금액 합계 2천만원 이하이면 주택 수와 관계없이 비과세",
                            "근거": f"{_L} 제12조제2호나목 괄호(2016.12.20. 개정), {_D} 제8조의2제6항"})
            else:
                out.append({"항목": "주택임대 — 과세 방식", "판정": "종합과세", "사유": f"주택임대수입금액 {_won(rental_revenue)} — 2천만원 초과(분리과세는 2019년부터)", "근거": f"{_L} 제12조제2호나목"})
        elif rental_revenue <= 20_000_000:
            reg = False if overseas_house else registered_rental
            rate, ded = ("60%", "400만원") if reg else ("50%", "200만원")
            dtxt = ("" if other_income is None else
                    f" 분리과세 주택임대소득 외 종합소득금액 {_won(other_income)} — " + (f"2천만원 이하라 {ded} 추가 공제." if other_income <= 20_000_000 else "2천만원 초과라 추가 공제 없음."))
            out.append({"항목": "주택임대 — 과세 방식", "판정": "분리과세 선택 가능",
                        "사유": f"주택임대수입금액 {_won(rental_revenue)} — 2천만원 이하: 종합과세와 분리과세(14%) 중 선택. 분리과세 필요경비율 "
                                + (f"{rate}(" + ("등록임대주택" if reg else "등록임대주택 아님") + ")" if reg is not None else "등록임대주택 60%·그 밖 50%(registered_rental 입력)")
                                + f", 다른 종합소득금액 2천만원 이하면 " + (ded if reg is not None else "400만원·200만원") + " 추가 공제." + dtxt
                                + " 등록임대주택은 민간임대주택법 등록 + 법 제168조 사업자등록 + 임대료 등 증가율 5% 이하(시행령 제122조의2제1항, 2020.2.11.·2020.10.7. 개정으로 유형 제한)."
                                + (" 감면·60% 적용 후 4년·10년 의무임대 미충족이면 추징(제64조의2제3항)." if reg else "")
                                + (" 국외주택은 시행령 제122조의2제1항 요건을 갖출 수 없어 60%·400만원 특례 대상 아님(기준-2020-법령해석소득-0004)." if overseas_house else ""),
                        "근거": f"{_L} 제14조제3항제7호, 제64조의2제1항·제2항, {_D} 제122조의2, 법 2014.12.23. 개정 부칙 제4조(2016.12.20. 개정)"})
        else:
            out.append({"항목": "주택임대 — 과세 방식", "판정": "종합과세", "사유": f"주택임대수입금액 {_won(rental_revenue)} — 2천만원 초과라 분리과세 선택 불가", "근거": f"{_L} 제14조제3항제7호"})
    # 3. 간주임대료
    if house_count is not None and house_count >= 2 and deposit_total is not None:
        crit, cb = small_house(y)
        small = small_house_count or 0
        n = house_count - small
        basis = f"{cb}, {_D} 제53조"
        why = f"주택 {house_count}채 중 소형주택({crit}) {small}채 제외 {n}채, 보증금 합계 {_won(deposit_total)}"
        if n >= 3 and deposit_total > 300_000_000:
            out.append({"항목": "주택임대 — 간주임대료", "판정": "대상", "사유": why + " — 3주택 이상이고 보증금 합계 3억원 초과(제25조제1항" + ("제1호" if y >= 2026 else "") + ")", "근거": basis})
        elif y >= 2026:
            prices = [p for p in (house_prices or [])]
            if len(prices) < house_count:
                out.append({"항목": "주택임대 — 간주임대료", "판정": "확인 필요" if deposit_total > 1_200_000_000 else "대상 아님",
                            "사유": why + (" — 3주택 기준 미충족. 2026년부터 기준시가 12억원 초과 주택 2채이고 보증금 합계 12억원 초과도 대상(제2호) — house_prices를 주택 수만큼 입력"
                                           if deposit_total > 1_200_000_000 else " — 3주택 기준 미충족, 보증금 12억원 이하라 2주택 기준(제2호)도 미충족"),
                            "근거": basis + ", 법 2023.12.31. 개정 부칙 제1조제1호, 시행령 제53조제1항"})
            else:
                high = sum(1 for p in prices if p > 1_200_000_000)
                hit = high >= 2 and deposit_total > 1_200_000_000
                out.append({"항목": "주택임대 — 간주임대료", "판정": "대상" if hit else "대상 아님",
                            "사유": why + f" — 기준시가 12억원 초과 주택 {high}채, 2026년부터 2주택(12억원 이하 주택은 주택 수에서 뺌)이고 보증금 합계 12억원 초과면 대상(제2호)",
                            "근거": basis + ", 법 2023.12.31. 개정 부칙 제1조제1호, 시행령 제53조제1항"})
        else:
            out.append({"항목": "주택임대 — 간주임대료", "판정": "대상 아님", "사유": why + " — 3주택 이상이고 보증금 합계 3억원 초과일 때만 대상(같으면 대상 아님). 2주택 기준은 2026년 과세기간부터",
                        "근거": basis})
    return out


def _bookkeeping(y, g, ind, revenue_prev, new_business, professional, asset_sale_prev):
    b = f"{_L} 제160조제2항·제3항, {_D} 제208조제5항"
    if professional:
        return {"항목": "기장 의무", "판정": "복식부기의무자", "사유": "의료업·수의업·약국(시행령 제" + ("147조의2" if y >= 2020 else "147조의3") + ")과 부가가치세법 시행령 제109조제2항제7호 전문직 사업자는 수입금액과 관계없이 간편장부대상자에서 제외",
                "근거": b + " 단서"}, "복식부기의무자"
    if new_business:
        return {"항목": "기장 의무", "판정": "간편장부대상자", "사유": "해당 과세기간에 신규로 사업을 개시한 사업자(직전 과세기간 수입금액이 있으면 신규 아님 — 소득세과-1068)", "근거": b + "제1호"}, "간편장부대상자"
    if revenue_prev is None:
        return {"항목": "기장 의무", "판정": "확인 필요", "사유": f"직전 과세기간 수입금액(revenue_prev)이 {_won(BOOK[g])} 미만이면 간편장부대상자 — {GROUP_NAME[g]}", "근거": b + "제2호"}, None
    base = revenue_prev
    adj = ""
    if asset_sale_prev:
        if y >= 2020:
            base = revenue_prev - asset_sale_prev
            adj = f" (사업용 유형자산 양도 수입금액 {_won(asset_sale_prev)} 제외 — 2020년 과세기간부터, 시행령 2020.2.11. 개정 부칙)"
        else:
            adj = " (사업용 유형자산 양도 수입금액 제외 규정은 2020년 과세기간부터 — 이 해에는 포함)"
    easy = base < BOOK[g]
    kind = "간편장부대상자" if easy else "복식부기의무자"
    return {"항목": "기장 의무", "판정": kind,
            "사유": f"직전 과세기간 수입금액 {_won(base)}{adj} — {GROUP_NAME[g]} 기준 {_won(BOOK[g])} " + ("미만" if easy else "이상")
                    + ". 업종 겸영·사업장 2곳 이상이면 주업종 기준 환산(시행령 제208조제7항)" + (" — 인적용역도 기장 기준은 다목" if ind == "수리·기타 개인서비스업(인적용역)" else ""),
            "근거": b + "제2호"}, kind


def _faithful(y, g, revenue_curr, business_service, asset_sale_curr):
    th, b = faithful(y)
    if business_service and g in ("가", "나"):
        g2, note = "다", " — 가·나목 업종 중 별표 3의3 사업서비스업은 다목 기준(제133조제1항 단서)"
    else:
        g2, note = g, ""
    if revenue_curr is None:
        return {"항목": "성실신고확인", "판정": "확인 필요", "사유": f"해당 과세기간 수입금액(revenue_curr)이 {_won(th[g2])} 이상이면 대상{note}", "근거": f"{_L} 제70조의2, {b}"}
    base, adj = revenue_curr, ""
    if asset_sale_curr:
        if y >= 2019:
            base = revenue_curr - asset_sale_curr
            adj = f" (사업용 유형자산 양도 수입금액 {_won(asset_sale_curr)} 제외 — 2020.2.11. 개정, 그 이후 제출하는 확인서부터)"
        else:
            adj = " (사업용 유형자산 양도 수입금액 제외는 2019년 과세기간 신고분부터 — 이 해에는 포함)"
    hit = base >= th[g2]
    return {"항목": "성실신고확인", "판정": "대상" if hit else "대상 아님",
            "사유": f"해당 과세기간 수입금액 {_won(base)}{adj} — 기준 {_won(th[g2])} " + ("이상" if hit else "미만") + note
                    + (". 대상이면 세무사 등의 성실신고확인서를 붙여 다음 해 5.1.~6.30.에 확정신고(제70조의2제2항)" if hit else "")
                    + ". 공동사업장은 1거주자로 따로 판단(서면-2024-소득-1229)",
            "근거": f"{_L} 제70조의2, {b}" + (", 2020.2.11. 개정 부칙" if asset_sale_curr and y >= 2019 else "")}


def _simple(y, g, ind, revenue_prev, revenue_curr, new_business, professional):
    b = f"{_D} 제143조제3항·제4항·제7항"
    sg = "나" if (ind == "수리·기타 개인서비스업(인적용역)" and y >= 2023) else g
    if professional:
        return {"항목": "추계 — 경비율", "판정": "기준경비율", "사유": "의료업·수의업·약국과 전문직 사업자(부가가치세법 시행령 제109조제2항제7호)는 단순경비율 적용대상자에서 제외", "근거": f"{_D} 제143조제7항제1호·제2호"}
    why_extra = " 현금영수증가맹점 미가입(가입 의무자), 신용카드·현금영수증 발급 거부 등으로 3회 이상·100만원 이상 또는 5회 이상 통보받은 해는 단순경비율 제외(제7항제3호·제4호)."
    if new_business:
        if revenue_curr is None:
            return {"항목": "추계 — 경비율", "판정": "확인 필요", "사유": f"신규 사업자 — 해당 과세기간 수입금액이 {_won(BOOK[g])} 미만이면 단순경비율(revenue_curr 입력)", "근거": b}
        ok = revenue_curr < BOOK[g]
        return {"항목": "추계 — 경비율", "판정": "단순경비율" if ok else "기준경비율",
                "사유": f"신규 사업자 — 해당 과세기간 수입금액 {_won(revenue_curr)}, 복식부기 기준 {_won(BOOK[g])} " + ("미만" if ok else "이상") + "." + why_extra, "근거": b}
    if revenue_prev is None:
        return {"항목": "추계 — 경비율", "판정": "확인 필요", "사유": f"직전 과세기간 수입금액이 {_won(SIMPLE[sg])} 미만이면 단순경비율(revenue_prev 입력)", "근거": b}
    prev_ok = revenue_prev < SIMPLE[sg]
    reason = f"직전 과세기간 수입금액 {_won(revenue_prev)} — 단순경비율 기준 {_won(SIMPLE[sg])} " + ("미만" if prev_ok else "이상")
    if ind == "수리·기타 개인서비스업(인적용역)":
        reason += " (인적용역은 2023년 과세기간부터 3천600만원 기준, 2022년까지 2천400만원 — 시행령 2023.2.28. 개정 부칙)"
    curr_ok = True
    if y >= 2019 and prev_ok:
        if revenue_curr is None:
            return {"항목": "추계 — 경비율", "판정": "확인 필요", "사유": reason + f". 2019년부터는 해당 과세기간 수입금액도 {_won(BOOK[g])} 미만이어야 함(revenue_curr 입력)",
                    "근거": b + ", 2018.2.13. 개정 부칙 제13조"}
        curr_ok = revenue_curr < BOOK[g]
        reason += f"; 해당 과세기간 수입금액 {_won(revenue_curr)} — 복식부기 기준 {_won(BOOK[g])} " + ("미만" if curr_ok else "이상(2019년부터 단순경비율 제외)")
    elif y <= 2018 and prev_ok:
        reason += " (2018년까지 계속사업자는 해당 과세기간 수입금액 요건 없음)"
    ok = prev_ok and curr_ok
    return {"항목": "추계 — 경비율", "판정": "단순경비율" if ok else "기준경비율", "사유": reason + "." + why_extra,
            "근거": b + (", 2018.2.13. 개정 부칙 제13조" if y >= 2019 else "") + (", 2023.2.28. 개정 부칙" if sg != g else "")}


def _estimate(kind):
    r = ("장부가 없거나 중요한 부분이 미비·허위이면 추계결정(법 제80조제3항 단서, 시행령 제143조제1항). 기준경비율 방법은 수입금액 − 증빙 있는 매입비용·사업용 자산 임차료·인건비 − 수입금액 × 기준경비율"
         "(복식부기의무자는 기준경비율의 2분의 1), 단순경비율 방법은 수입금액 − 수입금액 × 단순경비율.")
    if kind == "복식부기의무자":
        r += " 복식부기의무자가 재무상태표·손익계산서 등(제70조제4항제3호)을 내지 않고 추계로 신고하면 확정신고를 하지 않은 것으로 봄 — 무신고가산세는 국세기본법(미대조)."
    elif kind == "간편장부대상자":
        r += " 간편장부대상자가 장부 없이 추계신고하면 무기장가산세(제81조의5) — 신규 사업자, 직전 과세기간 수입금액 4천800만원 미만 등 소규모사업자(시행령 제132조제4항)는 제외."
    return {"항목": "추계 신고·결정", "판정": "가능(조건부)" if kind != "복식부기의무자" else "가능하나 무신고 간주", "사유": r,
            "근거": f"{_L} 제70조제4항, 제80조제3항, 제81조의5, {_D} 제143조, 제132조제4항"}


def _accounts(kind):
    out = []
    if kind == "복식부기의무자":
        out.append({"항목": "사업용계좌", "판정": "의무", "사유": "금융회사를 통한 대금 결제와 인건비·임차료 지급·수령은 사업용계좌 사용. 복식부기의무자에 해당하는 과세기간 개시일(사업 개시와 동시에 해당하면 다음 과세기간 개시일)부터 6개월 이내 신고. "
                    "미사용 금액·미신고 거래금액의 1천분의 2 가산세(제81조의8 — 2026.4.21. 시행본 문언, 연도별 대조 안 함)",
                    "근거": f"{_L} 제160조의5, 제81조의8"})
    elif kind == "간편장부대상자":
        out.append({"항목": "사업용계좌", "판정": "의무 없음", "사유": "사업용계좌 신고·사용 의무는 복식부기의무자에게만(법 제160조의5제1항)", "근거": f"{_L} 제160조의5"})
    out.append({"항목": "현금영수증", "판정": "업종별 확인", "사유": "주로 소비자에게 공급하는 업종(시행령 별표 3의2)으로 요건에 해당하면 그날부터 60일 이내 현금영수증가맹점 가입, 가맹점은 요청 시 발급 거부 금지. "
                "의무발행업종(별표 3의3)은 건당 10만원 이상 현금 거래면 요청이 없어도 발급(사업자에게 계산서·세금계산서를 발급한 경우 제외). 업종표는 연도별로 바뀌어 별표를 확인(미대조)",
                "근거": f"{_L} 제162조의3, {_D} 제210조의3"})
    return out


def guide(year=None, industry=None, revenue_prev=None, revenue_curr=None, new_business=None, professional=None, business_service=None,
          asset_sale_prev=None, asset_sale_curr=None, exempt_income=None, house_count=None, house_prices=None, overseas_house=None,
          small_house_count=None, deposit_total=None, rental_revenue=None, registered_rental=None, other_income=None):
    if year is None:
        return {"과세기간별 변화": [x.strip() for x in __doc__.split("과세기간에 따라 달라지는 것:")[1].strip().split("\n")],
                "업종 구분": {"가목": [k for k, v in GROUPS.items() if v[0] == "가"], "나목": [k for k, v in GROUPS.items() if v[0] == "나"],
                           "다목": [k for k, v in GROUPS.items() if v[0] == "다"], "비과세 업종": list(EXEMPT), "사업소득 아님": list(NOT_BUSINESS)},
                "기준 금액(2016~2026 같음)": {"복식부기(직전 수입금액 이상)": {"가": BOOK["가"], "나": BOOK["나"], "다": BOOK["다"]},
                                       "단순경비율(직전 수입금액 미만)": {"가": SIMPLE["가"], "나": SIMPLE["나"], "다": SIMPLE["다"]}},
                "입력": "year(2016~2026)와 industry, 수입금액(직전·해당), 주택임대 사실(house_count, house_prices, deposit_total, rental_revenue, registered_rental)",
                "확인 시행본": VERIFIED}
    문제 = []
    if isinstance(year, bool) or not isinstance(year, int) or year not in YEARS:
        문제.append(f"year={year!r} — 2016~2026 정수")
    if industry is not None and industry not in INDUSTRIES:
        문제.append(f"industry={industry!r} — {' | '.join(INDUSTRIES)}")
    nums = {}
    for k, v in (("revenue_prev", revenue_prev), ("revenue_curr", revenue_curr), ("asset_sale_prev", asset_sale_prev), ("asset_sale_curr", asset_sale_curr),
                 ("exempt_income", exempt_income), ("house_count", house_count), ("small_house_count", small_house_count), ("deposit_total", deposit_total),
                 ("rental_revenue", rental_revenue), ("other_income", other_income)):
        nums[k] = _num(v, k, 문제)
    for k, v in (("new_business", new_business), ("professional", professional), ("business_service", business_service), ("overseas_house", overseas_house),
                 ("registered_rental", registered_rental)):
        if v is not None and not isinstance(v, bool):
            문제.append(f"{k}={v!r} — true | false")
    if house_count is not None and not isinstance(house_count, bool) and isinstance(house_count, float) and not house_count.is_integer():
        문제.append("house_count — 정수")
    prices = None
    if house_prices is not None:
        if not isinstance(house_prices, list) or any(isinstance(p, bool) or not isinstance(p, (int, float)) or p < 0 for p in house_prices):
            문제.append("house_prices — 주택별 기준시가(원) 목록")
        else:
            prices = house_prices
    if nums["small_house_count"] and nums["house_count"] is not None and nums["small_house_count"] > nums["house_count"]:
        문제.append("small_house_count가 house_count보다 큼")
    if nums["asset_sale_prev"] and nums["revenue_prev"] is not None and nums["asset_sale_prev"] > nums["revenue_prev"]:
        문제.append("asset_sale_prev가 revenue_prev보다 큼")
    if nums["asset_sale_curr"] and nums["revenue_curr"] is not None and nums["asset_sale_curr"] > nums["revenue_curr"]:
        문제.append("asset_sale_curr가 revenue_curr보다 큼")
    if 문제:
        return {"error": "입력 확인 필요", "문제": 문제}
    y = year
    hc = int(nums["house_count"]) if nums["house_count"] is not None else None
    if industry is None and hc is not None:
        industry = "부동산임대업"
    out = {"과세기간": y, "업종": industry}
    판정 = []
    group = None
    if industry:
        판정.append(_scope(y, industry))
        판정.extend(_exempt(y, industry, nums["revenue_curr"], nums["exempt_income"]))
        if industry in GROUPS:
            group = GROUPS[industry][0]
        elif industry in EXEMPT and EXEMPT[industry]:
            group = EXEMPT[industry]
        if group:
            out["업종 구분"] = GROUP_NAME[group] + (" — 비과세 한도를 넘어 과세되는 경우" if industry in EXEMPT or industry == "작물재배업" else "")
    판정.extend(_housing(y, hc, prices, overseas_house, nums["small_house_count"], nums["deposit_total"], nums["rental_revenue"], registered_rental, nums["other_income"]))
    kind = None
    if group and industry != "논·밭 임대(작물 생산)":
        item, kind = _bookkeeping(y, group, industry, nums["revenue_prev"], new_business, professional, nums["asset_sale_prev"])
        판정.append(item)
        판정.append(_faithful(y, group, nums["revenue_curr"], business_service, nums["asset_sale_curr"]))
        판정.append(_simple(y, group, industry, nums["revenue_prev"], nums["revenue_curr"], new_business, professional))
        판정.append(_estimate(kind))
        판정.extend(_accounts(kind))
    out["판정"] = 판정
    th, _ = faithful(y)
    out["그 해 기준"] = {
        "1주택 비과세 고가주택(기준시가 초과)": one_house_cap(y),
        "주택임대 2천만원 이하": "비과세" if y <= 2018 else "분리과세 선택(필요경비율 60%·50%, 공제 400만원·200만원)",
        "간주임대료 소형주택(주택 수 제외)": small_house(y)[0],
        "간주임대료 2주택 기준": "기준시가 12억원 초과 2주택 + 보증금 12억원 초과" if y >= 2026 else "없음(2026년부터)",
        "성실신고확인(해당 과세기간 수입금액 이상)": th,
        "복식부기(직전 수입금액 이상)": BOOK, "단순경비율(직전 수입금액 미만)": SIMPLE,
        "조림 임목 비과세 한도": 30_000_000 if y >= 2026 else 6_000_000,
    }
    out["한계"] = [
        "업종은 한국표준산업분류에 따른 사실 판단 — 입력값으로 봄. 업종 겸영·사업장 2곳 이상의 주업종 환산(시행령 제208조제7항)과 영세사업 특례 금액(제208조제5항제2호 단서, 시행규칙)은 계산하지 않음(시행규칙 미대조)",
        "주택 수는 본인·배우자 합산, 다가구주택·공동소유·전대 규칙(시행령 제8조의2제3항)으로 센 값을 입력. 간주임대료의 '해당 주택의 보증금등 합계'는 deposit_total을 그대로 씀(제2호의 12억원 초과 주택분만 합산하는지는 원문 확인)",
        "시행령 제8조의2(공동소유 소수지분 기준시가 9억원 → 12억원)의 2023.2.28. 개정에는 별도 적용례가 없음 — 법 제12조제2호나목 12억원(2023.1.1. 이후 발생 소득)에 맞춰 안내",
        "비과세 한도를 넘는 농어가부업·전통주·어로어업 소득과 10억원 초과 작물재배업 소득의 과세 범위, 별표 1 농가부업규모 축산은 판정하지 않음(시행규칙·별표 미대조). 2016.2.17. 개정 전 농어가부업 한도 문언은 미대조(2016년 과세기간은 개정 부칙 제2조로 개정 규정 적용)",
        "현금영수증 업종(별표 3의2·3의3), 사업용계좌 가산세의 연도별 문언, 무신고·무기장 가산세율(국세기본법), 성실신고확인비용 세액공제(조세특례제한법 제126조의6)는 대조하지 않음(미확인)",
        "판정의 '관련 해석'은 국세법령정보시스템 문서 요지·질의 부분까지 확인 — 일부는 본문 조회 실패로 요지만(표시)",
        "세액·소득금액은 계산하지 않음",
    ]
    out["관련 해석"] = _RULINGS
    out["다음 단계"] = (f"원문: law_article(law_name='{_L}', article='제12조', as_of='{y}-12-31') · 제19조·제25조·제64조의2·제70조의2·제160조 · {_D} 제133조·제143조·제208조 · 부칙: article_addenda · "
                    "해석: search_tax_rulings('성실신고확인대상 수입금액') · 계산: 계산 MCP estimated_business_income(추계 기준·단순경비율), housing_rental_income(주택임대 분리·종합과세 비교), "
                    "housing_deemed_rent_income(간주임대료), income_tax(종합소득세율)")
    out["확인 시행본"] = VERIFIED
    return out
