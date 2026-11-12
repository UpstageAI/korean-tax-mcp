"""고용 세액공제 요건 안내(조세특례제한법 제29조의7 고용증대, 제29조의8 통합고용) — 과세연도별 요건과 사실관계 대조. Claude 작성(2026-11-12).

세액을 계산하지 않는다. 그 과세연도 말 시행본의 문언에 사실을 대어 요건별 충족 여부와 근거 조문을 돌려준다.
조문 대조(2018~2025 각 연말과 2026.11.12. 시행본): 법 제29조의7, 제29조의8, 제127조제4항·제11항, 제144조제1항, 시행령 제26조의7, 제26조의8, 제23조제10항~제13항, 제29조제3항, 제11조의2제8항.
개정 부칙: 법률 제16009호(2018.12.24.) 제13조, 2019.12.31. 제17조, 2020.12.29. 제35조, 2021.3.16. 제2조, 2025.3.14. 제6조, 2025.12.23. 제34조, 시행령 2019.2.12.·2021.2.17. 제2조, 2025.2.28. 제9조, 2025.12.31. 제2조, 2026.2.27. 제11조.
연도별로 달라진 것:
  · 제도: 2018~2022년 고용증대만, 2023·2024년 고용증대와 통합고용 중 선택(통합고용은 고용증대 공제를 받지 않은 경우만 — 제127조제11항), 2025년 새 증가분은 통합고용만, 2026년부터 통합고용 계산 방식 변경(직전 3개 과세연도 대비)
  · 청년 나이: 고용증대 15~29세, 통합고용 15~34세(병역 기간은 6년까지 빼고 계산). 기간제·단시간·파견 근로자와 청소년유해업소 청소년은 청년에서 제외
  · 청년등 범위: 2018년 청년·장애인·상이자, 2019년부터 5·18민주화운동부상자·고엽제후유의증환자(장애등급 판정), 2021년부터 근로계약 체결일 현재 60세 이상, 2023년 통합고용에 경력단절 여성, 2025년부터 경력단절 근로자·북한이탈주민
  · 상시근로자 범위: 2025년까지 시행령 제23조제10항(근로계약기간 1년 미만, 1개월 소정근로시간 60시간 미만 단시간근로자, 임원, 최대주주와 그 가족 등 제외). 2026년 통합고용은 시행령 제26조의8제2항(근로기간 1년 미만, 월 평균 근로시간 60시간 미만 단시간근로자 등 제외)
  · 인원 계산: 2025년까지 매월 말 현재 인원의 합 ÷ 과세연도 개월 수. 2026년 통합고용은 근로자별 근무개월 수 ÷ 과세연도 개월 수의 합
  · 창업감면과의 관계(제127조제4항 단서): 2022년까지 제6조제7항 감면과 고용증대 배제, 2023년부터 통합고용(제29조의8제1항)도 배제, 2025.1.1. 이후 창업분은 제6조 감면 전체와 배제
  · 이월공제: 2019년까지 신고분 5년, 2021.1.1. 이후 신고분부터 10년(제144조제1항, 2020.12.29. 개정 부칙 제35조)
  · 외국인 근로자: 소득세법의 거주자이면 상시근로자에 포함(서면-2024-소득-0033, 법규과-803)
  · 2025년 통합고용 최초 공제분: 청년 유지 기간(2025년 계약 3년, 중소·중견기업이 아니면 2년)과 근무개월 수 방식 인원 계산을 적용(시행령 2026.2.27. 개정 부칙 제11조)
  · 2026년 통합고용: 중소기업이 아니면 최소고용증가인원수(중견기업 5명, 그 밖 10명)를 넘게 늘어야 공제. 2024·2025년 증가분의 2차·3차 공제와 추가 납부는 종전 규정(2025.12.23. 개정 부칙 제34조)"""

from datetime import date

