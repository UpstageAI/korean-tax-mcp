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


_ITEM_HEAD_RE = re.compile(r"\s*(제\d+(?:-\d+)?조(?:의\d+)?)\s*\(")
_CHAPTER_RE = re.compile(r"\s*제\d+(?:-\d+)?(?:장|절|관)\s")


def articles_of(content):
    """lawService 응답의 '조문내용' → (조 번호, 조 원문) 목록.

    현행본은 한 문자열(split_articles로 나눔), 연혁본은 조 단위 문자열 목록으로 온다.
    목록이면 조 머리로 시작하는 항목이 한 조이고, 머리가 없는 항목은 장·절 제목이 아니면 앞 조에 잇는다(글자 추가 없음).
    """
    if not content:
        return []
    if isinstance(content, str):
        return split_articles(content)
    out = []
    for item in content:
        if not isinstance(item, str) or not item.strip():
            continue
        m = _ITEM_HEAD_RE.match(item)
        if m:
            out.append([m.group(1), item.strip()])
        elif out and not _CHAPTER_RE.match(item):
            out[-1][1] += "\n" + item.strip()
    return [(a, b) for a, b in out]


def addenda_text(svc_body, limit=1500):
    """lawService 응답의 '부칙' 가운데 그 판의 부칙(가장 최근 발령분)을 한 문자열로 — 시행일·적용례 확인용. 길면 앞 limit자.

    부칙은 {"부칙공포일자": [...], "부칙내용": [...], "부칙공포번호": [...]} 꼴로 그동안의 부칙이 모두 쌓여 오므로 마지막 것만 낸다.
    """
    ad = svc_body.get("부칙")
    if not ad:
        return ""
    if isinstance(ad, dict):
        body = ad.get("부칙내용")
        if isinstance(body, list):
            body = body[-1] if body else ""
        txt = str(body or "").strip()
    elif isinstance(ad, list):
        txt = str(ad[-1]).strip() if ad else ""
    else:
        txt = str(ad).strip()
    return txt if len(txt) <= limit else txt[:limit] + " …(생략)"


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


def versions(name):
    """행정규칙의 현행본 + 연혁본 목록(시행일자 오름차순). 법제처 lawSearch target=admrul, nw=1(현행)·nw=2(연혁).

    이름이 정확히 같은 행만 모은다(비슷한 이름의 다른 고시가 섞이지 않게).
    반환: [{"행정규칙일련번호", "행정규칙명", "행정규칙종류", "시행일자", "발령일자", "발령번호", "소관부처명", "현행연혁구분"}]
    """
    q = urllib.parse.quote(name)
    rows = []
    for nw in ("1", "2"):
        for page in range(1, 11):                      # 100건씩, 많아야 10쪽
            data = law._get("lawSearch.do", f"target=admrul&display=100&page={page}&nw={nw}&query={q}")
            got = data.get("AdmRulSearch", {}).get("admrul", [])
            if isinstance(got, dict):
                got = [got]
            rows += [r for r in got if r.get("행정규칙명") == name]
            if len(got) < 100:
                break
    seen, out = set(), []
    for r in rows:
        seq = r.get("행정규칙일련번호")
        if not seq or seq in seen:
            continue
        seen.add(seq)
        out.append({k: r.get(k) for k in ("행정규칙일련번호", "행정규칙명", "행정규칙종류", "시행일자", "발령일자", "발령번호",
                                           "소관부처명", "현행연혁구분")})
    out.sort(key=lambda r: (r.get("시행일자") or "", r.get("발령일자") or ""))
    return out


def version_as_of(name, as_of):
    """as_of(YYYYMMDD) 당시 시행 중이던 판 — 시행일자가 as_of 이하인 것 가운데 가장 늦은 판.

    반환: (그 판 | None, 다음 판의 시행일자 | None, 전체 판 수). 그 날짜에 시행 중인 판이 없으면 판 자리에 None.
    """
    vs = versions(name)
    past = [v for v in vs if (v.get("시행일자") or "") <= as_of]
    if not past:
        return None, (vs[0].get("시행일자") if vs else None), len(vs)
    cur = past[-1]
    later = [v for v in vs if (v.get("시행일자") or "") > as_of]
    return cur, (later[0].get("시행일자") if later else None), len(vs)


def article(name, article_no, as_of=None):
    """행정규칙 조문을 조회.

    search → lawService(target=admrul, ID=일련번호) → split_articles → 해당 조.
    as_of(YYYYMMDD)를 주면 그 날짜에 시행 중이던 판(연혁본)을 고른다.
    """
    next_ef = None
    if as_of:
        info, next_ef, n_versions = version_as_of(name, as_of)
        if info is None and n_versions:
            return {
                "법령": name, "구분": "행정규칙(고시)", "조": normalize(article_no), "적용 시행일": "", "발령일": "", "소관": "",
                "본문": f"{as_of} 당시 시행본 없음 — 법제처에 등록된 가장 이른 판의 시행일은 {next_ef}",
                "링크": f"https://www.law.go.kr/행정규칙/{urllib.parse.quote(name)}",
                "주의": "행정규칙 연혁은 법제처에 등록된 판만 조회",
                "error": f"{as_of} 당시 시행본 없음 — 가장 이른 판 시행일 {next_ef}",
            }
        if info is None:
            info = search(name)                      # 정확한 이름이 아니면 현행본 검색으로(비슷한 이름) — 연혁은 적용 못 함
            as_of = None
    else:
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
    arts = dict(articles_of(content))
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
    } if not as_of else {
        "법령": basics.get("행정규칙명") or info["행정규칙명"],
        "구분": _구분(basics.get("행정규칙종류") or info["행정규칙종류"]),
        "조": norm,
        "적용 시행일": basics.get("시행일자") or info["시행일자"],
        "발령일": basics.get("발령일자") or info.get("발령일자") or "",
        "발령번호": basics.get("발령번호") or info.get("발령번호") or "",
        "소관": basics.get("소관부처명") or info["소관부처명"],
        "기준일": as_of,
        "현행 여부": "현행" if next_ef is None else f"연혁(다음 판 시행일 {next_ef})",
        "본문": body,
        "부칙": addenda_text(svc.get("AdmRulService", {})),
        "링크": f"https://www.law.go.kr/행정규칙/{urllib.parse.quote(info['행정규칙명'])}",
        "주의": "행정규칙 — as_of 기준일에 시행 중이던 판(법제처 등록 연혁). 시행일 전후 거래는 부칙의 적용례·경과조치 확인",
    }
