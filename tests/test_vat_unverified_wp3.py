"""부가가치세 면세·영세율 안내 — 원문 대조로 닫은 항목(2026-11-15). 작성 Claude.

대조한 시행본(법제처 DRF, 원자료 raw_wp3):
- 부가가치세법 시행규칙 2015.7.1.(제470호)·2019.7.1.(제718호)·2020.3.13.(제775호)·2022.9.6.(제934호)·2026.4.1.(재정경제부령 제9호) 전문 — 제22조·제23조·제24조·별표 1·부칙
- 부가가치세법 시행령 2015.10.25. 시행본(제26600호) 제33조, 2026.4.1. 시행본(제36133호) 제71조(2016~2021 연말 시행본 제71조와 비교)
- 조세특례제한법 2016.1.1. 시행본 제106조, 같은 법 시행령 2016.1.1.(제26070호)·2026.9.18.(제36587호) 시행본 제106조, 주택법 2026.9.8. 시행본 제2조제6호
- 법인세법 제75조의2(2019.1.1.·2026.7.1. 시행본), 구 제76조(2016.1.1.·2018.11.1. 시행본), 법률 제14386호 부칙 제1조·제6조
"""
from korean_tax_mcp import vat_exempt_zero_rate as V, nominee_trust as N


def P(r):
    return {x["항목"]: x["판정"] for x in r["판정"]}


def test_no_unverified_tags_left():
    import inspect
    src = inspect.getsource(V)
    for tag in ("미확인", "미대조", "대조하지 못"):
        assert tag not in src, tag


# ── 별표 1 제12호: 포장 단순가공식료품(2022.7.1.~2025.12.31. 공급분만 면세) ──
def test_packaged_simple_processed_food_window():
    f = {"simple_processed": True, "packaged_for_sale": True}
    assert P(V.guide("2022-06-30", "미가공식료품", f))["미가공식료품"] == "과세"
    assert P(V.guide("2022-07-01", "미가공식료품", f))["미가공식료품"] == "면세"
    assert P(V.guide("2025-12-31", "미가공식료품", f))["미가공식료품"] == "면세"
    assert P(V.guide("2026-01-01", "미가공식료품", f))["미가공식료품"] == "과세"
    # 포장하지 않은 것(운반 편의 일시 포장 포함)은 전 기간 면세
    g = {"simple_processed": True, "packaged_for_sale": False}
    for d in ("2016-03-01", "2022-06-30", "2026-01-01"):
        assert P(V.guide(d, "미가공식료품", g))["미가공식료품"] == "면세"
    # 포장 여부를 모르면 한시 면세 기간 밖에서는 확인 필요
    assert P(V.guide("2021-05-01", "미가공식료품", {"simple_processed": True}))["미가공식료품"] == "확인 필요"
    assert P(V.guide("2024-05-01", "미가공식료품", {"simple_processed": True}))["미가공식료품"] == "면세"


def test_appendix1_headings_in_requirements():
    r = V.guide("2025-05-01", "미가공식료품", {"primary_processing_only": True})
    t = next(x for x in r["요건"] if x["요건"] == "미가공식료품 분류표")
    for h in ("1. 곡류", "6. 수축류", "9. 생선류", "11. 해조류", "단순가공식료품", "김치", "천연꿀", "0409"):
        assert h in t["내용"], h
    assert len(V.APPENDIX1) == 12 and "별표 1" in t["근거"]
    assert not any(x["요건"] == "미가공식료품 분류표" for x in V.guide("2025-05-01", "교육", {"registered": True})["요건"])


# ── 시행규칙 제22조: 제3호~제5호는 2020.3.13. 이후 공급분부터 ──
FX = {"counterparty_nonresident": True, "has_domestic_place": False, "service_kind": "통신업", "payment": "기획재정부령 방법"}


