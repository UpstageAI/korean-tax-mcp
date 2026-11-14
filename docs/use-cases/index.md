# Korean tax for foreign companies, expats and Korean subsidiaries: use cases

Each page takes one question a foreign company, an expat or an AI agent working for them would ask about Korean tax. It shows which MCP tools answer it and what the calls and answers look like. The pages use two servers:

- **[korean-tax-mcp](https://github.com/UpstageAI/korean-tax-mcp)**: the legal basis (statutes on any date, NTS rulings, court decisions, 96 tax treaties, treaty withholding rates, residency test, transfer pricing guides). `uvx korean-tax-mcp`
- **[korean-tax-calc-mcp](https://github.com/UpstageAI/korean-tax-calc-mcp)**: the amounts (withholding, VAT reverse charge, expat cost recharge, foreign subsidiary dividends and more). `uvx korean-tax-calc-mcp`

| # | Question | Main tools |
|---|---|---|
| 1 | [Royalties paid by a Korean subsidiary to its US parent: what is the withholding tax under the treaty?](royalty-withholding-us-parent.md) | `treaty_withholding_rates`, `nonresident_withholding` |
| 2 | [A seconded employee spends more than 183 days in Korea: is she a Korean tax resident?](183-day-residency-seconded-employee.md) | `residency_check`, `residency_report` |
| 3 | [Recharging the cost of staff seconded to an overseas subsidiary](expat-cost-recharge-overseas-subsidiary.md) | `transfer_pricing_guide`, `search_tax_rulings`, `expat_cost_recharge` |
| 4 | [VAT reverse charge on services bought from a foreign supplier](vat-reverse-charge-foreign-services.md) | `find_article`, `law_article`, `vat_reverse_charge` |
| 5 | [Dividends from a foreign subsidiary in 2026: the 100% exclusion (Restriction of Special Taxation Act Art. 23-2)](foreign-subsidiary-dividend-exclusion-2026.md) | `law_article`, `foreign_subsidiary_dividend` |

## How the examples were made

The calls and results on these pages were run on 2026-11-14 against the published packages `korean-tax-mcp==0.15.1` and `korean-tax-calc-mcp==0.51.1` over MCP stdio. The amounts are made-up inputs; every output amount comes from the tool, not from hand calculation. Result fields are shown in English here; the tools return Korean keys by default, and korean-tax-mcp tools accept `lang="en"`.

Tool inputs use Korean values for some enums (for example `income_kind: "사용료"` for royalties). Each page gives the exact arguments that were used.

## Limits

These pages are not tax advice. They show how to find and compute with the sources. Check the statute in force for your tax year (`law_article` with `as_of`), read the full treaty clause and the rulings cited, and confirm your facts with a qualified professional.

[Back to README](../../README-EN.md)
