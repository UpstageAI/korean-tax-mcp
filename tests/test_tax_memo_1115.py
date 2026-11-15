"""세무 메모(tax_memo_guide·build_tax_memo): 따지는 순서 점검 규칙과 Word 파일. 작성 Mia(윤승미)

규칙마다 통과하는 구조와 그 규칙만 어긴 구조를 넣는다. 외부 호출 없음.
통과하는 구조는 tests/fixtures/tax_memo_fixture_{en,ko}.json — 법 이름·법원·세율·금액을 모두 지어낸 자료(쟁점 5개, 결과 표, 경우의 수 2개,
우선순위 전부). 도구가 돌려주는 예시도 지어낸 사례(모양만)다. 실제 사례의 답은 도구 출력에도 tests/fixtures에도 두지 않는다.
"""
import asyncio
import copy
import json
import re
import zipfile
from pathlib import Path
from xml.dom import minidom

import pytest

from korean_tax_mcp import tax_memo as M
from korean_tax_mcp.server import mcp

EX = {lang: json.loads((Path(__file__).parent / "fixtures" / f"tax_memo_fixture_{lang}.json").read_text("utf-8")) for lang in ("en", "ko")}


def _codes(structure, lang=""):
    _, _, errors, warnings = M.check(structure, lang)
    return [x[1:4] for x in errors + warnings]


def _mut(lang, fn):
    s = copy.deepcopy(EX[lang]); fn(s); return s


# ── 예시는 경고 0건 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_examples_pass_every_rule(lang):
    got_lang, s, errors, warnings = M.check(EX[lang])
    assert got_lang == lang and not errors and not warnings, errors + warnings
    assert len(s["summary"]) == 3 and len(s["analysis"]) >= 3
    assert [M.STAGES.index(i["stage"]) for i in s["analysis"]] == sorted(M.STAGES.index(i["stage"]) for i in s["analysis"])


def test_guide_returns_logic_line_schema_and_example():
    for lang in ("en", "ko"):
        g = M.guide(lang)
        assert g["lang"] == lang and g["example"] == M.example(lang) and len(g["checks"]) == len(M.RULES) == 42
        assert g["example_note"] == M.EXAMPLE_NOTE[lang]
        assert [x["stage"] for x in g["stages"]] == list(M.STAGES) and g["priorities"] == list(M.PRIORITIES[lang])
        for key in ("head", "summary", "question", "short_answer", "facts", "analysis", "calculation", "risks", "next_steps", "footnotes", "prepared_how"):
            assert key in g["schema"]
    en, ko = M.guide("en")["guide"], M.guide("ko")["guide"]
    for word in ("exactly 3", "characterization", "korean-tax-calc-mcp", "verify_citations", "Nothing may be asserted", "reuses the same note number", "issue lists", "no checklist", "[Length", "target_pages", "about 90 words", "printed once"):
        assert word in en, word
    for word in ("정확히 3개", "characterization", "korean-tax-calc-mcp", "verify_citations", "단정하지 않는다", "처음 번호를 다시 쓴다", "쟁점 목록", "점검 목록이 없다", "[분량", "target_pages", "280자", "한 번만"):
        assert word in ko, word
    with pytest.raises(ValueError): M.guide("jp")


