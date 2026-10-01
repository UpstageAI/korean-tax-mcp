# korean-tax-mcp — Korea Tax Law MCP

<!-- mcp-name: io.github.seungmiyoon/korean-tax-mcp -->

![Demo](https://raw.githubusercontent.com/seungmiyoon/korean-tax-mcp/main/docs/demo.gif)

An MCP server for **Korean tax law sources**. Plug it into Claude, Cursor, or any MCP client to get National Tax Service (NTS) rulings, court and tax tribunal decisions, basic rules, and statutes — with document numbers.

Works well alongside [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) for general Korean statutes.

## Features

| Tool | What it does | Key |
|---|---|---|
| `search_tax_rulings` | Search NTS rulings (Q&A replies, advance rulings) and decisions (courts, Tax Tribunal, objections) — newest first, filter by tax type and date | none |
| `get_tax_ruling` | Full text — facts, question, reply / holding and reasons, cited statutes | none |
| `rulings_by_article` | All rulings and decisions citing a given article (e.g. Corporate Tax Act Art. 52) | none |
| `basic_rules` | Full text of NTS Basic Rules (기본통칙) by article | none |
| `execution_standards` | Tax Execution Standards (집행기준) items, page and link | none |
| `casebook_search` | NTS 2025 Tax Interpretation Casebook (96 cases) | none |
| `law_article` | Statute text as in force on a given date, plus Act → Decree → Rule delegation chain | `LAW_OC` |
| `compare_with_case` | Compare your facts and argument with rulings: supports / contradicts / distinguish | `UPSTAGE_API_KEY` (Solar) |
| `research_issue` | Everything that applied at a past date: statute chain, basic rules, standards, and rulings — flags statute changes and whether each ruling was issued under the same text | `LAW_OC` for statutes |
| `tax_treaty` | Korea's tax treaties with 96 countries, article by article (Korean / English) | none |
| `search_nts_publications` | Full-text search in NTS guidebooks — transfer pricing, APA reports, overseas business guides | none |
| `search_local_documents` | Page-level search over PDFs you downloaded (e.g. OECD Transfer Pricing Guidelines) — set `KOREAN_TAX_MCP_DOCS` | none |
| `verify_citations` | Check that cited ruling numbers and statute articles in a draft actually exist | `LAW_OC` for statutes |

## Install

```bash
claude mcp add korean-tax -- uvx korean-tax-mcp
```

```json
{
  "mcpServers": {
    "korean-tax": {
      "command": "uvx",
      "args": ["korean-tax-mcp"],
      "env": { "LAW_OC": "optional", "UPSTAGE_API_KEY": "optional" }
    }
  }
}
```

- `LAW_OC`: free key from [open.law.go.kr](https://open.law.go.kr) (Ministry of Government Legislation)
- `UPSTAGE_API_KEY`: [console.upstage.ai](https://console.upstage.ai)

## Notes

- Rulings and decisions reflect the law at the time they were issued; check the statute in force for the relevant year (`law_article` with `as_of`).
- Uses the public lookup of the NTS legal information system (taxlaw.nts.go.kr) with a 1-day cache and ≥0.5 s between calls.
- Results are research aids, not tax advice.

## License

MIT · Mia (Seungmi Yoon), Upstage
