"""세무 메모 Word(.docx) 그리기 — 외부 라이브러리 없이 OOXML을 직접 쓴다(zipfile). 작성 Mia(윤승미)

입력은 tax_memo.check가 정리한 구조. 모양: A4(본문 10pt·줄 간격 1.1), 제목·머리 표 한 개, 번호 붙은 요약, 소제목, 표(머리·합계 음영, 우선순위 색),
실제 Word 각주(읽는 순서로 번호, 같은 출처는 처음 번호를 다시 씀), 바닥글 안내와 쪽 번호.
선택 블록(있을 때만 찍음): 머리의 수신·근거 자료·계산 파일, 결론 아래 숫자 표(경우 열 나란히), 쟁점 안의 표, 기존 처리 검토 결과,
조치 목록 표, 한계와 미확인 사항, 주요 근거.
한글이 어느 환경에서나 보이도록 모든 글자 조각에 동아시아 글꼴(맑은 고딕)을 지정한다.
"""
import re
import zipfile
from xml.sax.saxutils import escape

from . import tax_memo as M

INK, MUTED, RULE, ACCENT, SOFT = "1F2933", "5F6B7A", "C9D1DA", "1F3A5F", "F3F6F9"
EMPH = "E3EAF2"                        # 결론 아래 숫자 표의 합계 행
PAGE_W, PAGE_H = 11906, 16838          # A4
MARGIN_TB, MARGIN_LR = 1000, 1134      # 위아래 약 1.8cm, 좌우 2cm
W = PAGE_W - 2 * MARGIN_LR             # 본문 너비 9638
EA = "Malgun Gothic"                   # 동아시아 글꼴: 윈도·맥용 Word에 들어 있음. 없으면 fontTable의 대체 이름으로
FONTS = {"en": {"body": "Georgia", "sans": "Arial"}, "ko": {"body": "Arial", "sans": "Arial"}}   # 한글은 eastAsia 글꼴로, 영문·숫자는 어디에나 있는 글꼴로
SIZE = {"en": {"body": 20, "cell": 18, "note": 16}, "ko": {"body": 20, "cell": 18, "note": 16}}   # 반 포인트: 본문 10pt, 표 9pt, 각주 8pt
LINE, CELL_LINE = 264, 250             # 줄 간격(240 = 1줄): 본문 1.1줄, 표 칸 1.04줄
KEEP_ROWS, KEEP_HEIGHT = 16, 7400      # 이보다 작은 표(행 수, 어림 높이 twip — 반 쪽)는 통째로 한 쪽에 둔다
TAG = {0: ("FBE4E1", "9B2C1F"), 1: ("FDF1D6", "8A5A00"), 2: ("E4F2E7", "22663A")}   # 우선순위 칸 (바탕, 글자)
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_INLINE = re.compile(r"(\*\*.+?\*\*|\[\^[^\]\s]+\])", re.S)
_TAGS = re.compile(r"<[^>]+>")
_WIDE = re.compile(r"[ᄀ-ᇿ⺀-鿿가-힯＀-￯]")
_SZ = re.compile(r'<w:sz w:val="(\d+)"/>')
_PARA = re.compile(r"<w:p>.*?</w:p>", re.S)
# 분량 어림에 쓰는 블록 이름(build가 차례로 바꿔 가며 높이를 쌓는다)
BLOCKS = ("head", "summary", "question", "short_answer", "key_figures", "facts", "analysis", "review", "calculation", "risks",
          "next_steps", "limitations", "authorities", "prepared_how", "footnotes")


def _t(text):
    return escape(_CTRL.sub("", text))