YEAR_MIN, YEAR_MAX = 2018, 2026
CREDITS = ("고용증대", "통합고용")
SIZES = ("중소기업", "중견기업", "일반")
DISABLED_KINDS = ("장애인", "상이자", "5·18민주화운동부상자", "고엽제후유의증환자")
_L, _D = "조세특례제한법", "조세특례제한법 시행령"
_RULINGS = [
    {"문서번호": "서면-2024-소득-0033", "제도": "공통", "내용": "외국인 근로자도 거주자에 해당하면 상시근로자에 포함하고 거주자가 되는 날부터 상시근로자 수에 포함. 입국한 날부터인지 183일이 지난 날부터인지는 사실 판단(제29조의7 회신, 전문 확인)"},
    {"문서번호": "사전-2026-법규법인-0729", "제도": "통합고용", "내용": "2026 과세연도를 최초 공제연도로 신청하는 경우 2024년 근로계약 체결 당시 34세 이하인 사람에게는 2026.2.27. 개정 시행령 제26조의8제4항제1호를 적용할 수 없음(요지·관련 법령 확인)"},
    {"문서번호": "서면-2019-법인-2363", "제도": "공통", "내용": "근로계약기간이 1년 이상인 기간제 근로자는 상시근로자에 해당(요지)"},
    {"문서번호": "사전-2025-법규소득-0773", "제도": "통합고용", "내용": "육아기 근로시간 단축근무자는 시행령 제23조제10항제2호의 단시간근로자에 해당(요지)"},
    {"문서번호": "서면-2025-법규소득-1241", "제도": "통합고용", "내용": "근로소득 원천징수 납부세액이 없고 국민연금·건강보험 중 하나의 납부 사실도 확인되지 않으면 상시근로자가 아님(요지)"},
    {"문서번호": "서면-2024-법인-3478", "제도": "통합고용", "내용": "근로 제공이 주로 비수익사업과 관련된 직원은 상시근로자 수 계산에서 제외(요지)"},
]
_NUM_FIELDS = ("age", "military_years", "age_at_contract", "contract_months", "service_months", "monthly_hours")


def _art(credit):
    return ("제29조의7", "제26조의7") if credit == "고용증대" else ("제29조의8", "제26조의8")


def available(year):
    """그 과세연도에 새로 늘어난 인원에 쓸 수 있는 제도와 앞 해 증가분의 남은 공제."""
    if year <= 2022:
        return ["고용증대"], "새로 늘어난 인원은 고용증대(제29조의7)만"
    if year <= 2024:
        return ["고용증대", "통합고용"], "새로 늘어난 인원은 고용증대(제29조의7)와 통합고용(제29조의8) 중 선택 — 통합고용은 고용증대 공제를 받지 않은 경우만(제127조제11항)"
    if year == 2025:
        return ["통합고용"], "새로 늘어난 인원은 통합고용(제29조의8)만. 고용증대는 2023·2024 과세연도 증가분의 2차·3차 공제만 남음(적용기한 2024.12.31.이 속하는 과세연도)"
    return ["통합고용"], ("새로 늘어난 인원은 2026년부터의 통합고용(직전 3개 과세연도 대비 증가, 2028.12.31.이 속하는 과세연도까지). 2024·2025 과세연도 증가분의 2차·3차 공제와 추가 납부는 종전 규정"
                      "(법률 2025.12.23. 개정 부칙 제34조), 고용증대는 2024 과세연도 증가분의 3차 공제(중소·중견기업)만 남음")


def _new_rule(year, credit):
    return credit == "통합고용" and year >= 2026


def _regular_rule(year, credit):
    exec_art = "법인세법 시행령 제42조제1항" if year <= 2018 else "법인세법 시행령 제40조제1항"
    if _new_rule(year, credit):
        return (["근로기간이 1년 미만인 근로자", "단시간근로자(해당 과세연도의 총 근로시간 ÷ 근무개월 수로 계산한 월 평균 근로시간이 60시간 이상이면 상시근로자)", f"{exec_art} 각 호의 임원",
                 "최대주주 또는 최대출자자(개인사업자는 대표자)와 그 배우자", "최대주주 등의 직계존비속(그 배우자 포함)과 친족관계에 있는 사람",
                 "근로소득세 원천징수 사실이 확인되지 않고 국민연금 부담금·기여금과 건강보험 직장가입자 보험료 납부 사실도 확인되지 않는 사람"], f"{_D} 제26조의8제2항(2026.2.27. 개정)")
    return (["근로계약기간이 1년 미만인 근로자(연속된 갱신으로 총 기간이 1년 이상이면 상시근로자)", "단시간근로자(1개월간의 소정근로시간이 60시간 이상이면 상시근로자)", f"{exec_art} 각 호의 임원",
             "최대주주 또는 최대출자자(개인사업자는 대표자)와 그 배우자", "최대주주 등의 직계존비속(그 배우자 포함)과 친족관계인 사람",
             "근로소득세 원천징수 사실이 확인되지 않고 국민연금 부담금·기여금과 건강보험 직장가입자 보험료 납부 사실도 확인되지 않는 사람"], f"{_D} 제23조제10항({_art(credit)[1]}제2항에서 준용)")


