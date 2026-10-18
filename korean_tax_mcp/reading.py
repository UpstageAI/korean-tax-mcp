"""law_article 읽기 주의 — 돌려준 본문의 단서·우선·제외 구절 원문(최대 3개).

대상 텍스트: 이번 호출에서 실제로 돌려주는 본문(paragraph·keyword로 좁혔으면 좁힌 본문).
표시 태그(<개정 …>, <신설 …>, <전문개정 …>)는 찾기 전에 지운다.
본문이 비었거나 error면 아무것도 붙이지 않는다.
"""
import re
from typing import Optional


def _clean_body(body: str) -> str:
    """표시 태그 제거. <개정 …>, <신설 …>, <전문개정 …>, <타법개정 …>."""
    return re.sub(r"<(?:개정|신설|전문개정|타법개정)(?:[^>]*?|)>", "", body)


def _remove_delete_only_lines(body: str) -> str:
    """'삭제 <…>'만 있는 줄은 건너뛴다."""
    lines = body.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if re.match(r"^삭제\s*<", s) and len(s) < 20:
            continue
        out.append(ln)
    return "\n".join(out)


def _split_sentences(text: str) -> list[tuple[str, str]]:
    """문장 분할: 줄바꿈, 그리고 마침표(.) 뒤 공백·줄끝 — 단 마침표 앞이 한글이나 )일 때만.

    반환: [(문장, 문장 앞 항·호·목 표시)] — 항·호·목 표시(③, 1., 가.)는 먼저 떼어 낸다.
    목 표시(가.)는 문장 끝이 아니다.
    """
    if not text:
        return []

    # 항 표시(①~⑳), 호 표시(N.), 목 표시(가.)를 먼저 떼어 내서 기억
    marker_re = re.compile(r"^([①-⑳]\s*|(\d+)\.\s*|(?:[가-하])\.\s*)")
    markers: list[tuple[int, str]] = []  # (시작 위치, 표시 문자열)

    result = []
    lines = text.split("\n")
    for line in lines:
        m = marker_re.match(line)
        if m:
            marker = m.group(0)
            rest = line[m.end():]
        else:
            marker = ""
            rest = line

        # 마침표 기준 문장 분할: 마침표 앞이 한글이나 )일 때만
        # 숫자 2.9, 호 표시 1.은 경계 아님
        sentences = []
        buf = ""
        i = 0
        while i < len(rest):
            ch = rest[i]
            buf += ch
            if ch == ".":
                # 마침표 앞이 한글이나 )인지 확인
                if buf and len(buf) >= 2:
                    prev = buf[-2]
                    is_hangul = ("\uAC00" <= prev <= "\uD7A3") or ("\u3131" <= prev <= "\u318E")
                    if is_hangul or prev == ")":
                        if buf.strip():
                            sentences.append(buf.strip())
                        buf = ""
            i += 1
        if buf.strip():
            sentences.append(buf.strip())

        for sent in sentences:
            if sent:
                result.append((sent, marker))

    return result


def _find_parenthesized(text: str, start: int) -> Optional[tuple[int, int]]:
    """text[start]에서 '('를 찾았을 때 짝 맞는 괄호 묶음 (start, end) 반환.

    중첩이면 그 말을 품은 가장 안쪽 짝을 찾는다.
    """
    depth = 0
    inner_start = -1
    for i in range(start, len(text)):
        if text[i] == "(":
            if depth == 0:
                inner_start = i
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0 and inner_start >= 0:
                return (inner_start, i + 1)
    return None


def _extract_exclusion(text: str, match_start: int, match_end: int) -> str:
    """제외 구절 추출: '제외한다'/'제외하고'가 괄호 안에 있으면 괄호 묶음 전체,
    괄호 밖이면 그 문장."""
    # 괄호 안에 있는지 확인
    before = text[:match_start]
    last_open = before.rfind("(")
    if last_open >= 0:
        # 괄호 짝 확인
        pair = _find_parenthesized(text, last_open)
        if pair and pair[0] <= match_start < pair[1]:
            # 괄호 묶음 전체 추출
            parens_text = text[pair[0]:pair[1]]
            if len(parens_text) <= 120:
                return parens_text
            else:
                return "…" + parens_text[-119:]
    # 괄호 밖이면 문장 전체 (마침표까지)
    end = text.find(".", match_end)
    if end == -1:
        end = len(text)
    sentence = text[:end + 1] if end < len(text) else text
    if len(sentence) > 120:
        return "…" + sentence[-119:]
    return sentence