def _lines(xml, width, default_size):
    """문단 XML 한 개가 width(twip) 안에서 몇 줄인지와 글자 크기(반 포인트) — 분량 어림용. 영문·숫자는 글자 크기의 절반, 한글·한자는 글자 크기만큼의 너비로 본다."""
    sizes = [int(x) for x in _SZ.findall(xml)]
    size = max(sizes) if sizes else default_size
    n = 0
    for piece in re.split(r"<w:br/>", xml):
        text = _TAGS.sub("", piece).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        wide = len(_WIDE.findall(text))
        need = (wide + (len(text) - wide) * 0.5) * size * 10 * 1.04          # 낱말 단위 줄바꿈으로 남는 자리 4%
        n += max(1, -(-int(need) // max(int(width), 1)))
    return n, size


class Doc:
    def __init__(self, s):
        self.s = s; self.lang = s["lang"]; self.L = M.LABELS[self.lang]
        self.f = FONTS[self.lang]; self.z = SIZE[self.lang]
        self.body = []; self.notes = []; self.first = {}; self.nums = 0
        self.fn_text = {f["id"]: f["text"] for f in s["footnotes"]}
        self.block = "head"; self.height = {}          # 블록별 어림 높이(twip)

    # ── 글자 조각 ──
    def run(self, text, font="body", size=None, bold=False, italic=False, color=INK, spacing=0, extra=""):
        if not text and not extra: return ""
        face = self.f[font]
        pr = (f'<w:rFonts w:ascii="{face}" w:hAnsi="{face}" w:eastAsia="{EA}" w:cs="{face}"/>'
              + ("<w:b/><w:bCs/>" if bold else "") + ("<w:i/><w:iCs/>" if italic else "")
              + f'<w:color w:val="{color}"/>' + (f'<w:spacing w:val="{spacing}"/>' if spacing else "")
              + f'<w:sz w:val="{size or self.z["body"]}"/><w:szCs w:val="{size or self.z["body"]}"/>')
        inner = extra or f'<w:t xml:space="preserve">{_t(text)}</w:t>'
        return f"<w:r><w:rPr>{pr}</w:rPr>{inner}</w:r>"

    def fn(self, key):
        """각주 참조 조각. 번호는 읽는 순서. 같은 출처가 다시 나오면 각주를 새로 만들지 않고 처음 번호를 다시 쓴다."""
        if key not in self.fn_text: return ""
        if key in self.first:
            return f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:t>{self.first[key]}</w:t></w:r>'
        n = len(self.notes) + 1
        self.notes.append(self.fn_text[key]); self.first[key] = n
        return f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="{n}"/></w:r>'

    def inline(self, text, notes=True, **kw):
        """**굵게**와 [^각주]가 섞인 글 → 조각들."""
        out = []; after_ref = False
        for part in _INLINE.split(text or ""):
            if not part: continue
            if part.startswith("[^") and part.endswith("]"):
                ref = self.fn(part[2:-1]) if notes else ""
                if ref and after_ref:      # 각주 번호가 잇달아 오면 쉼표로 나눈다(¹,²)
                    out.append('<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:t>,</w:t></w:r>')
                out.append(ref); after_ref = after_ref or bool(ref)
                continue
            after_ref = False
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                out.append(self.run(part[2:-2], **{**kw, "bold": True}))
            else:
                out.append(self.run(part, **kw))
        return "".join(out)

    # ── 문단 ──
    def p(self, runs, after=70, line=LINE, before=0, style="", num=None, ind=None, tabs="", border=False, keep=False, jc=""):
        pr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:keepNext/>" if keep else "")
        if num: pr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
        if border: pr += f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{RULE}"/></w:pBdr>'
        if tabs: pr += f"<w:tabs>{tabs}</w:tabs>"
        pr += f'<w:spacing w:before="{before}" w:after="{after}"' + (f' w:line="{line}" w:lineRule="auto"' if line else "") + "/>"
        if ind: pr += f'<w:ind w:left="{ind[0]}" w:hanging="{ind[1]}"/>'
        if jc: pr += f'<w:jc w:val="{jc}"/>'
        return f"<w:p><w:pPr>{pr}</w:pPr>{runs}</w:p>"

    def _tall(self, xml, width, line=LINE):
        """문단 XML의 어림 높이(twip)."""
        m = re.search(r'<w:spacing w:before="(\d+)" w:after="(\d+)"(?: w:line="(\d+)")?', xml)
        before, after, ln = (int(m.group(1)), int(m.group(2)), int(m.group(3) or line)) if m else (0, 0, line)
        if "<w:numPr>" in xml: width -= 420
        n, size = _lines(xml, width, self.z["body"])
        return before + after + n * size * 10 * 1.16 * ln / 240          # 글꼴의 줄 높이는 글자 크기의 약 1.16배

    def add(self, x):
        self.body.append(x)
        self.height[self.block] = self.height.get(self.block, 0) + (self._table_tall(x) if x.startswith("<w:tbl>") else self._tall(x, W))

    def _row_tall(self, row):
        tall = 0
        for width, cell in re.findall(r'<w:tc><w:tcPr><w:tcW w:w="(\d+)".*?</w:tcPr>(.*?)</w:tc>', row, re.S):
            tall = max(tall, sum(self._tall(p, int(width) - 160, CELL_LINE) for p in _PARA.findall(cell)))
        return tall + 90          # 칸 위아래 여백과 선

    def _table_tall(self, xml):
        return sum(self._row_tall(r) for r in re.findall(r"<w:tr>.*?</w:tr>", xml, re.S)) + 60

    def h1(self, text):
        self.add(self.p(self.run(text, "sans", 22, bold=True, color=ACCENT), after=60, before=200, line=0, style="Heading1", keep=True))

    def h2(self, text):
        self.add(self.p(self.inline(text, notes=False, font="sans", size=19, bold=True), after=40, before=110, line=0, style="Heading2", keep=True))

    def caption(self, text):
        """표 위의 작은 제목 — 표와 떨어지지 않는다."""
        self.add(self.p(self.inline(text, notes=False, font="sans", size=17, bold=True, color=MUTED), before=100, after=50, line=0, keep=True))

    def rule(self):
        self.add(self.p("", after=80, line=0, border=True))

    def new_list(self):
        """번호 목록 하나 — 목록마다 1부터 다시 센다."""
        self.nums += 1
        return self.nums + 1          # numId 1은 글머리표

    # ── 표 ──
    def cell(self, runs, width, fill="", jc="", span=0, edge=True, pad=35):
        para = runs if runs.startswith("<w:p>") else self.p(runs, after=0, line=CELL_LINE, jc=jc)
        line = f'w:val="single" w:sz="4" w:space="0" w:color="{RULE}"'
        top, bottom = (line if edge is True else 'w:val="nil"'), (line if edge else 'w:val="nil"')          # edge="bottom": 아래 선만
        return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span else "")
                + f'<w:tcBorders><w:top {top}/><w:left w:val="nil"/><w:bottom {bottom}/><w:right w:val="nil"/></w:tcBorders>'
                + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else "")
                + f'<w:tcMar><w:top w:w="{pad}" w:type="dxa"/><w:left w:w="80" w:type="dxa"/><w:bottom w:w="{pad}" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>'
                + f"</w:tcPr>{para}</w:tc>")

    def table(self, widths, rows, header=True):
        """rows: [[칸 XML]] — 첫 행은 머리(쪽이 넘어가면 반복), 모든 행은 쪽 경계에서 갈라지지 않는다.
        작은 표는 통째로 한 쪽에 둔다(마지막 행을 뺀 모든 문단에 '다음 문단과 함께'). 큰 표는 행 사이에서만 넘어간다."""
        trs = ["".join(cells) for cells in rows]
        if len(trs) <= KEEP_ROWS and sum(self._row_tall(f"<w:tr>{r}</w:tr>") for r in trs) <= KEEP_HEIGHT:
            trs = [r.replace("<w:p><w:pPr>", "<w:p><w:pPr><w:keepNext/>") for r in trs[:-1]] + trs[-1:]
        out = [f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr>'
               "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{x}"/>' for x in widths) + "</w:tblGrid>"]
        for i, r in enumerate(trs):
            out.append("<w:tr><w:trPr><w:cantSplit/>" + ("<w:tblHeader/>" if header and i == 0 else "") + "</w:trPr>" + r + "</w:tr>")
        out.append("</w:tbl>")
        self.add("".join(out))

    def hd(self, text, width, jc=""):
        return self.cell(self.run(text, "sans", 16, bold=True, color=MUTED), width, SOFT, jc)

    def tc(self, text, width, bold=False, fill="", jc="", notes=True):
        return self.cell(self.inline(text, notes=notes, size=self.z["cell"], bold=bold), width, fill, jc)

    def calc_table(self, rows, currency):
        L = self.L; ws = [4100, 3300, W - 7400]
        amount = f'{L["amount"]} ({currency})' if currency else L["amount"]
        out = [[self.hd(L["item"], ws[0]), self.hd(L["basis_col"], ws[1], "right"), self.hd(amount, ws[2], "right")]]
        for r in rows:
            tot = r["role"] == "total"; fill = SOFT if tot else ""
            out.append([self.tc(r["item"], ws[0], tot, fill), self.tc(r["basis"] or "—", ws[1], tot, fill, "right"),
                        self.tc(r["amount"] or "—", ws[2], tot, fill, "right")])
        self.table(ws, out)

    def grid(self, tb, key=False):
        """선택 표 블록 — 첫 열은 항목, 숫자만 든 열은 오른쪽 맞춤, role='total' 행은 굵게·음영. key=True면 결론 아래 숫자 표(권고 열 표시)."""
        L = self.L; n = len(tb["columns"])
        if n < 1 or not tb["rows"]: return
        rows = [(r["cells"] + [""] * n)[:n] for r in tb["rows"]]
        numeric = [i > 0 and any(r[i] for r in rows) and all(M._NUMERIC.match(M.plain(r[i])) for r in rows if r[i]) for i in range(n)]
        if n == 1: ws = [W]
        elif all(numeric[1:]):
            side = 2300 if n <= 3 else (1900 if n == 4 else (W - 2800) // (n - 1))
            ws = [W - side * (n - 1)] + [side] * (n - 1)
        else:
            first = min(3800, W // n + 600); ws = [first] + [(W - first) // (n - 1)] * (n - 1); ws[-1] += W - sum(ws)
        if tb["title"]: self.caption(tb["title"])
        head = []
        for i, c in enumerate(tb["columns"]):
            runs = self.run(M.plain(c), "sans", 16, bold=True, color=MUTED)
            if key and i > 0 and tb["recommended"] and c == tb["recommended"]:
                runs += self.run(" · " + L["recommended"], "sans", 15, bold=True, color=ACCENT)
            head.append(self.cell(runs or self.run(" ", "sans", 16), ws[i], SOFT, "right" if numeric[i] else ""))
        out = [head]
        for r, cells in zip(tb["rows"], rows):
            tot = r["role"] == "total"; fill = (EMPH if key else SOFT) if tot else ""
            out.append([self.tc(c or ("—" if i else ""), ws[i], tot, fill, "right" if numeric[i] else "") for i, c in enumerate(cells)])
        self.table(ws, out)
        if tb["note"]:
            self.add(self.p(self.inline(tb["note"], italic=True, color=MUTED, size=self.z["body"] - 2), before=60))

    def severity(self, value, width):
        rank = M.PRIORITIES[self.lang].index(value) if value in M.PRIORITIES[self.lang] else 1
        fill, color = TAG[rank]
        return self.cell(self.run(value, "sans", 15, bold=True, color=color), width, fill)

    def head_table(self):
        """머리 — 표 한 개. 짧은 일자는 수신(없으면 작성) 줄 오른쪽에 붙여 한 줄을 아낀다."""
        s, L, z = self.s, self.L, self.z
        ko = self.lang == "ko"
        label = lambda t: self.p(self.run(t if ko else t.upper(), "sans", 15, bold=True, color=MUTED), after=0, before=24, line=CELL_LINE)          # 작은 글자를 값의 첫 줄 높이에 맞춤
        value = lambda k: self.inline(s["head"][k], notes=False, size=z["body"] - 1)
        items = [(k, t) for k, t in L["head"] if s["head"][k]]
        names = dict(L["head"])
        ws = [1250, W - 1250 - 800 - 2000, 800, 2000]
        one = lambda k, width: _lines(value(k), width - 200, z["body"])[0] == 1          # 그 칸에 한 줄로 들어가는가
        mate = next((k for k in ("to", "prepared_by") if s["head"][k] and s["head"]["date"] and one("date", ws[3]) and one(k, ws[1])), "")
        rows = []
        last = [k for k, _ in items if not (mate and k == "date")][-1:]
        for k, t in items:
            if mate and k == "date": continue
            c = dict(edge="bottom" if [k] == last else False, pad=20)          # 마지막 줄 아래에 가는 선
            if k == mate:
                rows.append([self.cell(label(t), ws[0], **c), self.cell(value(k), ws[1], **c),
                             self.cell(label(names["date"]), ws[2], **c), self.cell(value("date"), ws[3], **c)])
            else:
                rows.append([self.cell(label(t), ws[0], **c), self.cell(value(k), W - ws[0], span=3, **c)])
        if rows: self.table(ws, rows, header=False)

    # ── 본문 ──
    def build(self):
        s, L, z = self.s, self.L, self.z
        ko = self.lang == "ko"
        small = z["body"] - 2
        self.add(self.p(self.run(L["title"], "sans", 28, bold=True, color=ACCENT, spacing=40), after=100, line=0))
        self.head_table()

        self.block = "summary"
        if s["summary"]:
            self.h1(L["summary"]); n = self.new_list()
            for it in s["summary"]:
                self.add(self.p(self.inline(it["conclusion"], bold=True) + self.run(" ") + self.inline(it["basis"]), after=50, num=n))
        sa0, rv = s["short_answer"], s["review"]
        # 절 번호 — 앞 절이 모두 있고 검토 결과 절이 없으면 '위험과 확인할 점'은 6
        review_no = 1 + sum(map(bool, (s["question"] or s["background"], sa0["answer"] or sa0["conditions"] or s["key_figures"], s["facts"],
                                       s["analysis"] or s["decision_table"])))
        risk_no = 1 + sum(map(bool, (s["question"] or s["background"], sa0["answer"] or sa0["conditions"], s["facts"],
                                     s["analysis"] or s["decision_table"], rv, s["calculation"])))
        k = 0
        self.block = "question"
        if s["question"] or s["background"]:
            k += 1; self.h1(f'{k}. {L["background_question"] if s["background"] else L["question"]}')
            if s["background"]: self.add(self.p(self.inline(s["background"])))
            if s["question"]: self.add(self.p(self.inline(s["question"])))
        sa = s["short_answer"]
        self.block = "short_answer"
        if sa["answer"] or sa["conditions"]:
            k += 1; self.h1(f'{k}. {L["short_answer"]}')
            self.add(self.p(self.inline(sa["answer"], bold=True) + self.run(" ") + self.inline(sa["conditions"]), keep=bool(s["key_figures"])))
        if s["key_figures"]:
            self.block = "key_figures"
            if not (sa["answer"] or sa["conditions"]): k += 1; self.h1(f'{k}. {L["key_figures"]}')
            self.grid(s["key_figures"], key=True)
        review_up = bool(rv and (sa["answer"] or sa["conditions"]))
        if review_up:          # 결론부: 굵은 한 줄 판정 + 발견 사항 이름(금액·조치는 검토 결과 절의 표에 한 번만)
            self.block = "review"
            names = [M.plain(it["finding"]) for it in rv["findings"] if M.plain(it["finding"])]
            tail = ("  " if ko else " ") + ("; ".join(names) + " " + L["see_section"].format(n=review_no)) if names else ""
            self.add(self.p(self.inline(rv["verdict"], notes=False, bold=True) + self.run(tail), before=60))
        self.block = "facts"
        if s["facts"]:
            k += 1; self.h1(f'{k}. {L["facts"]}')
            point = {r["id"]: r["point"] for r in s["risks"]}
            for it in s["facts"]:
                runs = self.inline(it["text"])
                if it["changes_answer"] and point.get(it["risk"]):
                    runs += self.run(" " + L["if_not"].format(n=risk_no, p=M.plain(point[it["risk"]])), italic=True, color=MUTED, size=small)
                self.add(self.p(runs, after=40, num=1))
        self.block = "analysis"
        if s["analysis"] or s["decision_table"]:
            k += 1; self.h1(f'{k}. {L["analysis"]}')
            for j, it in enumerate(s["analysis"], 1):
                self.h2(f'{k}.{j} {it["heading"]}')
                # 근거 규정과 적용을 한 문단, 결론과 확인할 점을 한 문단 — 표지는 굵게
                for group in (("rule", "application"), ("conclusion", "confirm")):
                    runs = ""
                    for key in group:
                        if not it[key]: continue
                        runs += ((self.run(" ") if runs else "")
                                 + self.run(L[key] + ("  " if ko else " "), "sans" if ko else "body", bold=True,
                                            color=MUTED if key == "confirm" else INK, size=z["body"] - (1 if ko else 0))
                                 + self.inline(it[key]))
                    if runs: self.add(self.p(runs, after=40))
                if it["table"]: self.grid(it["table"])
            dt = s["decision_table"]
            if dt and dt["columns"] and dt["rows"]:
                self.h2(dt["title"] or L["decision"])
                n = len(dt["columns"]); first = min(3800, W // n + 600) if n > 1 else W
                ws = [first] + [(W - first) // (n - 1)] * (n - 1) if n > 1 else [W]
                ws[-1] += W - sum(ws)
                rows = [[self.hd(c, ws[i]) for i, c in enumerate(dt["columns"])]]
                for r in dt["rows"]:
                    r = (r + [""] * n)[:n]
                    rows.append([self.tc(c, ws[i], bold=(i == n - 1)) for i, c in enumerate(r)])
                self.table(ws, rows)
        if rv:
            self.block = "review"
            k += 1; self.h1(f'{k}. {L["review"]}')
            if rv["verdict"] and not (review_up and rv["findings"]):          # 결론부에 이미 찍은 판정은 표 앞에서 되풀이하지 않는다
                self.add(self.p(self.inline(rv["verdict"], bold=True), keep=bool(rv["findings"])))
            if rv["findings"]:
                ws = [900, 3300, 2300, W - 6500]
                rows = [[self.hd(L["severity"], ws[0]), self.hd(L["finding"], ws[1]), self.hd(L["amount"], ws[2]), self.hd(L["fix"], ws[3])]]
                for it in rv["findings"]:
                    what = self.inline(it["finding"], size=z["cell"], bold=True) + (self.run("", extra="<w:br/>") + self.inline(it["detail"], size=z["cell"]) if it["detail"] else "")          # 이름 아래 줄에 설명
                    rows.append([self.severity(it["severity"], ws[0]), self.cell(what, ws[1]), self.tc(it["amount"] or "—", ws[2]), self.tc(it["action"], ws[3])])
                self.table(ws, rows)
        calc = s["calculation"]
        if calc:
            self.block = "calculation"
            k += 1; self.h1(f'{k}. {L["calculation"]}')
            if calc["rows"]: self.calc_table(calc["rows"], calc["currency"])
            for sc in calc["scenarios"]:
                if not sc["rows"]: continue
                self.caption(sc["title"])
                self.calc_table(sc["rows"], calc["currency"])
            if calc["note"]: self.add(self.p(self.inline(calc["note"], color=MUTED, size=small), before=60))
        if s["risks"]:
            self.block = "risks"
            k += 1; self.h1(f'{k}. {L["risks"]}')
            ws = [900, 2100, W - 3000]
            rows = [[self.hd(L["priority"], ws[0]), self.hd(L["point"], ws[1]), self.hd(L["why"], ws[2])]]
            for r in s["risks"]:
                why = self.inline(r["why"], size=z["cell"])
                if r["check"]: why += self.run((" " if r["why"] else "") + L["check"] + " ", size=z["cell"], bold=True, color=MUTED) + self.inline(r["check"], size=z["cell"])
                rows.append([self.severity(r["priority"], ws[0]), self.tc(r["point"], ws[1], bold=True), self.cell(why, ws[2])])
            self.table(ws, rows)
        self.block = "next_steps"
        if s["action_list"]:
            k += 1; self.h1(f'{k}. {L["action_list"]}')
            ws = [450, W - 3950, 1750, 1750]
            rows = [[self.hd(L["no"], ws[0]), self.hd(L["action"], ws[1]), self.hd(L["owner"], ws[2]), self.hd(L["by"], ws[3])]]
            for j, it in enumerate(s["action_list"], 1):
                rows.append([self.tc(str(j), ws[0]), self.tc(it["action"], ws[1]), self.tc(it["owner"] or "—", ws[2]), self.tc(it["deadline"] or "—", ws[3])])
            self.table(ws, rows)
        elif s["next_steps"]:
            k += 1; self.h1(f'{k}. {L["next_steps"]}'); n = self.new_list()
            for it in s["next_steps"]:
                tail = "; ".join(x for x in ((f'{L["owner"]}: {it["owner"]}' if it["owner"] else ""), (f'{L["by"]}: {it["deadline"]}' if it["deadline"] else "")) if x)
                self.add(self.p(self.inline(it["action"]) + (self.run(f" ({tail})", color=MUTED, size=small) if tail else ""), after=50, num=n))
        lim = s["limitations"]
        if lim:
            self.block = "limitations"
            k += 1; self.h1(f'{k}. {L["limitations"]}')
            if lim["text"]: self.add(self.p(self.inline(lim["text"]), after=50))
            for x in lim["items"]: self.add(self.p(self.inline(x, size=z["body"] - 1), after=20, num=1))
        if s["authorities"]:
            self.block = "authorities"
            self.h2(L["authorities"])
            for x in s["authorities"]: self.add(self.p(self.inline(x, notes=False, size=small), after=20, line=CELL_LINE, num=1))
        if s["prepared_how"]:
            self.block = "prepared_how"
            self.rule()
            self.add(self.p(self.run(L["how"] + " ", bold=True, size=small - 1, color=MUTED) + self.inline(s["prepared_how"], notes=False, size=small - 1, color=MUTED), line=CELL_LINE))
        for text in self.notes:          # 각주가 쪽 아래에서 차지하는 높이
            n, _ = _lines(text, W, z["note"])
            self.height["footnotes"] = self.height.get("footnotes", 0) + 30 + n * z["note"] * 10 * 1.16
        return self

    def length(self):
        """분량 어림 — {pages, blocks: {블록: 쪽}}. 실제 쪽수는 Word가 정하므로 어림값이다."""
        usable = PAGE_H - 2 * MARGIN_TB          # LibreOffice로 뽑은 쪽수에 맞춰 본 값(긴 메모 5.7쪽 → 5.9, 짧은 예시 1.45쪽 → 1.4)
        blocks = {b: round(self.height[b] / usable, 2) for b in BLOCKS if self.height.get(b)}
        return {"pages": round(sum(self.height.values()) / usable, 1), "blocks": blocks}

    # ── 파일 조각 ──
    def document(self):
        sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId5"/>'
                f'<w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
                f'<w:pgMar w:top="{MARGIN_TB}" w:right="{MARGIN_LR}" w:bottom="{MARGIN_TB}" w:left="{MARGIN_LR}" w:header="600" w:footer="480" w:gutter="0"/></w:sectPr>')
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>{"".join(self.body)}{sect}</w:body></w:document>'

    def footnotes(self):
        out = ['<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>',
               '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>']
        for n, text in enumerate(self.notes, 1):
            ref = '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>'
            body = self.run(" ", size=self.z["note"]) + self.inline(text, notes=False, size=self.z["note"])
            out.append(f'<w:footnote w:id="{n}"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/><w:spacing w:after="30"/></w:pPr>{ref}{body}</w:p></w:footnote>')
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:footnotes {NS}>{"".join(out)}</w:footnotes>'

    def footer(self):
        kw = dict(font="sans", size=14, color=MUTED)
        page = (self.run("", extra="<w:tab/>", **kw) + self.run("", extra='<w:fldChar w:fldCharType="begin"/>', **kw)
                + self.run("", extra='<w:instrText xml:space="preserve"> PAGE </w:instrText>', **kw)
                + self.run("", extra='<w:fldChar w:fldCharType="separate"/>', **kw) + self.run("1", **kw)
                + self.run("", extra='<w:fldChar w:fldCharType="end"/>', **kw))
        notice = self.s["notice"] or self.L["notice"]
        para = self.p(self.run(notice, **kw) + page, after=0, line=0, ind=(0, 0), tabs=f'<w:tab w:val="right" w:pos="{W}"/>')
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:ftr {NS}>{para}</w:ftr>'

    def numbering(self):
        body = self.f["body"]
        def lvl(fmt, text, hang, rpr):
            return (f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                    f'<w:pPr><w:ind w:left="420" w:hanging="{hang}"/></w:pPr><w:rPr>{rpr}</w:rPr></w:lvl>')
        fonts = f'<w:rFonts w:ascii="{body}" w:hAnsi="{body}" w:eastAsia="{EA}" w:cs="{body}"/>'
        out = ['<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>' + lvl("bullet", "•", 220, f'<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="{EA}" w:cs="Arial"/>') + "</w:abstractNum>",
               '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>' + lvl("decimal", "%1.", 320, fonts + "<w:b/><w:bCs/>") + "</w:abstractNum>",
               '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>']
        for i in range(self.nums):
            out.append(f'<w:num w:numId="{i + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:numbering {NS}>{"".join(out)}</w:numbering>'

    def styles(self):
        body, sans, z = self.f["body"], self.f["sans"], self.z
        def fonts(face): return f'<w:rFonts w:ascii="{face}" w:hAnsi="{face}" w:eastAsia="{EA}" w:cs="{face}"/>'
        lang = '<w:lang w:val="en-US" w:eastAsia="ko-KR" w:bidi="ar-SA"/>'
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles {NS}>'
                f'<w:docDefaults><w:rPrDefault><w:rPr>{fonts(body)}<w:color w:val="{INK}"/><w:sz w:val="{z["body"]}"/><w:szCs w:val="{z["body"]}"/>{lang}</w:rPr></w:rPrDefault>'
                f'<w:pPrDefault><w:pPr><w:spacing w:after="70" w:line="{LINE}" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
                '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr>{fonts(sans)}<w:b/><w:bCs/><w:color w:val="{ACCENT}"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="110" w:after="40"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr>{fonts(sans)}<w:b/><w:bCs/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>'
                '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/></w:style>'
                '<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/>'
                f'<w:pPr><w:spacing w:after="30" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="{z["note"]}"/><w:szCs w:val="{z["note"]}"/></w:rPr></w:style>'
                '<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/><w:basedOn w:val="DefaultParagraphFont"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>'
                '</w:styles>')


CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                 + "".join(f'<Override PartName="/word/{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{t}+xml"/>'
                           for n, t in (("document", "document.main"), ("styles", "styles"), ("numbering", "numbering"), ("footnotes", "footnotes"),
                                        ("settings", "settings"), ("footer1", "footer"), ("fontTable", "fontTable")))
                 + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{t}" Target="{t if t != "footer" else "footer1"}.xml"/>'
                      for i, t in enumerate(("styles", "numbering", "footnotes", "settings", "footer", "fontTable"), 1))
            + "</Relationships>")
SETTINGS = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:settings {NS}><w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>'
            '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
            '<w:themeFontLang w:val="en-US" w:eastAsia="ko-KR"/></w:settings>')
FONT_TABLE = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:fonts {NS}>'
              f'<w:font w:name="{EA}"><w:altName w:val="맑은 고딕"/><w:charset w:val="81"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
              '<w:font w:name="Georgia"><w:charset w:val="00"/><w:family w:val="roman"/><w:pitch w:val="variable"/></w:font>'
              '<w:font w:name="Arial"><w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font></w:fonts>')


def build(s, dst):
    """정리된 구조 s를 dst(.docx)에 쓴다. 각주 수를 돌려준다. 같은 입력이면 같은 바이트가 나오도록 날짜를 고정한다."""
    d = Doc(s).build()
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{_t(M.plain(s["head"]["re"]))}</dc:title><dc:creator>korean-tax-mcp</dc:creator></cp:coreProperties>')
    parts = [("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELS), ("word/document.xml", d.document()),
             ("word/_rels/document.xml.rels", DOC_RELS), ("word/styles.xml", d.styles()), ("word/numbering.xml", d.numbering()),
             ("word/footnotes.xml", d.footnotes()), ("word/settings.xml", SETTINGS), ("word/footer1.xml", d.footer()),
             ("word/fontTable.xml", FONT_TABLE), ("docProps/core.xml", core)]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data.encode("utf-8"))
    return len(d.notes)
