"""세무 메모 분량 — 촘촘한 기본 서식, 표가 쪽에서 잘리지 않게 하는 속성, 분량 어림과 목표 쪽수(target_pages), 같은 표 되풀이 점검. 작성 Mia(윤승미)

자료는 지어낸 사례(tests/fixtures/tax_memo_fixture_*.json)와 도구가 돌려주는 선택 블록 예시(지어낸 값). 외부 호출 없음.
쪽수 어림은 LibreOffice로 뽑은 PDF에 맞춰 본 값이라(긴 메모 5.7쪽 → 5.9, 짧은 예시 1.45쪽 → 1.4) 여기서는 범위만 본다.
"""
import asyncio
import copy
import json
import re
import zipfile
from pathlib import Path

import pytest

from korean_tax_mcp import memo_docx as D
from korean_tax_mcp import tax_memo as M
from korean_tax_mcp.server import mcp

EX = {lang: json.loads((Path(__file__).parent / "fixtures" / f"tax_memo_fixture_{lang}.json").read_text("utf-8")) for lang in ("en", "ko")}


def _mut(fn, lang="en"):
    s = copy.deepcopy(EX[lang]); fn(s); return s


def _codes(structure, **kw):
    _, _, errors, warnings = M.check(structure, **kw)
    return [x[1:4] for x in errors + warnings]


def _doc(structure, tmp_path, name="m"):
    r = M.build(structure, str(tmp_path), name)
    assert not r["errors"], r
    with zipfile.ZipFile(r["path"]) as z:
        return r, z.read("word/document.xml").decode("utf-8"), z.read("word/footnotes.xml").decode("utf-8")


def _long(lang="en", issues=40):
    """쟁점을 많이 넣어 목표 분량을 넘긴 구조(지어낸 글)."""
    s = copy.deepcopy(EX[lang]); last = copy.deepcopy(s["analysis"][-1])
    filler = ("The made-up office counts each day of delay separately and adds the daily amount to the fixed amount. " * 6) if lang == "en" else ("지어낸 관서는 늦은 날을 하루씩 세어 일수분을 정액분에 더한다. " * 9)
    for k in range(issues):
        it = copy.deepcopy(last); it["heading"] = f"{last['heading']} ({k + 1})"; it["application"] = filler.strip()
        s["analysis"].append(it)
    return s