def _youth_group(year, credit):
    age = 29 if credit == "고용증대" else 34
    items = [f"15세 이상 {age}세 이하(병역을 이행한 기간은 6년까지 빼고 계산). 기간제근로자·단시간근로자, 파견근로자, 청소년유해업소에 근무하는 청소년은 제외", "장애인(장애인복지법), 상이자(국가유공자법)"]
    if year >= 2019 or credit == "통합고용":
        items[1] += ", 5·18민주화운동부상자, 고엽제후유의증환자로서 장애등급 판정을 받은 사람"
    if year >= 2021 or credit == "통합고용":
        items.append("근로계약 체결일 현재 60세 이상인 사람")
    if credit == "통합고용":
        if year <= 2024:
            items.append("경력단절 여성(법 제29조의3제1항)")
        else:
            items.append("경력단절 근로자(같은 기업에서 1년 이상 근무 후 결혼·임신·출산·육아·자녀교육·가족돌봄 사유로 퇴직, 퇴직 후 2년 이상 15년 미만, 최대주주 등과 그 특수관계인이 아닐 것 — 법 제29조의8제2항)")
            items.append("북한이탈주민")
        if year >= 2025:
            items[0] += (". 근로계약 체결 당시 34세 이하였으면 근로기간 중 34세를 넘어도 체결일부터 4년간(중소·중견기업이 아니면 3년간) 청년등으로 봄. 2025년에 체결한 계약은 3년간(중소·중견기업이 아니면 2년간). "
                         "2025.1.1. 이후 개시하는 과세연도를 최초 공제연도로 신청하는 경우부터 적용하고, 2024년 이전에 체결한 계약에는 적용하지 않음(시행령 2026.2.27. 개정 부칙 제11조, 사전-2026-법규법인-0729)")
    para = "제3항" if (credit == "고용증대" or year <= 2025) else "제4항"
    extra = "(청년 유지 기간은 2026.2.27. 개정 제4항제1호 후단, 부칙 제11조제1항·제2항)" if (credit == "통합고용" and year == 2025) else ""
    return items, f"{_D} {_art(credit)[1]}{para}{extra}"