def test_payment_method_boundary_2020_03_13():
    for m in ("국외 발급 신용카드", "국외 금융기관 개인수표 매각", "외화예금 계좌 예치"):
        assert P(V.guide("2020-03-12", "외화 획득 용역", {**FX, "payment_method": m}))["대금 결제"] == "과세"
        assert P(V.guide("2020-03-13", "외화 획득 용역", {**FX, "payment_method": m}))["외화 획득 용역"] == "영세율"
    for m in ("외화 송금 후 외국환은행 매각", "지급할 금액에서 차감"):
        assert P(V.guide("2017-05-01", "외화 획득 용역", {**FX, "payment_method": m}))["외화 획득 용역"] == "영세율"
    # 방법을 모르면 2020.3.13. 전 공급분은 확인 필요, 이후는 그대로 영세율
    assert P(V.guide("2019-05-01", "외화 획득 용역", FX))["외화 획득 용역"] == "확인 필요"
    assert P(V.guide("2021-05-01", "외화 획득 용역", FX))["외화 획득 용역"] == "영세율"


def test_bonded_transport_listed_by_rule_23():
    r = V.guide("2019-05-01", "외화 획득 용역", {**FX, "service_kind": "보세운송용역", "payment": "외국환은행 원화"})
    assert P(r)["외화 획득 용역"] == "영세율" and "시행규칙 제23조" in r["판정"][0]["근거"]
    r = V.guide("2019-05-01", "외화 획득 용역", {**FX, "service_kind": "그 밖의 업종", "payment": "외국환은행 원화"})
    assert P(r)["외화 획득 용역"] == "과세" and "보세운송" in r["판정"][-1]["사유"]


# ── 시행령 제33조제2항: 2016.7.1. 전 계약분은 개정 전 문언(상호면세 단서 없음) ──
def test_pre_2016_07_contract_has_no_reciprocity():
    base = {"counterparty_nonresident": True, "has_domestic_place": False, "service_kind": "전문서비스업", "payment": "외국환은행 원화", "reciprocal": False}
    old = V.guide("2016-09-01", "외화 획득 용역", {**base, "contract_date": "2016-06-30"})
    new = V.guide("2016-09-01", "외화 획득 용역", {**base, "contract_date": "2016-07-01"})
    assert P(old)["외화 획득 용역"] == "영세율" and P(old)["계약일"] == "개정 전 문언"
    assert P(new)["상호면세"] == "과세" and "외화 획득 용역" not in P(new)
    # 사업시설관리 및 사업지원 서비스업도 같음, 투자자문업은 2020.7.1. 신설이라 해당 없음
    b2 = {**base, "service_kind": "사업시설관리 및 사업지원 서비스업"}
    assert P(V.guide("2017-03-01", "외화 획득 용역", {**b2, "contract_date": "2015-12-01"}))["외화 획득 용역"] == "영세율"
    assert P(V.guide("2017-03-01", "외화 획득 용역", {**b2, "contract_date": "2016-12-01"}))["상호면세"] == "과세"


# ── 조세특례제한법 시행령 제106조제4항·제5항: 국민주택 공급 ──
def test_national_housing_size_boundary():
    g = lambda **f: P(V.guide("2024-05-01", "국민주택 공급", f))
    assert g(supply_kind="주택 공급", exclusive_area=85)["국민주택 공급"] == "면세"
    assert g(supply_kind="주택 공급", exclusive_area=85.1, non_urban_eup_myeon=False)["국민주택 공급"] == "과세"
    assert g(supply_kind="주택 공급", exclusive_area=100, non_urban_eup_myeon=True)["국민주택 공급"] == "면세"
    assert g(supply_kind="주택 공급", exclusive_area=100.1, non_urban_eup_myeon=True)["국민주택 공급"] == "과세"
    assert g(supply_kind="주택 공급", exclusive_area=90)["국민주택 규모"] == "확인 필요"
    # 2016 시행본(제51조의2제3항 인용)도 같은 기준
    r = V.guide("2016-05-01", "국민주택 공급", {"supply_kind": "주택 공급", "exclusive_area": 84})
    assert P(r)["국민주택 공급"] == "면세" and "제51조의2제3항" in r["판정"][0]["근거"]


