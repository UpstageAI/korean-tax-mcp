"""행정규칙(고시·훈령·예규) 조문 조회 — 법제처 DRF target=admrul.

단순 파서 + 조회 모듈. 캐싱은 law._get의 TTL 캐시를 그대로 사용하며 별도 캐시를 두지 않는다.
"""
import re
import urllib.parse

from . import law

_HEAD_RE = re.compile(r"제\d+(?:-\d+)?조(?:의\d+)?(?=\()")
_ROW_RE = re.compile(r"^(?:제\s*)?(\d+)(?:-(\d+))?(?:조)?(?:의(\d+))?$")


def split_articles(text):
    """행정규칙 조문내용 문자열을 (조 번호, 조 원문) 목록으로 분할.

    조 번호 정규식: 제N조, 제N-M조, 제N조의M, 제N-M조의K (머리 괄호 '(' 앞까지).
    원문은 조 머리부터 다음 조 머리 앞까지, 공백 정리만 하고 글자 추가 없음.
    """
    if not text:
        return []
    heads = list(_HEAD_RE.finditer(text))
    if not heads:
        return []
    out = []
    for i, m in enumerate(heads):
        label = m.group()
        start = m.start()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            out.append((label, chunk))
    return out


def normalize(raw):
    """조 번호 표기를 정규화. 하이픈 조(제9-5조)는 그대로 유지.

    '9-5' → '제9-5조', '제9조의5' → '제9조의5', '제12조' → '제12조' 등.
    """
    if not raw:
        return ""
    s = raw.strip()
    m = _ROW_RE.match(s)
    if not m:
        return s
    main = m.group(1)
    dash = m.group(2)
    branch = m.group(3)
    if dash:
        base = f"제{main}-{dash}조"
    else:
        base = f"제{main}조"
    if branch:
        base += f"의{branch}"
    return base


def _구분(kind):
    """행정규칙 종류 코드에 '행정규칙(...)' 접두어를 붙인다."""
    if not kind:
        return "행정규칙"
    return f"행정규칙({kind})"


def search(name):
    """행정규칙명으로 법제처 DRF lawSearch(target=admrul) 조회.

    정확히 같은 이름이 첫 행에 있으면 그것을, 없으면 가장 짧은 포함 행을 반환.
    반환: {"행정규칙일련번호", "행정규칙명", "행정규칙종류", "시행일자", "소관부처명"}
    """
    query = f"target=admrul&display=10&query={urllib.parse.quote(name)}"
    data = law._get("lawSearch.do", query)
    rows = data.get("AdmRulSearch", {}).get("admrul", [])
    if not rows:
        return None
    exact = [r for r in rows if r.get("행정규칙명") == name]
    if exact:
        r = exact[0]
    else:
        r = min(rows, key=lambda x: len(x.get("행정규칙명", "")))
    return {
        "행정규칙일련번호": r.get("행정규칙일련번호"),
        "행정규칙명": r.get("행정규칙명"),
        "행정규칙종류": r.get("행정규칙종류"),
        "시행일자": r.get("시행일자"),
        "소관부처명": r.get("소관부처명"),
    }


def article(name, article_no):
    """행정규칙 조문을 조회.

    search → lawService(target=admrul, ID=일련번호) → split_articles → 해당 조.
    """
    info = search(name)
    if info is None:
        return {
            "법령": name,
            "구분": "행정규칙(고시)",
            "조": normalize(article_no),
            "적용 시행일": "",
            "발령일": "",
            "소관": "",
            "본문": "행정규칙 없음 — 이름 확인",
            "링크": f"https://www.law.go.kr/행정규칙/{urllib.parse.quote(name)}",
            "주의": "행정규칙은 현행본만 조회(연혁·as_of 미지원) — 개정 잦음",
            "error": "행정규칙 없음 — 이름 확인",
        }
    seq = info["행정규칙일련번호"]
    svc = law._get("lawService.do", f"target=admrul&ID={seq}")
    basics = svc.get("AdmRulService", {}).get("행정규칙기본정보", {})
    content = svc.get("AdmRulService", {}).get("조문내용", "")
    norm = normalize(article_no)
    arts = dict(split_articles(content))
    body = arts.get(norm, "")
    if not body:
        body = "조문 없음 — 조번호 확인"
    return {
        "법령": basics.get("행정규칙명") or info["행정규칙명"],
        "구분": _구분(basics.get("행정규칙종류") or info["행정규칙종류"]),
        "조": norm,
        "적용 시행일": basics.get("시행일자") or info["시행일자"],
        "발령일": basics.get("발령일자") or "",
        "소관": basics.get("소관부처명") or info["소관부처명"],
        "본문": body,
        "링크": f"https://www.law.go.kr/행정규칙/{urllib.parse.quote(info['행정규칙명'])}",
        "주의": "행정규칙은 현행본만 조회(연혁·as_of 미지원) — 개정 잦음",
    }
