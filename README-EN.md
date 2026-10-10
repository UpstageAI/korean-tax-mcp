# korean-tax-mcp — Korea Tax Law MCP

<!-- mcp-name: io.github.UpstageAI/korean-tax-mcp -->

![Demo](https://raw.githubusercontent.com/UpstageAI/korean-tax-mcp/main/docs/demo.gif)

[![Built with Upstage Solar Pro 4](https://img.shields.io/badge/Built%20with-Upstage%20Solar%20Pro%204-7A3FF2)](https://www.upstage.ai/)

> **Developed with Upstage Solar Pro 4 since 0.7.0** (0.6.0 and earlier predate it). Residency determination (`residency_check`, `residency_report`), treaty keyword synonyms and lookup hardening (retries, cache, key masking) were written by Solar Pro 4 (Solar Code CLI), reviewed on each PR by CodeSolar (Solar Pro 4-based code review) and cross-checked with tests by Claude.

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
| `compare_with_case` | Compare your facts and argument with rulings: supports / contradicts / distinguish. By default returns candidate excerpts plus judging instructions for your AI (`mode: "host_ai"`); Solar judges when configured | none (`UPSTAGE_API_KEY` optional) |
| `research_issue` | Everything that applied at a past date: statute chain, basic rules, standards, and rulings — flags statute changes and whether each ruling was issued under the same text | `LAW_OC` for statutes |
| `treaty_withholding_rates` | Treaty withholding caps on dividends, interest, royalties with ownership conditions and the clause text | none |
| `search_forms` | Statutory annexes (useful-life and depreciation tables) and official tax forms | none |
| `article_history` | When an article changed and whether an upcoming amendment changes it | `LAW_OC` |
| `tax_treaty` | Korea's tax treaties with 96 countries, article by article (Korean / English) | none |
| `search_nts_publications` | Full-text search in NTS guidebooks — transfer pricing, APA reports, overseas business guides | none |
| `search_local_documents` | Page-level search over PDFs you downloaded (e.g. OECD Transfer Pricing Guidelines) — set `KOREAN_TAX_MCP_DOCS` | none |
| `verify_citations` | Check that cited ruling numbers and statute articles in a draft actually exist | `LAW_OC` for statutes |

## English output

Every tool takes `lang="en"`:

- English field names and labels (`doc_no`, `summary`, `effective_date`, …)
- Tax treaties: official English text
- Statutes: official English translation from the Korea Legislation Research Institute (not legally binding; the Korean text prevails). Requires your `LAW_OC` key to be approved for English laws (open.law.go.kr → OPEN API → 영문법령)
- Rulings, decisions, basic rules: originals are Korean only. By default they are returned in Korean with a `host_ai_translate` instruction so your AI translates them (nothing sent to Upstage). Optionally, with `UPSTAGE_API_KEY`, titles and summaries are machine-translated by Upstage Solar (originals kept in `*_ko`); full texts stay Korean

Ask your agent in English, e.g. *"Find recent NTS rulings on deemed interest for loans to related parties (lang=en)"* or *"Show the dividend article of the Korea–US tax treaty in English."*

## On-prem Solar

Fact comparison, outcome summary and translation are done by your own AI by default; Solar is optional. To use a Solar instance installed inside a closed network (OpenAI-compatible API), set `KOREAN_TAX_MCP_SOLAR_BASE_URL` (e.g. `http://10.0.0.5:8000/v1`), optionally `KOREAN_TAX_MCP_MODEL`, `KOREAN_TAX_MCP_SOLAR_KEY`, and `KOREAN_TAX_MCP_SOLAR_VERIFY=0` for self-signed certificates.

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
- `UPSTAGE_API_KEY` (optional): [console.upstage.ai](https://console.upstage.ai) — without it, `compare_with_case`, `compare_outcomes` `explain=True` and `lang="en"` still work in `host_ai` mode; with it, Solar does the comparison, summary and translation (`solar_cloud`). `KOREAN_TAX_MCP_SOLAR_BASE_URL` uses an in-house Solar (`solar_onprem`)

## Notes

- **Data transmission** — By default the server calls only the public APIs of the Ministry of Government Legislation and the National Tax Service, and AI judgment, summaries and translation are done by your own AI — nothing is sent to Upstage. Optional: when `UPSTAGE_API_KEY` is set, Solar performs the comparison, summary and translation, and then the input is sent to the Upstage API (api.upstage.ai) — **do not enter personal or other sensitive data**. In air-gapped environments, set `KOREAN_TAX_MCP_SOLAR_BASE_URL` to an in-house Solar to avoid any external transmission.

- Rulings and decisions reflect the law at the time they were issued; check the statute in force for the relevant year (`law_article` with `as_of`).
- Uses the public lookup of the NTS legal information system (taxlaw.nts.go.kr) with a 1-day cache and ≥0.5 s between calls.
- Results are research aids, not tax advice.

## License

MIT © 2026 Upstage

Created by Mia (Seungmi Yoon)
