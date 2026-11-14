# Royalties paid to a US parent: withholding tax under the Korea–US treaty

**Question:** *"Our Korean subsidiary pays KRW 100 million of royalties to its US parent in 2026. How much Korean withholding tax applies under the Korea–US tax treaty, and is local income tax on top?"*

## Tools

| Step | Server | Tool | Why |
|---|---|---|---|
| 1 | korean-tax-mcp | `treaty_withholding_rates` | treaty cap on royalties, with the clause text and whether the treaty covers Korean local income tax |
| 2 | korean-tax-mcp | `tax_treaty` (optional) | read the whole royalties article and related documents |
| 3 | korean-tax-calc-mcp | `nonresident_withholding` | withholding amount = lower of the domestic rate and the treaty cap, plus local income tax |
| 4 | korean-tax-mcp | `search_tax_rulings`, `get_tax_ruling` (optional) | if the payment is for software or know-how, check whether it is a royalty at all |

## 1. Treaty cap

```json
{"tool": "treaty_withholding_rates", "arguments": {"country": "미국", "income": "royalties", "lang": "en"}}
```

Result outline (0.15.1):

- Treaty in force since 1979-10-20 (signed 1976-06-15); related documents listed: a US Treasury technical explanation and mutual agreements of 1999-06-23 and 2017-04-10.
- Article 14 (royalties): caps of **15%** and **10%**. Paragraph (1) sets 15% of the gross amount; paragraph (2) begins *"Royalties derived from copyrights, or rights, to produce or reproduce any literary, dramatic, musical, or artistic work…"*, which is where the 10% cap comes from. Read the full clause to see which one fits your payment.
- Local income tax: **not covered** by the treaty (Article 1 lists only Korean income tax and corporation tax). So the treaty cap applies to the corporation tax, and local income tax of 10% of the withholding tax is charged separately (Corporate Tax Act Art. 98-7(1)1).
- Note from the tool: rates are extracted automatically; check amending protocols and exchanges of notes before applying.

## 2. Withholding amount

Industrial royalty, 15% treaty cap:

```json
{"tool": "nonresident_withholding", "arguments": {"income_kind": "사용료", "amount": 100000000, "recipient_type": "법인", "residence_country": "US", "treaty_rate": 0.15, "year": 2026}}
```

| Field | Result |
|---|---|
| Domestic rate | 20% |
| Treaty rate | 15% |
| Applied rate | 15% |
| Withholding tax | KRW 15,000,000 |
| Local income tax | KRW 1,500,000 |
| Total | KRW 16,500,000 |
| Basis | Corporate Tax Act Art. 98(1)6; treaty cap 15%; treaty does not cover local income tax |

Without the treaty rate (for example, if the application for the reduced rate was not filed), the same call without `treaty_rate` gives 20%: KRW 20,000,000 plus KRW 2,000,000 local income tax.

The tool also flags issues to check:

- Software and technology payments can be royalties or business income (purchase of goods). If business income, there is no Korean tax unless the recipient has a permanent establishment in Korea. Cited for both sides: 적부-국세청-2025-0126 and 서울행정법원-2022-구합-87351 (treated as royalties), 수원고등법원-2023-누-15618 (business income), 수원지방법원-2023-구합-76700 (purchase price of goods).
- The Korea–US treaty can apply different rates to copyright royalties and other royalties. Check what the payment is for.
- The reduced rate requires the beneficial owner check and the application form (Income Tax Act Art. 156-6, Corporate Tax Act Art. 98-6); otherwise the domestic rate applies.

## What the agent should answer

- The treaty cap that fits the payment (15% or 10%), quoting Article 14.
- The withholding tax and the separate 10% local income tax, from `nonresident_withholding`.
- The conditions: beneficial ownership, the reduced-rate application, and whether the payment is a royalty at all.

Not tax advice. Verify against the treaty text, the statute in force on the payment date and the rulings cited.

[All use cases](index.md)
