"""행정규칙(고시) 연혁 조회 — as_of에 시행 중이던 판을 고른다(Claude 작성 2026-11-11). 네트워크 없음(law._get 대체).
응답 모양은 법제처 DRF target=admrul 실제 응답을 본뜸: lawSearch nw=1(현행)·nw=2(연혁), 연혁본 조문내용은 조 단위 문자열 목록, 부칙은 누적 목록."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from korean_tax_mcp import admrul, law, server

NAME = "외국환거래규정"
def _row(seq, issued, ef, no, cur, name=NAME):
    return {"행정규칙일련번호": seq, "행정규칙명": name, "행정규칙종류": "고시", "발령일자": issued, "시행일자": ef, "발령번호": no,
            "소관부처명": "재정경제부", "현행연혁구분": cur}
CUR = _row("300", "20261030", "20261102", "2026-110", "현행")
OLD = [_row("200", "20191008", "20191008", "2019-20", "연혁"), _row("100", "20161005", "20161005", "2016-26", "연혁"),
       _row("999", "20180101", "20180101", "2018-1", "연혁", name="외국환거래규정 시행세칙")]
BODY = {
    "100": {"조문내용": ["    제9장 자본거래", "제9-5조(해외직접투자의 신고 등) ① 누적 투자금액이 미화 50만불 이내에서의 투자의 경우에는 1개월 이내에 사후보고할 수 있다.",
                      "② 이어지는 항.", "제9-6조(사후관리) ① 내용."],
            "부칙": {"부칙공포일자": ["20020702", "20161005"], "부칙내용": ["부칙 <제2002-12호>옛 부칙", "부칙 <제2016-26호,2016. 10. 5.>이 규정은 2016년 10월 5일부터 시행한다."]}},
    "200": {"조문내용": ["제9-5조(해외직접투자의 신고 등) ① 2019년 판 본문.", "제9-6조(사후관리) ① 내용."],
            "부칙": {"부칙내용": ["부칙 <제2019-20호,2019. 10. 8.>제1조(시행일) 이 규정은 2019년 10월 8일부터 시행한다."]}},
    "300": {"조문내용": "제9-5조(해외직접투자의 신고 등)① 현행 본문. 3개월 이내에 사후보고를 할 수 있다.제9-6조(사후관리)① 내용.", "부칙": {"부칙내용": ["부칙 현행"]}},
}

def _fake_get(path, query):
    if path == "lawSearch.do" and "target=admrul" in query:
        rows = [CUR] if "nw=1" in query or "nw=" not in query else (OLD if "page=1" in query else [])
        return {"AdmRulSearch": {"totalCnt": str(len(rows)), "admrul": rows}}
    if path == "lawService.do" and "target=admrul" in query:
        seq = query.split("ID=")[1].split("&")[0]
        row = next(r for r in [CUR] + OLD if r["행정규칙일련번호"] == seq)
        return {"AdmRulService": {"행정규칙기본정보": {"행정규칙명": NAME, "행정규칙종류": "고시", "시행일자": row["시행일자"], "발령일자": row["발령일자"],
                                                 "발령번호": row["발령번호"], "소관부처명": "재정경제부"}, **BODY[seq]}}
    if "target=eflaw" in query or "target=elaw" in query or "target=law" in query:
        return {"LawSearch": {"totalCnt": "0", "law": []}}
    raise AssertionError(f"unexpected call {path} {query}")


def test_versions_exact_name_sorted(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    vs = admrul.versions(NAME)
    assert [v["시행일자"] for v in vs] == ["20161005", "20191008", "20261102"]      # 비슷한 이름('… 시행세칙')은 섞이지 않음

def test_article_as_of_picks_version_in_force(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    a = admrul.article(NAME, "제9-5조", as_of="20171231")
    assert a["적용 시행일"] == "20161005" and a["발령번호"] == "2016-26" and a["현행 여부"] == "연혁(다음 판 시행일 20191008)"
    assert "50만불" in a["본문"] and "이어지는 항" in a["본문"] and "제9-6조" not in a["본문"] and "제9장" not in a["본문"]
    assert a["부칙"].startswith("부칙 <제2016-26호") and "옛 부칙" not in a["부칙"]
    b = admrul.article(NAME, "9-5", as_of="20191231")
    assert b["적용 시행일"] == "20191008" and "2019년 판" in b["본문"]
    c = admrul.article(NAME, "제9-5조", as_of="20261111")
    assert c["현행 여부"] == "현행" and "3개월" in c["본문"] and "제9-6조" not in c["본문"]

def test_article_before_first_version_is_error(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    a = admrul.article(NAME, "제9-5조", as_of="20100101")
    assert "error" in a and "20161005" in a["error"]

def test_article_without_as_of_is_current(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    a = admrul.article(NAME, "제9-5조")
    assert a["적용 시행일"] == "20261102" and "기준일" not in a and "현행본만" in a["주의"]

def test_law_article_fallback_applies_as_of(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    fn = getattr(server.law_article, "fn", server.law_article)
    r = fn(NAME, "제9-5조", as_of="2017-12-31")
    assert r.get("적용 시행일") == "20161005" and r.get("기준일") == "20171231", r
    r2 = fn(NAME, "제9-5조")
    assert r2.get("적용 시행일") == "20261102", r2


def test_as_of_is_normalized(monkeypatch):
    """'2017-12-31'처럼 구분자가 있어도 같은 판을 고른다(문자열 비교가 깨지지 않게)."""
    monkeypatch.setattr(law, "_get", _fake_get)
    v, nxt, n = admrul.version_as_of(NAME, "2017-12-31")
    assert v["시행일자"] == "20161005" and nxt == "20191008" and n == 3
    assert admrul.article(NAME, "제9-5조", as_of="2019.12.31")["적용 시행일"] == "20191008"

def test_find_article_before_first_version_does_not_use_current(monkeypatch):
    monkeypatch.setattr(law, "_get", _fake_get)
    fn = getattr(server.find_article, "fn", server.find_article)
    r = fn("사후보고", law_name=NAME, as_of="20100101")
    assert "당시 시행본 없음" in r.get("error", "") and not r.get("결과"), r
    ok = fn("사후보고", law_name=NAME, as_of="20171231")
    assert ok.get("결과") and ok["결과"][0]["적용 시행일"] == "20161005", ok
