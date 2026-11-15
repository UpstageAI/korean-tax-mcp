"""세무 메모 쪽 나눔 — 붙여 두는 묶음(다음 문단과 함께)의 크기와 경계. 작성 Mia(윤승미)

자료는 지어낸 사례(tests/fixtures/tax_memo_fixture_en.json)를 늘려 만든 것 — 머리 블록 6줄, 요약 3항(각주 6개), 질문 한 문단,
결론 문단 + 숫자 표(경우 2열·6행) + 주석 + 판정 문단. 0.17.0에서는 이 모양에서 '결론 제목 + 결론 문단 + 표 제목 + 표 전체'가
한 덩어리로 묶여 1쪽 아래 절반이 비고 통째로 2쪽으로 넘어갔다. 외부 호출 없음.
0.17.1은 숫자 표를 통째로 두어 표가 2쪽으로 넘어가면 1쪽 아래 15~20%가 비었다. 0.18.2부터 숫자 표는 쪽 사이에서 나뉜다.
규칙: 결론 문단은 숫자 표와 묶지 않는다. 숫자 표는 행(머리 행 제외)이 4개 이하면 통째로, 5개 이상이면 나뉘되 표 제목 + 머리 행 + 첫 두 행,
합계 행 + 앞 행 + 뒤 행(합계 표시가 없으면 마지막 세 행), 마지막 두 행, 마지막 행 + 조건 주석은 한 덩어리. 다른 표는 쪽의 약 20% 이하이면 통째로,
그보다 크면 행 사이에서 넘어가되 머리 행 + 첫 행, 합계 행 + 앞 행 + 뒤 행은 붙는다.
문서 XML의 묶음은 어디서나 검사하고, 쪽 나눔은 LibreOffice(soffice)와 poppler가 있을 때만 본다.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from korean_tax_mcp import memo_docx as D
from korean_tax_mcp import tax_memo as M

EX = json.loads((Path(__file__).parent / "fixtures" / "tax_memo_fixture_en.json").read_text("utf-8"))
USABLE = D.PAGE_H - 2 * D.MARGIN_TB


def repro():
    """1쪽이 반쯤 찬 자리에 결론 절이 오는 메모(지어낸 값)."""
    s = copy.deepcopy(EX)
    s["head"] = {"to": "Made-up addressee, Example Company Ltd.", "prepared_by": "Example team — made-up data for a page-break check",
                 "date": "1 January 2000",
                 "re": "Made-up memo on a late-payment charge under the Example Tax Act, and a look back at the charge paid in the earlier period",
                 "scope": "Late-payment charge under the fabricated Example Tax Act for one made-up period; the under-reporting penalty and "
                          "any other charge are outside this memo.",
                 "basis": "Made-up folder of documents put together on 1 January 2000 (notice, bank record, earlier computation, return "
                          "summary, payment log, letters from the office); the fabricated act as it stood on 1 January 2000",
                 "workings": "Example_Charge_Workings_2000.xlsx"}
    more = ["The fixed part does not depend on the day count while the daily part does, so the bank record of the payment date settles "
            "the figure; the office reads the period from the day after the deadline, and a payment that reaches the office after its "
            "closing hour counts as made on the next working day under the made-up rule.",
            "The daily part keeps running until the day the tax reaches the office, and a made-up notice does not stop it; a part "
            "payment is set against the tax first, so the daily part is then worked out on what is still unpaid.",
            "An application filed after the period is refused without a look at the cause, as the made-up court has held, and a cause "
            "outside the list in the act does not count; the made-up form has to reach the office, not merely be posted, within "
            "the period, and the office answers in writing within a made-up number of days."]
    for it, text in zip(s["summary"], more): it["basis"] = it["basis"] + " " + text
    s["summary"][1]["basis"] += "[^a9]"; s["summary"][2]["basis"] += "[^a13]"
    for f in s["footnotes"]:          # 각주가 1쪽 아래에서 두 줄씩 차지하게
        f["text"] += " The wording is fabricated for this check and is quoted here at some length so that the note runs on to a second line."
    s["question"] += (" Was the charge paid in the earlier period worked out the right way, and if it was not, what has to be paid "
                      "or claimed back now under the made-up act?")
    s["short_answer"] = {"answer": "Yes — pay KRW 330,000 (a fixed charge of KRW 300,000 plus a daily charge of KRW 30,000 for 30 days), and "
                                   "put right the charge paid in the earlier period, which was one day short.",
                         "conditions": "This holds if the unpaid tax was KRW 10,000,000, payment was 30 days late, the shortfall was not an "
                                       "under-reporting, and no reduction has been granted. If the office grants a reduction on an application "
                                       "filed in time, the charge is KRW 180,000 (case B)."}
    s["key_figures"] = {"title": "Charge for the made-up period — KRW", "columns": ["Item", "A. No reduction", "B. Reduction granted"],
                        "rows": [["Unpaid tax", "10,000,000", "10,000,000"], ["Fixed charge", "300,000", "150,000"],
                                 ["Daily charge (30 days)", "30,000", "30,000"], ["Each further day", "1,000", "1,000"],
                                 {"cells": ["Total charge", "330,000", "180,000"], "role": "total"}, ["Days counted", "30", "30"]],
                        "recommended": "A. No reduction",
                        "note": "A applies as things stand. B applies only if an application is filed within the period and the office grants it; "
                                "without that grant the office may still ask for the full fixed charge."}
    s["review"] = M.optional_blocks("en")["example"]["review"]
    return s


def _doc(structure, tmp_path, name="memo"):
    r = M.build(structure, str(tmp_path), name)
    assert not r["errors"], r["errors"]
    with zipfile.ZipFile(r["path"]) as z:
        return r, re.sub(r"<w:sectPr>.*?</w:sectPr>", "", z.read("word/document.xml").decode("utf-8").split("<w:body>")[1])


def chains(doc):
    """쪽 경계가 들어갈 수 없는 묶음들 — [(어림 높이 twip, [블록 글…])]. 문단은 '다음 문단과 함께'면 다음 블록과, 표의 행은 그 행의
    문단이 '다음 문단과 함께'면 다음 행과 묶인다. 묶음의 끝이 긴 문단이면 Word는 그 문단의 첫 두 줄만 붙든다(높이는 두 줄만 센다)."""
    d = D.Doc({"lang": "en", "footnotes": []})
    units = []          # (글, 높이, 다음과 묶임, 문단인가)
    for m in re.finditer(r"<w:tbl>.*?</w:tbl>|<w:p>.*?</w:p>", doc, re.S):
        b = m.group(0)
        if b.startswith("<w:tbl>"):
            for row in re.findall(r"<w:tr>.*?</w:tr>", b, re.S):
                units.append((re.sub(r"<[^>]+>", " ", row)[:40], d._row_tall(row), "<w:keepNext/>" in row, False))
        else:
            styled = 'w:pStyle w:val="Heading' in b
            units.append((re.sub(r"<[^>]+>", "", b)[:40], d._tall(b, D.W), "<w:keepNext/>" in b or styled, True))
    out, cur = [], []
    for i, (text, tall, keep, para) in enumerate(units):
        if not keep and cur and para:          # 묶음 끝의 문단: 첫 두 줄만
            tall = min(tall, 2 * 20 * 10 * 1.16 * D.LINE / 240)
        cur.append((text, tall))
        if not keep:
            if len(cur) > 1: out.append((sum(t for _, t in cur), [x for x, _ in cur]))
            cur = []
    return out


# ── 문서 XML: 묶음의 크기와 경계 (LibreOffice 없이) ──
def _rows(tbl): return re.findall(r"<w:tr>.*?</w:tr>", tbl, re.S)
def _keep(tbl): return ["<w:keepNext/>" in r for r in _rows(tbl)]
def _tables(doc): return re.findall(r"<w:tbl>.*?</w:tbl>", doc, re.S)
def _paras(doc): return re.findall(r"<w:p>.*?</w:p>", re.sub(r"<w:tbl>.*?</w:tbl>", "", doc, flags=re.S), re.S)


def test_limits():
    assert 0.19 * USABLE <= D.KEEP_HEIGHT <= 0.2 * USABLE and D.KEY_WHOLE == 4


def test_kept_together_chains_stay_bounded(tmp_path):
    """통째로 넘어가는 묶음의 키 = 앞 쪽에 생길 수 있는 빈 자리. 그 밖의 표는 27%(표 20% + 제목들) 아래, 숫자 표는 나뉘므로 가장 큰 묶음(합계 앞 행 ~ 조건 주석)이 쪽의 12% 아래."""
    for name, s in (("repro", repro()), ("fixture", EX), ("example", M.example("en")), ("ko", M.example("ko"))):
        _, doc = _doc(s, tmp_path, name)
        for tall, texts in chains(doc):
            assert tall <= 0.27 * USABLE, (name, round(tall / USABLE, 2), texts)
    _, doc = _doc(repro(), tmp_path, "repro2")          # 재현 입력의 숫자 표: 묶음이 둘로 갈린다
    parts = [c for c in chains(doc) if c[1][0].startswith("Charge for the made-up period") or c[1][-1].startswith("A applies as things stand")]
    assert len(parts) == 2 and all(tall <= 0.12 * USABLE for tall, _ in parts), [(round(t / USABLE, 2), x) for t, x in parts]


def _key(doc): return [t for t in _tables(doc) if "A. No reduction" in t][0]


def test_key_figures_table_splits_between_groups_and_is_not_tied_to_the_answer(tmp_path):
    s = repro()
    _, doc = _doc(s, tmp_path)
    answer = [p for p in _paras(doc) if "Yes — pay KRW 330,000" in p][-1]
    assert "<w:keepNext/>" not in answer          # 결론 문단은 표에 묶지 않는다(제목은 결론 문단의 첫 줄들과만)
    title = [p for p in _paras(doc) if s["key_figures"]["title"] in p][0]
    assert "<w:keepNext/>" in title          # 표 제목 → 머리 행
    key = _key(doc); rows = _rows(key)
    assert len(rows) == 7 and all("<w:cantSplit/>" in r for r in rows) and "<w:tblHeader/>" in rows[0] and key.count("<w:tblHeader/>") == 1
    # 머리 0 · 행 1~6(합계는 5): [제목 + 머리 + 1 + 2] | [3] | [4 + 합계 5 + 6 + 주석] — 나뉠 자리는 2행 뒤와 3행 뒤
    assert _keep(key) == [True, True, False, False, True, True, True]
    for r, k in zip(rows, _keep(key)): assert r.count("<w:keepNext/>") == (r.count("<w:p>") if k else 0)
    assert "Total charge" in rows[5] and f'w:fill="{D.EMPH}"' in rows[5]
    note = [p for p in _paras(doc) if "A applies as things stand" in p][0]
    assert "<w:keepNext/>" not in note and doc.index(key) < doc.index(note)          # 사슬은 주석에서 끝난다
    # 사슬로 보면: 제목 ~ 둘째 행, 합계 앞 행 ~ 주석의 두 묶음. 결론 제목·결론 문단은 어느 묶음에도 없다
    cs = [c[1] for c in chains(doc)]
    first = [c for c in cs if c[0].startswith("Charge for the made-up period")][0]
    last = [c for c in cs if c[-1].startswith("A applies as things stand")][0]
    assert len(first) == 4 and first[-1].split()[0] == "Fixed" and len(last) == 4 and [x.split()[0][:4] for x in last[:3]] == ["Each", "Tota", "Days"]
    assert doc.index(answer) < doc.index(key) < doc.index("3. Facts and assumptions")          # 순서는 그대로: 결론 → 숫자 표 → 사실관계
    # 주석이 없으면 마지막 행에서 끝난다
    s["key_figures"]["note"] = ""
    _, doc = _doc(s, tmp_path, "nonote")
    assert _keep(_key(doc)) == [True, True, False, False, True, True, False]
    # 긴 숫자 표도 같은 규칙: 머리 + 첫 두 행, 합계 앞 행 + 합계 + 뒤 행만 붙고 그 사이는 어디서나 나뉜다
    s["key_figures"]["rows"] = [[f"Made-up line {k} that is long enough to run over on to a second line of the first column of this table", "1,000", "1,000"] for k in range(12)] \
                               + [{"cells": ["Total charge", "330,000", "180,000"], "role": "total"}, ["Days counted", "30", "30"]]
    _, doc = _doc(s, tmp_path, "tall")
    assert _keep(_key(doc)) == [True, True] + [False] * 10 + [True, True, False]


def test_small_key_figures_table_stays_whole(tmp_path):
    """행(머리 행 제외)이 4개 이하인 숫자 표는 통째로 — 넘겨도 앞 쪽에 비는 자리가 작다. 5개부터 나뉠 자리가 생긴다."""
    s = repro(); rows = s["key_figures"]["rows"]
    s["key_figures"]["rows"] = rows[1:5]          # 4행(마지막이 합계)
    _, doc = _doc(s, tmp_path, "four")
    assert _keep(_key(doc)) == [True] * 5
    s["key_figures"]["rows"] = rows[:5]          # 5행(마지막이 합계): [머리 + 1 + 2] | [3] | [4 + 합계 + 주석]
    _, doc = _doc(s, tmp_path, "five")
    assert _keep(_key(doc)) == [True, True, False, False, True, True]
    s["key_figures"]["rows"] = [r if isinstance(r, list) else r["cells"] for r in rows[:5]]          # 합계 표시 없는 5행: [머리 + 1 + 2] | [3 + 4 + 5 + 주석]
    _, doc = _doc(s, tmp_path, "plain")
    assert _keep(_key(doc)) == [True, True, False, True, True, True]


def test_other_tables_whole_up_to_a_fifth_of_a_page_and_total_row_stays_with_the_rows_around_it(tmp_path):
    s = repro(); s["short_answer"] = {"answer": "", "conditions": ""}          # 결론이 없으면 판정 문단은 검토 결과 절의 표 앞에 찍힌다
    rows = s["calculation"]["rows"]
    s["calculation"]["rows"] = [dict(rows[1], item=f"Made-up component {k} with a name long enough to wrap in its cell of the calculation table") for k in range(14)] + rows[3:]          # … 합계, 참고 행
    _, doc = _doc(s, tmp_path)
    d = D.Doc({"lang": "en", "footnotes": []}); seen = set(); big = False
    for tbl in _tables(doc)[1:]:          # 머리 표(머리 행 없음)는 뺀다
        rows = _rows(tbl); keep = _keep(tbl)
        if "A. No reduction" in tbl: continue          # 숫자 표는 위의 테스트에서
        whole = sum(d._row_tall(r) for r in rows) <= D.KEEP_HEIGHT
        seen.add(whole)
        if whole: assert all(keep[:-1])          # 쪽의 20% 이하 표는 통째로
        elif "Made-up component" in tbl:          # 큰 계산 표: 머리 행 + 첫 행, 합계 앞 행 + 합계 행 + 뒤 행만 붙는다
            total = [i for i, r in enumerate(rows) if "Total charge" in r][0]
            assert len(rows) == 17 and total == 15 and keep == [i in (0, total - 1, total) for i in range(17)]
            big = True
        else: assert keep == [True] + [False] * (len(rows) - 1)          # 합계 행이 없는 큰 표(위험 표): 머리 행 + 첫 행
    assert seen == {True, False} and big
    verdict = [p for p in _paras(doc) if s["review"]["verdict"][:30] in p]
    assert verdict and all("<w:keepNext/>" not in p for p in verdict)          # 판정 문단은 발견 사항 표에 묶지 않는다
    rule = [p for p in _paras(doc) if "<w:pBdr>" in p]
    assert len(rule) == 1 and "<w:keepNext/>" in rule[0]          # 가는 선만 쪽 끝에 남지 않게 '작성 방법' 문단과


def test_tied_rule():
    H = D.KEEP_HEIGHT
    # 보통 표
    assert D.tied([300] * 7, True, [5], H) == {0, 1, 2, 3, 4, 5}          # 7행 계산 표(쪽의 14%): 통째로
    assert D.tied([300] * 12, True, [10], H) == {0, 9, 10}          # 큰 표: 머리 행 + 첫 행, 합계 앞 행 + 합계 행 + 뒤 행
    assert D.tied([300] * 12, True, [11], H) == {0, 10}          # 합계가 마지막 행이면 앞 행하고만
    assert D.tied([300] * 12, True, [3, 8], H) == {0, 2, 3, 7, 8}          # 합계 행이 여러 개면 각각
    assert D.tied([300] * 12, False, [], H) == set()
    # 결론 아래 숫자 표(key): 행 번호 0은 머리 행
    key = lambda n, totals, tail=False: D.tied([300] * n, True, totals, H, tail, True)
    assert key(5, [4]) == {0, 1, 2, 3} and key(5, [4], True) == set(range(5)) and key(2, []) == {0}          # 4행 이하: 통째로
    assert key(40, [20]) == {0, 1, 19, 20, 38}          # 키와 무관하게 나뉜다: 머리 + 첫 두 행, 합계 앞뒤, 마지막 두 행
    assert key(6, []) == {0, 1, 3, 4} and key(6, [], True) == {0, 1, 3, 4, 5}          # 합계 표시 없는 5행: [머리 + 1 + 2] | [3 + 4 + 5]
    assert key(7, [5], True) == {0, 1, 4, 5, 6}          # 재현 입력
    assert key(6, [4], True) == {0, 1, 3, 4, 5}          # 5행·합계 넷째: [머리 + 1 + 2] | [3 + 합계 + 5 + 주석]
    assert key(9, [3, 8]) == {0, 1, 2, 3, 7}          # 합계 둘: 3행 앞뒤, 마지막 합계는 앞 행과
    # 묶음이 겹쳐 나뉠 자리가 없으면 가운데에 가장 가까운 합계 행을 뒤 행에서 뗀다(앞 행과는 그대로)
    assert key(6, [3], True) == {0, 1, 2, 4, 5} and key(6, [2, 4]) == {0, 1, 3, 4}
    for n in range(6, 12):          # 5행 이상이면 어떤 합계 배치에서도 나뉠 자리가 한 곳 이상, 합계 행은 앞 행과 늘 붙는다(합계 행이 잇달아 놓인 자리만 예외)
        for mask in range(2 ** (n - 1)):
            totals = [i + 1 for i in range(n - 1) if mask >> i & 1]
            keep = key(n, totals)
            assert len(keep) < n - 1 and n - 1 not in keep and {0, 1} <= keep and all(t - 1 in keep or t - 1 in totals for t in totals), (n, totals, keep)


def test_length_estimate_does_not_change_with_keep_rules(tmp_path):
    """분량 어림은 문단·표 높이의 합이라 묶는 규칙과 무관하다 — 재현 입력은 LibreOffice에서 3쪽 + 3줄, 어림 3.0."""
    r, _ = _doc(repro(), tmp_path)
    assert 2.6 <= r["length"]["estimated_pages"] <= 3.2


# ── 쪽수: LibreOffice가 있을 때만 ──
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
needs_office = pytest.mark.skipif(not (SOFFICE and shutil.which("pdfinfo") and shutil.which("pdftotext")),
                                  reason="LibreOffice(soffice)와 poppler(pdfinfo·pdftotext)가 있을 때만 쪽수를 본다")


def _pages(path, tmp_path):
    env = dict(os.environ)
    conf = "/opt/homebrew/etc/fonts/fonts.conf"
    if os.path.exists(conf): env.setdefault("FONTCONFIG_FILE", conf)
    profile = tmp_path / "lo_profile"; profile.mkdir(exist_ok=True)
    subprocess.run([SOFFICE, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(path)],
                   check=True, capture_output=True, timeout=180, env=env)
    pdf = Path(tmp_path) / (Path(path).stem + ".pdf")
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout).group(1))
    return n, [subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
               for i in range(1, n + 1)]


@needs_office
def test_page_breaks_in_libreoffice(tmp_path):
    r, _ = _doc(repro(), tmp_path, "repro")
    n, text = _pages(r["path"], tmp_path)
    assert "2. Short answer" in text[0] and "the charge is KRW 180,000 (case B)" in text[0]          # 결론 절이 1쪽에 온다(0.17.0: 제목부터 2쪽으로 넘어감)
    row = lambda name, a, b: re.compile(re.escape(name) + r"\s+" + a + r"\s+" + b + r"\s*$", re.M)          # 숫자 표의 행(계산 표에도 같은 이름이 있어 두 값으로 가린다)
    page = lambda pat: [i for i, t in enumerate(text) if (pat.search(t) if hasattr(pat, "search") else pat in t)]
    title, first, second = page("Charge for the made-up period"), page(row("Unpaid tax", "10,000,000", "10,000,000")), page(row("Fixed charge", "300,000", "150,000"))
    before, total, after = page(row("Each further day", "1,000", "1,000")), page(row("Total charge", "330,000", "180,000")), page(row("Days counted", "30", "30"))
    note = page("A applies as things stand")
    assert title == first == second == [0]          # 숫자 표가 1쪽에서 시작한다(0.17.1: 통째로 2쪽으로 넘어가 1쪽 아래가 빔) — 제목·머리 행·첫 두 행이 함께
    assert len(total) == 1 and before == total == after == note          # 합계 행은 앞 행·뒤 행·조건 주석과 같은 쪽
    if total != [0]:          # 표가 나뉘었으면 다음 쪽에 머리 행이 되풀이되고, 합계 행은 그 쪽의 첫 행이 아니다
        t = text[total[0]]
        assert t.index("B. Reduction granted") < t.index("Each further day") < t.index("Total charge")
    assert n <= 4
