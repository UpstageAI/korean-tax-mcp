"""세무 메모(tax_memo_guide·build_tax_memo): 따지는 순서 점검 규칙과 Word 파일. 작성 Mia(윤승미)

규칙마다 통과하는 구조와 그 규칙만 어긴 구조를 넣는다. 외부 호출 없음.
통과하는 구조는 tests/fixtures/tax_memo_royalty_{en,ko}.json(테스트 전용, 패키지에 넣지 않음) — 조문·판례·금액은 2026-11-15에
korean-tax-mcp 0.15.3·korean-tax-calc-mcp 0.53.1 호출 결과로 대조한 것. 도구가 돌려주는 예시는 이와 무관한 지어낸 사례(모양만)다.
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

EX = {lang: json.loads((Path(__file__).parent / "fixtures" / f"tax_memo_royalty_{lang}.json").read_text("utf-8")) for lang in ("en", "ko")}


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
        assert g["lang"] == lang and g["example"] == M.example(lang) and len(g["checks"]) == len(M.RULES) == 33
        assert g["example_note"] == M.EXAMPLE_NOTE[lang]
        assert [x["stage"] for x in g["stages"]] == list(M.STAGES) and g["priorities"] == list(M.PRIORITIES[lang])
        for key in ("head", "summary", "question", "short_answer", "facts", "analysis", "calculation", "risks", "next_steps", "footnotes", "prepared_how"):
            assert key in g["schema"]
    en, ko = M.guide("en")["guide"], M.guide("ko")["guide"]
    for word in ("exactly 3", "characterization", "korean-tax-calc-mcp", "verify_citations", "Nothing may be asserted", "See note N", "issue lists", "no checklist"):
        assert word in en, word
    for word in ("정확히 3개", "characterization", "korean-tax-calc-mcp", "verify_citations", "단정하지 않는다", "주 N 참조", "쟁점 목록", "점검 목록이 없다"):
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
        assert r["ok"] and r["footnotes"] == 9, r
        texts.append(json.dumps(M.build({"lang": lang, "head": {}, "summary": [{}], "analysis": [{}]}, check_only=True), ensure_ascii=False))
    texts.append(Path(M.__file__).read_text("utf-8")); texts.append(Path(M.__file__).with_name("memo_docx.py").read_text("utf-8"))
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
    ("M03", lambda s: s["summary"][0].update(conclusion="Withhold KRW 16,500,000. That is KRW 15,000,000 plus KRW 1,500,000.")),
    ("M04", lambda s: s["summary"][1].update(basis="[^cta98]")),
    ("M05", lambda s: s["summary"][2].update(conclusion="We reviewed the Supreme Court decision on unregistered patents.")),
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
    ("M15", lambda s: s["calculation"]["rows"][3].update(amount="16,000,000")),
    ("M15", lambda s: s["calculation"]["scenarios"][0]["rows"][2].update(amount="21,000,000")),
    ("M16", lambda s: s["risks"][0].update(priority="URGENT")),
    ("M16", lambda s: s["risks"][5].update(why="", check="")),
    ("M17", lambda s: s.update(next_steps=[])),
    ("M18", lambda s: s["footnotes"].append(dict(s["footnotes"][0]))),
    ("M20", lambda s: s["footnotes"].append({"id": "unused", "text": "Corporate Tax Act, Art. 1."})),
    ("M21", lambda s: s["analysis"][0].update(application=" ".join(["word"] * 130) + ".")),
    ("M22", lambda s: s["analysis"][0].update(conclusion="It should be noted that this is treated as a royalty.")),
    ("M23", lambda s: s.update(recipient="CFO")),
    ("T01", lambda s: s.update(analysis=s["analysis"][:2])),
    ("T02", lambda s: s["analysis"].insert(0, s["analysis"].pop())),
    ("T02", lambda s: s["analysis"][0].update(stage="")),
    ("T03", lambda s: s["analysis"][2].update(rule=_drop_notes(s["analysis"][2]["rule"]))),
    ("T03", lambda s: [f.update(text="Corporate Tax Act: 20 percent on royalties.") for f in s["footnotes"] if f["id"] == "cta98"]),
    ("T04", lambda s: s["summary"][2].update(basis=_drop_notes(s["summary"][2]["basis"]))),
    ("T05", lambda s: s.pop("calculation")),
    ("T05", lambda s: s["calculation"]["rows"].pop(3)),
    ("T05", lambda s: [r.update(role="") for r in s["calculation"]["rows"] if r["role"] == "component"]),
    ("T06", lambda s: s["summary"][0].update(conclusion="Withhold KRW 16,600,000 on a KRW 100,000,000 royalty.")),
    ("T06", lambda s: s["short_answer"].update(answer="KRW 18,000,000, if five conditions hold.")),
    ("T06", lambda s: s["calculation"].update(scenarios=[])),          # 요약의 22,000,000이 표에서 사라짐
    ("T07", lambda s: [f.update(text=re.sub(r"[가-힣]", "", f["text"])) for f in s["footnotes"]]),
    ("T08", lambda s: s.update(prepared_how="")),
]


@pytest.mark.parametrize("code,fn", FAIL, ids=[f"{c}-{i}" for i, (c, _) in enumerate(FAIL)])
def test_each_rule_fails_when_broken(code, fn):
    codes = _codes(_mut("en", fn))
    assert code in codes, codes


def test_every_rule_has_a_failing_case():
    covered = {c for c, _ in FAIL} | {"E01", "E02", "E03", "M10"}      # E·M10은 아래 테스트
    assert {r[:3] for r in M.RULES} <= covered, {r[:3] for r in M.RULES} - covered


KO_FAIL = [
    ("M03", lambda s: s["summary"][0].update(conclusion="16,500,000원을 원천징수한다. 법인세와 지방소득세의 합계이다.")),
    ("M05", lambda s: s["summary"][0].update(conclusion="검토한 결과 16,500,000원을 원천징수한다.")),
    ("M12", lambda s: s["analysis"][2].update(heading="세율")),
    ("M16", lambda s: s["risks"][0].update(priority="HIGH")),
    ("M21", lambda s: s["analysis"][0].update(application="가" * 401)),
    ("M22", lambda s: s["analysis"][0].update(conclusion="사용료에 해당하는 것으로 보입니다.")),
    ("T03", lambda s: [f.update(text="법인세법: 사용료 20%.") for f in s["footnotes"] if f["id"] == "cta98"]),
    ("T06", lambda s: s["short_answer"].update(answer="다섯 가지 조건이 맞으면 17,000,000원이다.")),
]


@pytest.mark.parametrize("code,fn", KO_FAIL, ids=[f"ko-{c}-{i}" for i, (c, _) in enumerate(KO_FAIL)])
def test_korean_rules(code, fn):
    w = M.check(_mut("ko", fn))[3]
    assert any(x.startswith(f"[{code}]") for x in w), w
    assert all(re.search(r"[가-힣]", x) for x in w)          # 국문 메모 경고는 한국어


def test_dates_and_case_numbers_are_not_sentences_or_amounts():
    assert M.sentences("대법원 2025. 9. 18. 선고 2021두59908 전원합의체 판결은 국내원천 사용료로 본다.") == 1
    assert M.sentences("Under Art. 14(1) of the treaty the cap is 15 percent. See Art. 98-6.") == 2
    assert M._amounts("Supreme Court, 2021두59908, KRW 16,500,000 and 22000000 in 2026") == {"16500000", "22000000"}
    assert M.number("(1,500,000)") == -1500000 and M.number("—") is None and M.number("16,500,000") == 16500000


# ── 오류(파일을 만들지 않음) ──
def test_hard_errors_write_no_file(tmp_path):
    r = M.build(_mut("en", lambda s: s["summary"][0].update(basis="Tax is withheld.[^missing]")), str(tmp_path))
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
    assert refs == defined == list(range(1, r["footnotes"] + 1)) and r["footnotes"] == 25
    assert 'w:type="separator" w:id="-1"' in notes and 'w:type="continuationSeparator" w:id="0"' in notes
    assert notes.count("<w:footnoteRef/>") == len(defined)
    # 같은 출처가 다시 나오면 '주 N 참조'
    see = "See note 1." if lang == "en" else "주 1 참조."
    assert see in notes and notes.count(EX[lang]["footnotes"][0]["text"][:30]) == 1
    # 한글이 본문과 각주에 그대로 들어 있고, 모든 글자 조각에 동아시아 글꼴이 지정됨
    assert re.search(r"[가-힣]", notes) and "법인세법" in notes
    assert ("대법원" in notes) and (lang == "en" or "핵심 요약" in doc)
    for xml in (doc, notes, parts["word/footer1.xml"]):
        fonts = re.findall(r"<w:rFonts [^>]*/>", xml)
        assert fonts and all('w:eastAsia="Malgun Gothic"' in f for f in fonts)
    assert 'w:eastAsia="Malgun Gothic"' in parts["word/styles.xml"] and 'w:eastAsia="ko-KR"' in parts["word/styles.xml"]
    # 쪽: A4, 여백, 바닥글(안내 + 쪽 번호)
    assert '<w:pgSz w:w="11906" w:h="16838"/>' in doc and 'w:top="1300"' in doc and 'w:left="1440"' in doc
    assert " PAGE " in parts["word/footer1.xml"] and M.LABELS[lang]["notice"][:20] in parts["word/footer1.xml"]
    # 표: 행이 쪽에서 갈라지지 않고 머리 행 반복, 머리·합계 음영, 우선순위 색
    assert doc.count("<w:tr>") == doc.count("<w:cantSplit/>") and doc.count("<w:tblHeader/>") == doc.count("<w:tbl>") == 5
    for fill in ("F3F6F9", "FBE4E1", "FDF1D6", "E4F2E7"): assert f'w:fill="{fill}"' in doc
    # 번호 목록은 목록마다 1부터(요약, 다음 단계), 글머리표는 따로
    num = parts["word/numbering.xml"]
    assert num.count("<w:startOverride w:val=\"1\"/>") == 2 and '<w:numId w:val="2"/>' in doc and '<w:numId w:val="3"/>' in doc
    assert doc.count('<w:numId w:val="2"/>') == 3 and doc.count('<w:numId w:val="3"/>') == len(EX[lang]["next_steps"])
    assert doc.count('<w:numId w:val="1"/>') == len(EX[lang]["facts"])
    # 머리 표: 내어쓰기, 제목 낱말, 소제목
    assert 'w:left="1500" w:hanging="1500"' in doc
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
    assert r["path"].endswith("세무메모_미국_모회사에_지급하는_특허_기술_사용료의_원천징수.docx")
    assert M.build(EX["en"], str(tmp_path))["path"].split("/")[-1].startswith("Tax_Memo_Korean_withholding_tax")
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
    assert names[i + 1:i + 3] == ["tax_memo_guide", "build_tax_memo"] and len(names) == 51
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
