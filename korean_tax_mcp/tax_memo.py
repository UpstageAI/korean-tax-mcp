"""세무 검토 메모(tax memo) — 따지는 순서(논리선)·구조 스키마·점검. 작성 Mia(윤승미)

AI가 즉흥으로 쓰지 않도록, 메모 순서와 쟁점을 따지는 차례를 서버가 정하고(tax_memo_guide),
채워 온 구조 JSON을 그 순서에 대어 점검한 뒤(build_tax_memo) Word 파일로 그린다(memo_docx.py).
외부 호출 없음. 내용의 근거는 이 서버의 조문·조약·해석 도구와 계산 서버(korean-tax-calc-mcp) 결과여야 한다.
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

LANGS = ("en", "ko")
PRIORITIES = {"en": ("HIGH", "MEDIUM", "LOW"), "ko": ("긴급", "높음", "보통")}
# 쟁점을 따지는 순서(issue.stage)
STAGES = ("characterization", "taxability", "rate", "treaty", "procedure", "related_taxes")
STAGE_LABEL = {
    "en": {"characterization": "what the payment or transaction is", "taxability": "whether and where it is taxed (source)",
           "rate": "rate and tax base under domestic law", "treaty": "treaty relief", "procedure": "procedure, filing and documents",
           "related_taxes": "related taxes (local income tax, VAT, penalties)"},
    "ko": {"characterization": "소득·거래의 구분", "taxability": "과세 여부·원천", "rate": "국내 세법의 세율·과세표준",
           "treaty": "조세조약", "procedure": "절차·신고·서류", "related_taxes": "관련 세목(지방소득세·부가가치세·가산세)"},
}
ROLES = ("component", "total", "base", "info", "")

LABELS = {
    "en": {
        "title": "MEMORANDUM",
        "head": (("to", "To"), ("prepared_by", "Prepared by"), ("date", "Date"), ("re", "Re"), ("scope", "Scope"), ("basis", "Basis"), ("workings", "Workings")),
        "summary": "Executive summary", "question": "Question presented", "background_question": "Background and question",
        "short_answer": "Short answer", "facts": "Facts and assumptions", "analysis": "Analysis",
        "calculation": "Calculation", "risks": "Risks and open points", "next_steps": "Recommended next steps",
        "rule": "Rule.", "application": "Application.", "conclusion": "Conclusion.", "confirm": "To confirm.",
        "decision": "How the facts change the result", "item": "Item", "basis_col": "Basis", "amount": "Amount",
        "priority": "Priority", "point": "Point", "why": "Why it matters · what to check", "check": "Check:",
        "see_section": "(Section {n}).", "if_not": "If not: see Section {n} — {p}.", "how": "How this memo was prepared.",
        "owner": "Owner", "by": "By",
        "key_figures": "Key figures", "recommended": "recommended", "review": "Review of the handling to date", "severity": "Severity",
        "finding": "Finding", "fix": "Action", "action_list": "Action list", "no": "#", "action": "Action",
        "limitations": "Limitations and unverified points", "authorities": "Principal authorities",
        "notice": "Prepared with AI tools (Korean Tax MCP). Not tax advice — verify against the statute and with a qualified adviser.",
    },
    "ko": {
        "title": "메모",
        "head": (("to", "수신"), ("prepared_by", "작성"), ("date", "일자"), ("re", "제목"), ("scope", "범위"), ("basis", "근거 자료"), ("workings", "계산 파일")),
        "summary": "핵심 요약", "question": "쟁점", "background_question": "배경과 쟁점",
        "short_answer": "결론", "facts": "사실관계와 전제", "analysis": "검토",
        "calculation": "계산", "risks": "위험과 확인할 점", "next_steps": "다음 단계",
        "rule": "근거 규정", "application": "적용", "conclusion": "결론", "confirm": "확인할 점",
        "decision": "사실관계별 결과", "item": "항목", "basis_col": "근거", "amount": "금액",
        "priority": "우선순위", "point": "사항", "why": "왜 중요한지 · 확인할 것", "check": "확인:",
        "see_section": "({n}절 표).", "if_not": "달라지면 {n}. 위험과 확인할 점 — {p}", "how": "작성 방법.",
        "owner": "담당", "by": "기한",
        "key_figures": "핵심 수치", "recommended": "권고", "review": "기존 처리 검토 결과", "severity": "위험도",
        "finding": "발견 사항", "fix": "조치", "action_list": "조치 목록", "no": "번호", "action": "할 일",
        "limitations": "한계와 미확인 사항", "authorities": "주요 근거",
        "notice": "AI 도구(Korean Tax MCP)로 작성했습니다. 세무 자문이 아니며, 법령 원문과 전문가 확인이 필요합니다.",
    },
}

SCHEMA = {
    "lang": "str('en'|'ko') — the user's language / 사용자 언어",
    "head": {"prepared_by": "str(required)", "date": "str(required)", "re": "str(required, subject)", "scope": "str(required)",
             "to": "str(optional, addressee)", "basis": "str(optional: documents relied on and the as-of date of the law)",
             "workings": "str(optional: file name of the accompanying Excel workings)"},
    "summary": "[{conclusion: str(one sentence, printed bold — the answer, with the amount if any), basis: str(1-2 sentences + at least one [^id])}] — exactly 3",
    "background": "str(optional, one short paragraph)",
    "question": "str(1-2 sentences, required)",
    "short_answer": {"answer": "str(printed bold)", "conditions": "str(what the answer depends on)"},
    "key_figures": "{title: str(optional), columns: [str] (row label + 1 to 3 scenario columns), rows: [[str] | {cells: [str], role: 'total'}], "
                   "recommended: str(the scenario column you recommend — required with 2+ scenarios), note: str(the condition for each scenario — required with 2+ scenarios)} "
                   "— optional: the numbers table printed right under the short answer; every amount must also be in calculation or analysis",
    "facts": "[str | {text: str, assumption: bool, changes_answer: bool, risk: str(risk id — required when changes_answer)}]",
    "analysis": "[{stage: '" + "'|'".join(STAGES) + "', heading: str(states the conclusion), rule: str(statute/treaty/ruling + [^id]), "
                "application: str, conclusion: str, confirm: str(optional), table: {title, columns: [str], rows: [[str] | {cells, role: 'total'}], note}(optional)}] — at least 3, in stage order",
    "review": "{verdict: str(one sentence, printed bold: was the handling to date correct?), findings: [{finding: str(short name of what is wrong), "
              "detail: str(optional), amount: str(amount at stake, '—' if none), severity: 'HIGH'|'MEDIUM'|'LOW' (ko: '긴급'|'높음'|'보통'), action: str(how to fix)}]} "
              "— required when the question asks whether past handling was correct; otherwise omit",
    "decision_table": "{title: str(optional), columns: [str], rows: [[str]]} — optional: fact pattern → result",
    "calculation": "{currency: str(e.g. 'KRW'), rows: [{item, basis, amount, role: 'component'|'total'|'base'|'info'}], "
                   "note: str(optional), scenarios: [{title, rows:[...]}]} — required; component rows must add up to the total row",
    "risks": "[{id: str, priority: 'HIGH'|'MEDIUM'|'LOW' (ko: '긴급'|'높음'|'보통'), point: str, why: str, check: str}]",
    "next_steps": "[str | {action: str, owner: str(optional), deadline: str(optional)}]",
    "action_list": "[{action: str, owner: str, deadline: str(required)}] — optional: prints the next steps as a table (#, action, owner, by); use instead of next_steps",
    "limitations": "{text: str(optional paragraph), items: [str]} — optional section collecting what could not be confirmed; required when any field or footnote is "
                   "marked not verified. Cite a not-verified footnote here as [^id]",
    "authorities": "[str] — optional closing list of principal authorities; leave out by default (the footnotes already carry the sources)",
    "footnotes": "[{id: str, text: str}] — referenced in any text field as [^id]; numbered in reading order by the server; a repeated source reuses its first note number",
    "notice": "str(optional footer line; a default is used when empty)",
    "prepared_how": "str(required: tools used, date, which text governs)",
    "target_pages": "int(optional, default 5) — the length the memo should fit in (A4 pages); build_tax_memo estimates the length and warns when it is over, naming the longest blocks",
    "inline": "**bold** and [^footnote-id] may be used inside any text field",
}

GUIDE = {}
GUIDE["en"] = """[Tax memo — the logic line] The server fixes the order of reasoning; you fill it only with the user's facts and tool results. Output: a finished Word (.docx) file written by build_tax_memo — do not write your own docx script.
[Workflow]
1. Gather the facts from the user (who pays whom, what for, how much, when, residence, documents held).
2. Call the tools before writing. Requirements and sources here: the requirement-guide tools (*_guide), find_article, law_article (as_of), tax_treaty, search_tax_rulings, compare_outcomes. Numbers in korean-tax-calc-mcp (find_tool picks the calculator). Take the issues from the requirement-guide results, from the calculators' issue lists (쟁점) and from the user's documents — this guide gives no checklist for any particular transaction. Do not compute or cite from memory.
3. Fill the structure JSON (schema and example below). Run verify_citations on the footnotes.
4. build_tax_memo(structure) → fix every warning → build again. check_only=true validates without writing.
Nothing may be asserted that is not in a tool result or in the user's facts; anything else goes under assumptions (facts) or open points (risks).
[Order of the memo]
- Head: prepared_by, date, re (subject), scope. Optional lines when known: to (addressee), basis (documents relied on and the as-of date of the law), workings (file name of the Excel workings that go with the memo).
- Executive summary: exactly 3 numbered items. Each = one conclusion sentence (the answer, with the amount if any; printed bold) + one or two sentences of basis + at least one footnote. Answer first; do not narrate how you worked.
- 1 Question presented: one or two sentences.
- 2 Short answer: starts with the answer (bold), then the conditions it depends on. Optional key_figures: a numbers table right under the answer — one row label column plus 1 to 3 scenario columns side by side, the total row marked role="total". With two or more scenarios name the one you recommend (recommended = that column's heading) and state in note the condition under which each applies. Every amount in it must also be in the calculation or the analysis.
- 3 Facts and assumptions: bullets. An assumption that would change the answer if false gets changes_answer=true and risk=<id of a risk item>.
- 4 Analysis: issues in the order an examiner tests requirements. Give each issue a stage and keep this order: characterization (what the payment or transaction is) → taxability (whether and where it is taxed) → rate (rate and base under domestic law) → treaty → procedure (filing, documents) → related_taxes (local income tax, VAT, penalties). Skip a stage that does not arise; never reorder. At least 3 issues. Each issue: a heading that states the conclusion (not just the topic), then rule (statute, treaty or ruling, with article or case number as a footnote) → application to the facts → conclusion, and optionally what to confirm.
- An issue may carry one table (analysis[].table) for a short computation or comparison that belongs to that issue.
- Optional decision table: fact pattern → result (which facts lead to which outcome).
- Review of the handling to date (review): required when the question asks whether something already done was right ("have we handled it correctly so far"). verdict = one bold sentence; findings = one item per problem with what is wrong, the amount at stake, severity (HIGH / MEDIUM / LOW) and the action that fixes it. The verdict and the names of the findings are printed under the short answer, the full table (amounts and actions) once, after the analysis. Leave it out when the question is only about the future.
- 5 Calculation: rows of item, basis, amount. Mark the rows that add up with role="component" and the sum with role="total". Every amount in the executive summary and short answer must appear here or in a table (key_figures, an issue table); put alternatives under scenarios.
- 6 Risks and open points: priority HIGH / MEDIUM / LOW, the point, why it matters, what to check. Only what is still open — a problem already set out as a review finding is not repeated here.
- 7 Recommended next steps: numbered actions, with an owner or deadline if known. Or action_list: the same as a table (#, action, owner, by) — every item then needs a deadline.
- Limitations and unverified points (limitations): collect in one place everything you could not confirm. Required as soon as any field or footnote says "not verified"; cite such a footnote here as [^id] so the two agree. Do not call something verified in a footnote and unconfirmed here.
- Principal authorities (authorities): optional closing list; off by default because the footnotes carry the sources.
- Footnotes: primary sources first — statute article, treaty article, case number and date. For Korean law give the original term once in parentheses, e.g. Example Tax Act (예시세법), Art. 00(0). Put [^id] where the source is used; the server numbers notes in reading order and reuses the same note number for a repeated source.
- Footer notice line, and a closing "How this memo was prepared" paragraph (prepared_how): tools used, date, and that the original-language text governs.
[Length — say each thing once]
- Target: target_pages (default 5 A4 pages; pass another number to build_tax_memo or set structure.target_pages when the reader asked for one). build_tax_memo returns length {estimated_pages, target_pages, blocks} and warns when the estimate is over, naming the longest blocks and the issues over budget.
- Budget per field: summary basis 1-2 sentences; short_answer.conditions up to 3 sentences; a fact bullet up to 3 sentences; per issue rule 1-2 sentences, application 2-3, conclusion 1, confirm 1 (about 90 words for the whole issue); a risk = why in 1-2 sentences + one check sentence; an action = one line.
- A number is worked out in one place. What a table shows (key_figures, an issue table, the calculation) is not spelled out again in prose — name the result and point to the table. A table is printed once: do not repeat an issue table under calculation.scenarios.
- A point is argued in one place. A review finding carries the problem, the amount and the fix; the analysis issue on the same point gives the rule and the reasoning and does not restate the amounts; a risk item or an action only names it. The summary and the short answer give the answer, not the derivation.
- Something not confirmed is stated once where it arises (confirm or the footnote) and listed in limitations in a few words. Leave authorities out unless the reader asked for a list of sources.
[Writing rules]
- Conclusions before reasons. One idea per paragraph (under about 120 words).
- Numbers carry units and currency (KRW 1,000,000; 3 percent).
- No invented facts, numbers or citations. No hedging filler ("it should be noted that", "generally speaking").
- Write in the user's language (lang="en" or "ko"); the memo headings follow lang."""

GUIDE["ko"] = """[세무 메모 — 따지는 순서] 따지는 순서는 서버가 정하고, 내용은 사용자가 준 사실과 도구 결과로만 채운다. 결과물은 build_tax_memo가 저장하는 완성된 Word(.docx) 파일 — docx를 직접 만들지 않는다.
[작업 순서]
1. 사용자에게서 사실을 모은다(누가 누구에게, 무엇의 대가로, 얼마를, 언제, 거주지, 갖춘 서류).
2. 쓰기 전에 도구를 호출한다. 요건·근거는 이 서버: 요건 안내 도구(*_guide), find_article, law_article(as_of), tax_treaty, search_tax_rulings, compare_outcomes. 숫자는 korean-tax-calc-mcp(find_tool로 계산기를 고름). 쟁점은 요건 안내 결과, 계산기가 돌려준 쟁점 목록, 사용자가 준 문서에서 가져온다 — 이 안내에는 특정 거래의 점검 목록이 없다. 기억으로 계산하거나 인용하지 않는다.
3. 구조 JSON을 채운다(아래 schema·example). 각주는 verify_citations로 확인한다.
4. build_tax_memo(structure) → 경고를 모두 고침 → 다시 만든다. check_only=true면 파일 없이 점검만 한다.
도구 결과나 사용자가 준 사실에 없는 것은 단정하지 않는다. 그런 내용은 전제(facts)나 확인할 점(risks)에 적는다.
[메모 순서]
- 머리: prepared_by(작성), date(일자), re(제목), scope(범위). 알면 선택으로 to(수신), basis(근거 자료와 법령 기준일), workings(함께 가는 엑셀 계산 파일 이름).
- 핵심 요약: 번호 붙은 항목 정확히 3개. 항목마다 결론 한 문장(답, 금액이 있으면 포함, 굵게 인쇄) + 근거 한두 문장 + 각주 1개 이상. 답부터 쓰고 작업 과정은 쓰지 않는다.
- 1 쟁점: 한두 문장.
- 2 결론: 답(굵게)으로 시작하고, 그 답이 성립하는 조건을 이어 쓴다. 선택 key_figures: 답 바로 아래 숫자 표 — 항목 열 하나와 경우(시나리오) 열 1~3개를 나란히, 합계 행은 role="total". 경우가 둘 이상이면 권고하는 쪽(recommended = 그 열 제목)과 경우마다 성립하는 조건(note)을 적는다. 표의 금액은 모두 계산이나 검토에도 있어야 한다.
- 3 사실관계와 전제: 글머리표. 틀리면 답이 바뀌는 전제는 changes_answer=true와 risk=<위험 항목 id>를 단다.
- 4 검토: 심사하는 사람이 요건을 따지는 차례대로 쟁점을 둔다. 쟁점마다 stage를 달고 이 순서를 지킨다: characterization(소득·거래의 구분) → taxability(과세 여부·원천) → rate(국내 세법의 세율·과세표준) → treaty(조세조약) → procedure(절차·신고·서류) → related_taxes(지방소득세·부가가치세·가산세). 해당 없는 단계는 건너뛰되 순서를 바꾸지 않는다. 쟁점은 3개 이상. 쟁점마다 결론을 말하는 소제목(주제만 쓰지 않음), 근거 규정(법령·조약·판례를 조문·사건 번호와 함께 각주로) → 사실관계에 적용 → 결론, 필요하면 확인할 점.
- 쟁점 안에 표 하나(analysis[].table)를 둘 수 있다 — 그 쟁점에 딸린 짧은 계산·비교.
- 선택: 사실관계별 결과 표(어떤 사실이면 어떤 결과가 되는지).
- 기존 처리 검토 결과(review): 이미 한 처리가 맞았는지를 묻는 질문("지금까지 맞게 처리했나")이면 필수. verdict = 굵은 한 문장 판정, findings = 문제마다 무엇이 문제인지·걸린 금액·위험도(긴급 / 높음 / 보통)·바로잡는 조치. 판정과 발견 사항 이름은 결론 아래에, 전체 표(금액·조치)는 검토 뒤에 한 번만 찍힌다. 앞으로의 처리만 묻는 질문이면 넣지 않는다.
- 5 계산: 항목·근거·금액 행. 더해서 합계가 되는 행은 role="component", 합계 행은 role="total". 핵심 요약과 결론에 쓴 금액은 모두 여기나 표(key_figures, 쟁점 안의 표)에 있어야 하고, 다른 경우는 scenarios에 둔다.
- 6 위험과 확인할 점: 우선순위 긴급 / 높음 / 보통, 사항, 왜 중요한지, 확인할 것. 아직 열려 있는 것만 — 검토 결과의 발견 사항으로 이미 적은 문제를 여기에 되풀이하지 않는다.
- 7 다음 단계: 번호 붙은 할 일. 담당·기한을 알면 적는다. 또는 action_list: 같은 내용을 표(번호·할 일·담당·기한)로 — 이때는 항목마다 기한이 필요하다.
- 한계와 미확인 사항(limitations): 확인하지 못한 것을 한곳에 모은다. 어느 칸이나 각주에 "미확인"이라고 적었다면 필수이고, 그런 각주는 여기서 [^id]로 가리켜 둘이 어긋나지 않게 한다. 각주에서는 확인했다고 하고 여기서는 미확인이라고 쓰지 않는다.
- 주요 근거(authorities): 끝에 붙이는 선택 목록. 각주에 출처가 있으므로 기본은 넣지 않는다.
- 각주: 1차 자료 먼저 — 법령 조문, 조약 조문, 사건 번호와 선고일. 출처를 쓴 자리에 [^id]를 넣으면 번호는 서버가 읽는 순서로 매기고, 같은 출처가 다시 나오면 처음 번호를 다시 쓴다.
- 바닥글 안내 한 줄과 "작성 방법" 맺음 문단(prepared_how): 쓴 도구, 날짜, 법령 원문이 기준임을 적는다.
[분량 — 같은 말은 한 번만]
- 목표: target_pages(기본 A4 5쪽. 읽는 사람이 분량을 정했으면 build_tax_memo에 그 숫자를 넘기거나 structure.target_pages에 적는다). build_tax_memo는 length {estimated_pages, target_pages, blocks}를 돌려주고, 어림 쪽수가 목표를 넘으면 가장 긴 블록과 기준을 넘은 쟁점을 짚어 경고한다.
- 칸마다 기준: 요약 basis 1~2문장, short_answer.conditions 3문장까지, 사실 항목 하나는 3문장까지, 쟁점마다 근거 규정 1~2문장·적용 2~3문장·결론 1문장·확인할 점 1문장(쟁점 하나에 280자 안쪽), 위험 항목은 why 1~2문장 + check 한 문장, 할 일은 한 줄.
- 숫자는 한 곳에서만 푼다. 표(key_figures, 쟁점 안의 표, 계산)에 있는 숫자를 글로 다시 풀어 쓰지 않는다 — 결과만 말하고 표를 가리킨다. 표도 한 번만: 쟁점 안의 표를 calculation.scenarios에 다시 넣지 않는다.
- 논점도 한 곳에서만 따진다. 검토 결과(review)의 발견 사항이 문제·금액·조치를 맡고, 같은 논점의 쟁점(analysis)은 근거 규정과 이유만 쓰며 금액을 되풀이하지 않는다. 위험 항목과 할 일은 이름만 가리킨다. 요약과 결론에는 답만 쓰고 계산 과정은 쓰지 않는다.
- 미확인 사항은 생긴 자리(confirm 또는 각주)에 한 번 쓰고 한계 절에는 몇 낱말로 적는다. 주요 근거(authorities)는 읽는 사람이 출처 목록을 원할 때만 넣는다.
[작성 규칙]
- 결론을 이유보다 먼저. 한 문단에 한 가지(문단은 400자 안쪽).
- 숫자에는 단위와 통화를 붙인다(1,000,000원, 3%).
- 사실·숫자·인용을 지어내지 않는다. 군말을 쓰지 않는다("~것으로 보입니다", "일반적으로 말하면").
- 사용자의 언어로 쓴다(lang="ko" 또는 "en"). 메모 제목·소제목은 lang을 따른다."""


EXAMPLE_NOTE = {"en": "Illustrative shape only — do not reuse its content. The example uses a made-up act, made-up rates and made-up amounts to show the form (3-item summary, rule → application → conclusion, calculation rows, risk priorities, footnote style).",
                "ko": "모양만 보여 주는 예시 — 내용을 가져다 쓰지 말 것. 지어낸 법 이름·세율·금액으로 형식(요약 3개, 근거 규정 → 적용 → 결론, 계산 행, 우선순위, 각주 쓰는 법)만 보인다."}


def example(lang="en"):
    return json.loads((DATA / f"tax_memo_example_{lang}.json").read_text("utf-8"))


def optional_blocks(lang="en"):
    """선택 블록의 쓰임과 모양(example과 같은 지어낸 사례). 넣지 않으면 메모는 기본 모양 그대로 나온다."""
    return json.loads((DATA / f"tax_memo_optional_{lang}.json").read_text("utf-8"))


def guide(lang="en"):
    if lang not in LANGS: raise ValueError(f"lang must be 'en' or 'ko' / lang은 'en' 또는 'ko': {lang}")
    return {"lang": lang, "guide": GUIDE[lang], "stages": [{"stage": k, "tests": STAGE_LABEL[lang][k]} for k in STAGES],
            "priorities": list(PRIORITIES[lang]), "schema": SCHEMA, "example_note": EXAMPLE_NOTE[lang], "example": example(lang), "optional_blocks": optional_blocks(lang), "checks": RULES,
            "next": "build_tax_memo(structure=<filled JSON>, lang='%s') — it writes the finished .docx and returns its path; fix every warning, then build again. Do not write the docx yourself." % lang}


# ── 정리 ──
MARK = re.compile(r"\[\^([^\]\s]+)\]")
_HANGUL = re.compile(r"[가-힣]")
_TOP_KEYS = {"lang", "head", "summary", "background", "question", "short_answer", "facts", "analysis", "decision_table",
             "calculation", "risks", "next_steps", "footnotes", "notice", "prepared_how", "title",
             "key_figures", "review", "action_list", "limitations", "authorities", "target_pages"}
HEAD_KEYS = ("to", "prepared_by", "date", "re", "scope", "basis", "workings")


def _s(v):
    if v is None: return ""
    if isinstance(v, (dict, list)): return ""
    return str(v).strip()


def _split_bold(v):
    """'**결론** 근거' 한 문자열을 (결론, 근거)로 나눈다."""
    m = re.match(r"\s*\*\*(.+?)\*\*\s*(.*)$", v, re.S)
    return (m.group(1).strip(), m.group(2).strip()) if m else (v.strip(), "")


def _unbold(v):
    return v.replace("**", "").strip()


def plain(v):
    """각주 표시와 굵게 표시를 뗀 글."""
    return MARK.sub("", v or "").replace("**", "").strip()


def resolve_lang(structure, lang=""):
    v = (lang or _s((structure or {}).get("lang"))).lower()
    v = {"english": "en", "korean": "ko", "kr": "ko", "한국어": "ko", "영어": "en", "국문": "ko", "영문": "en"}.get(v, v)
    if v in LANGS: return v
    if v: raise ValueError(f"lang must be 'en' or 'ko' / lang은 'en' 또는 'ko': {lang or structure.get('lang')}")
    head = (structure or {}).get("head") if isinstance((structure or {}).get("head"), dict) else {}
    probe = _s(head.get("re")) + _s((structure or {}).get("question"))
    return "ko" if _HANGUL.search(probe) else "en"


def _rows(v):
    out = []
    for r in v if isinstance(v, list) else []:
        if isinstance(r, dict):
            out.append({"item": _s(r.get("item")), "basis": _s(r.get("basis")), "amount": _s(r.get("amount")), "role": _s(r.get("role")).lower()})
        elif isinstance(r, list):
            c = [_s(x) for x in r] + ["", "", ""]
            out.append({"item": c[0], "basis": c[1], "amount": c[2], "role": ""})
    return out


def _table(v):
    """선택 표 블록(key_figures, analysis[].table) → {title, columns, rows: [{cells, role}], note, recommended} 또는 None."""
    if not isinstance(v, dict) or not (v.get("columns") or v.get("rows")): return None
    rows = []
    for r in v.get("rows") if isinstance(v.get("rows"), list) else []:
        if isinstance(r, dict):
            cells = r.get("cells") if isinstance(r.get("cells"), list) else ([r.get("item")] + list(r.get("values") or []) if isinstance(r.get("values"), list) else [])
            rows.append({"cells": [_s(c) for c in cells], "role": _s(r.get("role")).lower()})
        elif isinstance(r, list):
            rows.append({"cells": [_s(c) for c in r], "role": ""})
    return {"title": _s(v.get("title")), "columns": [_s(c) for c in v.get("columns")] if isinstance(v.get("columns"), list) else [],
            "rows": rows, "note": _s(v.get("note")), "recommended": _s(v.get("recommended"))}


def normalize(structure, lang):
    """입력을 한 가지 형태로 정리한다(문자열·객체 둘 다 받는 칸을 객체로). 원본은 바꾸지 않는다."""
    src = json.loads(json.dumps(structure or {}))
    s = {"lang": lang}
    head = src.get("head") if isinstance(src.get("head"), dict) else {}
    s["head"] = {k: _s(head.get(k)) for k in HEAD_KEYS}
    if not s["head"]["re"] and _s(src.get("title")): s["head"]["re"] = _s(src.get("title"))
    s["summary"] = []
    for it in src.get("summary") if isinstance(src.get("summary"), list) else []:
        if isinstance(it, dict):
            s["summary"].append({"conclusion": _unbold(_s(it.get("conclusion"))), "basis": _s(it.get("basis"))})
        else:
            c, b = _split_bold(_s(it)); s["summary"].append({"conclusion": c, "basis": b})
    s["background"] = _s(src.get("background"))
    s["question"] = _s(src.get("question"))
    sa = src.get("short_answer")
    if isinstance(sa, dict):
        s["short_answer"] = {"answer": _unbold(_s(sa.get("answer"))), "conditions": _s(sa.get("conditions"))}
    else:
        a, c = _split_bold(_s(sa)); s["short_answer"] = {"answer": a, "conditions": c}
    s["facts"] = []
    for it in src.get("facts") if isinstance(src.get("facts"), list) else []:
        if isinstance(it, dict):
            s["facts"].append({"text": _s(it.get("text")), "assumption": bool(it.get("assumption") or it.get("changes_answer")),
                               "changes_answer": bool(it.get("changes_answer")), "risk": _s(it.get("risk"))})
        elif _s(it):
            s["facts"].append({"text": _s(it), "assumption": False, "changes_answer": False, "risk": ""})
    s["analysis"] = []
    for it in src.get("analysis") if isinstance(src.get("analysis"), list) else []:
        it = it if isinstance(it, dict) else {"heading": _s(it)}
        s["analysis"].append({"heading": _s(it.get("heading")), "rule": _s(it.get("rule")) or _s(it.get("basis")),
                              "application": _s(it.get("application")), "conclusion": _s(it.get("conclusion")),
                              "confirm": _s(it.get("confirm")), "stage": _s(it.get("stage")).lower(), "table": _table(it.get("table"))})
    dt = src.get("decision_table")
    s["decision_table"] = None
    if isinstance(dt, dict) and (dt.get("columns") or dt.get("rows")):
        s["decision_table"] = {"title": _s(dt.get("title")), "columns": [_s(c) for c in dt.get("columns") or []],
                               "rows": [[_s(c) for c in r] for r in dt.get("rows") or [] if isinstance(r, list)]}
    calc = src.get("calculation")
    s["calculation"] = None
    if isinstance(calc, dict) and (calc.get("rows") or calc.get("scenarios")):
        s["calculation"] = {"currency": _s(calc.get("currency")), "rows": _rows(calc.get("rows")),
                            "note": _s(calc.get("note")),
                            "scenarios": [{"title": _s(sc.get("title")), "rows": _rows(sc.get("rows"))}
                                          for sc in calc.get("scenarios") or [] if isinstance(sc, dict)]}
    s["risks"] = []
    for k, it in enumerate(src.get("risks") if isinstance(src.get("risks"), list) else []):
        it = it if isinstance(it, dict) else {"point": _s(it)}
        s["risks"].append({"id": _s(it.get("id")) or f"r{k + 1}", "priority": _s(it.get("priority")), "point": _s(it.get("point")),
                           "why": _s(it.get("why")), "check": _s(it.get("check"))})
    s["next_steps"] = []
    for it in src.get("next_steps") if isinstance(src.get("next_steps"), list) else []:
        if isinstance(it, dict):
            s["next_steps"].append({"action": _s(it.get("action")), "owner": _s(it.get("owner")), "deadline": _s(it.get("deadline"))})
        elif _s(it):
            s["next_steps"].append({"action": _s(it), "owner": "", "deadline": ""})
    fn = src.get("footnotes")
    s["footnotes"] = []
    if isinstance(fn, dict):
        s["footnotes"] = [{"id": _s(k), "text": _s(v)} for k, v in fn.items()]
    elif isinstance(fn, list):
        for k, it in enumerate(fn):
            if isinstance(it, dict): s["footnotes"].append({"id": _s(it.get("id")) or f"n{k + 1}", "text": _s(it.get("text"))})
    s["notice"] = _s(src.get("notice"))
    s["prepared_how"] = _s(src.get("prepared_how"))
    # 선택 블록 — 없으면 None·빈 목록이고 출력은 그대로
    s["key_figures"] = _table(src.get("key_figures"))
    rv = src.get("review")
    s["review"] = None
    if isinstance(rv, dict) and (rv.get("verdict") or rv.get("findings")):
        s["review"] = {"verdict": _unbold(_s(rv.get("verdict"))), "findings": [
            {"finding": _unbold(_s(it.get("finding"))), "detail": _s(it.get("detail")), "amount": _s(it.get("amount")),
             "severity": _s(it.get("severity")) or _s(it.get("priority")), "action": _s(it.get("action"))}
            for it in (rv.get("findings") if isinstance(rv.get("findings"), list) else []) if isinstance(it, dict)]}
    s["action_list"] = []
    for it in src.get("action_list") if isinstance(src.get("action_list"), list) else []:
        if isinstance(it, dict):
            s["action_list"].append({"action": _s(it.get("action")), "owner": _s(it.get("owner")), "deadline": _s(it.get("deadline")) or _s(it.get("by"))})
        elif _s(it):
            s["action_list"].append({"action": _s(it), "owner": "", "deadline": ""})
    lim = src.get("limitations")
    s["limitations"] = None
    if isinstance(lim, dict): lim = {"text": _s(lim.get("text")), "items": [_s(x) for x in (lim.get("items") if isinstance(lim.get("items"), list) else []) if _s(x)]}
    elif isinstance(lim, list): lim = {"text": "", "items": [_s(x) for x in lim if _s(x)]}
    elif _s(lim): lim = {"text": _s(lim), "items": []}
    else: lim = None
    if lim and (lim["text"] or lim["items"]): s["limitations"] = lim
    s["authorities"] = [_s(x) for x in (src.get("authorities") if isinstance(src.get("authorities"), list) else []) if _s(x)]
    return s, sorted(set(src) - _TOP_KEYS)


# ── 점검 ──
_ABBR = re.compile(r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.|\b(?:Arts?|Nos?|paras?|Sec|cl|vs?|e\.g|i\.e|U\.S|Inc|Ltd|Co|cf|approx)\.|\d\.\d|(?<=\d)\.(?=\s?\d)|(?<=\d)\.(?=\()")
_HEDGE = {"en": ("it should be noted that", "it is important to note", "it is worth noting", "needless to say", "as you know",
                 "generally speaking", "it goes without saying", "arguably", "it would seem", "at the end of the day", "in my opinion",
                 "may potentially"),
          "ko": ("것으로 보입니다", "것으로 사료", "라고 할 수 있을 것", "일 수도 있을 것", "아마도", "주지하다시피", "말할 필요도 없이",
                 "일반적으로 말하면", "참고로 말씀드리면")}
_NARRATION = {"en": re.compile(r"^(I |We |First,|To answer|In order to|This memo|Having reviewed|After reviewing|Based on (my|our) (review|research)|Let me)", re.I),
              "ko": re.compile(r"^(먼저|우선|검토한 결과|살펴본 결과|조사한 결과|본 메모는|이 메모는|도구를 호출)")}
_AMOUNT = re.compile(r"(?<![\w,.])(?:\d{1,3}(?:,\d{3})+|\d{5,})(?![\d,]*\d)")
_CITE = re.compile(r"Art(?:icle|s)?\.?\s*\d|§\s*\d|제\s*\d+\s*조|\d{4}\s*[가-힣]{1,3}\s*\d{2,}|\d{4}-[가-힣]+-\d+|[가-힣]+-\d{4}-\d+|No\.\s*\d|\d{1,3}-\d{1,3}\s?…\s?\d+|[가-힣]{2,}\s?\d{4,6}-\d+")
_KOREAN_LAW_EN = re.compile(r"\b(?:Act|Decree|Enforcement Rule)\b")
# 질문이 이미 한 처리의 적정성을 묻는가(T09)
_PAST = {"en": re.compile(r"\b(?:so far|to date|until now|up to now|have we|did we|has it been|have they been|been (?:handled|treated|withheld|filed|reported|paid) (?:correctly|properly)|"
                          r"(?:handled|treated|withheld|filed|reported) (?:it |them |this )?(?:correctly|properly)|was (?:it|that|this) (?:right|correct)|were we (?:right|correct)|"
                          r"(?:past|prior|previous|earlier|historical) (?:handling|treatment|payments?|filings?|returns?|periods?|practice|withholding))\b", re.I),
         "ko": re.compile(r"지금까지|그동안|이제까지|여태|기존 (?:처리|신고|원천징수)|과거 (?:처리|신고|지급|원천징수)|종전 (?:처리|신고)|처리(?:가|는|를)? ?(?:맞|적정|올바|제대로)|적정했|적정하였|맞았|맞게 (?:처리|신고|원천징수|납부)|제대로 (?:처리|신고|원천징수|납부)")}
# 확인하지 못했다고 적은 표시(T13)
_UNVERIFIED = re.compile(r"\b(?:not (?:been )?verified|(?:was|were|is|are|been) not confirmed|not been confirmed|unverified|unconfirmed|could not (?:be )?(?:verif|confirm)\w*|unable to (?:verify|confirm))\b|미확인|확인하지 못|확인되지 않|확인 못|검증하지 못", re.I)
_NUMERIC = re.compile(r"^[\s\d,.\-−△()%+×÷*/—–]*\d[\s\d,.\-−△()%+×÷*/—–]*(?:\((?:est\.?|추정)\))?$")


def sentences(text):
    t = _ABBR.sub("x", plain(text))
    n = len(re.findall(r"[.?!]+[\"”’)\]]*(?=\s|$)", t))
    return max(n, 1) if t else 0


def number(v):
    """표의 금액 글자를 숫자로. 못 읽으면 None."""
    t = _s(v).replace(",", "").replace("−", "-").replace("△", "-").replace(" ", "")
    neg = t.startswith("(") and t.endswith(")")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m: return None
    x = float(m.group(0))
    return -abs(x) if neg else x


def _amounts(text):
    return {a.replace(",", "") for a in _AMOUNT.findall(plain(text))}


def _too_long(text, lang):
    t = plain(text)
    return (len(t) > 400) if lang == "ko" else (len(t.split()) > 120)


def _texts(s):
    """(위치, 글) — 문단으로 찍히는 모든 칸."""
    for k, it in enumerate(s["summary"]):
        yield f"summary[{k}].conclusion", it["conclusion"]; yield f"summary[{k}].basis", it["basis"]
    yield "background", s["background"]; yield "question", s["question"]
    yield "short_answer.answer", s["short_answer"]["answer"]; yield "short_answer.conditions", s["short_answer"]["conditions"]
    if s["key_figures"]:
        for where, text in _table_texts("key_figures", s["key_figures"]): yield where, text
    if s["review"]:
        yield "review.verdict", s["review"]["verdict"]
        for k, it in enumerate(s["review"]["findings"]):
            for f in ("finding", "detail", "amount", "action"): yield f"review.findings[{k}].{f}", it[f]
    for k, it in enumerate(s["facts"]): yield f"facts[{k}]", it["text"]
    for k, it in enumerate(s["analysis"]):
        for f in ("heading", "rule", "application", "conclusion", "confirm"): yield f"analysis[{k}].{f}", it[f]
        if it["table"]:
            for where, text in _table_texts(f"analysis[{k}].table", it["table"]): yield where, text
    if s["decision_table"]:
        for r, row in enumerate(s["decision_table"]["rows"]):
            for c, cell in enumerate(row): yield f"decision_table.rows[{r}][{c}]", cell
    if s["calculation"]:
        for name, rows in _tables(s["calculation"]):
            for r, row in enumerate(rows):
                yield f"{name}[{r}].item", row["item"]; yield f"{name}[{r}].basis", row["basis"]
        yield "calculation.note", s["calculation"]["note"]
    for k, it in enumerate(s["risks"]):
        yield f"risks[{k}].point", it["point"]; yield f"risks[{k}].why", it["why"]; yield f"risks[{k}].check", it["check"]
    for k, it in enumerate(s["next_steps"]): yield f"next_steps[{k}]", it["action"]
    for k, it in enumerate(s["action_list"]): yield f"action_list[{k}]", it["action"]
    if s["limitations"]:
        yield "limitations.text", s["limitations"]["text"]
        for k, x in enumerate(s["limitations"]["items"]): yield f"limitations.items[{k}]", x
    yield "prepared_how", s["prepared_how"]


def _table_texts(name, tb):
    for r, row in enumerate(tb["rows"]):
        for c, cell in enumerate(row["cells"]): yield f"{name}.rows[{r}][{c}]", cell
    yield f"{name}.note", tb["note"]


def _tables(calc):
    yield "calculation.rows", calc["rows"]
    for k, sc in enumerate(calc["scenarios"]): yield f"calculation.scenarios[{k}].rows", sc["rows"]


def _fmt(x):
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,}"


_SHAPES = (("head", dict), ("summary", list), ("short_answer", (dict, str)), ("facts", list), ("analysis", list), ("decision_table", dict),
           ("calculation", dict), ("risks", list), ("next_steps", list), ("footnotes", (list, dict)),
           ("key_figures", dict), ("review", dict), ("action_list", list), ("limitations", (dict, list, str)), ("authorities", list))


TARGET_PAGES = 5          # 기본 권고 분량(A4 쪽)
PAGE_SLACK = 0.25         # 어림값이라 이만큼 넘는 것까지는 넘지 않은 것으로 본다
ISSUE_BUDGET = {"en": 90, "ko": 280}          # 쟁점 하나(근거·적용·결론·확인)의 낱말 수(영문)·글자 수(국문)
BLOCK_TIP = {
    "en": {"analysis": "keep each issue to rule 1-2 sentences, application 2-3, conclusion 1; drop amounts a table already shows",
           "calculation": "do not repeat a table that an issue or key_figures already shows; keep only the rows needed to rebuild the total",
           "risks": "why in 1-2 sentences + one check sentence; drop what the review findings already cover",
           "facts": "only the facts the answer rests on, up to 3 sentences a bullet",
           "review": "finding = short name; detail one sentence; amount and action in a few words",
           "footnotes": "cite the article only; no explanation inside the footnote", "authorities": "leave it out — the footnotes carry the sources",
           "limitations": "a few words per item", "next_steps": "one line per action", "summary": "basis in 1-2 sentences",
           "short_answer": "conditions in up to 3 sentences", "head": "shorten scope and basis", "key_figures": "only the rows that carry the answer",
           "question": "1-2 sentences", "prepared_how": "tools, date, governing text — two sentences"},
    "ko": {"analysis": "쟁점마다 근거 규정 1~2문장·적용 2~3문장·결론 1문장으로, 표에 있는 금액은 글에서 뺌",
           "calculation": "쟁점 안의 표나 key_figures에 있는 표를 되풀이하지 않고, 합계를 다시 낼 수 있는 행만 둠",
           "risks": "why 1~2문장 + check 한 문장, 검토 결과의 발견 사항과 겹치는 항목은 뺌",
           "facts": "답의 바탕이 되는 사실만, 항목 하나는 3문장까지",
           "review": "finding은 짧은 이름, detail 한 문장, 금액·조치는 몇 낱말",
           "footnotes": "각주에는 조문만 적고 설명을 넣지 않음", "authorities": "뺌 — 출처는 각주에 있음",
           "limitations": "항목마다 몇 낱말", "next_steps": "할 일은 한 줄", "summary": "basis 1~2문장",
           "short_answer": "conditions 3문장까지", "head": "scope·basis를 줄임", "key_figures": "답을 담은 행만",
           "question": "1~2문장", "prepared_how": "쓴 도구·날짜·기준 원문 두 문장"},
}


def _size(text, lang):
    t = plain(text)
    return len(t) if lang == "ko" else len(t.split())


def _table_amounts(tb):
    out = set()
    for row in (tb or {}).get("rows", []):
        for cell in row["cells"][1:]: out |= _amounts(cell)
    return out


def length(s, target_pages=0):
    """분량 어림 — {estimated_pages, target_pages, blocks}. 그리는 코드(memo_docx)가 문단·표 높이를 어림해 블록별로 쌓은 값."""
    from . import memo_docx
    est = memo_docx.Doc(s).build().length()
    return {"estimated_pages": est["pages"], "target_pages": target_pages or TARGET_PAGES, "blocks": est["blocks"]}


def _target_pages(structure, target_pages=0):
    for v in (target_pages, structure.get("target_pages") if isinstance(structure, dict) else 0):
        try:
            if v and float(v) >= 1: return int(float(v))
        except (TypeError, ValueError):
            pass
    return TARGET_PAGES


def check(structure, lang="", target_pages=0):
    """(lang, 정리된 구조, 오류, 고칠 점). 오류는 구조가 깨져 파일을 만들 수 없는 것, 고칠 점은 파일은 만들되 고쳐서 다시 만들 것.
    문구는 lang에 맞추고 앞에 규칙 번호를 단다([E..] 오류, [M..] 메모 형식, [T..] 세무 논리)."""
    if not isinstance(structure, dict):
        raise ValueError("structure must be a JSON object / structure는 JSON 객체여야 함 — tax_memo_guide의 schema·example 참고")
    lang = resolve_lang(structure, lang)
    s, unknown = normalize(structure, lang)
    w = []; e = []; ko = lang == "ko"

    def E(code, en, kr): e.append(f"[{code}] " + (kr if ko else en))

    for key, typ in _SHAPES:
        v = structure.get(key)
        if v is not None and not isinstance(v, typ):
            E("E01", f"{key}: wrong JSON type ({type(v).__name__}) — see schema", f"{key}: JSON 형태가 다름({type(v).__name__}) — schema 참고")
    for key in ("summary", "analysis", "risks", "footnotes"):
        v = structure.get(key)
        if isinstance(v, list) and any(not isinstance(x, (dict, str) if key == "summary" else dict) for x in v):
            E("E01", f"{key}: every item must be an object — see schema", f"{key}: 항목은 모두 객체여야 함 — schema 참고")
    if not s["summary"] and not s["analysis"]:
        E("E02", "nothing to write: summary and analysis are both empty — fill the structure from tax_memo_guide", "쓸 내용이 없음: summary와 analysis가 모두 비어 있음 — tax_memo_guide의 구조를 채움")

    def W(code, en, kr): w.append(f"[{code}] " + (kr if ko else en))

    # M01 머리
    miss = [k for k in ("prepared_by", "date", "re", "scope") if not s["head"][k]]
    if miss: W("M01", f"head: missing {', '.join(miss)} — the head needs prepared_by, date, re and scope", f"head: {', '.join(miss)} 비어 있음 — 머리에는 prepared_by·date·re·scope가 모두 필요")
    # M02~M05 핵심 요약
    if len(s["summary"]) != 3:
        W("M02", f"summary: exactly 3 items required (found {len(s['summary'])})", f"summary: 항목은 정확히 3개(지금 {len(s['summary'])}개)")
    for k, it in enumerate(s["summary"]):
        if not it["conclusion"]: W("M03", f"summary[{k}]: no conclusion sentence", f"summary[{k}]: conclusion(결론 문장)이 없음")
        elif sentences(it["conclusion"]) > 1: W("M03", f"summary[{k}].conclusion: one sentence only — move the rest to basis", f"summary[{k}].conclusion: 한 문장만 — 나머지는 basis로")
        if not plain(it["basis"]): W("M04", f"summary[{k}]: no basis — add one or two sentences saying why", f"summary[{k}]: basis(근거)가 없음 — 이유를 한두 문장으로")
        elif sentences(it["basis"]) > 3: W("M04", f"summary[{k}].basis: keep to one or two sentences", f"summary[{k}].basis: 한두 문장으로 줄임")
        if _NARRATION[lang].search(it["conclusion"]): W("M05", f"summary[{k}]: starts with how you worked — start with the answer", f"summary[{k}]: 작업 과정으로 시작함 — 답부터 쓴다")
    # M06 쟁점
    if not s["question"]: W("M06", "question: empty — state the question in one or two sentences", "question: 비어 있음 — 쟁점을 한두 문장으로")
    elif sentences(s["question"]) > 2: W("M06", "question: one or two sentences — move background to 'background' or facts", "question: 한두 문장으로 — 배경은 background나 facts로")
    # M07 결론
    if not s["short_answer"]["answer"]: W("M07", "short_answer.answer: empty — start with the answer", "short_answer.answer: 비어 있음 — 답으로 시작")
    elif _NARRATION[lang].search(s["short_answer"]["answer"]): W("M07", "short_answer.answer: starts with how you worked — start with the answer", "short_answer.answer: 작업 과정으로 시작함 — 답부터 쓴다")
    if not plain(s["short_answer"]["conditions"]): W("M07", "short_answer.conditions: empty — state the conditions the answer depends on", "short_answer.conditions: 비어 있음 — 답이 성립하는 조건을 적음")
    # M08·M09 사실관계와 전제
    if not s["facts"]: W("M08", "facts: empty — list the facts and assumptions the answer rests on", "facts: 비어 있음 — 답의 바탕이 되는 사실과 전제를 적음")
    risk_ids = [r["id"] for r in s["risks"]]
    for k, it in enumerate(s["facts"]):
        if it["changes_answer"] and it["risk"] not in risk_ids:
            W("M09", f"facts[{k}]: changes_answer is set but risk '{it['risk']}' is not a risk id ({', '.join(risk_ids) or 'no risks'}) — link it to a risk item",
              f"facts[{k}]: changes_answer인데 risk '{it['risk']}'가 위험 항목 id가 아님({', '.join(risk_ids) or '위험 항목 없음'}) — 위험 항목과 잇는다")
    # M10~M12 검토
    if not s["analysis"]: W("M10", "analysis: empty — issues with rule, application and conclusion", "analysis: 비어 있음 — 근거·적용·결론을 갖춘 쟁점이 1개 이상 필요")
    for k, it in enumerate(s["analysis"]):
        miss = [f for f in ("rule", "application", "conclusion") if not plain(it[f])]
        if miss: W("M11", f"analysis[{k}]: missing {', '.join(miss)} — every issue needs rule → application → conclusion", f"analysis[{k}]: {', '.join(miss)} 없음 — 쟁점마다 근거 → 적용 → 결론")
        h = plain(it["heading"])
        if not h: W("M12", f"analysis[{k}]: no heading", f"analysis[{k}]: heading(소제목)이 없음")
        elif (len(h) < 6) if ko else (len(h.split()) < 3): W("M12", f"analysis[{k}].heading '{h}': state the conclusion, not just the topic", f"analysis[{k}].heading '{h}': 주제만 쓰지 말고 결론을 말하는 소제목으로")
    # M13 사실관계별 결과 표
    dt = s["decision_table"]
    if dt:
        n = len(dt["columns"])
        if n < 2 or not dt["rows"]: W("M13", "decision_table: needs at least 2 columns and 1 row", "decision_table: 열 2개 이상, 행 1개 이상 필요")
        elif any(len(r) != n for r in dt["rows"]): W("M13", f"decision_table: every row needs {n} cells", f"decision_table: 모든 행의 칸 수가 {n}개여야 함")
    # M14·M15 수치 표
    calc = s["calculation"]
    if calc:
        for name, rows in _tables(calc):
            if not rows: W("M14", f"{name}: empty", f"{name}: 비어 있음"); continue
            for r, row in enumerate(rows):
                if row["role"] not in ROLES: W("M14", f"{name}[{r}].role '{row['role']}': use component, total, base or info", f"{name}[{r}].role '{row['role']}': component·total·base·info 중 하나")
                if not row["item"]: W("M14", f"{name}[{r}]: no item", f"{name}[{r}]: item(항목)이 없음")
            acc = []; marked = False
            for r, row in enumerate(rows):
                if row["role"] == "component":
                    marked = True; x = number(row["amount"])
                    if x is None: W("M15", f"{name}[{r}]: component amount '{row['amount']}' is not a number", f"{name}[{r}]: component 금액 '{row['amount']}'이 숫자가 아님")
                    else: acc.append(x)
                elif row["role"] == "total":
                    x = number(row["amount"])
                    if x is None: W("M15", f"{name}[{r}]: total amount '{row['amount']}' is not a number", f"{name}[{r}]: 합계 금액 '{row['amount']}'이 숫자가 아님")
                    elif acc and abs(sum(acc) - x) > 0.5:
                        W("M15", f"{name}[{r}]: total {_fmt(x)} does not equal the sum of its component rows {_fmt(sum(acc))}", f"{name}[{r}]: 합계 {_fmt(x)}가 component 행의 합 {_fmt(sum(acc))}과 다름")
                    acc = []
            has_total = any(row["role"] == "total" for row in rows)
            if not has_total: W("T05", f"{name}: no total row — mark the sum with role='total' and its parts with role='component'", f"{name}: 합계 행이 없음 — 합계는 role='total', 더하는 행은 role='component'")
            elif has_total and not marked: W("T05", f"{name}: no rows marked role='component' — mark the rows that add up so the total can be reconciled", f"{name}: role='component' 행이 없음 — 합계를 대조하도록 더하는 행을 표시")
        if not calc["currency"]: W("M14", "calculation.currency: empty — name the currency or unit (e.g. KRW)", "calculation.currency: 비어 있음 — 통화·단위를 적음(예: 원)")
    # M16 위험과 확인할 점
    if not s["risks"]: W("M16", "risks: empty — list at least one risk or open point", "risks: 비어 있음 — 위험이나 확인할 점을 1개 이상")
    if len(set(risk_ids)) < len(risk_ids): W("M16", "risks: duplicate id", "risks: id가 겹침")
    for k, it in enumerate(s["risks"]):
        if it["priority"] not in PRIORITIES[lang]:
            W("M16", f"risks[{k}].priority '{it['priority']}': use {' / '.join(PRIORITIES[lang])}", f"risks[{k}].priority '{it['priority']}': {' / '.join(PRIORITIES[lang])} 중 하나")
        if not it["point"] or not (plain(it["why"]) or plain(it["check"])):
            W("M16", f"risks[{k}]: needs point plus why it matters or what to check", f"risks[{k}]: point(사항)와 why(왜 중요한지)·check(확인할 것)가 필요")
    # M17 다음 단계
    steps = s["action_list"] or s["next_steps"]
    if not steps or any(not it["action"] for it in steps):
        W("M17", "next_steps: at least one action; each item needs an action", "next_steps: 할 일이 1개 이상 필요하고 항목마다 action이 있어야 함")
    if s["action_list"] and s["next_steps"]:
        W("M17", "next_steps and action_list are both filled — keep one (action_list prints the table; next_steps is then not printed)", "next_steps와 action_list가 모두 있음 — 하나만 둔다(action_list가 표로 찍히고 next_steps는 찍히지 않음)")
    # M18~M20 각주
    ids = [f["id"] for f in s["footnotes"]]
    if len(set(ids)) < len(ids): W("M18", "footnotes: duplicate id", "footnotes: id가 겹침")
    for f in s["footnotes"]:
        if not f["text"]: W("M18", f"footnotes '{f['id']}': empty text", f"footnotes '{f['id']}': text가 비어 있음")
    used = []
    for where, text in _texts(s):
        for m in MARK.findall(text or ""):
            used.append(m)
            if m not in ids: E("E03", f"{where}: footnote [^{m}] is not defined under footnotes", f"{where}: 각주 [^{m}]가 footnotes에 없음")
    for i in ids:
        if i not in used: W("M20", f"footnotes '{i}': never referenced — put [^{i}] where the source is used or remove it", f"footnotes '{i}': 본문에서 쓰이지 않음 — 출처를 쓴 자리에 [^{i}]를 넣거나 지움")
    # M21 문단 길이, M22 군말
    for where, text in _texts(s):
        if _too_long(text, lang): W("M21", f"{where}: paragraph too long (over about 120 words) — one idea per paragraph", f"{where}: 문단이 김(400자 초과) — 한 문단에 한 가지")
        low = plain(text).lower()
        for h in _HEDGE[lang]:
            if h in low: W("M22", f"{where}: filler '{h}' — say it directly", f"{where}: 군말 '{h}' — 바로 말한다")
    # M23 모르는 키
    if unknown: W("M23", f"unknown keys ignored: {', '.join(unknown)} — see schema", f"알 수 없는 키(무시됨): {', '.join(unknown)} — schema 참고")

    # 세무 논리
    fn_text = {f["id"]: f["text"] for f in s["footnotes"]}
    if len(s["analysis"]) < 3: W("T01", f"analysis: a tax memo tests at least 3 issues (found {len(s['analysis'])})", f"analysis: 세무 메모는 쟁점을 3개 이상 따짐(지금 {len(s['analysis'])}개)")
    last = -1
    for k, it in enumerate(s["analysis"]):
        if it["stage"] not in STAGES:
            W("T02", f"analysis[{k}].stage '{it['stage']}': use one of {', '.join(STAGES)}", f"analysis[{k}].stage '{it['stage']}': {', '.join(STAGES)} 중 하나")
        else:
            i = STAGES.index(it["stage"])
            if i < last: W("T02", f"analysis[{k}]: stage '{it['stage']}' comes after '{STAGES[last]}' — keep the order {' → '.join(STAGES)}", f"analysis[{k}]: stage '{it['stage']}'가 '{STAGES[last]}' 뒤에 옴 — 순서는 {' → '.join(STAGES)}")
            last = max(last, i)
        marks = MARK.findall(it["rule"])
        cited = it["rule"] + " " + " ".join(fn_text.get(m, "") for m in marks)
        if not marks: W("T03", f"analysis[{k}].rule: no footnote — cite the statute, treaty or ruling as [^id]", f"analysis[{k}].rule: 각주 없음 — 법령·조약·판례를 [^id]로 인용")
        elif not _CITE.search(cited): W("T03", f"analysis[{k}].rule: the citation has no article or case number", f"analysis[{k}].rule: 인용에 조문 번호나 사건 번호가 없음")
    for k, it in enumerate(s["summary"]):
        if not MARK.search(it["conclusion"] + it["basis"]): W("T04", f"summary[{k}]: no footnote — each summary item needs at least one source", f"summary[{k}]: 각주 없음 — 요약 항목마다 출처가 1개 이상 필요")
    if not calc: W("T05", "calculation: required — rows of item, basis, amount with a total row", "calculation: 필수 — 항목·근거·금액 행과 합계 행")
    else:
        have = _table_amounts(s["key_figures"])          # 숫자 표(결론 아래 표, 쟁점 안의 표)에 있는 금액도 표에 있는 것으로 본다
        for it in s["analysis"]: have |= _table_amounts(it["table"])
        for _, rows in _tables(calc):
            for row in rows: have |= _amounts(row["amount"])
        for where, text in [(f"summary[{k}]", it["conclusion"] + " " + it["basis"]) for k, it in enumerate(s["summary"])] + \
                           [("short_answer", s["short_answer"]["answer"] + " " + s["short_answer"]["conditions"])]:
            for a in sorted(_amounts(text) - have, key=int):
                W("T06", f"{where}: amount {int(a):,} is not in the calculation table (or in key_figures or an issue table) — add a row or a scenario", f"{where}: 금액 {int(a):,}이 계산 표(또는 key_figures·쟁점 안의 표)에 없음 — 행이나 scenarios에 넣음")
    if not ko and any(_KOREAN_LAW_EN.search(t) for t in fn_text.values()) and not any(_HANGUL.search(t) for t in fn_text.values()):
        W("T07", "footnotes: give the original Korean name of each Korean statute once in parentheses, e.g. Corporate Tax Act (법인세법)", "footnotes: 한국 법령은 원어를 한 번 괄호로 적음")
    # ── 선택 블록 ──
    # M24 표 블록 모양(결론 아래 숫자 표, 쟁점 안의 표)
    kf = s["key_figures"]
    for name, tb in [("key_figures", kf)] + [(f"analysis[{k}].table", it["table"]) for k, it in enumerate(s["analysis"])]:
        if not tb: continue
        n = len(tb["columns"])
        if n < 2 or not tb["rows"]: W("M24", f"{name}: needs at least 2 columns and 1 row", f"{name}: 열 2개 이상, 행 1개 이상 필요")
        elif any(len(r["cells"]) != n for r in tb["rows"]): W("M24", f"{name}: every row needs {n} cells", f"{name}: 모든 행의 칸 수가 {n}개여야 함")
        if any(r["role"] not in ("total", "") for r in tb["rows"]): W("M24", f"{name}: row role is 'total' or empty", f"{name}: 행의 role은 'total'이거나 비움")
        if name == "key_figures" and n > 4:
            W("M24", f"key_figures: at most 3 scenario columns beside the row label (found {n - 1}) — move the rest to calculation.scenarios", f"key_figures: 항목 열 옆의 경우 열은 3개까지(지금 {n - 1}개) — 나머지는 calculation.scenarios로")
    # M25 검토 결과 절의 모양
    rv = s["review"]
    if rv:
        if not rv["verdict"]: W("M25", "review.verdict: empty — one bold sentence saying whether the handling to date was correct", "review.verdict: 비어 있음 — 지금까지의 처리가 맞았는지 한 문장 판정")
        elif sentences(rv["verdict"]) > 1: W("M25", "review.verdict: one sentence only — details go in findings", "review.verdict: 한 문장만 — 자세한 내용은 findings로")
        for k, it in enumerate(rv["findings"]):
            miss = [f for f in ("finding", "amount", "severity", "action") if not plain(it[f])]
            if miss: W("M25", f"review.findings[{k}]: missing {', '.join(miss)} — each finding needs what is wrong, the amount at stake ('—' if none), severity and the action",
                       f"review.findings[{k}]: {', '.join(miss)} 없음 — 발견 사항마다 무엇이 문제인지·걸린 금액(없으면 '—')·위험도·조치")
            if it["severity"] and it["severity"] not in PRIORITIES[lang]:
                W("M25", f"review.findings[{k}].severity '{it['severity']}': use {' / '.join(PRIORITIES[lang])}", f"review.findings[{k}].severity '{it['severity']}': {' / '.join(PRIORITIES[lang])} 중 하나")
    # T09 과거 처리의 적정성을 묻는 질문이면 검토 결과 절
    if not rv and _PAST[lang].search(plain(s["question"]) + " " + plain(s["background"]) + " " + plain(s["head"]["re"])):
        W("T09", "review: the question asks whether the handling to date was correct — add review {verdict, findings[{finding, amount, severity, action}]} (verdict alone if nothing is wrong)",
          "review: 질문이 지금까지의 처리가 맞았는지를 묻고 있음 — review {verdict, findings[{finding, amount, severity, action}]}를 넣음(문제가 없으면 verdict만)")
    # T10 결론 아래 숫자 표의 금액은 계산·본문에 있어야 함
    if kf:
        body = set()
        if calc:
            for _, rows in _tables(calc):
                for row in rows: body |= _amounts(row["amount"]) | _amounts(row["basis"])
        for it in s["analysis"]:
            for f in ("rule", "application", "conclusion", "confirm"): body |= _amounts(it[f])
            if it["table"]:
                for row in it["table"]["rows"]:
                    for cell in row["cells"]: body |= _amounts(cell)
        for it in s["facts"]: body |= _amounts(it["text"])
        for it in (rv["findings"] if rv else []): body |= _amounts(it["amount"]) | _amounts(it["detail"])
        seen = set()
        for row in kf["rows"]:
            for cell in row["cells"][1:]: seen |= _amounts(cell)
        for a in sorted(seen - body, key=int):
            W("T10", f"key_figures: amount {int(a):,} is not in the calculation or the analysis — show where it comes from", f"key_figures: 금액 {int(a):,}이 계산·검토에 없음 — 어디서 나온 숫자인지 계산이나 검토에 넣음")
    # T11 조치 목록 표는 항목마다 기한
    for k, it in enumerate(s["action_list"]):
        if not it["deadline"]: W("T11", f"action_list[{k}]: no deadline — every action in the table needs a date or a trigger (e.g. 'before payment')", f"action_list[{k}]: 기한 없음 — 표의 할 일마다 날짜나 시점(예: '지급 전')이 필요")
    # T12 경우가 둘 이상이면 권고하는 쪽과 조건
    if kf and len(kf["columns"]) > 2:
        if kf["recommended"] not in kf["columns"][1:]:
            W("T12", f"key_figures.recommended '{kf['recommended']}': with two or more scenarios name the one you recommend — one of {' | '.join(kf['columns'][1:])}",
              f"key_figures.recommended '{kf['recommended']}': 경우가 둘 이상이면 권고하는 쪽을 적음 — {' | '.join(kf['columns'][1:])} 중 하나")
        if not plain(kf["note"]): W("T12", "key_figures.note: empty — state the condition under which each scenario applies", "key_figures.note: 비어 있음 — 경우마다 성립하는 조건을 적음")
    # T13 미확인이라고 적은 것은 한계 절에도
    lim = s["limitations"]
    flagged = [where for where, text in _texts(s) if not where.startswith(("limitations", "prepared_how")) and _UNVERIFIED.search(plain(text))]
    flagged_notes = [f["id"] for f in s["footnotes"] if _UNVERIFIED.search(f["text"])]
    if (flagged or flagged_notes) and not lim:
        spots = ", ".join(flagged[:4] + [f"footnote '{i}'" for i in flagged_notes[:4]])
        W("T13", f"limitations: {len(flagged) + len(flagged_notes)} place(s) are marked not verified ({spots}) — collect them under limitations",
          f"limitations: 미확인으로 적은 곳이 {len(flagged) + len(flagged_notes)}군데({spots}) — limitations(한계와 미확인 사항)에 모아 적음")
    elif lim:
        cited = set(MARK.findall(lim["text"] + " " + " ".join(lim["items"])))
        for i in flagged_notes:
            if i not in cited: W("T13", f"limitations: footnote '{i}' is marked not verified but is not cited here — add the point with [^{i}]", f"limitations: 각주 '{i}'는 미확인으로 적었는데 여기에 없음 — 그 점을 [^{i}]와 함께 적음")
    # M27 같은 표를 두 번 찍지 않는다 — 쟁점 안의 표와 금액이 모두 같은 계산 표(scenarios)
    if calc:
        for k, sc in enumerate(calc["scenarios"]):
            mine = set()
            for row in sc["rows"]: mine |= _amounts(row["amount"])
            for j, it in enumerate(s["analysis"]):
                if len(mine) >= 2 and mine <= _table_amounts(it["table"]):
                    W("M27", f"calculation.scenarios[{k}]: every amount is already in analysis[{j}].table — print the table once (drop the scenario or the issue table)",
                      f"calculation.scenarios[{k}]: 금액이 모두 analysis[{j}].table에 이미 있음 — 표는 한 번만 찍는다(scenarios나 쟁점 안의 표 중 하나를 뺌)")
                    break
    # M26 분량 — 어림 쪽수가 목표를 넘으면 가장 긴 블록과 기준을 넘은 쟁점을 짚는다
    target = _target_pages(structure, target_pages)
    if not e:
        s["length"] = length(s, target)
        if s["length"]["estimated_pages"] > target + PAGE_SLACK:
            top = sorted(s["length"]["blocks"].items(), key=lambda x: -x[1])[:3]
            over = [(k, _size(" ".join(it[f] for f in ("rule", "application", "conclusion", "confirm")), lang)) for k, it in enumerate(s["analysis"])]
            over = sorted([x for x in over if x[1] > ISSUE_BUDGET[lang]], key=lambda x: -x[1])[:5]
            tips = BLOCK_TIP[lang]
            W("M26", f"length: about {s['length']['estimated_pages']} pages against target_pages {target} — longest blocks: "
                     + "; ".join(f"{b} {v} p. ({tips[b]})" for b, v in top)
                     + (". Issues over about %d words: " % ISSUE_BUDGET["en"] + ", ".join(f"analysis[{k}] {n}" for k, n in over) if over else "")
                     + ". Say each thing once (see [Length] in tax_memo_guide), or raise target_pages if the reader wants a longer memo",
              f"분량: 어림 {s['length']['estimated_pages']}쪽으로 목표(target_pages) {target}쪽을 넘음 — 가장 긴 블록: "
              + "; ".join(f"{b} {v}쪽({tips[b]})" for b, v in top)
              + (". %d자를 넘는 쟁점: " % ISSUE_BUDGET["ko"] + ", ".join(f"analysis[{k}] {n}자" for k, n in over) if over else "")
              + ". 같은 말은 한 번만 쓴다(tax_memo_guide의 [분량] 참고). 읽는 사람이 더 긴 메모를 원하면 target_pages를 올림")
    if not s["prepared_how"]: W("T08", "prepared_how: required — name the tools used and the date, and say the original-language text governs", "prepared_how: 필수 — 쓴 도구와 날짜, 원어 조문이 기준임을 적음")
    return lang, s, e, w


RULES = [
    "E01 sections have the right JSON type", "E02 summary or analysis present", "E03 every [^id] has a footnote",
    "M01 head: prepared_by, date, re, scope", "M02 executive summary has exactly 3 items", "M03 one-sentence conclusion per summary item",
    "M04 basis per summary item (1-2 sentences)", "M05 answer first, no process narration", "M06 question in 1-2 sentences",
    "M07 short answer = answer + conditions", "M08 facts present", "M09 answer-changing assumption links to a risk id",
    "M10 analysis present", "M11 rule → application → conclusion per issue", "M12 issue heading states the conclusion",
    "M13 decision table shape", "M14 calculation rows, roles, currency", "M15 total equals the sum of component rows",
    "M16 risks with valid priority, point and why/check", "M17 next steps with actions", "M18 footnote ids unique, text present",
    "M20 every footnote is referenced", "M21 paragraph length", "M22 no hedging filler", "M23 unknown keys",
    "T01 at least 3 issues", "T02 issues follow the stage order " + " → ".join(STAGES),
    "T03 each issue cites a statute, treaty or ruling with article or case number", "T04 footnote per summary item",
    "T05 calculation required, with total and component rows", "T06 amounts in the summary and short answer appear in the calculation (or in key_figures or an issue table)",
    "T07 original-language term for Korean law (lang=en)", "T08 prepared_how names tools and date",
    "M24 optional tables (key_figures, analysis[].table): columns, cell counts, at most 3 scenario columns",
    "M25 review: one-sentence verdict; each finding has what is wrong, amount, severity, action",
    "T09 a question about past handling needs the review section", "T10 every amount in key_figures is in the calculation or the analysis",
    "T11 every action_list item has a deadline", "T12 two or more scenarios: name the recommended one and the condition for each",
    "T13 whatever is marked not verified is collected under limitations (not-verified footnotes cited there)",
    "M26 length: the estimated pages stay within target_pages (default 5); the warning names the longest blocks and the issues over budget",
    "M27 a table is printed once: no calculation scenario that repeats an issue table",
]


# ── 만들기 ──
def _as_structure(structure):
    if isinstance(structure, str):
        try: structure = json.loads(structure)
        except json.JSONDecodeError as e:
            raise ValueError(f"structure must be a JSON object or its string / structure는 JSON 객체(또는 그 문자열)여야 함: {e}") from e
    if not isinstance(structure, dict):
        raise ValueError("structure must be a JSON object / structure는 JSON 객체여야 함 — tax_memo_guide의 schema·example 참고")
    return structure


def _target(s, output_dir, filename):
    import os
    d = Path(output_dir or ".").expanduser()
    if str(output_dir or ".") == "." and (Path.cwd() == Path(Path.cwd().anchor) or not os.access(Path.cwd(), os.W_OK)):
        d = Path.home() / "korean-tax-mcp"      # 앱이 서버를 루트(/)에서 띄우면 쓸 수 없으므로 홈 아래로
    name = Path(str(filename)).name if filename else ""
    if not name:
        stem = re.sub(r"[^가-힣A-Za-z0-9]+", "_", plain(s["head"]["re"])).strip("_")[:60] or "memo"
        name = ("세무메모_" if s["lang"] == "ko" else "Tax_Memo_") + stem
    if not name.lower().endswith(".docx"): name = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name) + ".docx"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def build(structure, output_dir=".", filename=None, lang="", check_only=False, target_pages=0):
    """구조를 점검하고 Word 파일을 쓴다. {path, ok, lang, errors, warnings, length?, footnotes?, next}.
    errors가 있으면 파일을 만들지 않는다. warnings만 있으면 파일을 만들고, 고쳐서 다시 만들라고 돌려준다."""
    lang, s, errors, warnings = check(_as_structure(structure), lang, target_pages)
    ko = lang == "ko"
    out = {"path": "", "ok": not errors and not warnings, "lang": lang, "errors": errors, "warnings": warnings}
    if s.get("length"): out["length"] = s["length"]
    if errors:
        out["next"] = "오류를 고쳐 다시 호출 — 파일을 만들지 않았음" if ko else "Fix the errors and call again — no file was written."
        return out
    if check_only:
        out["next"] = ("경고를 고친 뒤 check_only 없이 호출" if warnings else "check_only 없이 호출해 파일 생성") if ko else \
                      ("Fix the warnings, then call without check_only." if warnings else "Call without check_only to write the file.")
        return out
    from . import memo_docx
    dst = _target(s, output_dir, filename)
    out["footnotes"] = memo_docx.build(s, dst)
    out["path"] = str(dst)
    out["next"] = ("경고를 고쳐 다시 만든 뒤 사용자에게 전달" if warnings else "path의 완성된 .docx를 그대로 사용자에게 전달(직접 다시 만들지 않음) — 각주의 문서번호·조문은 verify_citations로 확인") if ko else \
                  ("Fix the warnings and build again before handing the file over." if warnings else "Hand the finished .docx at `path` to the user as is (do not rebuild it yourself) — check the footnote citations with verify_citations.")
    return out
