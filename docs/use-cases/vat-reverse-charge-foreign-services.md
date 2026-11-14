# VAT reverse charge on services from a foreign supplier

**Question:** *"We are a Korean company. On 2026-03-15 we paid KRW 50 million to a foreign consulting firm with no place of business in Korea. Do we have to pay Korean VAT on it ourselves (대리납부, the reverse charge), how much, and by when? Does it matter what we use the service for?"*

## Tools

| Step | Server | Tool | Why |
|---|---|---|---|
| 1 | korean-tax-mcp | `find_article` | find the reverse charge provisions |
| 2 | korean-tax-mcp | `law_article` (`as_of`) | read Value-Added Tax Act Art. 52 and Decree Art. 95 as in force on the payment date |
| 3 | korean-tax-calc-mcp | `vat_foreign_currency_base` (if paid in foreign currency) | convert to KRW at the exchange rate you supply |
| 4 | korean-tax-calc-mcp | `vat_reverse_charge` | whether each payment is subject, tax base, VAT, due date |
| 5 | korean-tax-mcp | `search_tax_rulings` (`tax="부가"`) | rulings on whether a service is used in a taxable business |

## 1. Find the provisions

```json
{"tool": "find_article", "arguments": {"keyword": "대리납부"}}
```

Result (0.15.1): Value-Added Tax Act Art. 52 (대리납부, reverse charge; version in force from 2026-01-02) and its Enforcement Decree Art. 95 (from 2026-04-01). Also returned: the separate credit-card VAT withholding rules in Restriction of Special Taxation Act Art. 106-10, which are a different regime. Next step suggested by the tool: `law_article` for the paragraph you need.

## 2. The numbers

Two payments of the same service, one used for a VAT-exempt business and one for a taxable business, to show the difference:

```json
{"tool": "vat_reverse_charge", "arguments": {"year": 2026, "items": [
  {"이름": "Consulting, exempt use", "공급자": "국내사업장_없음", "대가": 50000000, "지급일": "2026-03-15", "용도": "면세"},
  {"이름": "Consulting, taxable use", "공급자": "국내사업장_없음", "대가": 50000000, "지급일": "2026-03-15", "용도": "과세"}]}}
```

Input values: 공급자 = supplier status (국내사업장_없음 no place of business in Korea / 국내사업장_있음_비귀속 has one but the supply is not attributable to it / 국내사업장_있음_귀속 attributable), 대가 = amount paid in KRW, 지급일 = payment date, 용도 = use (면세 exempt / 과세 taxable / 불공제 non-deductible / 공통 shared / 비사업 non-business).

| Item | Subject? | Reason | Tax base (KRW) | VAT (KRW) | Statutory due date | Due date applied |
|---|---|---|---|---|---|---|
| Consulting, exempt use | yes | used in an exempt (non-taxable) business: the whole amount is subject | 50,000,000 | 5,000,000 | 2026-04-25 | 2026-04-27 |
| Consulting, taxable use | no | used in a taxable business: not subject (Art. 52(1), words in parentheses) | 50,000,000 | 0 | 2026-04-25 | 2026-04-27 |

Total reverse-charge VAT: KRW 5,000,000. The due date moves from 2026-04-25 (a Saturday) to Monday 2026-04-27. Basis: Value-Added Tax Act Art. 52(1) and (2), Enforcement Decree Art. 95(1) and (2).

For a service used in both kinds of business (용도 `공통`), pass `taxable_supply` and `exempt_supply` for the tax period and the tool apportions.

The tool notes that electronic services supplied by foreign businesses under the simplified registration (Value-Added Tax Act Art. 53-2) are out of its scope.

## What the agent should answer

- Whether the payment is subject (supplier has no Korean place of business, and the service is not used in a taxable business), with Art. 52.
- The VAT and the due date from `vat_reverse_charge`.
- What to confirm: the supplier's Korean presence, the actual use of the service, and the exchange rate if paid in foreign currency.

Not tax advice. Verify against the statute in force on the payment date (`law_article` with `as_of`).

[All use cases](index.md)
