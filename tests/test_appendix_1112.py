"""0.12.22 law_article 별표 조회 — 외부 호출 없이 응답 틀로 확인(2026-11-12, Claude 작성)."""
from korean_tax_mcp import law

_ROWS = ["■ 가상법 시행령 [별표 1] <개정 2025. 9. 1.>", "┌─────┬───┬───────┐", "│업종      │기호  │규모 기준      │", "├─────┼───┼───────┤",
         "│1. 갑업   │C17   │평균매출액등   │", "├─────┼───┤1,800억원 이하 │", "│2. 을업   │C24   │               │", "├─────┼───┼───────┤",
         "│3. 병업   │C20   │평균매출액등   │", "├─────┼───┤1,200억원 이하 │", "│4. 정업   │G     │               │", "└─────┴───┴───────┘", "비고", "1. 분류는 표준산업분류에 따른다."]
_PAYLOAD = {"별표": {"별표단위": [
    {"별표번호": "0001", "별표가지번호": "00", "별표제목": "규모 기준", "별표구분": "별표", "별표시행일자": "20250901", "별표내용": [_ROWS]},
    {"별표번호": "0003", "별표가지번호": "02", "별표제목": "가지 별표", "별표구분": "별표", "별표내용": [["본문 한 줄"]]},
    {"별표번호": "0001", "별표가지번호": "00", "별표제목": "신청서", "별표구분": "서식", "별표내용": []}]}}


def _patch(monkeypatch):
    monkeypatch.setattr(law, "version", lambda l, e="": ("1", "20250901"))
    monkeypatch.setattr(law, "_eflaw", lambda m, e: _PAYLOAD)


def test_not_an_appendix_returns_none():
    assert law.appendix("가상법 시행령", "제2조", "20251231") is None and law.appendix("가상법 시행령", "별표 1 관련", "20251231") is None


def test_listing_and_full_text(monkeypatch):
    _patch(monkeypatch)
    r = law.appendix("가상법 시행령", "별표", "20251231")
    assert r["별표 목록"] == [{"별표": "별표 1", "제목": "규모 기준"}, {"별표": "별표 3의2", "제목": "가지 별표"}]       # 서식은 빠짐
    r = law.appendix("가상법 시행령", "[별표 1]", "20251231")
    assert r["반환 범위"] == "전체" and r["별표 시행일"] == "20250901" and "1,800억원 이하" in r["본문"] and r["본문"].splitlines()[0].startswith("■")
    assert law.appendix("가상법 시행령", "별표 3의2", "20251231")["본문"] == "본문 한 줄"
    assert "error" in law.appendix("가상법 시행령", "별표 9", "20251231")


def test_keyword_returns_merged_cell_value(monkeypatch):
    _patch(monkeypatch)
    r = law.appendix("가상법 시행령", "별표 1", "20251231", "G")
    assert "4. 정업" in r["본문"] and r["병합 칸 값"] == ["평균매출액등 1,200억원 이하"]
    r = law.appendix("가상법 시행령", "별표 1", "20251231", "C24")
    assert r["병합 칸 값"] == ["평균매출액등 1,800억원 이하"]
    assert "안내" in law.appendix("가상법 시행령", "별표 1", "20251231", "없는말")
