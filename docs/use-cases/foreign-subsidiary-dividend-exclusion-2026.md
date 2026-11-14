# Dividends from a foreign subsidiary in 2026: the 100% exclusion

**Question:** *"Our Korean company owns 100% of a foreign subsidiary and has held it for two years. The subsidiary pays us a KRW 1 billion dividend on 2026-04-30, with KRW 50 million foreign withholding tax. How much is excluded from our taxable income? Is it different from a 2025 dividend, and can we still claim a foreign tax credit?"*

Background: Corporate Tax Act Art. 18-4 excludes 95% of dividends from foreign subsidiaries (from 2023). Restriction of Special Taxation Act Art. 23-2 raises this to 100% for dividends received from 2026-01-01 to 2026-12-31. This matters to Korean parents of foreign groups and to foreign groups with a Korean holding company.

## Tools

| Step | Server | Tool | Why |
|---|---|---|---|
| 1 | korean-tax-mcp | `find_article` | find the provisions (Corporate Tax Act Art. 18-4, Restriction of Special Taxation Act Art. 23-2 and their decrees) |
| 2 | korean-tax-mcp | `law_article` (`as_of`) | read Art. 23-2 as in force for the tax year |
| 3 | korean-tax-mcp | `article_addenda` (optional) | from when the amendment applies |
| 4 | korean-tax-calc-mcp | `foreign_subsidiary_dividend` | exclusion vs foreign tax credit, amounts and tax adjustments |

## 1. The provision

```json
{"tool": "law_article", "arguments": {"law_name": "조세특례제한법", "article": "제23조의2", "as_of": "20261231"}}
```

Result outline (0.15.1), version in force from 2026-09-18:

- Paragraph 1: for dividends a Korean company (excluding indirect investment companies under Corporate Tax Act Art. 57-2(1)) receives **from 2026-01-01 to 2026-12-31** from a foreign subsidiary (10% or more of voting shares; 5% for overseas resource development companies; plus requirements set by decree), **100%** is excluded when applying Corporate Tax Act Art. 18-4(1).
- Paragraph 2: 100% also for dividends received in 2026 from a specified foreign corporation (CFC) that has no distributable retained earnings at year end and therefore no deemed dividend.
- Paragraph 3: if the company paid interest on borrowings in the year, an amount computed by decree from that interest (reflecting the share of foreign-subsidiary investment in total assets) is subtracted from the exclusion.

## 2. The numbers

```json
{"tool": "foreign_subsidiary_dividend", "arguments": {"received_on": "2026-04-30", "ownership_ratio": 1.0, "held_months": 24, "dividend": 1000000000, "foreign_withholding": 50000000}}
```

The same call with `received_on: "2025-04-30"` shows the 95% rule:

| Field | Received 2026-04-30 | Received 2025-04-30 |
|---|---|---|
| Regime | exclusion | exclusion |
| Dividend | 1,000,000,000 | 1,000,000,000 |
| Excluded from income | 1,000,000,000 | 950,000,000 |
| Included in income | 0 | 50,000,000 |
| Creditable foreign tax | 0 | 0 |
| Foreign tax not deductible | 50,000,000 | 50,000,000 |
| Basis | Restriction of Special Taxation Act Art. 23-2 and Decree Art. 20; Act No. 21549 addenda Art. 2; Corporate Tax Act Art. 18-4, 57(7), 21(1) | Corporate Tax Act Art. 18-4, 57(7), 21(1) |

Amounts in KRW. What the tool explains:

- A dividend that gets the exclusion cannot also get the foreign tax credit (Corporate Tax Act Art. 57(7)), so the creditable foreign tax is 0.
- The KRW 50 million foreign tax is not deductible (Art. 21(1)). That adjustment applies only if you booked it as an expense.
- For 2026 receipts, if the company paid interest on borrowings that year, pass `borrowing_interest`, `subsidiary_book_value_daily_sum` and `total_assets_daily_sum` so the Art. 23-2(3) deduction is applied. The example assumes no interest.
- With several foreign subsidiaries, run each separately and add up the results.
- Form: the foreign subsidiary dividend statement (외국자회사 수입배당금액 명세서) attached to the corporate tax return.

## What the agent should answer

- 100% exclusion for 2026 receipts (95% otherwise), quoting Art. 23-2(1).
- No foreign tax credit on an excluded dividend; foreign tax not deductible.
- What to confirm: shareholding of 10% or more on the dividend date and the holding period, CFC status, and interest on borrowings for the 2026 deduction.

Not tax advice. Verify against the statute in force for the tax year and the addenda.

[All use cases](index.md)