def _requirements(year, credit):
    law, dec = _art(credit)
    new = _new_rule(year, credit)
    excl, reg_basis = _regular_rule(year, credit)
    youth, youth_basis = _youth_group(year, credit)
    r = [{"요건": "업종", "내용": "소비성서비스업을 경영하는 내국인은 제외 — 호텔업·여관업(관광숙박업 제외), 주점업(일반유흥주점업·무도유흥주점업·단란주점 영업만, 외국인전용유흥음식점업·관광유흥음식점업 제외), 그 밖에 오락·유흥 목적 사업으로 부령이 정하는 사업",
          "근거": f"{_L} {law}제1항, 시행령 {dec}제1항·제29조제3항"}]
    if new:
        r.append({"요건": "상시근로자 수 증가", "내용": "해당 과세연도의 상시근로자 수가 직전 3개 과세연도(2024.12.31. 이전에 개시한 과세연도는 제외) 중 1개 이상 과세연도보다 늘 것. 중소기업이 아니면 최소고용증가인원수(중견기업 5명, 그 밖 10명)를 넘게 늘어난 경우만 공제",
                  "근거": f"{_L} 제29조의8제1항(2025.12.23. 개정), 시행령 제26조의8제3항"})
    else:
        if credit == "고용증대":
            term = "2024.12.31.이 속하는 과세연도까지 늘어난 인원(2021.12.28. 개정 전에는 2021.12.31.까지)"
        else:
            term = "2025.12.31.이 속하는 과세연도까지 늘어난 인원"
        r.append({"요건": "상시근로자 수 증가", "내용": f"해당 과세연도의 상시근로자 수가 직전 과세연도보다 늘 것. {term}. 청년등과 청년등 외 증가 인원은 각각 전체 증가 인원을 한도로 함",
                  "근거": f"{_L} {law}제1항"})
    r.append({"요건": "상시근로자 범위", "내용": "근로기준법에 따라 근로계약을 체결한 내국인 근로자. 외국인 근로자도 소득세법의 거주자이면 포함하고 거주자가 되는 날부터 셈(서면-2024-소득-0033, 법규과-803). 아래에 해당하면 제외",
              "제외": excl, "근거": reg_basis + f", {_L} 제2조제1항제1호"})
    r.append({"요건": "청년등상시근로자 범위", "내용": "상시근로자 중 아래 어느 하나에 해당하는 사람", "해당": youth, "근거": youth_basis})
    if new:
        r.append({"요건": "인원 계산", "내용": "근로자별 (해당 과세연도의 근무개월 수 ÷ 과세연도 개월 수)의 합. 매월 말 현재 근무하면 그 달을 근무개월 수에 넣음. 100분의 1 미만은 버림. 월 평균 근로시간 60시간 이상 단시간근로자는 0.5명(요건을 모두 갖추면 0.75명)",
                  "근거": f"{_D} 제26조의8제6항, 제11조의2제8항"})
    else:
        r.append({"요건": "인원 계산", "내용": "매월 말 현재 상시근로자 수의 합 ÷ 과세연도 개월 수(청년등도 같은 방법). 100분의 1 미만은 버림. 1개월 소정근로시간 60시간 이상 단시간근로자는 0.5명(상시근로자 수가 줄지 않고, 기간의 정함이 없는 계약이며, "
                  "차별적 처우가 없고, 시간당 임금이 최저임금의 130%(중소기업 120%) 이상이면 0.75명). 창업한 해의 직전 과세연도 인원은 0, 합병·사업 양수·특수관계인에게서 승계한 인원은 직전 과세연도에도 있던 것으로 봄",
                  "근거": f"{_D} {dec}" + ("제7항~제9항" if credit == "고용증대" else "제6항~제8항") + ", 제23조제11항·제13항"})
        if credit == "통합고용" and year == 2025:
            r[-1]["내용"] = ("2025.1.1. 이후 개시하는 과세연도를 최초 공제연도로 신청하는 경우부터 2026.2.27. 개정 제6항을 적용 — 근로자별 (해당 과세연도의 근무개월 수 ÷ 과세연도 개월 수)의 합, 매월 말 현재 근무하면 그 달을 근무개월 수에 넣음, 100분의 1 미만은 버림. "
                           "2023·2024 과세연도를 최초 공제연도로 한 분의 2차·3차 공제와 사후관리는 종전 방식(매월 말 현재 인원의 합 ÷ 과세연도 개월 수). 창업한 해의 직전 과세연도 인원은 0")
            r[-1]["근거"] = f"{_D} 제26조의8제6항(2026.2.27. 개정)·제11조의2제8항, 시행령 2026.2.27. 개정 부칙 제11조제1항(2026.5.22. 개정), 종전 제26조의8제6항~제8항"
    if new:
        r.append({"요건": "공제 기간과 사후관리", "내용": "해당 과세연도에 공제. 2025년까지의 '2년 안에 줄면 공제 중단·추가 납부' 항은 삭제됨(2025.12.23.). 2024·2025 과세연도 증가분의 2차·3차 공제와 추가 납부는 종전 규정",
                  "근거": f"{_L} 제29조의8제1항·제3항(삭제), 법률 2025.12.23. 개정 부칙 제34조, 시행령 2025.12.31. 개정 부칙 제2조"})
    else:
        base = "공제받은 직전 과세연도" if (credit == "고용증대" and year == 2018) else "최초로 공제받은 과세연도"
        text = (f"해당 과세연도와 그 뒤 1년(중소·중견기업은 2년)까지 공제. 최초로 공제받은 과세연도 종료일부터 2년이 되는 날이 속하는 과세연도까지 전체 상시근로자 수가 {base}보다 줄면 그 과세연도부터 공제하지 않고, "
                "청년등상시근로자 수가 줄면 청년등 금액을 적용하지 않으며, 공제받은 세액을 추가 납부. 추가 납부를 계산할 때 최초로 공제받은 과세연도에 청년이던 사람은 이후에도 청년등으로 봄")
        basis = f"{_L} {law}제1항·" + ("제2항" if (credit == "고용증대" or year <= 2024) else "제3항") + f", 시행령 {dec}" + ("제5항·제6항" if credit == "고용증대" else "제4항·제5항")
        if credit == "고용증대" and year == 2018:
            text += ". 2018.12.24. 개정(금액 상향, 공제 기간 1년 연장)은 2019.1.1. 이후 신고분부터 적용되어 2018 과세연도에도 적용"
            basis += ", 법률 제16009호 부칙 제13조"
        if credit == "고용증대" and year in (2020, 2021, 2022):
            text += ". 2020 과세연도에 인원이 줄어든 경우는 사후관리 유예 특례(제5항~제7항, 2021.3.16. 신설)"
        r.append({"요건": "공제 기간과 사후관리", "내용": text, "근거": basis})
    if year <= 2022:
        dup = "창업중소기업 감면 중 제6조제7항(고용 증가에 따른 추가 감면)을 받는 경우에는 고용증대를 함께 적용하지 않음. 제6조의 다른 항 감면과는 함께 적용"
    elif year <= 2024:
        dup = "제6조제7항 감면을 받는 경우에는 고용증대와 통합고용(제29조의8제1항)을 함께 적용하지 않음. 통합고용은 고용증대(제29조의7) 또는 제30조의4 공제를 받지 않은 경우에만 적용"
    else:
        dup = ("제6조 감면을 받는 경우에는 고용증대와 통합고용을 함께 적용하지 않음 — 2025.1.1. 이후 창업분부터이고, 2024.12.31.까지 창업한 기업은 종전대로 제6조제7항 감면만 배제(법률 제20617호 부칙 제2조). "
               "통합고용은 고용증대(제29조의7) 또는 제30조의4 공제를 받지 않은 경우에만 적용")
    r.append({"요건": "다른 감면·공제와의 관계", "내용": dup, "근거": f"{_L} 제127조제4항 단서" + ("" if year <= 2022 else "·제11항")})
    carry = "5년" if year <= 2019 else "10년"
    r.append({"요건": "이월공제", "내용": f"납부할 세액이 없거나 최저한세 때문에 공제받지 못한 금액은 다음 과세연도부터 {carry} 이내에 이월" + (" — 10년은 2021.1.1. 이후 과세표준을 신고하는 경우부터" if year >= 2020 else ""),
              "근거": f"{_L} 제144조제1항" + (", 법률 2020.12.29. 개정 부칙 제35조" if year >= 2020 else "")})
    docs = "세액공제신청서와 공제세액계산서" + ("" if (credit == "고용증대" or year <= 2024) else ", 상시근로자 명세서(시행령 2025.2.28. 개정)")
    r.append({"요건": "신청", "내용": f"과세표준 신고와 함께 {docs} 제출", "근거": f"{_D} {dec}" + ("제10항" if credit == "고용증대" else "제11항")})
    return r


