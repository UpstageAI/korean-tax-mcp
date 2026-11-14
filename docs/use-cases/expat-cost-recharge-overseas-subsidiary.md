# Recharging the cost of staff seconded to an overseas subsidiary

**Question:** *"Our Korean company seconded an engineer to its overseas subsidiary for all of 2026. The work is for the subsidiary. Her cost was KRW 120 million salary, KRW 12 million employer social insurance and KRW 24 million living allowance, but we only charged the subsidiary KRW 100 million. What are the Korean tax consequences?"*

This is the outbound case: a Korean company (often the Korean arm of a group) sends staff to a related company abroad. The same tools help a Korean subsidiary check charges to and from its foreign parent.

## Tools

| Step | Server | Tool | Why |
|---|---|---|---|
| 1 | korean-tax-mcp | `transfer_pricing_guide` | which rule applies to an intra-group service and which arm's length methods fit |
| 2 | korean-tax-mcp | `search_tax_rulings` (`tax="국조"`), `get_tax_ruling` | NTS rulings and tribunal decisions on seconded staff costs |
| 3 | korean-tax-calc-mcp | `expat_cost_recharge` | arm's length charge, under-charge, tax adjustment, the employee's overseas work exemption |
| 4 | korean-tax-mcp | `residency_check` (optional) | whether the employee stays a Korean resident (Decree Art. 3) |
| 5 | korean-tax-mcp | `transfer_pricing_far`, `transfer_pricing_report` (optional) | FAR analysis and the Local File outline |

## 1. Which rule applies

```json
{"tool": "transfer_pricing_guide", "arguments": {"transaction": "용역", "lang": "en"}}
```

Result outline (0.15.1): a cross-border transaction with a foreign related party is adjusted to the arm's length price under the Adjustment of International Taxes Act (Art. 4(2), Art. 7(1)), not under Corporate Tax Act Art. 52 (unfair transactions), so the KRW 300 million / 5% threshold does not apply. Exceptions where Art. 52 applies are listed (Decree Art. 4). The tool then lists the methods with their conditions and OECD Guidelines paragraphs; for services the cost plus method fits when costs can be identified (Art. 8(1)3, Decree Art. 7). It does not compute a price.

## 2. What the NTS has said

`search_tax_rulings` with `query: "해외 파견 직원 인건비 현지법인 부담"`, `tax: "국조"`:

- 서면인터넷방문상담2팀-2108 (2004-10-18): the cost of technicians seconded to an overseas subsidiary is deductible for the Korean company when they are recognised as working for the Korean company's business.
- 조심-2012-중-2416 (2014-05-28): the Tax Tribunal rejected an arm's length adjustment under the TNMM in that case and accepted the seconded staff's pay as the claimant's own cost.
- 서면-2023-국제세원-2887 (2023-12-06): exit tax filing duty when leaving Korea on secondment to an overseas subsidiary.

Read the full text (`get_tax_ruling`) before relying on any of them; the facts decide.

## 3. The numbers

```json
{"tool": "expat_cost_recharge", "arguments": {"year": 2026, "items": [{"이름": "Seconded engineer", "급여": 120000000, "사회보험": 12000000, "체재비": 24000000, "귀속": "현지법인", "마크업": 0.05, "청구액": 100000000, "국외근로_개월": 12, "국외근로_유형": "일반", "거주자": true}]}}
```

Input keys: 급여 = annual salary, 사회보험 = employer social insurance, 체재비 = living allowance, 귀속 = whose work it is (본사 head office / 현지법인 subsidiary / 공통 shared), 마크업 = markup (an input you choose; 5% is the tool's default), 청구액 = amount actually charged, 국외근로_개월 = months worked abroad, 거주자 = the employee is a Korean resident.

| Field | Result (KRW) |
|---|---|
| Cost | 156,000,000 |
| Cost attributable to the subsidiary | 156,000,000 |
| Arm's length charge (cost + 5%) | 163,800,000 |
| Amount charged | 100,000,000 |
| Under-charge | 63,800,000 |
| Deductible at head office | 156,000,000 |
| Arm's length adjustment (added to income) | 63,800,000 |
| Employee's overseas work exemption | 12,000,000 |

Tax adjustment from the tool: add KRW 63,800,000 to income, disposed of as temporary retained earnings (임시유보) under Adjustment of International Taxes Act Art. 7 and Art. 13(1), Decree Art. 24(1). The tool explains what happens next: if the confirmation that the amount was returned is not filed within 90 days of the return, it is treated as an increase in investment (if the subsidiary is owned by the Korean company) or a dividend, under Decree Art. 22 and 23.

The overseas work exemption is KRW 1 million a month for a resident employee (KRW 5 million from 2024 for construction and ships), Income Tax Act Art. 12(3) and Decree Art. 16(1)1.

Basis cited by the tool: Corporate Tax Act Art. 15 and 19, Decree Art. 106(1)1, Adjustment of International Taxes Act Art. 7, Income Tax Act Art. 12(3), Decree Art. 16(1)1, ruling 서면-2017-법인-3468.

## What the agent should answer

- The rule: arm's length under the Adjustment of International Taxes Act, not the domestic unfair-transaction rule.
- The under-charge and the adjustment, from `expat_cost_recharge`, with the 90-day follow-up.
- Open points: whether the markup is arm's length (support it with a FAR analysis and comparables), whose business the employee really serves, and the employee's residency.

Not tax advice. Verify against the statute in force for the tax year and the rulings' full text.

[All use cases](index.md)