def test_tools_teach_the_logic_line_only(tmp_path):
    """도구가 돌려주는 글(안내·스키마·예시·경고·도구 설명)에 특정 사례의 답이 들어 있지 않다 — 예시는 지어낸 사례로 모양만 보인다."""
    banned = ("royalt", "사용료", "2021두59908", "Halden")
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    texts = [tools["tax_memo_guide"].description, tools["build_tax_memo"].description,
             json.dumps(tools["tax_memo_guide"].input_schema, ensure_ascii=False), json.dumps(tools["build_tax_memo"].input_schema, ensure_ascii=False)]
    for lang in ("en", "ko"):
        g = _call("tax_memo_guide", {"lang": lang})
        texts.append(json.dumps(g, ensure_ascii=False))
        assert "do not reuse" in g["example_note"] or "가져다 쓰지 말 것" in g["example_note"]
        assert "do not reuse" in g["example"]["head"]["scope"] or "가져다 쓰지 말 것" in g["example"]["head"]["scope"]
        r = M.build(g["example"], str(tmp_path), f"shape_{lang}")          # 예시는 그대로 넣으면 경고 0건
        assert r["ok"] and r["footnotes"] == len(g["example"]["footnotes"]) == 3, r          # 각주는 출처마다 하나
        texts.append(json.dumps(M.build({"lang": lang, "head": {}, "summary": [{}], "analysis": [{}]}, check_only=True), ensure_ascii=False))
    texts.append(Path(M.__file__).read_text("utf-8")); texts.append(Path(M.__file__).with_name("memo_docx.py").read_text("utf-8"))
    fixtures = Path(__file__).parent / "fixtures"
    texts += [f.read_text("utf-8") for f in sorted(fixtures.glob("tax_memo*"))]          # 테스트 자료에도 실제 사례를 두지 않는다
    assert len(list(fixtures.glob("tax_memo*"))) == 2          # 메모 자료는 지어낸 사례 2개뿐(다른 도구의 조약 자료는 대상 아님)
    for text in texts:
        for word in banned: assert word.lower() not in text.lower(), word
    for name in ("tax_memo_example_en.json", "tax_memo_example_ko.json"):
        assert "Example Tax Act" in (M.DATA / name).read_text("utf-8") or "예시세법" in (M.DATA / name).read_text("utf-8")


# ── 규칙마다 어긴 구조 → 그 규칙 번호 ──
def _drop_notes(text): return M.MARK.sub("", text)


FAIL = [
    ("M01", lambda s: s["head"].update(scope="")),
    ("M02", lambda s: s["summary"].pop()),
    ("M02", lambda s: s["summary"].append(dict(s["summary"][0]))),
    ("M03", lambda s: s["summary"][0].update(conclusion="")),
    ("M03", lambda s: s["summary"][0].update(conclusion="A charge of KRW 330,000 is due. That is KRW 300,000 plus KRW 30,000.")),
    ("M04", lambda s: s["summary"][1].update(basis="[^a11]")),
    ("M05", lambda s: s["summary"][2].update(conclusion="We reviewed the Example Court decision on reductions.")),
    ("M06", lambda s: s.update(question="")),
    ("M06", lambda s: s.update(question="First sentence here. Second sentence here. Third sentence here.")),
    ("M07", lambda s: s["short_answer"].update(conditions="")),
    ("M07", lambda s: s["short_answer"].update(answer="")),
    ("M08", lambda s: s.update(facts=[])),
    ("M09", lambda s: s["facts"][1].update(risk="nope")),
    ("M09", lambda s: s["facts"][1].pop("risk")),
    ("M11", lambda s: s["analysis"][2].update(application="")),
    ("M11", lambda s: s["analysis"][2].update(conclusion="")),
    ("M12", lambda s: s["analysis"][2].update(heading="Rate")),
    ("M13", lambda s: s["decision_table"]["rows"][0].pop()),
    ("M14", lambda s: s["calculation"].update(currency="")),
    ("M14", lambda s: s["calculation"]["rows"][1].update(role="subtotal")),
    ("M15", lambda s: s["calculation"]["rows"][3].update(amount="331,000")),
    ("M15", lambda s: s["calculation"]["scenarios"][0]["rows"][2].update(amount="361,000")),
    ("M16", lambda s: s["risks"][0].update(priority="URGENT")),
    ("M16", lambda s: s["risks"][5].update(why="", check="")),
    ("M17", lambda s: s.update(next_steps=[])),
    ("M18", lambda s: s["footnotes"].append(dict(s["footnotes"][0]))),
    ("M20", lambda s: s["footnotes"].append({"id": "unused", "text": "Corporate Tax Act, Art. 1."})),
    ("M21", lambda s: s["analysis"][0].update(application=" ".join(["word"] * 130) + ".")),
    ("M22", lambda s: s["analysis"][0].update(conclusion="It should be noted that this is a late-payment charge.")),
    ("M23", lambda s: s.update(recipient="CFO")),
    ("T01", lambda s: s.update(analysis=s["analysis"][:2])),
    ("T02", lambda s: s["analysis"].insert(0, s["analysis"].pop())),
    ("T02", lambda s: s["analysis"][0].update(stage="")),
    ("T03", lambda s: s["analysis"][2].update(rule=_drop_notes(s["analysis"][2]["rule"]))),
    ("T03", lambda s: [f.update(text="Example Tax Act: fixed and daily rates.") for f in s["footnotes"] if f["id"] == "a11"]),
    ("T04", lambda s: s["summary"][2].update(basis=_drop_notes(s["summary"][2]["basis"]))),
    ("T05", lambda s: s.pop("calculation")),
    ("T05", lambda s: s["calculation"]["rows"].pop(3)),
    ("T05", lambda s: [r.update(role="") for r in s["calculation"]["rows"] if r["role"] == "component"]),
    ("T06", lambda s: s["summary"][0].update(conclusion="A late-payment charge of KRW 999,000 is due on KRW 10,000,000 of unpaid tax.")),
    ("T06", lambda s: s["short_answer"].update(answer="Yes — KRW 998,000.")),
    ("T06", lambda s: s["calculation"].update(scenarios=[])),          # 요약의 360,000이 표에서 사라짐
    ("T07", lambda s: [f.update(text=re.sub(r"[가-힣]", "", f["text"])) for f in s["footnotes"]]),
    ("T08", lambda s: s.update(prepared_how="")),
]


