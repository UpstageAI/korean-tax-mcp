"""세무 메모 선택 블록(머리 줄·결론 아래 숫자 표·쟁점 안의 표·기존 처리 검토 결과·조치 목록 표·한계·주요 근거)과 새 점검 규칙. 작성 Mia(윤승미)

블록이 없으면 기존 출력과 같고, 블록마다 문서 XML에 표·절이 생기며, 새 규칙은 걸리는 쪽과 통과하는 쪽을 모두 넣는다. 외부 호출 없음.
자료는 지어낸 사례(tests/fixtures/tax_memo_fixture_*.json)에 도구가 돌려주는 선택 블록 예시(지어낸 값)를 얹은 것.
"""
import asyncio
import copy
import json
import re
import zipfile
from pathlib import Path

import pytest

from korean_tax_mcp import server as S
from korean_tax_mcp import tax_memo as M
from korean_tax_mcp.server import mcp

ROOT = Path(__file__).resolve().parent.parent
EX = {lang: json.loads((Path(__file__).parent / "fixtures" / f"tax_memo_fixture_{lang}.json").read_text("utf-8")) for lang in ("en", "ko")}
NEW_RULES = ("M24", "M25", "T09", "T10", "T11", "T12", "T13")


def _blend(base, lang):
    """기본 구조에 선택 블록을 모두 얹는다."""
    s = copy.deepcopy(base); o = M.optional_blocks(lang)["example"]
    s["head"].update(o["head"]); s["workings_check"] = o["workings_check"]; s["key_figures"] = o["key_figures"]; s["review"] = o["review"]; s["limitations"] = o["limitations"]
    s["authorities"] = o["authorities"]; s.pop("next_steps"); s["action_list"] = o["action_list"]
    next(a for a in s["analysis"] if a["stage"] == "procedure")["table"] = o["analysis_table"]
    calc = s["calculation"]          # 쟁점 안의 표와 같은 숫자의 계산 표는 한 번만(M27) — 표에 든 경우는 scenarios에서 뺀다
    if calc.get("scenarios"): calc["scenarios"] = [sc for sc in calc["scenarios"] if not {r["amount"] for r in sc["rows"]} <= {c for r in o["analysis_table"]["rows"] for c in (r["cells"] if isinstance(r, dict) else r)}]
    return s


FULL = {lang: _blend(EX[lang], lang) for lang in ("en", "ko")}


def _codes(structure):
    _, _, errors, warnings = M.check(structure)
    return [x[1:4] for x in errors + warnings]


def _mut(fn, lang="en", base=None):
    s = copy.deepcopy(base or FULL[lang]); fn(s); return s


def _parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def _doc(structure, tmp_path, name="m"):
    r = M.build(structure, str(tmp_path), name)
    assert not r["errors"], r
    return r, _parts(r["path"])["word/document.xml"]