def _worker(w, i, year, credit, size):
    name = w.get("name") or f"직원 {i + 1}"
    new = _new_rule(year, credit)
    _, reg_basis = _regular_rule(year, credit)
    out = lambda res, why, basis=reg_basis, **kw: {"항목": f"직원 — {name}", "판정": res, "사유": why, "근거": basis, **kw}
    if w.get("executive"):
        return out("상시근로자 아님", "임원")
    if w.get("foreigner") and w.get("resident") is False:
        return out("상시근로자 아님", "비거주자인 외국인 근로자 — 내국인 근로자가 아님. 거주자가 되면 그 날부터 상시근로자(서면-2024-소득-0033)", f"{reg_basis}, {_L} 제2조제1항제1호")
    if w.get("owner_or_family"):
        return out("상시근로자 아님", "최대주주·최대출자자(개인사업자는 대표자) 본인, 배우자, 직계존비속(그 배우자 포함) 또는 친족")
    if w.get("withholding") is False and w.get("social_insurance") is False:
        return out("상시근로자 아님", "근로소득세 원천징수 사실과 국민연금·건강보험 납부 사실이 모두 확인되지 않음")
    pending = []
    if w.get("foreigner") and w.get("resident") is None:
        pending.append("외국인 근로자는 소득세법의 거주자인지 확인(resident) — 거주자이면 거주자가 되는 날부터 상시근로자(서면-2024-소득-0033)")
    if w.get("withholding") is False and w.get("social_insurance") is None:
        pending.append("원천징수 사실이 없으면 국민연금·건강보험 납부 사실 확인(social_insurance)")
    if w.get("social_insurance") is False and w.get("withholding") is None:
        pending.append("국민연금·건강보험 납부 사실이 없으면 근로소득세 원천징수 사실 확인(withholding)")
    months = w.get("service_months") if new else w.get("contract_months")
    if months is not None and months < 12:
        return out("상시근로자 아님", "근로기간이 1년 미만" if new else "근로계약기간이 1년 미만(연속 갱신으로 총 1년 이상이면 contract_months에 총 기간을)")
    if not new and months is None and w.get("fixed_term"):
        pending.append("기간제근로자는 근로계약기간이 갱신을 포함해 1년 이상인지 확인(contract_months)")
    if new and months is None:
        pending.append("2026년 통합고용은 근로기간 1년 이상인지 확인(service_months)")
    weight = 1
    if w.get("part_time"):
        h = w.get("monthly_hours")
        label = "월 평균 근로시간" if new else "1개월 소정근로시간"
        if h is None:
            pending.append(f"단시간근로자는 {label}이 60시간 이상인지 확인(monthly_hours)")
        elif h < 60:
            return out("상시근로자 아님", f"단시간근로자이고 {label} {h}시간 — 60시간 미만")
        else:
            weight = 0.5
    youth, why_y = _youth(w, year, credit, size)
    y_basis = _youth_group(year, credit)[1]
    if pending:
        return out("확인 필요", "; ".join(pending), reg_basis)
    kind = {True: "상시근로자 — 청년등", False: "상시근로자 — 청년등 외", None: "상시근로자 — 청년등 여부 확인 필요"}[youth]
    note = why_y + (". 단시간근로자라 0.5명으로 계산(요건을 모두 갖추면 0.75명)" if weight == 0.5 else "")
    return out(kind, note, f"{reg_basis}, {y_basis}", 인원_환산=weight)