@pytest.mark.parametrize("code,fn", FAIL, ids=[f"{c}-{i}" for i, (c, _) in enumerate(FAIL)])
def test_each_rule_fails_when_broken(code, fn):
    codes = _codes(_mut("en", fn))
    assert code in codes, codes


def test_every_rule_has_a_failing_case():
    covered = {c for c, _ in FAIL} | {"E01", "E02", "E03", "M10"}      # E·M10은 아래 테스트
    covered |= {"M24", "M25", "T09", "T10", "T11", "T12", "T13"}      # 선택 블록 규칙은 test_tax_memo_blend_1115.py
    covered |= {"M26", "M27"}      # 분량 규칙은 test_tax_memo_length_1115.py
    assert {r[:3] for r in M.RULES} <= covered, {r[:3] for r in M.RULES} - covered


KO_FAIL = [
    ("M03", lambda s: s["summary"][0].update(conclusion="가산금 330,000원을 내야 한다. 정액분과 일수분의 합계이다.")),
    ("M05", lambda s: s["summary"][0].update(conclusion="검토한 결과 가산금 330,000원을 내야 한다.")),
    ("M12", lambda s: s["analysis"][2].update(heading="세율")),
    ("M16", lambda s: s["risks"][0].update(priority="HIGH")),
    ("M21", lambda s: s["analysis"][0].update(application="가" * 401)),
    ("M22", lambda s: s["analysis"][0].update(conclusion="지연 가산금에 해당하는 것으로 보입니다.")),
    ("T03", lambda s: [f.update(text="예시세법: 정액·일수 비율.") for f in s["footnotes"] if f["id"] == "a11"]),
    ("T06", lambda s: s["short_answer"].update(answer="내야 하며 999,000원이다.")),
]


@pytest.mark.parametrize("code,fn", KO_FAIL, ids=[f"ko-{c}-{i}" for i, (c, _) in enumerate(KO_FAIL)])
def test_korean_rules(code, fn):
    w = M.check(_mut("ko", fn))[3]
    assert any(x.startswith(f"[{code}]") for x in w), w
    assert all(re.search(r"[가-힣]", x) for x in w)          # 국문 메모 경고는 한국어