def test_national_housing_services():
    g = lambda **f: P(V.guide("2024-05-01", "국민주택 공급", f))
    assert g(supply_kind="건설용역", exclusive_area=80, registered=True)["국민주택 공급"] == "면세"
    assert g(supply_kind="건설용역", exclusive_area=80, registered=False)["국민주택 공급"] == "과세"
    assert g(supply_kind="설계용역", exclusive_area=80)["국민주택 공급"] == "확인 필요"
    # 리모델링: 후 면적이 국민주택규모와 전 면적의 130%를 모두 넘으면 제외
    assert g(supply_kind="리모델링용역", exclusive_area=70, area_after_remodeling=91, registered=True)["국민주택 공급"] == "면세"      # 91 ≤ 70×1.3
    assert g(supply_kind="리모델링용역", exclusive_area=70, area_after_remodeling=91.1, registered=True)["국민주택 공급"] == "과세"
    assert g(supply_kind="리모델링용역", exclusive_area=60, area_after_remodeling=85, registered=True)["국민주택 공급"] == "면세"      # 규모 이하면 130% 넘어도 면세
    # 소방공사감리업 제외 단서는 2026.9.18. 시행본 문언
    assert P(V.guide("2026-05-01", "국민주택 공급", {"supply_kind": "건설용역", "exclusive_area": 80, "fire_supervision": True}))["국민주택 공급"] == "과세"
    assert P(V.guide("2017-05-01", "국민주택 공급", {"supply_kind": "건설용역", "exclusive_area": 80, "fire_supervision": True}))["국민주택 공급"] == "확인 필요"


# ── 시행령 제71조제1항제4호·제5호: 세금계산서 발급의무 면제 ──
def test_invoice_exemption_by_category():
    inv = lambda cat, f=None, d="2024-05-01": next(x for x in V.guide(d, cat, f or {})["요건"] if x["요건"] == "세금계산서")["내용"]
    assert "발급의무 면제" in inv("직수출")
    assert "발급 대상" in inv("내국신용장·구매확인서") and "발급 대상" in inv("수출재화임가공")
    assert "발급 대상" in inv("중계무역 등 수출", {"export_form": "원료 무상 반출"})
    assert "발급의무 면제" in inv("국외 제공 용역") and "발급의무 면제" in inv("외화 획득 용역")
    assert "항공기" in inv("외국항행 용역") and "국내에 사업장이 없는" in inv("외항선박 등 공급")
    assert "일반여행업자" in inv("외국인 관광객 관광알선", d="2021-03-22") and "일반여행업자" not in inv("외국인 관광객 관광알선", d="2021-03-23")


# ── 법인세법 제75조의2제2항(구 제76조제6항): 주식등변동상황명세서 제출 불성실 가산세 ──
def test_nominee_guide_cites_share_statement_penalty():
    rows = N._corporate("상장주식" if "상장주식" in N.ASSETS_SHARE else next(iter(N.ASSETS_SHARE)), None)
    t = rows[0]["내용"]
    assert "1%" in t and "2%" in t and "제75조의2제2항" in t and "제14386호" in t and "대조하지" not in t


# ── 계약일(2016.7.1.) × 업종 × 상호면세 — 2016.2.17. 개정령 부칙 제3조가 닿는 범위 ──
import pytest

_B = {"counterparty_nonresident": True, "has_domestic_place": False, "payment": "외국환은행 원화"}
OLD, NEW = "2016-06-30", "2016-07-01"


@pytest.mark.parametrize("kind", ["전문서비스업", "사업시설관리 및 사업지원 서비스업"])
@pytest.mark.parametrize("rc", [True, False, None])
def test_old_contract_2016_kinds_ignore_reciprocity(kind, rc):
    r = P(V.guide("2018-03-01", "외화 획득 용역", {**_B, "service_kind": kind, "contract_date": OLD, "reciprocal": rc}))
    assert r["외화 획득 용역"] == "영세율" and r["계약일"] == "개정 전 문언" and "상호면세" not in r


