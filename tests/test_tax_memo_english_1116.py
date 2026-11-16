"""영문 메모에 넣는 Word 교정 언어(en-US·en-GB) — english 입력, 메모 글에 쓰인 철자로 판단, 섞임 경고(M28)."""
import json
import zipfile

import pytest

from korean_tax_mcp import tax_memo as M


def _example():
    return M.example("en")


def _swap(obj, old, new):
    return json.loads(json.dumps(obj).replace(old, new))


def _docx_langs(path):
    with zipfile.ZipFile(path) as z:
        return z.read("word/styles.xml").decode(), z.read("word/settings.xml").decode()


def test_default_is_us_when_no_signal(tmp_path):
    s = {**_example(), "background": "The company pays a fee to its parent each quarter."}
    v, basis, gb, us = M.english_variant({"background": s["background"]})
    assert (v, basis, gb, us) == ("en-US", "default", 0, 0)
    out = M.build(s, str(tmp_path))
    assert out["english"]["proofing_language"] in ("en-US", "en-GB")   # 예시 본문의 철자에 따라 정해짐
    assert set(out["english"]) == {"proofing_language", "basis", "british_words", "american_words"}


def test_given_gb_sets_proofing_language(tmp_path):
    out = M.build(_example(), str(tmp_path), english="GB")
    assert out["english"]["proofing_language"] == "en-GB" and out["english"]["basis"] == "given"
    styles, settings = _docx_langs(out["path"])
    assert 'w:lang w:val="en-GB" w:eastAsia="ko-KR"' in styles
    assert 'w:themeFontLang w:val="en-GB"' in settings and "__LANG__" not in settings


def test_given_us_and_structure_field(tmp_path):
    s = {**_example(), "english": "US"}
    out = M.build(s, str(tmp_path))
    assert out["english"]["proofing_language"] == "en-US" and out["english"]["basis"] == "given"
    # 도구 인자가 structure.english보다 앞선다
    out = M.build(s, str(tmp_path), english="GB")
    assert out["english"]["proofing_language"] == "en-GB"


def test_detects_british_spelling(tmp_path):
    s = _example()
    s["background"] = (s.get("background") or "") + " The licence was authorised by the head office and the programme was organised in the Seoul centre."
    v, basis, gb, us = M.english_variant(s)
    assert (v, basis) == ("en-GB", "detected") and gb >= 5 and gb > us
    out = M.build(s, str(tmp_path))
    assert out["english"]["proofing_language"] == "en-GB"
    assert 'w:val="en-GB"' in _docx_langs(out["path"])[0]


def test_detects_american_spelling():
    s = {"background": "The payment was authorized and recognized; the parties organized the program and finalized the analysis. It was labeled and canceled."}
    v, basis, gb, us = M.english_variant(s)
    assert (v, basis) == ("en-US", "detected") and us >= 5 and gb == 0


def test_shared_and_official_names_are_not_counted():
    # license(영국식 동사)·program·practice, 공식 영문 이름의 Labor·Center는 어느 쪽으로도 세지 않는다
    s = {"background": "The license agreement, the Labor Standards Act, the National Tax Service Call Center, the program and the practice."}
    assert M.english_variant(s) == ("en-US", "default", 0, 0)


def test_mixed_spelling_warns_m28():
    s = _example()
    s["background"] = (s.get("background") or "") + (" The licence was authorised and organised in the centre; the favourable programme was recognised."
                                                    " The payment was authorized, finalized, summarized and analyzed; it was labeled.")
    _, _, _, warnings = M.check(s)
    assert any(w.startswith("[M28]") for w in warnings)


def test_one_stray_word_does_not_warn():
    s = _example()
    s["background"] = (s.get("background") or "") + " The licence was authorised and organised in the centre; the programme was recognised. It was finalized."
    _, _, _, warnings = M.check(s)
    assert not any(w.startswith("[M28]") for w in warnings)


def test_bad_value_is_an_error():
    with pytest.raises(ValueError):
        M.english_variant(_example(), "AU")


def test_korean_memo_keeps_default(tmp_path):
    out = M.build(M.example("ko"), str(tmp_path))
    assert "english" not in out
    styles, settings = _docx_langs(out["path"])
    assert 'w:lang w:val="en-US" w:eastAsia="ko-KR"' in styles and 'w:themeFontLang w:val="en-US"' in settings
