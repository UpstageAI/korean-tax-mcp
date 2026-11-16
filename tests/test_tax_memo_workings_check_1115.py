"""세무 메모에 적는 엑셀 대조 결과 블록(workings_check)과 점검 규칙 T14~T18, '작성 방법' 문단의 한 줄. 작성 Mia(윤승미)

함께 가는 엑셀(head.workings)의 금액을 계산 도구와 대조했는지 묻는 규칙이다. 이 서버는 엑셀을 열지 않는다 — 호출자가 적은 결과를 구조로 받고,
빠졌으면 알릴 뿐이다. 규칙마다 걸리는 쪽과 통과하는 쪽, 출력 문장(영문·국문, 세 method), head.workings가 없는 기존 입력의 무변화를 넣는다.
자료는 지어낸 사례(tests/fixtures/tax_memo_fixture_*.json)와 지어낸 파일 이름·수. 외부 호출 없음.
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

EX = {lang: json.loads((Path(__file__).parent / "fixtures" / f"tax_memo_fixture_{lang}.json").read_text("utf-8")) for lang in ("en", "ko")}
FILE = {"en": "Made_Up_Charge_Workings.xlsx", "ko": "지어낸_가산금_계산.xlsx"}
NEW = ("T14", "T15", "T16", "T17", "T18")
LIM = {"en": {"items": ["Two workbook amounts (the day count and the rounding row) were not checked against the calculation tools."]},
       "ko": {"items": ["통합 문서의 금액 2개(일수와 끝수 처리 행)는 계산 도구와 대조하지 않았다."]}}
NOTE = {"en": "The day count and the rounding row were typed in by hand", "ko": "일수와 끝수 처리 행은 손으로 옮긴 값이다"}


def _with(lang="en", wc=None, workings=True, **top):
    s = copy.deepcopy(EX[lang])
    if workings: s["head"]["workings"] = FILE[lang]
    if wc is not None: s["workings_check"] = wc
    s.update(top)
    return s


def _warn(structure):
    _, _, errors, warnings = M.check(structure)
    assert not errors, errors
    return warnings


def _codes(structure):
    return [x[1:4] for x in _warn(structure)]


def _text(structure, tmp_path, name="m"):
    """만든 파일의 문단 글(태그를 뗀 것)."""
    r = M.build(structure, str(tmp_path), name)
    assert not r["errors"], r
    with zipfile.ZipFile(r["path"]) as z: doc = z.read("word/document.xml").decode("utf-8")
    return [re.sub(r"<[^>]+>", "", p).replace("&amp;", "&") for p in re.findall(r"<w:p>.*?</w:p>", doc)]


def _how(structure, tmp_path, name="m"):
    label = M.LABELS[M.resolve_lang(structure)]["how"]
    return next(p for p in _text(structure, tmp_path, name) if p.startswith(label))


def _call(name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args)).content[0].text)


# ── head.workings가 없는 기존 입력은 그대로 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_no_workings_no_change(lang, tmp_path):
    assert _warn(EX[lang]) == []
    _, s, _, _ = M.check(EX[lang])
    assert s["workings_check"] is None and M.workings_line(s) == ""
    assert _how(EX[lang], tmp_path) == M.LABELS[lang]["how"] + " " + EX[lang]["prepared_how"]          # 맺음 문단에 덧붙는 글 없음
    a = M.build(EX[lang], str(tmp_path), "a"); b = M.build({**EX[lang], "workings_check": {}}, str(tmp_path), "b")
    assert Path(a["path"]).read_bytes() == Path(b["path"]).read_bytes() and b["ok"]          # 빈 블록은 없는 것과 같다


# ── T14: 엑셀을 함께 내는데 대조 결과가 없음 ──
def test_t14_real_flow_check_only_names_verify_workbook():
    """실제 사용 흐름: head.workings만 준 구조로 check_only → 경고가 verify_workbook을 지금 실행하라고 말한다."""
    en = _call("build_tax_memo", {"structure": _with("en"), "check_only": True})
    assert en["ok"] is False and en["path"] == "" and not en["errors"]
    w = [x for x in en["warnings"] if x.startswith("[T14]")]
    assert len(w) == 1 and len(en["warnings"]) == 1
    for word in ("verify_workbook", "export_workbook", "korean-tax-calc-mcp", "on the saved file now", "typed in by hand do not count as a check", "method='none'"):
        assert word in w[0], word
    assert w[0].index("Run verify_workbook (korean-tax-calc-mcp) on the saved file now") < w[0].index("If the file is a statutory form made with export_workbook, set method='export_workbook'")          # 대조가 먼저, 법정서식은 그다음
    assert "If the workbook was made with export_workbook" not in w[0] and "If you built it yourself" not in w[0]
    ko = _call("build_tax_memo", {"structure": _with("ko"), "check_only": True})
    w = [x for x in ko["warnings"] if x.startswith("[T14]")]
    assert len(w) == 1 and len(ko["warnings"]) == 1
    for word in ("verify_workbook을 지금 실행", "export_workbook", "요약의 대조·일치·불일치·대조_안_한_금액", "손으로 옮겨 적은 숫자와 비교한 칸은 대조로 치지 않는다"):
        assert word in w[0], word
    assert w[0].index("저장한 파일에 korean-tax-calc-mcp의 verify_workbook을 지금 실행하고") < w[0].index("법정서식을 export_workbook으로 만든 파일이면 method='export_workbook'")
    assert "으로 만들었으면" not in w[0] and "직접 짰으면" not in w[0]
    # 경고대로 결과를 옮겨 적으면 경고 0
    fixed = _call("build_tax_memo", {"structure": _with("en", {"method": "verify_workbook", "checked": 9, "mismatched": 0, "unchecked": 0, "file": "Made_Up_checked.xlsx"}), "check_only": True})
    assert fixed["ok"] is True and fixed["warnings"] == []


@pytest.mark.parametrize("wc", [{"method": "export_workbook"}, {"method": "EXPORT_WORKBOOK"}, {"method": "verify_workbook", "checked": "9", "mismatched": 0, "unchecked": 0}])
def test_t14_passes_when_stated(wc):
    assert _codes(_with("en", wc)) == []


def test_t14_shape():
    assert _codes(_with("en", {"method": "checked by eye"})) == ["T14"]
    assert _codes(_with("en", {"method": "verify_workbook", "checked": 9, "mismatched": "a few"})) == ["T14"]
    assert _codes(_with("en", {"method": "verify_workbook", "checked": -1})) == ["T14"]
    r = M.build(_with("en", ["verify_workbook"]), check_only=True)          # 객체가 아니면 다른 블록처럼 E01
    assert any(x.startswith("[E01] workings_check") for x in r["errors"])
    assert M.RULES == M.guide("en")["checks"] and "workings_check" not in _warn(_with("en", {"method": "export_workbook"}, extra_key=1))[0].split("ignored:")[1]


# ── T15: 대조하지 않은 금액은 한계 절에 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_t15_unchecked_goes_to_limitations(lang):
    wc = {"method": "verify_workbook", "checked": 7, "mismatched": 0, "unchecked": 2, "unchecked_note": NOTE[lang]}
    w = _warn(_with(lang, wc))
    assert [x[1:4] for x in w] == ["T15"] and "unchecked_note" in w[0] and "limitations" in w[0]
    assert _codes(_with(lang, wc, limitations=LIM[lang])) == []
    # 한계 절이 있어도 엑셀 얘기가 없으면 걸린다
    other = {"items": ["The made-up notice date was read from a copy." if lang == "en" else "지어낸 통지일은 사본으로 읽었다."]}
    assert _codes(_with(lang, wc, limitations=other)) == ["T15"]
    # 대조하지 않은 금액이 무엇인지(unchecked_note)가 비면 걸린다
    assert _codes(_with(lang, {**wc, "unchecked_note": ""}, limitations=LIM[lang])) == ["T15"]
    assert _codes(_with(lang, {**wc, "unchecked": 0, "unchecked_note": ""})) == []


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_t15_method_none(lang):
    w = _warn(_with(lang, {"method": "none"}))
    assert [x[1:4] for x in w] == ["T15"] and "method='none'" in w[0]
    lim = {"text": "The workbook amounts were not checked against the calculation tools." if lang == "en" else "엑셀 계산 파일의 금액은 계산 도구와 대조하지 않았다."}
    assert _codes(_with(lang, {"method": "none"}, limitations=lim)) == []


# ── T16: 불일치가 남음 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_t16_mismatch(lang):
    w = _warn(_with(lang, {"method": "verify_workbook", "checked": 9, "mismatched": 2, "unchecked": 0}))
    assert [x[1:4] for x in w] == ["T16"] and "verify_workbook" in w[0] and "= 2" in w[0]
    assert ("다시 실행" in w[0]) if lang == "ko" else ("again" in w[0])
    assert _codes(_with(lang, {"method": "verify_workbook", "checked": 9, "mismatched": 0})) == []


# ── T17: verify_workbook인데 대조한 수가 없음 ──
@pytest.mark.parametrize("wc", [{"method": "verify_workbook"}, {"method": "verify_workbook", "checked": 0, "mismatched": 0}, {"method": "verify_workbook", "checked": None}])
def test_t17_no_count(wc):
    w = _warn(_with("en", wc))
    assert [x[1:4] for x in w] == ["T17"] and "run verify_workbook on the saved file" in w[0]
    assert "verify_workbook을 실행" in _warn(_with("ko", wc))[0]


def test_t17_not_for_export_workbook():
    assert _codes(_with("en", {"method": "export_workbook", "checked": 0})) == []


# ── T18: 전부 검증했다는 표현 ──
ALL_EN = ["All amounts match the calculator results.", "All of the amounts in the workbook were verified against the calculation tools.",
          "Every figure was checked against the tool output.", "All figures have been reconciled to the calculators."]
ALL_KO = ["모든 금액을 계산 도구와 대조했다.", "모든 금액이 계산기 결과와 일치한다.", "전체 금액을 검증하였다."]
NOT_ALL_EN = ["Not all amounts were checked against the calculators.", "Seven amounts were checked against the calculation tools.",
              "The amounts in section 5 were computed with the made-up calculator.", "All amounts are in KRW."]
NOT_ALL_KO = ["금액 7개를 계산 도구와 대조했다.", "모든 금액은 원 단위이다.", "5절의 금액은 지어낸 계산기로 구했다."]


@pytest.mark.parametrize("lang,phrase", [("en", x) for x in ALL_EN] + [("ko", x) for x in ALL_KO])
def test_t18_all_amounts_claim_with_unchecked(lang, phrase):
    wc = {"method": "verify_workbook", "checked": 7, "mismatched": 0, "unchecked": 2, "unchecked_note": NOTE[lang]}
    how = EX[lang]["prepared_how"] + " " + phrase
    w = _warn(_with(lang, wc, limitations=LIM[lang], prepared_how=how))
    assert [x[1:4] for x in w] == ["T18"] and w[0].startswith("[T18] prepared_how:")
    assert _codes(_with(lang, {"method": "none"}, limitations=LIM[lang], prepared_how=how)) == ["T18"]
    # 대조하지 않은 금액이 없으면 그 표현은 걸리지 않는다
    assert _codes(_with(lang, {"method": "verify_workbook", "checked": 9, "mismatched": 0, "unchecked": 0}, prepared_how=how)) == []
    assert _codes(_with(lang, {"method": "export_workbook"}, prepared_how=how)) == []
    assert _codes(_with(lang, workings=False, prepared_how=how)) == []          # 엑셀이 없는 메모는 보지 않는다


@pytest.mark.parametrize("lang,phrase", [("en", x) for x in NOT_ALL_EN] + [("ko", x) for x in NOT_ALL_KO])
def test_t18_narrow(lang, phrase):
    wc = {"method": "verify_workbook", "checked": 7, "mismatched": 0, "unchecked": 2, "unchecked_note": NOTE[lang]}
    assert _codes(_with(lang, wc, limitations=LIM[lang], prepared_how=EX[lang]["prepared_how"] + " " + phrase)) == []


def test_every_new_rule_is_listed_and_covered():
    for code in NEW: assert sum(r.startswith(code) for r in M.RULES) == 1
    assert len(M.RULES) == 48


def test_block_without_head_workings_is_still_checked():
    """블록을 적었으면 파일 이름이 없어도 그 내용은 본다(불일치·빠진 수). T14는 head.workings가 있을 때만."""
    assert _codes(_with("en", {"method": "verify_workbook", "checked": 9, "mismatched": 1}, workings=False)) == ["T16"]
    assert _codes(_with("en", {"method": "export_workbook"}, workings=False)) == []


# ── '작성 방법' 문단의 한 줄 ──
def test_line_verify_workbook(tmp_path):
    wc = {"method": "verify_workbook", "checked": 16, "mismatched": 0, "unchecked": 12, "unchecked_note": "sums and differences worked out in the workbook itself.", "file": "Made_Up_checked.xlsx"}
    lim = {"items": ["Twelve workbook amounts were not checked against the calculation tools."]}
    how = _how(_with("en", wc, limitations=lim), tmp_path)
    assert how == ("How this memo was prepared. " + EX["en"]["prepared_how"] + " Workings: 16 amounts in the workbook were checked against the calculation tools (0 mismatches); "
                   "12 were not checked — sums and differences worked out in the workbook itself. Copy with the check sheet: Made_Up_checked.xlsx.")
    ko = {"method": "verify_workbook", "checked": 16, "mismatched": 0, "unchecked": 12, "unchecked_note": "통합 문서 안에서 낸 합계와 차액이다.", "file": "지어낸_검산.xlsx"}
    how = _how(_with("ko", ko, limitations={"items": ["통합 문서의 금액 12개는 계산 도구와 대조하지 않았다."]}), tmp_path, "k")
    assert how == ("작성 방법. " + EX["ko"]["prepared_how"] + " 계산 파일: 통합 문서의 금액 16개를 계산 도구와 대조했다(불일치 0개). 12개는 대조하지 않았다 — 통합 문서 안에서 낸 합계와 차액이다. "
                   "검산 시트가 붙은 사본: 지어낸_검산.xlsx.")


def test_line_counts_only(tmp_path):
    _, s, _, _ = M.check(_with("en", {"method": "verify_workbook", "checked": 1, "mismatched": 1, "unchecked": 1, "unchecked_note": "the rounding row"}))
    assert M.workings_line(s) == "Workings: 1 amount in the workbook was checked against the calculation tools (1 mismatch); 1 was not checked — the rounding row."
    _, s, _, _ = M.check(_with("en", {"method": "verify_workbook", "checked": 9, "mismatched": 0, "unchecked": 0}))
    assert M.workings_line(s) == "Workings: 9 amounts in the workbook were checked against the calculation tools (0 mismatches)."
    _, s, _, _ = M.check(_with("ko", {"method": "verify_workbook", "checked": 9, "mismatched": 0}))
    assert M.workings_line(s) == "계산 파일: 통합 문서의 금액 9개를 계산 도구와 대조했다(불일치 0개)."
    _, s, _, _ = M.check(_with("en", {"method": "verify_workbook"}))          # 수를 적지 않았으면 수를 지어내지 않는다
    assert M.workings_line(s) == "Workings: the workbook was checked with verify_workbook; the number of amounts checked was not recorded."
    _, s, _, _ = M.check(_with("en", {"method": "by eye", "checked": 3}))          # 정해진 method가 아니면 찍지 않는다
    assert M.workings_line(s) == ""


@pytest.mark.parametrize("lang,want", [("en", "Workings were produced by the calculation tools (export_workbook)."), ("ko", "계산 파일은 계산 도구로 만들었다(export_workbook).")])
def test_line_export_workbook(lang, want, tmp_path):
    assert _how(_with(lang, {"method": "export_workbook"}), tmp_path) == M.LABELS[lang]["how"] + " " + EX[lang]["prepared_how"] + " " + want


@pytest.mark.parametrize("lang,want", [("en", "The workbook amounts were not checked against the calculation tools."), ("ko", "통합 문서의 금액은 계산 도구와 대조하지 않았다.")])
def test_line_none(lang, want, tmp_path):
    lim = {"text": "The workbook amounts were not checked against the calculation tools." if lang == "en" else "엑셀 계산 파일의 금액은 계산 도구와 대조하지 않았다."}
    s = _with(lang, {"method": "none"}, limitations=lim)
    assert _how(s, tmp_path) == M.LABELS[lang]["how"] + " " + EX[lang]["prepared_how"] + " " + want
    assert M.build(s, str(tmp_path), "n")["ok"]


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_line_is_not_counted_in_the_length_estimate(lang, tmp_path):
    """대조 결과를 적었다는 이유로 분량 경고(M26)가 붙지 않는다 — 블록이 더하는 문장은 분량 어림에서 뺀다."""
    long = {"method": "verify_workbook", "checked": 16, "mismatched": 0, "unchecked": 12, "unchecked_note": NOTE[lang] + ", " + ", ".join([NOTE[lang]] * 6), "file": FILE[lang]}
    plain = M.build(_with(lang, limitations=LIM[lang]), check_only=True)          # 블록 없는 판(T14만 붙음)
    for wc in (long, {"method": "export_workbook"}, {"method": "none"}):
        r = M.build(_with(lang, wc, limitations=LIM[lang]), check_only=True)
        assert r["length"] == plain["length"], wc["method"]
        assert r["warnings"] == [] and [x[1:4] for x in plain["warnings"]] == ["T14"]
    # 목표 쪽수에 바짝 붙은 메모: 블록을 넣어도 어림값이 같고 M26이 새로 붙지 않는다
    est = plain["length"]["estimated_pages"]
    near = _with(lang, long, limitations=LIM[lang], target_pages=1)
    base = _with(lang, limitations=LIM[lang], target_pages=1)
    a = M.build(near, check_only=True); b = M.build(base, check_only=True)
    assert a["length"]["estimated_pages"] == b["length"]["estimated_pages"] == est
    assert len(a["warnings"]) == len(b["warnings"]) - 1 and sum(x.startswith("[M26]") for x in a["warnings"]) == sum(x.startswith("[M26]") for x in b["warnings"])
    assert M.workings_line(M.check(near)[1]) in _how(near, tmp_path)          # 문장은 그대로 찍힌다
    # 작성 방법 글 없이 블록만 있으면 그 문단은 어림에 들지 않는다
    only = M.build(_with(lang, long, limitations=LIM[lang], prepared_how=""), check_only=True)
    assert "prepared_how" not in only["length"]["blocks"]


# ── 안내 ──
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_guide_describes_the_block_and_the_order(lang):
    g = M.guide(lang)
    for word in ("export_workbook", "verify_workbook", "none", "checked", "mismatched", "unchecked", "unchecked_note", "file"): assert word in g["schema"]["workings_check"], word
    text = g["guide"]
    assert "workings_check" in text and "verify_workbook" in text and "export_workbook" in text
    assert ("finish and check the Excel before you write the memo" in text) if lang == "en" else ("메모를 쓰기 전에 엑셀을 먼저 끝내고 대조한다" in text)
    assert text.index("verify_workbook") < text.index("build_tax_memo(structure)")          # 엑셀 대조가 메모 만들기보다 먼저
    assert text.index("verify_workbook") < text.index("export_workbook")          # 직접 짜고 대조하는 길이 먼저, 법정서식(export_workbook)은 그다음
    assert ("build the workings workbook yourself" in text and "only when a statutory form" in text) if lang == "en" else ("계산 근거 통합 문서는 직접 짜고" in text and "법정서식(별지 서식) 엑셀이 필요하면 export_workbook" in text)
    for old in ("make it with export_workbook", "the calculation server made the workbook", "export_workbook(korean-tax-calc-mcp)으로 만들거나", "계산 서버가 만든 통합 문서"): assert old not in json.dumps(g, ensure_ascii=False), old
    assert g["schema"]["workings_check"].index("verify_workbook") < g["schema"]["workings_check"].index("export_workbook")
    assert g["optional_blocks"]["when"]["workings_check"].index("verify_workbook") < g["optional_blocks"]["when"]["workings_check"].index("export_workbook")
    ob = g["optional_blocks"]
    assert "workings_check" in ob["when"] and ob["example"]["workings_check"]["method"] in M.WORKINGS_METHODS
    assert sum(any(r.startswith(c) for r in g["checks"]) for c in NEW) == 5
    # 예시는 지어낸 값·무관한 주제 — 시연 사례의 낱말이 없다
    blob = json.dumps(g, ensure_ascii=False).lower()
    for word in ("royalt", "사용료", "halden", "withholding"): assert word not in blob, word


def test_guide_example_block_passes():
    for lang in ("en", "ko"):
        o = M.optional_blocks(lang)["example"]
        s = _with(lang, o["workings_check"]); s["head"]["workings"] = o["head"]["workings"]
        assert _warn(s) == []


def test_server_text_points_to_the_check():
    ins = mcp.instructions
    assert "계산 근거 통합 문서는 직접 짜고(구성 자유, 읽는 사람의 질문 단위로 필요한 줄만)" in ins and "verify_workbook으로 금액 칸을 대조한 결과를 메모 구조(workings_check)에 적는다. 법정서식(별지 서식) 엑셀이 필요하면 export_workbook." in ins
    assert "build the workings workbook yourself" in ins and "run verify_workbook (korean-tax-calc-mcp) on the saved file" in ins and "Use export_workbook only when a statutory form" in ins
    assert "export_workbook으로 만들거나" not in ins and "make it with export_workbook" not in ins
    for line in S.MEMO_NEXT.values():
        assert "export_workbook" in line and "verify_workbook" in line and "workings_check" in line
        assert line.index("verify_workbook") < line.index("export_workbook")          # 직접 짜고 대조가 먼저
    r = _call("tax_crime_guide", {})          # 요건 안내 도구의 꼬리(공통 래퍼)
    assert r[S.NEXT_KEY][-1] == S.MEMO_NEXT["ko"]
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for name in ("tax_memo_guide", "build_tax_memo"):
        d = tools[name].description
        assert "workings_check" in d and "verify_workbook" in d and d.index("verify_workbook") < d.index("export_workbook")