@pytest.mark.parametrize("kind", ["전문서비스업", "사업시설관리 및 사업지원 서비스업"])
def test_new_contract_2016_kinds_need_reciprocity(kind):
    g = lambda rc: P(V.guide("2018-03-01", "외화 획득 용역", {**_B, "service_kind": kind, "contract_date": NEW, "reciprocal": rc}))
    assert g(True)["외화 획득 용역"] == "영세율" and "계약일" not in g(True)
    assert g(False)["상호면세"] == "과세" and "외화 획득 용역" not in g(False)
    assert g(None)["상호면세"] == "확인 필요" and g(None)["외화 획득 용역"] == "확인 필요"


@pytest.mark.parametrize("cd", [OLD, NEW, None])
def test_investment_advisory_reciprocity_regardless_of_contract_date(cd):
    # 투자자문업(자목)은 2020.7.1. 신설 때부터 상호면세 조건 — 2016년 부칙과 무관
    g = lambda rc: P(V.guide("2021-03-01", "외화 획득 용역", {**_B, "service_kind": "투자자문업", "contract_date": cd, "reciprocal": rc}))
    assert g(True)["외화 획득 용역"] == "영세율" and "계약일" not in g(True)
    assert g(False)["상호면세"] == "과세" and "외화 획득 용역" not in g(False)
    assert g(None)["상호면세"] == "확인 필요"


@pytest.mark.parametrize("kind", ["통신업", "과학 및 기술 서비스업", "무형재산권 임대업", "교육지원 서비스업", "보세운송용역"])
@pytest.mark.parametrize("cd", [OLD, NEW])
@pytest.mark.parametrize("rc", [True, False, None])
def test_other_kinds_unaffected_by_contract_date_or_reciprocity(kind, cd, rc):
    r = P(V.guide("2018-03-01", "외화 획득 용역", {**_B, "service_kind": kind, "contract_date": cd, "reciprocal": rc}))
    assert r["외화 획득 용역"] == "영세율" and "계약일" not in r and "상호면세" not in r


def test_ship_management_bundle_by_contract_date():
    k = "컨테이너수리·보세창고·해운대리점·해운중개·선박관리"
    assert P(V.guide("2018-03-01", "외화 획득 용역", {**_B, "service_kind": k, "contract_date": OLD}))["계약일"] == "확인 필요"   # 개정 전 마목에 선박관리업 없음
    assert P(V.guide("2018-03-01", "외화 획득 용역", {**_B, "service_kind": k, "contract_date": NEW}))["외화 획득 용역"] == "영세율"


def test_unknown_contract_date_in_2016_is_not_taxed_on_reciprocity_alone():
    f = {**_B, "service_kind": "전문서비스업", "reciprocal": False}
    r = P(V.guide("2016-09-01", "외화 획득 용역", f))
    assert r["계약일"] == "확인 필요" and r["외화 획득 용역"] == "확인 필요" and "상호면세" not in r
    # 2017년 이후 공급분은 계약일을 주지 않으면 개정 뒤 문언
    assert P(V.guide("2017-01-01", "외화 획득 용역", f))["상호면세"] == "과세"


@pytest.mark.parametrize("bad", ["2016/03/01", "2016-13-01", "작년", 20160301, ""])
@pytest.mark.parametrize("extra", [{"service_kind": "전문서비스업"}, {"service_kind": "통신업", "payment": "기획재정부령 방법"}])
def test_invalid_contract_date_is_rejected(bad, extra):
    r = V.guide("2018-03-01", "외화 획득 용역", {**_B, **extra, "contract_date": bad})
    assert r.get("error") == "입력 확인 필요" and any("contract_date" in m for m in r["문제"])