# ── 촘촘한 기본 서식 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_compact_layout(tmp_path, lang):
    r, doc, notes = _doc(EX[lang], tmp_path)
    assert r["ok"]
    assert D.SIZE[lang]["body"] >= 20 and D.SIZE[lang]["cell"] >= 18          # 본문 10pt, 표 9pt 아래로 내리지 않는다
    assert f'w:top="{D.MARGIN_TB}"' in doc and f'w:left="{D.MARGIN_LR}"' in doc and D.W == 11906 - 2 * D.MARGIN_LR
    for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", doc):
        assert sum(int(x) for x in re.findall(r'<w:gridCol w:w="(\d+)"/>', tbl)) == D.W          # 모든 표가 본문 너비에 맞음
    # 근거 규정과 적용은 한 문단, 결론은 다음 문단
    L = M.LABELS[lang]
    paras = [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p>.*?</w:p>", doc)]
    both = [p for p in paras if p.startswith(L["rule"]) and L["application"] in p]
    assert len(both) == len(EX[lang]["analysis"]) and sum(p.startswith(L["conclusion"]) for p in paras) == len(EX[lang]["analysis"])


def test_head_is_one_table_and_pairs_the_date(tmp_path):
    short = "1 January 2000"
    _, doc, _ = _doc(_mut(lambda s: s["head"].update(date=short)), tmp_path)
    head = re.findall(r"<w:tbl>.*?</w:tbl>", doc)[0]
    rows = re.findall(r"<w:tr>.*?</w:tr>", head)
    first = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<w:tc>.*?</w:tc>", rows[0])]
    assert first == ["PREPARED BY", EX["en"]["head"]["prepared_by"], "DATE", short] and len(rows) == 3          # 한 줄에 들어가는 일자는 작성 줄 오른쪽에
    assert "<w:tblHeader/>" not in head and head.count('w:val="single"') == len(re.findall(r"<w:tc>", rows[-1]))          # 선은 마지막 줄 아래에만
    # 수신이 있으면 일자는 수신 줄에. 일자나 짝이 될 칸이 한 줄을 넘으면 일자는 제 줄에
    _, doc, _ = _doc(_mut(lambda s: s["head"].update(to="Made-up addressee", date=short)), tmp_path, "to")
    rows = re.findall(r"<w:tr>.*?</w:tr>", re.findall(r"<w:tbl>.*?</w:tbl>", doc)[0])
    assert [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<w:tc>.*?</w:tc>", rows[0])][::2] == ["TO", "DATE"] and len(rows) == 4
    for change in (dict(prepared_by="Made-up team " * 8, date=short), dict(date="1 January 2000 (a made-up date that runs long)")):
        _, doc, _ = _doc(_mut(lambda s: s["head"].update(change)), tmp_path, "wide")
        rows = re.findall(r"<w:tr>.*?</w:tr>", re.findall(r"<w:tbl>.*?</w:tbl>", doc)[0])
        assert len(rows) == 4 and all(len(re.findall(r"<w:tc>", r)) == 2 for r in rows) and '<w:gridSpan w:val="3"/>' in rows[0]


def test_tables_do_not_break_across_pages(tmp_path):
    o = M.optional_blocks("en")["example"]
    s = _mut(lambda s: (s.update(key_figures=o["key_figures"], action_list=o["action_list"]), s.pop("next_steps")))
    _, doc, _ = _doc(s, tmp_path)
    assert doc.count("<w:tr>") == doc.count("<w:cantSplit/>")          # 어느 행도 쪽 경계에서 갈라지지 않는다
    whole = 0
    for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", doc):          # 쪽의 20% 이하 표는 통째로(마지막 행을 뺀 모든 문단이 다음 문단과 함께), 더 큰 표(위험 표)는 머리 행 + 첫 행만
        rows = re.findall(r"<w:tr>.*?</w:tr>", tbl)
        keep = ["<w:keepNext/>" in r for r in rows]
        for r, k in zip(rows, keep): assert r.count("<w:keepNext/>") == (r.count("<w:p>") if k else 0)
        assert keep[-1] == ("A. No reduction" in tbl)          # 결론 아래 숫자 표만 마지막 행이 조건 주석과 붙는다
        assert all(keep[:-1]) or keep == [True] + [False] * (len(rows) - 1)
        whole += all(keep[:-1])
    assert whole >= 6
    # 결론 문단 → 숫자 표: 순서는 그대로지만 결론 문단을 표에 묶지 않는다(묶으면 제목 + 결론 + 표가 한 덩어리가 되어 앞 쪽 아래가 빈다)
    answer = [p for p in re.findall(r"<w:p>.*?</w:p>", doc) if EX["en"]["short_answer"]["answer"][:20] in p][-1]
    assert "<w:keepNext/>" not in answer and doc.index(answer) < doc.index("A. No reduction") < doc.index("3. Facts and assumptions")
    # 표 제목(쟁점 안의 표, 계산의 다른 경우)은 표의 첫 행과 떨어지지 않는다
    for title in [sc["title"] for sc in EX["en"]["calculation"]["scenarios"]]:
        assert "<w:keepNext/>" in [p for p in re.findall(r"<w:p>.*?</w:p>", doc) if title in p][0]
    # 쪽의 20%가 넘는 큰 표는 행 사이에서 넘어간다(머리 행 반복) — 머리 행 + 첫 행만 붙는다
    big = _mut(lambda s: s.update(risks=[dict(s["risks"][0], id=f"r{k}", why="Made-up reason that runs over more than one line in the table cell. " * 4) for k in range(20)]))
    big["facts"] = [f for f in big["facts"] if isinstance(f, str)]
    _, doc, _ = _doc(big, tmp_path, "big")
    risks = [t for t in re.findall(r"<w:tbl>.*?</w:tbl>", doc) if "Made-up reason" in t][0]
    rows = re.findall(r"<w:tr>.*?</w:tr>", risks)
    assert ["<w:keepNext/>" in r for r in rows] == [True] + [False] * 20 and "<w:tblHeader/>" in rows[0] and risks.count("<w:cantSplit/>") == 21


def test_repeated_source_reuses_its_note_number(tmp_path):
    r, doc, notes = _doc(EX["en"], tmp_path)
    marks = sum(len(M.MARK.findall(json.dumps(v))) for v in (EX["en"]["summary"], EX["en"]["analysis"], EX["en"]["risks"]))
    real = re.findall(r'<w:footnoteReference w:id="(\d+)"/>', doc)
    again = re.findall(r'<w:rStyle w:val="FootnoteReference"/></w:rPr><w:t>(\d+)</w:t>', doc)
    assert len(real) == r["footnotes"] == len(EX["en"]["footnotes"]) and len(real) + len(again) == marks and again
    assert notes.count("<w:footnoteRef/>") == len(real) and "See note" not in notes


# ── 분량 어림과 목표 쪽수 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_length_is_returned_and_short_memos_pass(tmp_path, lang):
    for s in (EX[lang], M.example(lang)):
        r = M.build(s, str(tmp_path), "len")
        ln = r["length"]
        assert r["ok"] and ln["target_pages"] == M.TARGET_PAGES == 5 and 1.0 <= ln["estimated_pages"] <= 3.0
        assert set(ln["blocks"]) <= set(D.BLOCKS) and abs(sum(ln["blocks"].values()) - ln["estimated_pages"]) < 0.2
        assert {"head", "summary", "analysis", "calculation", "risks", "footnotes"} <= set(ln["blocks"])
    assert M.build(EX[lang], check_only=True)["length"] == M.build(EX[lang], str(tmp_path), "again")["length"]          # 점검만 해도 같은 어림
    assert "length" not in M.build({"lang": lang, "head": {}, "summary": "x"}, check_only=True)          # 오류면 어림하지 않는다


def test_over_target_names_the_longest_blocks():
    s = _long()
    _, _, _, w = M.check(s)
    over = [x for x in w if x.startswith("[M26]")]
    assert len(over) == 1 and {x[1:4] for x in w} == {"M26"}
    msg = over[0]
    assert "target_pages 5" in msg and "longest blocks: analysis" in msg and "rule 1-2 sentences" in msg
    assert "Issues over about 90 words: analysis[" in msg and "raise target_pages" in msg
    est = M.check(s)[1]["length"]
    assert est["estimated_pages"] > 5.25 and max(est["blocks"], key=est["blocks"].get) == "analysis"
    # 목표를 올리면 걸리지 않는다 — 인자, 구조의 target_pages, 인자가 먼저
    high = int(est["estimated_pages"]) + 1
    assert _codes(s, target_pages=high) == [] and _codes(dict(s, target_pages=high)) == []
    assert "M26" in _codes(dict(s, target_pages=high), target_pages=2) and "M23" not in _codes(dict(s, target_pages=high))
    assert M.check(dict(s, target_pages="abc"))[1]["length"]["target_pages"] == 5          # 읽을 수 없는 값이면 권고값
    # 어림값이라 목표를 조금 넘는 것까지는 넘지 않은 것으로 본다
    assert M.PAGE_SLACK == 0.25 and "M26" in _codes(EX["en"], target_pages=1) and "M26" not in _codes(EX["en"], target_pages=3)


def test_over_target_korean_message():
    w = [x for x in M.check(_long("ko"))[3] if x.startswith("[M26]")]
    assert len(w) == 1 and "목표(target_pages) 5쪽" in w[0] and "가장 긴 블록: analysis" in w[0] and "280자를 넘는 쟁점: analysis[" in w[0]
    for lang in ("en", "ko"): assert set(M.BLOCK_TIP[lang]) == set(D.BLOCKS)          # 블록마다 줄이는 법이 있다


# ── 같은 표는 한 번만(M27), 표에 있는 금액(T06) ──
def test_same_table_twice():
    tb = M.optional_blocks("en")["example"]["analysis_table"]
    both = _mut(lambda s: next(a for a in s["analysis"] if a["stage"] == "procedure").update(table=tb))          # 계산 표의 '감면' 경우와 같은 숫자
    w = M.check(both)[3]
    assert [x[1:4] for x in w] == ["M27"] and "calculation.scenarios[1]" in w[0] and "analysis[3].table" in w[0]
    assert any("M27" in x and re.search(r"[가-힣]", x) for x in M.check(dict(both, lang="ko"), "ko")[3])
    once = copy.deepcopy(both); once["calculation"]["scenarios"].pop(1)          # 계산 표에서 빼면 통과 — 요약의 금액은 쟁점 안의 표에 있으면 된다(T06)
    assert _codes(once) == []
    other = _mut(lambda s: s["analysis"][0].update(table={"columns": ["Item", "Days"], "rows": [["Counted from the deadline", "30"], ["Counted from the notice", "29"]]}))
    assert _codes(other) == []          # 숫자가 다른 표는 걸리지 않는다
    gone = _mut(lambda s: s["calculation"].update(scenarios=[]))
    assert "T06" in _codes(gone)          # 표 어디에도 없는 금액은 여전히 걸린다
    assert _codes(_mut(lambda s: (s["calculation"].update(scenarios=[]), s["analysis"][2].update(table={"columns": ["Item", "Amount"], "rows": [["Charge if paid 60 days late", "360,000"], ["Charge with the reduction", "180,000"]]})))) == []


# ── 안내와 도구 설명 ──
def test_guide_teaches_length():
    en, ko = M.guide("en"), M.guide("ko")
    for word in ("[Length — say each thing once]", "target_pages (default 5 A4 pages", "about 90 words for the whole issue", "A table is printed once", "Leave authorities out"):
        assert word in en["guide"], word
    for word in ("[분량 — 같은 말은 한 번만]", "target_pages(기본 A4 5쪽", "쟁점 하나에 280자 안쪽", "표도 한 번만", "출처 목록을 원할 때만"):
        assert word in ko["guide"], word
    assert "target_pages" in en["schema"] and any(r.startswith("M26") for r in en["checks"]) and any(r.startswith("M27") for r in en["checks"])
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    prop = tools["build_tax_memo"].input_schema["properties"]["target_pages"]
    assert prop["default"] == 0 and "5" in prop["description"] and "target_pages" in tools["build_tax_memo"].description
    r = json.loads(asyncio.run(mcp.call_tool("build_tax_memo", {"structure": _long(), "check_only": True, "target_pages": 40})).content[0].text)
    assert r["ok"] and r["length"]["target_pages"] == 40
    r = json.loads(asyncio.run(mcp.call_tool("build_tax_memo", {"structure": _long(), "check_only": True})).content[0].text)
    assert not r["ok"] and r["warnings"][0].startswith("[M26]")
