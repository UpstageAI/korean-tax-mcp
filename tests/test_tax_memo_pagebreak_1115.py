"""세무 메모 쪽 나눔 — 붙여 두는 묶음(다음 문단과 함께)이 작아야 앞 쪽에 큰 빈 공간이 생기지 않는다. 작성 Mia(윤승미)

자료는 지어낸 사례(tests/fixtures/tax_memo_fixture_en.json)를 늘려 만든 것 — 머리 블록 6줄, 요약 3항(각주 6개), 질문 한 문단,
결론 문단 + 숫자 표(경우 2열·6행) + 주석 + 판정 문단. 0.17.0에서는 이 모양에서 '결론 제목 + 결론 문단 + 표 제목 + 표 전체'가
한 덩어리로 묶여 1쪽 아래가 비고 통째로 2쪽으로 넘어갔다. 외부 호출 없음.
문서 XML의 묶음 크기는 어디서나 검사하고, 쪽수는 LibreOffice(soffice)와 pdfinfo가 있을 때만 본다.
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


# ── 문서 XML: 묶음 크기 (LibreOffice 없이) ──
LIMIT = 0.2 * USABLE          # 어느 묶음이 통째로 다음 쪽으로 넘어가도 앞 쪽에 비는 자리는 쪽의 5분의 1 아래


def test_kept_together_chains_stay_small(tmp_path):
    for name, s in (("repro", repro()), ("fixture", EX), ("example", M.example("en")), ("ko", M.example("ko"))):
        _, doc = _doc(s, tmp_path, name)
        worst = max(chains(doc), key=lambda c: c[0])
        assert worst[0] <= LIMIT, (name, round(worst[0] / USABLE, 2), worst[1])
    assert D.KEEP_ROWS == 4 and D.KEEP_HEIGHT <= 0.1 * USABLE          # 통째로 두는 표는 쪽의 10% 이하


def test_old_rule_would_fail_this_check(tmp_path, monkeypatch):
    """검사가 실제로 결함을 잡는지 — 0.17.0의 규칙(반 쪽 이하 표는 통째로)으로 되돌리면 재현 입력에서 기준을 넘는 묶음이 나온다."""
    monkeypatch.setattr(D, "KEEP_ROWS", 16); monkeypatch.setattr(D, "KEEP_HEIGHT", 7400)
    _, doc = _doc(repro(), tmp_path)
    worst = max(chains(doc), key=lambda c: c[0])
    assert worst[0] > LIMIT and len(worst[1]) > 5


def test_short_answer_is_not_tied_to_the_figures_table(tmp_path):
    s = repro()
    _, doc = _doc(s, tmp_path)
    paras = re.findall(r"<w:p>.*?</w:p>", doc, re.S)
    answer = [p for p in paras if "Yes — pay KRW 330,000" in p][-1]
    assert "<w:keepNext/>" not in answer          # 결론 문단은 표에 묶지 않는다(제목은 결론 문단의 첫 두 줄과만)
    title = [p for p in paras if s["key_figures"]["title"] in p][0]
    assert "<w:keepNext/>" in title          # 표 제목은 표의 첫 행과
    tables = re.findall(r"<w:tbl>.*?</w:tbl>", doc, re.S)
    key = [t for t in tables if "A. No reduction" in t][0]
    rows = re.findall(r"<w:tr>.*?</w:tr>", key, re.S)
    assert len(rows) == 7 and all("<w:cantSplit/>" in r for r in rows) and "<w:tblHeader/>" in rows[0]          # 행은 갈라지지 않고 머리 행은 다음 쪽에 반복
    keep = ["<w:keepNext/>" in r for r in rows]
    assert keep == [True, False, False, False, False, True, False]          # 머리 행 + 첫 행, 마지막 두 행만 붙는다 — 그 사이에서는 쪽이 넘어갈 수 있다
    for r in (rows[0], rows[-2]): assert r.count("<w:keepNext/>") == r.count("<w:p>")
    assert doc.index(answer) < doc.index(key) < doc.index("3. Facts and assumptions")          # 순서는 그대로: 결론 → 숫자 표 → 사실관계


def test_small_tables_stay_whole_and_review_verdict_is_free(tmp_path):
    s = repro(); s["short_answer"] = {"answer": "", "conditions": ""}          # 결론이 없으면 판정 문단은 검토 결과 절의 표 앞에 찍힌다
    _, doc = _doc(s, tmp_path)
    d = D.Doc({"lang": "en", "footnotes": []}); seen = set()
    for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", doc, re.S):
        rows = re.findall(r"<w:tr>.*?</w:tr>", tbl, re.S)
        tall = [d._row_tall(r) for r in rows]
        keep = ["<w:keepNext/>" in r for r in rows]
        small = len(rows) <= D.KEEP_ROWS and sum(tall) <= D.KEEP_HEIGHT
        seen.add(small)
        assert not keep[-1]
        if small: assert all(keep[:-1])          # 아주 작은 표는 통째로
        else:
            want = [False] * len(rows)
            want[0] = "<w:tblHeader/>" in rows[0]          # 머리 행 + 첫 행
            if sum(tall[-2:]) <= D.KEEP_HEIGHT: want[-2] = True          # 마지막 두 행
            assert keep == want
    assert seen == {True, False}
    verdict = [p for p in re.findall(r"<w:p>.*?</w:p>", doc, re.S) if s["review"]["verdict"][:30] in p]
    assert verdict and all("<w:keepNext/>" not in p for p in verdict)          # 판정 문단은 발견 사항 표에 묶지 않는다
    rule = [p for p in re.findall(r"<w:p>.*?</w:p>", doc, re.S) if "<w:pBdr>" in p]
    assert len(rule) == 1 and "<w:keepNext/>" in rule[0]          # 가는 선만 쪽 끝에 남지 않게 '작성 방법' 문단과


def test_length_estimate_does_not_change_with_keep_rules(tmp_path):
    """분량 어림은 문단·표 높이의 합이라 묶는 규칙과 무관하다 — 재현 입력은 LibreOffice에서 2.9쪽(3쪽), 어림 3.0."""
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
def test_first_page_is_filled_in_libreoffice(tmp_path):
    r, _ = _doc(repro(), tmp_path, "repro")
    n, text = _pages(r["path"], tmp_path)
    assert "2. Short answer" in text[0] and "Yes — pay KRW 330,000" in text[0]          # 결론 절이 1쪽에서 시작한다(0.17.0: 2쪽으로 통째로 넘어감)
    assert n == 3          # 0.17.0: 4쪽