def _truncate_proviso_priority(text: str, pos: int) -> str:
    """단서·우선: 문장 처음부터 119자 + …"""
    truncated = text[:119]
    return truncated + "…" if len(text) > 119 else text


def _truncate_exclusion_limit_legal(text: str, keyword_end: int) -> str:
    """제외·한정·의제(괄호 밖 문장): … + 찾은 말이 끝나는 곳에서 끝나는 119자"""
    # 찾은 말 끝에서 119자 전까지 거슬러 올라감
    start = max(0, keyword_end - 118)
    chunk = text[start:keyword_end + 1]
    if len(chunk) > 119:
        chunk = "…" + chunk[-119:]
    elif len(text) > 120 and start > 0:
        chunk = "…" + chunk
    return chunk


def _find_paragraph_ho(text: str, sentence: str) -> str:
    """문장이 속한 항·호 위치 파악.

    항 표시(①~⑳)로 시작하고 그 뒤 호 표시(N. 또는 가.·나.)가 있으면 항+호.
    항 표시만 있으면 항. 호 표시만 있고 항 표시가 앞에 없으면 호.
    항·호 표시 모두 없으면 '본문'.

    문장이 항 표시 줄에는 있지만 호 표시보다 앞(항 머리말)이면 호 없이 항만 반환.
    """
    lines = text.split("\n")
    sentence_line_idx = -1
    for i, line in enumerate(lines):
        if sentence in line:
            sentence_line_idx = i
            break

    if sentence_line_idx < 0:
        return "본문"

    # 항 표시(①~⑳) 찾기 - 문장보다 앞선 줄에서 가장 최근 것
    hang_no = None
    hang_line_idx = -1
    for i in range(sentence_line_idx, -1, -1):
        hm = re.search(r"[①-⑳]", lines[i])
        if hm:
            circled = hm.group(0)
            hang_no = str(ord(circled) - 0x2460 + 1)
            hang_line_idx = i
            break

    if not hang_no:
        # 항 표시 없으면 호 표시만 찾기
        for i in range(sentence_line_idx, -1, -1):
            hm = re.match(r"^(\d+)\.\s", lines[i].lstrip())
            if hm:
                return f"제{hm.group(1)}호"
        return "본문"

    # 항 표시 이후에 문장보다 앞선 호 표시 찾기
    ho_no = None
    for i in range(hang_line_idx + 1, sentence_line_idx + 1):
        hm = re.match(r"^(\d+)\.\s", lines[i].lstrip())
        if hm:
            ho_no = hm.group(1)

    if ho_no:
        return f"제{hang_no}항 제{ho_no}호"
    return f"제{hang_no}항"


