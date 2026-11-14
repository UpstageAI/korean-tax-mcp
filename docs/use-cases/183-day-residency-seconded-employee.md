# A seconded employee in Korea for more than 183 days: Korean tax resident?

**Question:** *"A US citizen is seconded by our US parent to the Korean subsidiary for two years. She spent 200 days in Korea last year and her job needs her in Korea for more than 183 days a year. Is she a Korean tax resident for 2026? She also keeps her home in the US. What happens if the US treats her as a resident too?"*

## Tools

| Step | Server | Tool | Why |
|---|---|---|---|
| 1 | korean-tax-mcp | `residency_check` | 3-step test: Income Tax Act (domicile / 183-day residence) → dual residence → treaty tie-breaker. Rules in code, no key needed |
| 2 | korean-tax-mcp | `tax_treaty` | the treaty's residence article (`residency_check` attaches an excerpt when it can fetch it) |
| 3 | korean-tax-mcp | `residency_report` (optional) | a written review report from the `residency_check` result |
| 4 | korean-tax-mcp | `search_tax_rulings` with `tax="국조"` | NTS rulings on seconded employees |
| 5 | korean-tax-mcp | `wage_income_guide` | once residency is known: wage income rules, including the flat tax rate option for foreign employees |

`domestic_stay_days` is the number of days in Korea in the year before `judgment_year`. You can pass `entry_dates` and `exit_dates` instead and the tool counts the days.

## Case A: the US does not treat her as a resident

```json
{"tool": "residency_check", "arguments": {"judgment_year": 2026, "domestic_stay_days": 200, "job_needs_183_days": true, "domestic_business_activity": true, "foreign_nationality": true, "treaty_country": "미국"}}
```

Result outline (0.15.1):

- **Step 1 (Income Tax Act): resident.** Domicile is deemed because her job normally requires living in Korea for 183 days or more (Enforcement Decree Art. 2(3)1). Residence of 183 days or more: 200 days (Decree Art. 4(3)). Hence resident under Income Tax Act Art. 1-2(1).
- **Step 2: not a dual resident.** The other country does not treat her as its resident.
- **Step 3: tie-breaker not applied.**
- **Final: resident.** The tool states the legal principle it applies: residence is judged by living relations in Korea only, not by comparing Korea with abroad (Supreme Court 92누11695).

## Case B: the US also treats her as a resident

Add the facts for the tie-breaker:

```json
{"tool": "residency_check", "arguments": {"judgment_year": 2026, "domestic_stay_days": 200, "job_needs_183_days": true, "domestic_business_activity": true, "foreign_nationality": true, "treaty_country": "미국", "treaty_country_is_resident": true, "permanent_home": "양쪽", "center_of_vital_interests": "국외", "habitual_abode": "양쪽", "nationality": "외국"}}
```

Result outline (0.15.1):

- Step 1: resident (as in case A).
- **Step 2: dual resident.** The burden of proving dual residence and the treaty's application is on the taxpayer (Supreme Court 2006두3964, 2014두13959).
- **Step 3: tie-breaker applied.** Permanent home: in both countries, so not decided at this step. Center of vital interests: closer to the US, **decided here**. The treaty's residence article is attached as an excerpt.
- **Final: non-resident** (treated as a US resident under the treaty).
- Similar cases attached, e.g. Supreme Court 2018두60847 (Korea–Japan treaty tie-breaker, center of vital interests in Japan).

Values like `permanent_home` and `center_of_vital_interests` are your judgment of the facts. The tool does not decide them. Change them to see where the outcome turns.

> Fixed in 0.15.2: case B now also works with `lang="en"` (in 0.15.1 it stopped with a `KeyError` on the tie-breaker label). Re-run with 0.15.2 and `lang="en"`: final outcome `non-resident`, decided at the center-of-vital-interests step, as above.

## Seconded staff: what the NTS has said

`search_tax_rulings` with `query: "해외 파견 직원 인건비 현지법인 부담"` and `tax: "국조"` returns, among others:

- 서면-2021-국제세원-5503 (2022-04-25): employees of a Korean company seconded to its 100%-owned overseas subsidiary are residents under Korean law; if they are also residents of Canada, the Korea–Canada treaty Art. 4 decides.
- 서면인터넷방문상담2팀-1121 (2008-06-04): an employee seconded while keeping employment with the Korean company is a resident under Decree Art. 3.

These two cover the outbound case (Korean staff sent abroad). For an inbound secondee, the 3-step test above applies.

## What the agent should answer

- Resident or non-resident, step by step, with the article for each step.
- Where the answer turns (here: whether the US treats her as a resident, and where her center of vital interests is), and who carries the burden of proof.
- Next steps: wage income rules (`wage_income_guide`) and, for numbers, korean-tax-calc-mcp (`wage_income_tax`, `withholding_tax`).

Not tax advice. The residency rules are bundled; check the statute in force (`law_article` with `as_of`) and the treaty text (`tax_treaty`).

[All use cases](index.md)