def test_dates_and_case_numbers_are_not_sentences_or_amounts():
    assert M.sentences("예시법원 2000. 1. 1. 선고 2000예12345 판결은 감면 기간을 엄격하게 본다.") == 1
    assert M.sentences("Under Art. 14(1) of the treaty the cap is 15 percent. See Art. 98-6.") == 2
    assert M._amounts("Example Court, 2000예12345, KRW 16,500,000 and 22000000 in 2026") == {"16500000", "22000000"}
    assert M.number("(1,500,000)") == -1500000 and M.number("—") is None and M.number("16,500,000") == 16500000


# ── 오류(파일을 만들지 않음) ──
def test_hard_errors_write_no_file(tmp_path):
    r = M.build(_mut("en", lambda s: s["summary"][0].update(basis="A charge is due.[^missing]")), str(tmp_path))
    assert r["path"] == "" and not r["ok"] and any(x.startswith("[E03]") for x in r["errors"])
    r = M.build(_mut("en", lambda s: s.update(summary="three points", analysis="text")), str(tmp_path))
    assert r["path"] == "" and sum(x.startswith("[E01]") for x in r["errors"]) == 2 and any(x.startswith("[E02]") for x in r["errors"])
    r = M.build(_mut("en", lambda s: s.update(analysis=["just a string"])), str(tmp_path))
    assert r["path"] == "" and any(x.startswith("[E01]") for x in r["errors"])
    r = M.build({"lang": "en", "head": {"re": "x"}}, str(tmp_path))
    assert r["path"] == "" and any(x.startswith("[E02]") for x in r["errors"]) and any(x.startswith("[M10]") for x in r["warnings"])
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError): M.build("not json", str(tmp_path))
    with pytest.raises(ValueError): M.build([1, 2], str(tmp_path))
    with pytest.raises(ValueError): M.build(EX["en"], str(tmp_path), lang="jp")


def test_warnings_still_write_the_file(tmp_path):
    r = M.build(_mut("en", lambda s: s["risks"][0].update(priority="URGENT")), str(tmp_path), "draft")
    assert r["path"].endswith("draft.docx") and not r["ok"] and not r["errors"] and len(r["warnings"]) == 1
    assert zipfile.is_zipfile(r["path"]) and "again" in r["next"]


def test_check_only_writes_nothing(tmp_path):
    r = M.build(EX["en"], str(tmp_path), check_only=True)
    assert r["ok"] and r["path"] == "" and not list(tmp_path.iterdir())