def _youth(w, year, credit, size):
    """나이로 청년인지 먼저 보고, 아니면 장애인 등·60세 이상·북한이탈주민·경력단절, 끝으로 2026년 통합고용의 청년 유지 기간을 본다."""
    limit = 29 if credit == "고용증대" else 34
    mil = min(max(w.get("military_years") or 0, 0), 6)
    blocked = [k for k, v in (("기간제근로자", w.get("fixed_term")), ("단시간근로자", w.get("part_time")), ("파견근로자", w.get("dispatched")), ("청소년유해업소 청소년", w.get("youth_harmful_workplace"))) if v]
    age, notes = w.get("age"), []
    if age is not None:
        eff = age - mil
        if 15 <= eff <= limit and not blocked:
            return True, f"15세 이상 {limit}세 이하" + (f"(병역 기간을 빼고 계산한 나이 {eff}세)" if eff != age else "")
        notes.append(f"나이는 {limit}세 이하지만 {', '.join(blocked)}라 청년에서 제외" if 15 <= eff <= limit else (f"{limit}세 초과" if eff > limit else "15세 미만"))
    kind = w.get("disabled_kind")
    if kind in ("장애인", "상이자") or (kind in DISABLED_KINDS and (year >= 2019 or credit == "통합고용")):
        return True, f"{kind}"
    if kind in DISABLED_KINDS:
        notes.append(f"{kind}은 2019년 시행본부터 청년등에 포함 — {year}년에는 해당 없음")
    if w.get("age_at_contract") is not None and w["age_at_contract"] >= 60:
        if year >= 2021 or credit == "통합고용":
            return True, "근로계약 체결일 현재 60세 이상"
        notes.append("근로계약 체결일 현재 60세 이상은 2021년 시행본부터 청년등에 포함")
    if w.get("defector"):
        if credit == "통합고용" and year >= 2025:
            return True, "북한이탈주민(2025.1.1. 이후 개시하는 과세연도를 최초 공제연도로 신청하는 경우부터 — 시행령 2025.2.28. 개정 부칙 제9조)"
        notes.append("북한이탈주민은 2025년 통합고용부터 청년등에 포함")
    if w.get("career_break"):
        if credit == "통합고용":
            return None, ("경력단절 여성(법 제29조의3제1항) 요건을 갖췄는지 확인" if year <= 2024 else "경력단절 근로자 세 요건(1년 이상 근무 후 사유 퇴직, 퇴직 후 2년 이상 15년 미만, 최대주주 등이 아닐 것)을 갖췄는지 확인 — 법 제29조의8제2항")
        notes.append("경력단절 여성은 고용증대의 청년등이 아님(재고용 세액공제는 제29조의3)")
    if credit == "통합고용" and year >= 2025 and w.get("age_at_contract") is not None and w.get("contract_date") and not blocked:
        cd = date.fromisoformat(str(w["contract_date"]))
        if 15 <= w["age_at_contract"] - mil <= 34 and cd.year >= 2025:
            if size is None:
                return None, "근로계약 체결 당시 34세 이하 — 청년등으로 보는 기간은 기업 규모에 따라 다름(size)"
            sme = size in ("중소기업", "중견기업")
            yrs = (4 if sme else 3) if cd.year >= 2026 else (3 if sme else 2)
            until = cd.replace(year=cd.year + yrs, day=28) if (cd.month, cd.day) == (2, 29) else cd.replace(year=cd.year + yrs)
            src = "시행령 제26조의8제4항제1호 후단" if cd.year >= 2026 else "시행령 2026.2.27. 개정 부칙 제11조제2항"
            src += ", 2025.1.1. 이후 개시하는 과세연도를 최초 공제연도로 신청하는 경우"
            if date(year, 1, 1) < until:
                return True, f"근로계약 체결 당시 34세 이하 — 체결일({cd})부터 {yrs}년간({until} 전까지)은 청년등으로 봄({src}). 그 기간에 속하는 달만 청년등으로 계산"
            notes.append(f"근로계약 체결일({cd})부터 {yrs}년이 지남")
        elif 15 <= w["age_at_contract"] - mil <= 34:
            notes.append("근로계약 체결 당시 34세 이하였어도 2024년 이전에 체결한 계약에는 청년 유지 규정을 적용하지 않음(사전-2026-법규법인-0729)")
    if age is None and not notes:
        return None, "나이(age)를 주지 않아 청년 여부를 판정하지 않음"
    if age is None:
        return None, "; ".join(notes) + " — 나이(age)를 주지 않아 청년 여부는 판정하지 않음"
    return False, "; ".join(notes)