def _classify_sentence(sentence: str, body: str, pos_info: str) -> list[dict]:
    """문장 분류: 단서, 우선, 제외, 한정, 의제 중 가장 높은 우선순위 반환.

    한 문장에는 가장 높은 종류 하나만. 단, 제외의 괄호 묶음은 별개 단위로 여러 개 가능.
    같은 위치·원문은 중복 제거.
    반환: 분류 결과 목록 (한 문장에서 여러 개 나올 수 있음 - 제외 괄호 묶음).
    """
    results = []

    # 단서: 다만, 으로 시작 또는 그러하지 아니하다
    if sentence.startswith("다만,") or sentence.startswith("다만 "):
        results.append({"종류": "단서", "원문": sentence, "위치": pos_info})
    elif "그러하지 아니하다" in sentence:
        results.append({"종류": "단서", "원문": sentence, "위치": pos_info})

    # 우선: 불구하고
    if "불구하고" in sentence and not any(r["종류"] == "단서" for r in results):
        results.append({"종류": "우선", "원문": sentence, "위치": pos_info})

    # 제외: 제외한다, 제외하고 - 여러 괄호 묶음 가능
    for excl_match in re.finditer(r"제외한다|제외하고", sentence):
        pos = excl_match.start()
        # 괄호 안인지 확인
        before = sentence[:pos]
        last_open = before.rfind("(")
        if last_open >= 0:
            pair = _find_parenthesized(sentence, last_open)
            if pair:
                parens_text = sentence[pair[0]:pair[1]]
                results.append({"종류": "제외", "원문": parens_text, "위치": pos_info})
                continue

        # 괄호 밖
        end = sentence.find(".", pos)
        if end == -1:
            end = len(sentence)
        full_sentence = sentence[:end + 1] if end < len(sentence) else sentence
        results.append({"종류": "제외", "원문": full_sentence, "위치": pos_info})

    # 한정: 한정한다, 한정하여, 한정하는
    if re.search(r"한정한다|한정하여|한정하는", sentence):
        if not any(r["종류"] in ("단서", "우선", "제외") for r in results):
            results.append({"종류": "한정", "원문": sentence, "위치": pos_info})

    # 의제: 본다(문장 끝), 보지 아니한다
    if re.search(r"으로 본다\.$|것으로 본다\.$", sentence):
        if not any(r["종류"] in ("단서", "우선", "제외", "한정") for r in results):
            results.append({"종류": "의제", "원문": sentence, "위치": pos_info})
    elif "보지 아니한다" in sentence:
        if not any(r["종류"] in ("단서", "우선", "제외", "한정") for r in results):
            results.append({"종류": "의제", "원문": sentence, "위치": pos_info})

    # 길이 제한 처리
    for r in results:
        if r["종류"] in ("단서", "우선"):
            if len(r["원문"]) > 120:
                r["원문"] = r["원문"][:119] + "…"
        elif r["종류"] in ("한정", "의제"):
            kw_match = re.search(r"한정한다|한정하여|한정하는|으로 본다\.$|것으로 본다\.$|보지 아니한다", r["원문"])
            if kw_match and len(r["원문"]) > 120:
                r["원문"] = _truncate_exclusion_limit_legal(r["원문"], kw_match.end())

    return results if results else []


def _is_duplicate(existing: list[dict], new: dict) -> bool:
    """같은 위치·원문이면 중복."""
    for e in existing:
        if e["위치"] == new["위치"] and e["원문"] == new["원문"]:
            return True
    return False


def extract_reading_notes(body: str) -> tuple[list[dict], Optional[int]]:
    """본문(body)에서 읽기 주의 추출.

    반환: (노트 목록, 더 있음 개수 또는 None).
    본문은 이미 _article_body_with_scope에서 결정된 최종 본문.
    """
    if not body:
        return [], None

    cleaned = _clean_body(body)
    cleaned = _remove_delete_only_lines(cleaned)

    if not cleaned.strip():
        return [], None

    sentences_with_markers = _split_sentences(cleaned)
    results: list[dict] = []

    for sentence, marker in sentences_with_markers:
        pos_info = _find_paragraph_ho(cleaned, sentence)
        notes = _classify_sentence(sentence, cleaned, pos_info)
        for note in notes:
            if not _is_duplicate(results, note):
                # 길이 재확인 (분류 중 이미 잘랐지만 재확인)
                if len(note["원문"]) > 120:
                    note["원문"] = note["원문"][:119] + "…"
                results.append(note)

    # 종류 우선순위 → 본문에 나온 순서로 정렬
    priority = {"단서": 0, "우선": 1, "제외": 2, "한정": 3, "의제": 4}
    results.sort(key=lambda x: (priority.get(x["종류"], 99), 0))  # 종류 우선순위 먼저

    # 최대 3개
    capped = results[:3]
    remaining = len(results) - 3 if len(results) > 3 else 0

    return capped, remaining if remaining > 0 else None