# ── Word 파일 ──
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _parts(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_docx_is_well_formed_with_real_footnotes(tmp_path, lang):
    r = M.build(EX[lang], str(tmp_path), f"memo_{lang}")
    assert r["ok"] and r["lang"] == lang and r["path"] == str(tmp_path / f"memo_{lang}.docx")
    parts = _parts(r["path"])
    for name in ("[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/_rels/document.xml.rels", "word/styles.xml",
                 "word/numbering.xml", "word/footnotes.xml", "word/settings.xml", "word/footer1.xml", "word/fontTable.xml", "docProps/core.xml"):
        minidom.parseString(parts[name].encode("utf-8"))          # 모두 올바른 XML
    doc, notes = parts["word/document.xml"], parts["word/footnotes.xml"]
    # 각주: 본문 참조 번호 = 각주 파일 번호 = 1..n, 읽는 순서
    refs = [int(x) for x in re.findall(r'<w:footnoteReference w:id="(\d+)"/>', doc)]
    defined = [int(x) for x in re.findall(r'<w:footnote w:id="(\d+)">', notes)]
    n_marks = sum(len(M.MARK.findall(v)) for v in re.findall(r'"(?:basis|rule|why|check)": "([^"]*)"', json.dumps(EX[lang], ensure_ascii=False)))
    assert refs == defined == list(range(1, r["footnotes"] + 1)) and n_marks == 15 and r["footnotes"] == len(EX[lang]["footnotes"]) == 6
    assert 'w:type="separator" w:id="-1"' in notes and 'w:type="continuationSeparator" w:id="0"' in notes
    assert notes.count("<w:footnoteRef/>") == len(defined)
    # 같은 출처가 다시 나오면 각주를 새로 만들지 않고 처음 번호를 다시 쓴다(본문의 위첨자 수 = [^id] 수)
    again = re.findall(r'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:t>(\d+)</w:t></w:r>', doc)
    assert len(refs) + len(again) == n_marks and set(map(int, again)) <= set(refs)
    assert "See note" not in notes and "참조." not in notes and all(notes.count(f["text"][:30]) == 1 for f in EX[lang]["footnotes"])
    # 한글이 본문과 각주에 그대로 들어 있고, 모든 글자 조각에 동아시아 글꼴이 지정됨
    assert re.search(r"[가-힣]", notes) and "예시세법" in notes
    assert ("예시법원" in notes) and (lang == "en" or "핵심 요약" in doc)
    for xml in (doc, notes, parts["word/footer1.xml"]):
        fonts = re.findall(r"<w:rFonts [^>]*/>", xml)
        assert fonts and all('w:eastAsia="Malgun Gothic"' in f for f in fonts)
    assert 'w:eastAsia="Malgun Gothic"' in parts["word/styles.xml"] and 'w:eastAsia="ko-KR"' in parts["word/styles.xml"]
    # 쪽: A4, 여백, 바닥글(안내 + 쪽 번호)
    assert '<w:pgSz w:w="11906" w:h="16838"/>' in doc and 'w:top="1000"' in doc and 'w:left="1134"' in doc
    assert " PAGE " in parts["word/footer1.xml"] and M.LABELS[lang]["notice"][:20] in parts["word/footer1.xml"]
    # 표: 행이 쪽에서 갈라지지 않고 머리 행 반복, 머리·합계 음영, 우선순위 색
    assert doc.count("<w:tr>") == doc.count("<w:cantSplit/>") and doc.count("<w:tblHeader/>") + 1 == doc.count("<w:tbl>") == 6          # 머리 표에는 반복할 머리 행이 없음
    for fill in ("F3F6F9", "FBE4E1", "FDF1D6", "E4F2E7"): assert f'w:fill="{fill}"' in doc
    # 번호 목록은 목록마다 1부터(요약, 다음 단계), 글머리표는 따로
    num = parts["word/numbering.xml"]
    assert num.count("<w:startOverride w:val=\"1\"/>") == 2 and '<w:numId w:val="2"/>' in doc and '<w:numId w:val="3"/>' in doc
    assert doc.count('<w:numId w:val="2"/>') == 3 and doc.count('<w:numId w:val="3"/>') == len(EX[lang]["next_steps"])
    assert doc.count('<w:numId w:val="1"/>') == len(EX[lang]["facts"])
    # 머리: 표 한 개(작성·일자·제목·범위), 본문 10pt·줄 간격 1.1, 작은 표는 통째로 한 쪽에(마지막 행을 뺀 문단에 '다음 문단과 함께')
    head = re.findall(r"<w:tbl>.*?</w:tbl>", doc)[0]
    for k in ("prepared_by", "date", "re", "scope"): assert M.plain(EX[lang]["head"][k]) in re.sub(r"<[^>]+>", "", head).replace("&amp;", "&")
    assert "<w:tblHeader/>" not in head and doc.index("</w:tbl>") < doc.index('<w:pStyle w:val="Heading1"/>')
    assert '<w:sz w:val="20"/>' in doc and 'w:line="264"' in doc
    for para in re.findall(r"<w:p>.*?</w:p>", re.sub(r"<w:tbl>.*?</w:tbl>", "", doc)):          # 표 밖의 문단: 글머리표·번호 항목의 본문은 10pt 이상
        if "<w:numPr>" in para and "<w:t" in para: assert max(int(x) for x in re.findall(r'<w:sz w:val="(\d+)"/>', para)) >= 20
    for tbl in re.findall(r"<w:tbl>.*?</w:tbl>", doc)[1:]:
        rows = re.findall(r"<w:tr>.*?</w:tr>", tbl)
        assert all("<w:keepNext/>" in r for r in rows[:-1]) and "<w:keepNext/>" not in rows[-1]
    text = re.sub(r"<[^>]+>", "", doc)
    h1 = [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p>.*?</w:p>", doc) if '<w:pStyle w:val="Heading1"/>' in p]
    heads = (["MEMORANDUM", "Executive summary", "1. Question presented", "2. Short answer", "3. Facts and assumptions", "4. Analysis",
              "5. Calculation", "6. Risks and open points", "7. Recommended next steps", "How this memo was prepared."] if lang == "en" else
             ["메모", "핵심 요약", "1. 쟁점", "2. 결론", "3. 사실관계와 전제", "4. 검토", "5. 계산", "6. 위험과 확인할 점", "7. 다음 단계", "작성 방법."])
    assert h1 == heads[1:-1], h1
    assert text.lstrip().startswith(heads[0]) and heads[-1] in text
    assert "[^" not in text and "**" not in text


def test_docx_is_reproducible_and_escapes_markup(tmp_path):
    a = M.build(EX["en"], str(tmp_path), "a")["path"]; b = M.build(EX["en"], str(tmp_path), "b")["path"]
    assert open(a, "rb").read() == open(b, "rb").read()
    s = _mut("en", lambda s: s["facts"].append("R&D <cost> sharing \x0b is \"not\" covered"))
    doc = _parts(M.build(s, str(tmp_path), "c")["path"])["word/document.xml"]
    minidom.parseString(doc.encode("utf-8"))
    assert "R&amp;D &lt;cost&gt; sharing" in doc


def test_file_name_and_folder(tmp_path):
    r = M.build(EX["ko"], str(tmp_path / "새 폴더"))
    assert r["path"].endswith("세무메모_예시세법에_따른_지연_가산금_테스트_메모.docx")
    assert M.build(EX["en"], str(tmp_path))["path"].split("/")[-1].startswith("Tax_Memo_Made_up_test_memo")
    assert M.build(EX["en"], str(tmp_path), "../../evil.pdf")["path"] == str(tmp_path / "evil.docx")
    assert M.build(json.dumps(EX["en"]), str(tmp_path), "from_string")["ok"]          # JSON 문자열도 받음
    assert M.build(_mut("en", lambda s: s.pop("lang")), str(tmp_path), "auto")["lang"] == "en"
    assert M.build(_mut("ko", lambda s: s.pop("lang")), str(tmp_path), "auto_ko")["lang"] == "ko"


# ── 서버 도구 ──
def _call(name, args):
    r = asyncio.run(mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


def test_tools_registered_after_verify_citations(tmp_path):
    names = [t.name for t in asyncio.run(mcp.list_tools())]
    i = names.index("verify_citations")
    assert names[i + 1:i + 3] == ["tax_memo_guide", "build_tax_memo"] and len(names) == 52
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert tools["tax_memo_guide"].annotations.read_only_hint and not tools["build_tax_memo"].annotations.read_only_hint
    assert not tools["build_tax_memo"].annotations.destructive_hint
    g = _call("tax_memo_guide", {"lang": "ko"})
    assert g["lang"] == "ko" and g["example"] == M.example("ko")
    r = _call("build_tax_memo", {"structure": EX["ko"], "output_dir": str(tmp_path)})
    assert r["ok"] and r["warnings"] == [] and r["errors"] == [] and zipfile.is_zipfile(r["path"])
    r = _call("build_tax_memo", {"structure": json.dumps(_call("tax_memo_guide", {})["example"]), "output_dir": str(tmp_path), "check_only": True})
    assert r["ok"] and r["lang"] == "en" and r["path"] == ""
    assert "error" in _call("build_tax_memo", {"structure": "{broken", "output_dir": str(tmp_path)})
    assert "tax_memo_guide" in mcp.instructions and "build_tax_memo" in mcp.instructions and "export_workbook" in mcp.instructions