def _h1(doc):
    return [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p>.*?</w:p>", doc) if '<w:pStyle w:val="Heading1"/>' in p]


def _text(doc):
    return re.sub(r"<[^>]+>", "", doc)


# ── 블록이 없으면 기존 출력 그대로 ──
def _words(doc):
    """문서에 찍힌 글자만(문단 순서대로) — 서식이 바뀌어도 글은 같아야 한다."""
    return [t for t in (re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p>.*?</w:p>", doc)) if t]


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_without_blocks_the_file_is_unchanged(tmp_path, lang):
    r = M.build(EX[lang], str(tmp_path), f"fx_{lang}")
    assert r["ok"] and r["warnings"] == []
    doc = _parts(r["path"])["word/document.xml"]
    L = M.LABELS[lang]
    for label in (L["key_figures"], L["review"], L["action_list"], L["limitations"], L["authorities"], dict(L["head"])["basis"].upper(), dict(L["head"])["workings"].upper()):
        assert label not in _text(doc), label          # 선택 블록의 제목·머리 줄은 찍히지 않는다
    assert doc.count("<w:tbl>") == 6 and len(_h1(doc)) == 8          # 머리 표 + 계산 표 3 + 사실관계별 결과 + 위험 = 0.16.0의 표 5개에 머리 표 하나
    # 기존 구조에 든 글은 하나도 빠지지 않는다(촘촘한 서식으로 바뀌었을 뿐)
    body = " ".join(_words(doc)).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    for where, text in M._texts(M.check(EX[lang])[1]):
        for piece in re.split(r"\[\^[^\]]+\]", M.plain(text) if "[^" not in text else text.replace("**", "")):
            assert piece.strip() in body, (where, piece)
    # 빈 블록을 넣어도 같다
    empty = dict(EX[lang], key_figures={}, review={}, action_list=[], limitations={}, authorities=[])
    assert _parts(M.build(empty, str(tmp_path), "empty")["path"]) == _parts(r["path"])


# ── 블록을 모두 넣은 구조는 경고 0건 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_all_blocks_pass_every_rule(tmp_path, lang):
    assert _codes(FULL[lang]) == []
    assert _codes(_blend(M.example(lang), lang)) == []          # 안내가 돌려주는 예시 + 선택 블록 예시도 그대로 통과
    g = M.guide(lang)
    assert g["optional_blocks"] == M.optional_blocks(lang) and len(g["checks"]) == len(M.RULES) == 48
    assert set(g["optional_blocks"]["example"]) == {"head", "workings_check", "key_figures", "analysis_table", "review", "action_list", "limitations", "authorities"}
    for key in ("key_figures", "review", "action_list", "limitations", "authorities"):
        assert key in g["schema"] and key in g["guide"], key
    for key in ("to", "basis", "workings"): assert key in g["schema"]["head"]
    for code in NEW_RULES: assert any(r.startswith(code) for r in M.RULES)


# ── 블록마다 문서에 표·절이 생긴다 ──
def test_head_lines(tmp_path):
    _, base = _doc(EX["en"], tmp_path, "base")
    _, doc = _doc(_mut(lambda s: s["head"].update(to="Made-up addressee", basis="Made-up file of 1 January 2000", workings="made_up.xlsx"), base=EX["en"]), tmp_path)
    text = _text(doc)
    for label, value in (("TO", "Made-up addressee"), ("BASIS", "Made-up file of 1 January 2000"), ("WORKINGS", "made_up.xlsx")):
        assert label in text and value in text
    assert "BASIS" not in _text(base) and "WORKINGS" not in _text(base)
    assert text.index("TO") < text.index("PREPARED BY") < text.index("SCOPE") < text.index("BASIS") < text.index("WORKINGS") < text.index("Executive summary")
    _, ko = _doc(_mut(lambda s: s["head"].update(to="지어낸 수신인", basis="지어낸 자료", workings="지어낸.xlsx"), base=EX["ko"]), tmp_path, "ko")
    for label in ("수신", "근거 자료", "계산 파일", "지어낸 수신인"): assert label in _text(ko)


def test_key_figures_table_under_short_answer(tmp_path):
    _, base = _doc(EX["en"], tmp_path, "base")
    kf = M.optional_blocks("en")["example"]["key_figures"]
    _, doc = _doc(_mut(lambda s: s.update(key_figures=kf), base=EX["en"]), tmp_path)
    assert doc.count("<w:tbl>") == base.count("<w:tbl>") + 1 and _h1(doc) == _h1(base)          # 절은 그대로, 표 하나가 늘어남
    text = _text(doc)
    a, b, c = text.index("2. Short answer"), text.index("A. No reduction"), text.index("3. Facts and assumptions")
    assert a < b < c
    assert "A. No reduction · recommended" in text and "B. Reduction granted · recommended" not in text
    tbl = re.findall(r"<w:tbl>.*?</w:tbl>", doc)[1]          # 0번은 머리 표
    assert "Total charge" in tbl and 'w:fill="E3EAF2"' in tbl and tbl.count("<w:tr>") == 4          # 머리 + 3행, 합계 행 음영
    assert tbl.count('<w:jc w:val="right"/>') == 8 and '<w:gridCol w:w="2300"/>' in tbl          # 숫자 열(머리 포함)은 오른쪽 맞춤
    total = [r for r in re.findall(r"<w:tr>.*?</w:tr>", tbl) if "Total charge" in r][0]
    assert total.count("<w:b/>") == 3
    assert "B applies only if an application is filed" in text[b:c] and "<w:i/>" in doc          # 표 아래 조건 주석


def test_table_inside_an_issue(tmp_path):
    _, base = _doc(EX["en"], tmp_path, "base")
    tb = M.optional_blocks("en")["example"]["analysis_table"]
    _, doc = _doc(_mut(lambda s: s["analysis"][3].update(table=tb), base=EX["en"]), tmp_path)
    assert doc.count("<w:tbl>") == base.count("<w:tbl>") + 1
    text = _text(doc)
    assert text.index("4.4 A reduction needs") < text.index("Charge with and without the reduction (KRW)") < text.index("4.5 No further charge")
    assert 'w:fill="E3EAF2"' not in doc          # 쟁점 안의 표 합계 행은 계산 표와 같은 음영


def test_review_section(tmp_path):
    _, base = _doc(EX["en"], tmp_path, "base")
    rv = M.optional_blocks("en")["example"]["review"]
    _, doc = _doc(_mut(lambda s: s.update(review=rv), base=EX["en"]), tmp_path)
    assert _h1(doc) == ["Executive summary", "1. Question presented", "2. Short answer", "3. Facts and assumptions", "4. Analysis",
                        "5. Review of the handling to date", "6. Calculation", "7. Risks and open points", "8. Recommended next steps"]
    text = _text(doc)
    assert text.count(rv["verdict"]) == 1          # 판정은 결론부에 한 번 — 검토 결과 절의 표 앞에서 되풀이하지 않는다
    assert text.index("2. Short answer") < text.index(rv["verdict"]) < text.index("Days counted from the notice") < text.index("3. Facts and assumptions")
    assert "Days counted from the notice, not from the bank record (Section 5)." in text          # 결론부에는 발견 사항 이름과 절 번호만
    assert text.count("KRW 1,000") == _text(base).count("KRW 1,000") + 1 and "KRW 1,000" not in text[text.index(rv["verdict"]):text.index("3. Facts and assumptions")]          # 금액·조치는 표에 한 번
    only = _text(_doc(_mut(lambda s: s.update(review={"verdict": rv["verdict"]}), base=EX["en"]), tmp_path, "only")[1])
    assert only.count(rv["verdict"]) == 2          # 발견 사항이 없으면 검토 결과 절에 판정을 적는다
    assert doc.count("<w:tbl>") == base.count("<w:tbl>") + 1
    tbl = [x for x in re.findall(r"<w:tbl>.*?</w:tbl>", doc) if "Severity" in x][0]
    for word in ("Severity", "Finding", "Amount", "Action", "LOW", "KRW 1,000", "Pay the one-day difference", "The earlier computation used 29 days."):
        assert word in _text(tbl), word
    assert 'w:fill="E4F2E7"' in tbl          # 위험도 색
    assert "see Section 7 —" in text and "see Section 6 —" not in text and "see Section 6 —" in _text(base)          # 위험 절 번호를 따라감


def test_action_list_table(tmp_path):
    _, base = _doc(EX["en"], tmp_path, "base")
    al = M.optional_blocks("en")["example"]["action_list"]
    s = _mut(lambda s: (s.pop("next_steps"), s.update(action_list=al)), base=EX["en"])
    r, doc = _doc(s, tmp_path)
    assert r["ok"] and _h1(doc)[-1] == "7. Action list" and "Recommended next steps" not in _text(doc)
    assert doc.count("<w:tbl>") == base.count("<w:tbl>") + 1
    tbl = re.findall(r"<w:tbl>.*?</w:tbl>", doc)[-1]
    assert [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<w:tc>.*?</w:tc>", re.findall(r"<w:tr>.*?</w:tr>", tbl)[0])] == ["#", "Action", "Owner", "By"]
    assert tbl.count("<w:tr>") == 3 and "[before the application period ends]" in _text(tbl)
    assert '<w:numId w:val="3"/>' not in doc          # 번호 목록(다음 단계)은 찍히지 않음


def test_limitations_and_authorities(tmp_path):
    o = M.optional_blocks("en")["example"]
    r, doc = _doc(_mut(lambda s: s.update(limitations=o["limitations"], authorities=o["authorities"]), base=EX["en"]), tmp_path)
    assert r["ok"] and _h1(doc)[-1] == "8. Limitations and unverified points"
    text = _text(doc)
    assert text.index("8. Limitations and unverified points") < text.index("was not confirmed.") < text.index("Principal authorities") < text.index("How this memo was prepared.")
    assert "Example Tax Act (예시세법), Arts. 10(1), 11(2) and 12(1)" in text
    assert r["footnotes"] == M.build(EX["en"], str(tmp_path), "b")["footnotes"]          # 한계 항목의 [^a12]는 이미 나온 출처 — 각주를 새로 만들지 않고 처음 번호를 다시 씀
    lim = [p for p in re.findall(r"<w:p>.*?</w:p>", doc) if "was not confirmed." in p][0]
    assert re.search(r'<w:rStyle w:val="FootnoteReference"/></w:rPr><w:t>\d+</w:t>', lim)
    # 문자열·목록도 받는다
    for v in ("One plain paragraph of limits.", ["First limit.", "Second limit."]):
        assert "Limitations and unverified points" in _text(_doc(_mut(lambda s: s.update(limitations=v), base=EX["en"]), tmp_path, "v")[1])
    # 주요 근거는 기본으로 없다
    assert "Principal authorities" not in _text(_doc(EX["en"], tmp_path, "c")[1])


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_all_blocks_file(tmp_path, lang):
    r, doc = _doc(FULL[lang], tmp_path, f"full_{lang}")
    assert r["ok"] and doc.count("<w:tr>") == doc.count("<w:cantSplit/>") and doc.count("<w:tblHeader/>") + 1 == doc.count("<w:tbl>") == 9          # 머리 표 + 숫자 표·쟁점 안의 표·검토 결과·조치 목록 + 계산 2·사실관계별 결과·위험
    heads = (["Executive summary", "1. Question presented", "2. Short answer", "3. Facts and assumptions", "4. Analysis", "5. Review of the handling to date",
              "6. Calculation", "7. Risks and open points", "8. Action list", "9. Limitations and unverified points"] if lang == "en" else
             ["핵심 요약", "1. 쟁점", "2. 결론", "3. 사실관계와 전제", "4. 검토", "5. 기존 처리 검토 결과", "6. 계산", "7. 위험과 확인할 점", "8. 조치 목록", "9. 한계와 미확인 사항"])
    assert _h1(doc) == heads
    text = _text(doc)
    assert "[^" not in text and "**" not in text
    if lang == "ko":
        for word in ("수신", "근거 자료", "계산 파일", "가. 감면 없음 · 권고", "위험도", "발견 사항", "조치", "번호", "할 일", "담당", "기한", "주요 근거", "달라지면 7. 위험과 확인할 점"):
            assert word in text, word
    a = M.build(FULL[lang], str(tmp_path), "again")["path"]
    assert open(a, "rb").read() == open(r["path"], "rb").read()          # 같은 입력이면 같은 바이트


# ── 영문 메모 안의 한글: 새 블록의 모든 글자 조각에 동아시아 글꼴 ──
def test_korean_text_in_english_memo_keeps_east_asian_font(tmp_path):
    def add(s):
        s["head"]["basis"] = "Made-up ruling 예규 가나12345-678 and the Example Tax Act (예시세법)"
        s["key_figures"]["rows"].insert(0, ["Made-up basis (예시세법 제10조)", "—", "—"])
        s["review"]["findings"][0]["detail"] = "The earlier computation used 29 days (지어낸 예규 가나12345-678)."
        s["action_list"][0]["owner"] = "예시 담당"
        s["limitations"]["items"].append("The made-up ruling 가나12345-678 was read in summary only.")
        s["authorities"].append("지어낸 예규 가나12345-678")
    r = M.build(_mut(add), str(tmp_path), "han")
    parts = _parts(r["path"])
    doc = parts["word/document.xml"]
    assert r["ok"] and doc.count("가나12345-678") == 4 and "예시 담당" in doc
    for xml in (doc, parts["word/footnotes.xml"], parts["word/footer1.xml"]):
        runs = re.findall(r"<w:r>.*?</w:r>", xml)
        texts = [x for x in runs if "<w:t" in x and "FootnoteReference" not in x]
        assert texts and all('w:eastAsia="Malgun Gothic"' in x for x in texts)          # 글자가 든 조각은 모두 한글 글꼴 지정
        for x in texts:
            if re.search(r"[가-힣]", re.sub(r"<[^>]+>", "", x)): assert 'w:eastAsia="Malgun Gothic"' in x
    assert 'w:eastAsia="Malgun Gothic"' in parts["word/numbering.xml"] and "맑은 고딕" in parts["word/fontTable.xml"]
    assert 'w:eastAsia="ko-KR"' in parts["word/styles.xml"] and 'w:eastAsia="ko-KR"' in parts["word/settings.xml"]


# ── 새 점검 규칙: 걸리는 쪽 ──
PAST_Q = "Is a late-payment charge due on the tax paid 30 days late, and have we handled the earlier payments correctly so far?"
FAIL = [
    ("M24", lambda s: s["key_figures"]["rows"][0].pop()),
    ("M24", lambda s: s["key_figures"].update(columns=["Item"])),
    ("M24", lambda s: s["key_figures"]["rows"].__setitem__(1, {"cells": ["Daily charge", "30,000", "30,000"], "role": "subtotal"})),
    ("M24", lambda s: (s["key_figures"]["columns"].extend(["C", "D"]), [r.extend(["—", "—"]) if isinstance(r, list) else r["cells"].extend(["—", "—"]) for r in s["key_figures"]["rows"]])),
    ("M24", lambda s: next(a for a in s["analysis"] if a.get("table"))["table"]["rows"][0].append("extra")),
    ("M25", lambda s: s["review"].update(verdict="")),
    ("M25", lambda s: s["review"].update(verdict="The charge was computed correctly. Only the day count was off.")),
    ("M25", lambda s: s["review"]["findings"][0].update(amount="")),
    ("M25", lambda s: s["review"]["findings"][0].update(action="")),
    ("M25", lambda s: s["review"]["findings"][0].update(severity="CRITICAL")),
    ("T09", lambda s: (s.pop("review"), s.update(question=PAST_Q))),
    ("T09", lambda s: (s.pop("review"), s["head"].update(re="Made-up memo on a late-payment charge and review of past filings"))),
    ("T10", lambda s: s["key_figures"]["rows"][0].__setitem__(2, "155,000")),
    ("T10", lambda s: s["key_figures"]["rows"].insert(0, ["Made-up extra", "777,000", "888,000"])),
    ("T11", lambda s: s["action_list"][1].update(deadline="")),
    ("T11", lambda s: s["action_list"].append({"action": "Pay the charge together with the tax.", "owner": "Example owner"})),
    ("T12", lambda s: s["key_figures"].pop("recommended")),
    ("T12", lambda s: s["key_figures"].update(recommended="Scenario A")),
    ("T12", lambda s: s["key_figures"].update(note="")),
    ("T13", lambda s: (s.pop("limitations"), s["analysis"][0].update(confirm="Whether the made-up court still follows this was not verified."))),
    ("T13", lambda s: (s.pop("limitations"), s["footnotes"][0].update(text=s["footnotes"][0]["text"] + " The made-up paragraph numbering was not verified."))),
    ("T13", lambda s: s["footnotes"][0].update(text=s["footnotes"][0]["text"] + " The made-up paragraph numbering was not verified.")),          # 한계 절은 있는데 그 각주를 가리키지 않음
    ("M17", lambda s: s.update(next_steps=["Pay the charge."])),          # 조치 목록 표와 다음 단계를 함께 넣음
]


@pytest.mark.parametrize("code,fn", FAIL, ids=[f"{c}-{i}" for i, (c, _) in enumerate(FAIL)])
def test_new_rule_fails_when_broken(code, fn):
    codes = _codes(_mut(fn))
    assert code in codes and set(codes) <= {code}, codes          # 그 규칙만 걸린다


def test_every_new_rule_has_a_failing_case():
    assert set(NEW_RULES) <= {c for c, _ in FAIL}


KO_FAIL = [
    ("M25", lambda s: s["review"]["findings"][0].update(severity="LOW")),
    ("T09", lambda s: (s.pop("review"), s.update(question="지연 가산금을 내야 하는가, 그리고 지금까지 낸 가산금은 맞게 계산되었는가?"))),
    ("T10", lambda s: s["key_figures"]["rows"][0].__setitem__(2, "155,000")),
    ("T11", lambda s: s["action_list"][0].update(deadline="")),
    ("T12", lambda s: s["key_figures"].update(recommended="")),
    ("T13", lambda s: (s.pop("limitations"), s["risks"][0].update(check="납부일이 찍힌 은행 기록은 확인하지 못하였다."))),
]


@pytest.mark.parametrize("code,fn", KO_FAIL, ids=[f"ko-{c}-{i}" for i, (c, _) in enumerate(KO_FAIL)])
def test_new_rules_korean(code, fn):
    w = M.check(_mut(fn, "ko"))[3]
    assert [x[1:4] for x in w] and {x[1:4] for x in w} == {code}, w
    assert all(re.search(r"[가-힣]", x) for x in w)


# ── 새 점검 규칙: 통과하는 쪽 ──
def test_new_rules_pass_side():
    # T09: 과거 처리를 묻는 질문 + 검토 결과 절(문제가 없으면 판정만) → 통과. 앞으로의 처리만 묻는 질문은 검토 결과 절 없이 통과
    assert _codes(_mut(lambda s: s.update(question=PAST_Q))) == []
    assert _codes(_mut(lambda s: (s.update(question=PAST_Q), s.update(review={"verdict": "The charge paid earlier was computed correctly."})))) == []
    assert "T09" not in _codes(EX["en"]) and not M._PAST["en"].search(EX["en"]["question"]) and not M._PAST["ko"].search(EX["ko"]["question"])
    for q in ("How much should we withhold on the next payment?", "Is the reduction available if we apply correctly next month?"):
        assert not M._PAST["en"].search(q), q
    for q in ("Have we handled it correctly so far?", "Was the tax withheld correctly on prior payments?", "Did we file the returns on time to date?"):
        assert M._PAST["en"].search(q), q
    for q in ("다음 지급분에서 얼마를 원천징수해야 하는가?",): assert not M._PAST["ko"].search(q)
    for q in ("그동안 원천징수를 제대로 했는가?", "지금까지의 처리가 맞았는지 검토", "기존 처리가 적정했는지"): assert M._PAST["ko"].search(q), q
    # T10: 숫자 표의 금액이 계산 표의 다른 경우·쟁점 안의 표·검토 결과 가운데 한 곳에만 있어도 통과
    assert _codes(_mut(lambda s: (next(a for a in s["analysis"] if a.get("table")).pop("table"), s["calculation"].update(scenarios=copy.deepcopy(EX["en"]["calculation"]["scenarios"]))))) == []          # 계산 표의 경우(scenarios)에 있음
    def only_in_issue_table(s):          # 계산 표에는 없고 쟁점 안의 표에만 있는 금액
        s["key_figures"]["rows"].insert(0, ["Half-month charge", "15,000", "15,000"])
        next(a for a in s["analysis"] if a.get("table"))["table"]["rows"].insert(0, ["Half-month charge", "15,000", "15,000"])
    assert _codes(_mut(only_in_issue_table)) == []
    def only_in_issue_text(s):          # 쟁점의 적용 문단에만 있는 금액
        s["key_figures"]["rows"].insert(0, ["Half-month charge", "15,000", "15,000"])
        s["analysis"][2]["application"] += " For 15 days the daily charge would be KRW 15,000."
    assert _codes(_mut(only_in_issue_text)) == []
    # T11: 날짜가 아닌 시점도 기한
    assert _codes(_mut(lambda s: s["action_list"][0].update(deadline="before payment"))) == []
    # T12: 경우가 하나면 권고·조건을 요구하지 않음
    one = lambda s: s["key_figures"].update(columns=["Item", "Amount"], rows=[["Fixed charge", "300,000"], {"cells": ["Total charge", "330,000"], "role": "total"}], recommended="", note="")
    assert _codes(_mut(one)) == []
    # T13: 미확인 표시가 없으면 한계 절 없이 통과, 미확인 각주를 한계 절에서 [^id]로 가리키면 통과
    assert _codes(_mut(lambda s: s.pop("limitations"))) == []
    assert not M._UNVERIFIED.search("No application, or beneficial owner not confirmed") and M._UNVERIFIED.search("The date was not confirmed.")          # 사실관계 표현은 미확인 표시가 아님
    def cited(s):
        s["footnotes"][0]["text"] += " The made-up paragraph numbering was not verified."
        s["limitations"]["items"].append("The paragraph numbering of the made-up act was not verified.[^a10]")
    assert _codes(_mut(cited)) == []
    # 기존 구조(블록 없음)는 새 규칙에 걸리지 않음
    for lang in ("en", "ko"): assert _codes(EX[lang]) == [] and _codes(M.example(lang)) == []


def test_new_fields_get_the_existing_checks(tmp_path):
    # 새 칸의 [^id]도 각주 정의가 있어야 하고(E03), 새 칸에서 쓴 각주는 쓰인 것으로 센다(M20)
    r = M.build(_mut(lambda s: s["limitations"]["items"].append("Unknown source.[^nope]")), str(tmp_path))
    assert r["path"] == "" and any(x.startswith("[E03] limitations.items[1]") for x in r["errors"])
    def only_here(s):
        s["footnotes"].append({"id": "z9", "text": "Example Tax Act, Art. 99 — made-up provision."}); s["key_figures"]["note"] += "[^z9]"
    assert _codes(_mut(only_here)) == []
    assert "E01" in _codes(_mut(lambda s: s.update(review="fine", key_figures=[1])))
    assert "M22" in _codes(_mut(lambda s: s["review"]["findings"][0].update(detail="It should be noted that the day count was off.")))
    assert "M23" not in _codes(FULL["en"])


# ── 쓰이게 만들기: 도구 설명·서버 안내문·요건 안내의 다음 도구·llms.txt ──
def _call(name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


def test_descriptions_say_finished_docx_first():
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert len(tools) == 52
    g, b = tools["tax_memo_guide"].description, tools["build_tax_memo"].description
    assert g.startswith("Start here whenever the user wants a tax memo, opinion, review note or report as a Word file")
    assert b.startswith("Produces a finished Word (.docx) tax memo file — use this instead of writing your own docx script")
    for d in (g, b):
        first = d.split("\n")[0]
        assert "finished Word (.docx) tax memo file" in first and "docx script" in first and "path" in first and "output_dir" in first
        assert "tax_memo_guide" in first
        for word in ("memo", "Word", "docx", "report", "메모", "보고서"): assert word in d, word
    assert "~/korean-tax-mcp" in b.split("\n")[0]
    ins = mcp.instructions
    assert "요건 안내 도구(_guide) → 계산(korean-tax-calc-mcp) → tax_memo_guide → build_tax_memo" in ins and "docx를 직접 만들거나" in ins
    assert "requirement guide (*_guide) → calculators (korean-tax-calc-mcp) → tax_memo_guide → build_tax_memo" in ins and "do not build the docx yourself" in ins
    assert "finished .docx" in M.guide("en")["next"] and "Do not write the docx yourself" in M.guide("en")["next"]


def test_every_requirement_guide_points_to_the_memo_tools():
    names = [t.name for t in asyncio.run(mcp.list_tools()) if t.name.endswith("_guide") and t.name != "tax_memo_guide"]
    assert len(names) == 19
    offline = [n for n in names if n != "transfer_pricing_guide"]          # 필수 인자가 없는 요건 안내는 인자 없이 불러 본다(외부 호출 없음)
    for n in offline:
        r = _call(n, {})
        assert "error" not in r, n
        assert r[S.NEXT_KEY][-1] == S.MEMO_NEXT["ko"], n
    en = _call("tax_crime_guide", {"lang": "en"})
    assert S.MEMO_NEXT["en"] in json.dumps(en, ensure_ascii=False)
    for line in S.MEMO_NEXT.values():
        assert "tax_memo_guide → build_tax_memo" in line and ".docx" in line
    # 이미 '다음에 부를 도구'가 있으면 그 뒤에 붙이고 원본은 바꾸지 않는다. 오류 결과·요건 안내가 아닌 도구는 그대로
    src = {S.NEXT_KEY: ["first"]}
    out = S._memo_next("x_guide", src, "ko")
    assert out[S.NEXT_KEY] == ["first", S.MEMO_NEXT["ko"]] and src == {S.NEXT_KEY: ["first"]}
    assert S._memo_next("x_guide", {S.NEXT_KEY: "one line"}, "en")[S.NEXT_KEY] == ["one line", S.MEMO_NEXT["en"]]
    assert S._memo_next("x_guide", {"error": "e"}, "ko") == {"error": "e"} and S._memo_next("law_article", {"a": 1}, "ko") == {"a": 1}
    assert S.NEXT_KEY not in _call("tax_memo_guide", {})


def test_llms_txt_lists_the_search_words():
    row = [x for x in (ROOT / "llms.txt").read_text("utf-8").splitlines() if "`build_tax_memo`" in x and x.startswith("|")]
    assert len(row) == 1
    for word in ("memo", "Word", "docx", "report", "메모", "보고서", "tax_memo_guide"): assert word in row[0], word


def test_guide_and_examples_carry_no_real_case():
    banned = ("royalt", "사용료", "2021두59908", "Halden", "withholding", "원천징수")
    for lang in ("en", "ko"):
        text = json.dumps(M.optional_blocks(lang), ensure_ascii=False)
        for word in banned: assert word.lower() not in text.lower(), word
        assert "made-up" in text or "지어낸" in text
