"""요건 안내 도구가 짝이 되는 계산 MCP 도구를 결과에서 가리킨다(이전가격·중소기업 조세지원·국내사업장)."""
import re

from korean_tax_mcp import permanent_establishment as PE
from korean_tax_mcp import sme_incentives as SME
from korean_tax_mcp import transfer_pricing as TP
from korean_tax_mcp import i18n

# 계산 MCP(korean-tax-calc-mcp 0.57.x)에 실제로 있는 도구 이름
CALC_TOOLS = {"arm_length_range", "tp_comparable_screen", "kr_comparable_candidates", "kr_comparable_profile_compare", "expat_cost_recharge", "deemed_interest", "startup_tax_reduction",
              "sme_special_tax_reduction", "loss_carryback_refund", "minimum_tax_adjustment", "rural_special_tax", "sme_status",
              "corporate_tax", "income_tax", "branch_profits_tax", "nonresident_withholding"}


def _names(out):
    steps = out["계산 다음 단계"]
    assert steps and all(s["도구"].startswith("계산 MCP ") and s["용도"] for s in steps)
    names = [s["도구"].removeprefix("계산 MCP ") for s in steps]
    assert set(names) <= CALC_TOOLS, set(names) - CALC_TOOLS
    return names


def test_transfer_pricing_every_transaction():
    for tx in TP.TRANSACTIONS:
        names = _names(TP.guide(tx))
        assert ("deemed_interest" in names) == (tx == "금전대차")
        if tx != "금전대차":
            assert names[0] == "arm_length_range"


def test_sme_incentives_points_to_reduction_tools():
    names = _names(SME.guide(founded_on="20240301", region="수도권 밖", industry="제조업"))
    assert {"startup_tax_reduction", "sme_special_tax_reduction", "loss_carryback_refund"} <= set(names)
    assert names[0] == "sme_status"          # 규모를 주지 않으면 판정부터


def test_permanent_establishment_by_conclusion():
    yes = PE.guide(year=2025, taxpayer="외국법인", fixed_place=True)
    if "국내사업장 있음" in yes["결론"]:
        assert _names(yes) == ["corporate_tax", "branch_profits_tax"]
    no = PE.guide(year=2025, taxpayer="외국법인", fixed_place=False, construction_months=0, service_months_in_12=0, specific_activities=False,
                  agent_contract_authority=False, agent_principal_role=False)
    names = _names(no)
    if "국내사업장 없음" in no["결론"]:
        assert names == ["nonresident_withholding"]
    else:
        assert "nonresident_withholding" in names


def test_english_keys():
    en = i18n.localize(TP.guide("금전대차"))
    assert en["next_calculation"][0]["tool"] == "계산 MCP deemed_interest" and "purpose" in en["next_calculation"][0]


def test_pe_treaty_service_pe_note():
    """조약 안내: 건설 기간·용역 고정사업장 조항 유무를 확인하라는 목록, 국내법상 용역·건설로 '있음'이면 조약으로 다시 판단하라는 주의."""
    o = PE.guide(year=2026, taxpayer="외국법인", fixed_place=False, service_months_in_12=8, treaty_country="독일")
    items = o["조세조약"]["조약에서 확인할 조항"]
    assert any("용역 고정사업장" in x for x in items) and any("건설" in x for x in items)
    assert "용역 고정사업장 조항" in o["조세조약"]["주의"]
    c = PE.guide(year=2026, taxpayer="외국법인", fixed_place=False, construction_months=8, treaty_country="독일")
    assert "주의" in c["조세조약"]
    assert "주의" not in PE.guide(year=2026, taxpayer="외국법인", fixed_place=False, service_months_in_12=8)["조세조약"]   # 조약국을 안 주면 없음