def guide(year=None, credit=None, size=None, consumer_service=None, workers=None, startup_reduction=None, founded=None, extra_reduction_for_employment=None,
          took_employment_increase=None, increase=None):
    if year is None:
        return {"연도별 변화": [x.strip() for x in __doc__.split("연도별로 달라진 것:")[1].strip().split("\n")], "입력": f"year({YEAR_MIN}~{YEAR_MAX})를 주면 그 과세연도 요건과 사실관계 판정",
                "제도 구분": list(CREDITS), "기업 규모 구분": list(SIZES), "장애인 등 구분": list(DISABLED_KINDS), "확인 시행본": "2018~2025 각 연말과 2026.11.12. 시행본"}
    문제 = []
    if not isinstance(year, int) or isinstance(year, bool) or not YEAR_MIN <= year <= YEAR_MAX:
        return {"error": "입력 확인 필요", "문제": [f"year={year!r} — {YEAR_MIN}~{YEAR_MAX} 과세연도(2017년 이전은 다른 제도)"]}
    if credit is not None and credit not in CREDITS:
        문제.append(f"credit={credit!r} — {' | '.join(CREDITS)}")
    if credit == "통합고용" and year <= 2022:
        문제.append("통합고용세액공제는 2023 과세연도부터(법률 2022.12.31. 신설)")
    if size is not None and size not in SIZES:
        문제.append(f"size={size!r} — {' | '.join(SIZES)}")
    for i, w in enumerate(workers or []):
        if not isinstance(w, dict):
            문제.append(f"workers[{i}] — {{name?, age?, ...}} 형식")
        else:
            if w.get("disabled_kind") is not None and w["disabled_kind"] not in DISABLED_KINDS:
                문제.append(f"workers[{i}].disabled_kind — {' | '.join(DISABLED_KINDS)}")
            for k in _NUM_FIELDS:
                if w.get(k) is not None and (isinstance(w[k], bool) or not isinstance(w[k], (int, float)) or w[k] < 0):
                    문제.append(f"workers[{i}].{k}={w[k]!r} — 0 이상의 수")
            if w.get("contract_date") is not None:
                try:
                    date.fromisoformat(str(w["contract_date"]))
                except ValueError:
                    문제.append(f"workers[{i}].contract_date={w['contract_date']!r} — YYYY-MM-DD")
    if increase is not None and (isinstance(increase, bool) or not isinstance(increase, (int, float))):
        문제.append(f"increase={increase!r} — 증가 인원(수)")
    for k, v in (("consumer_service", consumer_service), ("startup_reduction", startup_reduction), ("extra_reduction_for_employment", extra_reduction_for_employment), ("took_employment_increase", took_employment_increase)):
        if v is not None and not isinstance(v, bool):
            문제.append(f"{k}={v!r} — true | false")
    fd = None
    if founded is not None:
        try:
            fd = date.fromisoformat(str(founded))
        except ValueError:
            문제.append(f"founded={founded!r} — YYYY-MM-DD")
    if 문제:
        return {"error": "입력 확인 필요", "문제": 문제}
    usable, usable_text = available(year)
    chosen = credit or ("고용증대" if year <= 2022 else "통합고용")
    out = {"과세연도": year, "제도": chosen, "그 해에 쓸 수 있는 제도": usable_text, "요건": _requirements(year, chosen)}
    판정 = []
    if credit is None and year in (2023, 2024):
        판정.append({"항목": "제도 선택", "판정": "확인 필요", "사유": "2023·2024 과세연도는 고용증대와 통합고용 중 선택 — credit을 주지 않아 통합고용 기준으로 안내. 고용증대 기준은 credit='고용증대'", "근거": f"{_L} 제127조제11항"})
    if chosen == "고용증대" and year >= 2025:
        판정.append({"항목": "새로 늘어난 인원", "판정": "대상 아님", "사유": "고용증대는 2024.12.31.이 속하는 과세연도까지 늘어난 인원만 — 이 해에는 앞 해 증가분의 2차·3차 공제와 사후관리만 해당", "근거": f"{_L} 제29조의7제1항"})
    if consumer_service is not None:
        판정.append({"항목": "업종", "판정": "대상 아님" if consumer_service else "충족", "사유": "소비성서비스업을 경영" if consumer_service else "소비성서비스업이 아님", "근거": out["요건"][0]["근거"]})
    if startup_reduction is not None:
        basis = f"{_L} 제127조제4항 단서"
        if not startup_reduction:
            판정.append({"항목": "창업감면과의 관계", "판정": "해당 없음", "사유": "제6조 감면을 받지 않음", "근거": basis})
        elif year >= 2025 and fd is None:
            판정.append({"항목": "창업감면과의 관계", "판정": "확인 필요", "사유": "2025.1.1. 이후 창업이면 제6조 감면 전체와 함께 적용하지 않고, 그 전 창업이면 제6조제7항 감면만 배제 — 창업일(founded) 확인", "근거": basis + ", 법률 제20617호 부칙 제2조"})
        elif year >= 2025 and fd >= date(2025, 1, 1):
            판정.append({"항목": "창업감면과의 관계", "판정": "함께 적용하지 않음", "사유": f"{fd} 창업 — 2025.1.1. 이후 창업분은 제6조 감면을 받는 과세연도에 고용증대·통합고용을 함께 적용하지 않음", "근거": basis + ", 법률 제20617호 부칙 제2조"})
        elif extra_reduction_for_employment is None:
            판정.append({"항목": "창업감면과의 관계", "판정": "확인 필요", "사유": "제6조제7항(고용 증가에 따른 추가 감면)을 받으면 함께 적용하지 않음. 제6조의 다른 항 감면만 받으면 함께 적용 — extra_reduction_for_employment 확인", "근거": basis})
        elif extra_reduction_for_employment:
            target = "고용증대" if year <= 2022 else "고용증대와 통합고용(제29조의8제1항)"
            판정.append({"항목": "창업감면과의 관계", "판정": "함께 적용하지 않음", "사유": f"제6조제7항 감면을 받는 과세연도에는 {target}을 함께 적용하지 않음", "근거": basis})
        else:
            판정.append({"항목": "창업감면과의 관계", "판정": "함께 적용", "사유": "제6조제7항 감면을 받지 않으면 제6조 감면과 함께 적용" + ("(2024.12.31.까지 창업한 기업)" if year >= 2025 else ""), "근거": basis + (", 법률 제20617호 부칙 제2조" if year >= 2025 else "")})
    if took_employment_increase is not None and chosen == "통합고용":
        판정.append({"항목": "고용증대와의 관계", "판정": "대상 아님" if took_employment_increase else "충족",
                   "사유": "고용증대(제29조의7) 공제를 받은 경우 통합고용(제29조의8제1항)을 적용하지 않음" if took_employment_increase else "고용증대 공제를 받지 않음", "근거": f"{_L} 제127조제11항"})
    if increase is not None and _new_rule(year, chosen):
        basis = f"{_L} 제29조의8제1항 단서, 시행령 제26조의8제3항"
        if size is None:
            판정.append({"항목": "최소고용증가인원수", "판정": "확인 필요", "사유": "중소기업은 기준 없음, 중견기업 5명, 그 밖 10명 — 기업 규모(size) 확인", "근거": basis})
        elif size == "중소기업":
            판정.append({"항목": "최소고용증가인원수", "판정": "해당 없음", "사유": "중소기업은 최소고용증가인원수 기준이 없음", "근거": basis})
        else:
            floor = 5 if size == "중견기업" else 10
            ok = increase > floor
            판정.append({"항목": "최소고용증가인원수", "판정": "충족" if ok else "대상 아님", "사유": f"증가 {increase}명 — {floor}명을 넘어야 공제" + ("" if ok else "(같으면 넘은 것이 아님)"), "근거": basis})
    for i, w in enumerate(workers or []):
        판정.append(_worker(w, i, year, chosen, size))
    if 판정:
        out["판정"] = 판정
    law, dec = _art(chosen)
    out["한계"] = ["그 과세연도 말 시행본 기준. 연중 개정으로 들어온 항목은 개정 부칙의 적용례에 따라 달라질 수 있음(article_addenda)",
                 "직원 판정은 입력한 사실에 문언을 댄 것 — 외국인 근로자가 거주자인지(입국일부터인지 183일이 지난 날부터인지), 임원·친족 해당 여부, 경력단절 요건의 실질은 사실 판단이라 판정하지 않음. 해석은 search_tax_rulings",
                 "추가 납부 계산식(시행령 2020.2.11. 개정)과 2020 과세연도 사후관리 유예 특례, 정규직 전환·육아휴직 복귀 공제의 세부 요건은 다루지 않음",
                 "세액은 계산하지 않음 — 요건을 갖춘 인원으로 계산 MCP의 employment_increase_credit, integrated_employment_credit(2026년 통합고용 계산식은 아직 계산 도구에 없음)"]
    art = law.replace("제", "").replace("조", "")
    out["다음 단계"] = (f"원문: law_article(law_name='{_L}', article='{art}', as_of=과세연도 말) · 시행령 {dec}" + ("" if _new_rule(year, chosen) else " · 제23조제10항")
                    + " · 부칙: article_addenda · 해석: search_tax_rulings('상시근로자 수 계산')")
    if chosen == "통합고용" and year == 2025:
        out["한계"].insert(1, "2025 과세연도는 상시근로자 범위를 종전 규정(시행령 제23조제10항)으로 안내(시행령 2025.12.31. 개정 부칙 제2조). 청년 유지 기간과 인원 계산은 2026.2.27. 개정 부칙 제11조제1항에 따라 개정규정으로 안내 — "
                         "개정 제6항이 인용하는 단시간근로자 기준(개정 제26조의8제2항제2호 단서)을 2025년에 어떻게 읽는지는 해석을 찾지 못함")
    out["관련 해석"] = [x for x in _RULINGS if x["제도"] in ("공통", chosen)]
    out["확인 시행본"] = "2018~2025 각 연말과 2026.11.12. 시행본(법 제29조의7·제29조의8·제127조④⑪·제144조①, 시행령 제26조의7·제26조의8·제23조⑩~⑬·제29조③)과 개정 부칙"
    return out
