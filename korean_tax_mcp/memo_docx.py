"""세무 메모 Word(.docx) 그리기 — 외부 라이브러리 없이 OOXML을 직접 쓴다(zipfile). 작성 Mia(윤승미)

입력은 tax_memo.check가 정리한 구조. 모양: A4, 제목·머리 표, 번호 붙은 요약, 소제목, 표(머리·합계 음영, 우선순위 색),
실제 Word 각주(읽는 순서로 번호, 같은 출처는 '주 N 참조'), 바닥글 안내와 쪽 번호.
한글이 어느 환경에서나 보이도록 모든 글자 조각에 동아시아 글꼴(맑은 고딕)을 지정한다.
"""
import re
import zipfile
from xml.sax.saxutils import escape

from . import tax_memo as M

INK, MUTED, RULE, ACCENT, SOFT = "1F2933", "5F6B7A", "C9D1DA", "1F3A5F", "F3F6F9"
PAGE_W, PAGE_H = 11906, 16838          # A4
MARGIN_TB, MARGIN_LR = 1300, 1440
W = PAGE_W - 2 * MARGIN_LR             # 본문 너비 9026
EA = "Malgun Gothic"                   # 동아시아 글꼴: 윈도·맥용 Word에 들어 있음. 없으면 fontTable의 대체 이름으로
FONTS = {"en": {"body": "Georgia", "sans": "Arial"}, "ko": {"body": "Arial", "sans": "Arial"}}   # 한글은 eastAsia 글꼴로, 영문·숫자는 어디에나 있는 글꼴로
SIZE = {"en": {"body": 21, "cell": 20, "note": 17}, "ko": {"body": 20, "cell": 19, "note": 17}}
TAG = {0: ("FBE4E1", "9B2C1F"), 1: ("FDF1D6", "8A5A00"), 2: ("E4F2E7", "22663A")}   # 우선순위 칸 (바탕, 글자)
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_INLINE = re.compile(r"(\*\*.+?\*\*|\[\^[^\]\s]+\])", re.S)


def _t(text):
    return escape(_CTRL.sub("", text))


class Doc:
    def __init__(self, s):
        self.s = s; self.lang = s["lang"]; self.L = M.LABELS[self.lang]
        self.f = FONTS[self.lang]; self.z = SIZE[self.lang]
        self.body = []; self.notes = []; self.first = {}; self.nums = 0
        self.fn_text = {f["id"]: f["text"] for f in s["footnotes"]}

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
        """각주 참조 조각. 번호는 읽는 순서, 같은 출처가 다시 나오면 '주 N 참조'."""
        if key not in self.fn_text: return ""
        n = len(self.notes) + 1
        self.notes.append(self.L["see"].format(n=self.first[key]) if key in self.first else self.fn_text[key])
        self.first.setdefault(key, n)
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
    def p(self, runs, after=120, line=300, before=0, style="", num=None, ind=None, tabs="", border=False, keep=False, jc=""):
        pr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:keepNext/>" if keep else "")
        if num: pr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
        if border: pr += f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{RULE}"/></w:pBdr>'
        if tabs: pr += f"<w:tabs>{tabs}</w:tabs>"
        pr += f'<w:spacing w:before="{before}" w:after="{after}"' + (f' w:line="{line}" w:lineRule="auto"' if line else "") + "/>"
        if ind: pr += f'<w:ind w:left="{ind[0]}" w:hanging="{ind[1]}"/>'
        if jc: pr += f'<w:jc w:val="{jc}"/>'
        return f"<w:p><w:pPr>{pr}</w:pPr>{runs}</w:p>"

    def add(self, x): self.body.append(x)

    def h1(self, text):
        self.add(self.p(self.run(text, "sans", 23, bold=True, color=ACCENT), after=120, before=300, line=0, style="Heading1", keep=True))

    def h2(self, text):
        self.add(self.p(self.inline(text, notes=False, font="sans", size=20, bold=True), after=80, before=180, line=0, style="Heading2", keep=True))

    def rule(self):
        self.add(self.p("", after=160, line=0, border=True))

    def new_list(self):
        """번호 목록 하나 — 목록마다 1부터 다시 센다."""
        self.nums += 1
        return self.nums + 1          # numId 1은 글머리표

    # ── 표 ──
    def cell(self, runs, width, fill="", jc=""):
        para = runs if runs.startswith("<w:p>") else self.p(runs, after=0, line=280, jc=jc)
        edge = f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{RULE}"/><w:left w:val="nil"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="{RULE}"/><w:right w:val="nil"/>'
        return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:tcBorders>{edge}</w:tcBorders>'
                + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else "")
                + '<w:tcMar><w:top w:w="70" w:type="dxa"/><w:left w:w="110" w:type="dxa"/><w:bottom w:w="70" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tcMar>'
                + f"</w:tcPr>{para}</w:tc>")

    def table(self, widths, rows):
        """rows: [[칸 XML]] — 첫 행은 머리(쪽이 넘어가면 반복), 모든 행은 쪽 경계에서 갈라지지 않는다."""
        out = [f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr>'
               "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{x}"/>' for x in widths) + "</w:tblGrid>"]
        for i, cells in enumerate(rows):
            out.append("<w:tr><w:trPr><w:cantSplit/>" + ("<w:tblHeader/>" if i == 0 else "") + "</w:trPr>" + "".join(cells) + "</w:tr>")
        out.append("</w:tbl>")
        self.add("".join(out))

    def hd(self, text, width, jc=""):
        return self.cell(self.run(text, "sans", 17, bold=True, color=MUTED), width, SOFT, jc)

    def tc(self, text, width, bold=False, fill="", jc="", notes=True):
        return self.cell(self.inline(text, notes=notes, size=self.z["cell"], bold=bold), width, fill, jc)

    def calc_table(self, rows, currency):
        L = self.L; ws = [3700, 3000, 2326]
        amount = f'{L["amount"]} ({currency})' if currency else L["amount"]
        out = [[self.hd(L["item"], ws[0]), self.hd(L["basis_col"], ws[1], "right"), self.hd(amount, ws[2], "right")]]
        for r in rows:
            tot = r["role"] == "total"; fill = SOFT if tot else ""
            out.append([self.tc(r["item"], ws[0], tot, fill), self.tc(r["basis"] or "—", ws[1], tot, fill, "right"),
                        self.tc(r["amount"] or "—", ws[2], tot, fill, "right")])
        self.table(ws, out)

    # ── 본문 ──
    def build(self):
        s, L, z = self.s, self.L, self.z
        ko = self.lang == "ko"
        self.add(self.p(self.run(L["title"], "sans", 30, bold=True, color=ACCENT, spacing=40), after=140, line=0))
        for key, label in L["head"]:
            if not s["head"][key]: continue
            self.add(self.p(self.run(label if ko else label.upper(), "sans", 16, bold=True, color=MUTED) + self.run("", extra="<w:tab/>")
                            + self.inline(s["head"][key], notes=False), after=50, line=0, ind=(1500, 1500),
                            tabs='<w:tab w:val="left" w:pos="1500"/>'))
        self.rule()

        if s["summary"]:
            self.h1(L["summary"]); n = self.new_list()
            for it in s["summary"]:
                self.add(self.p(self.inline(it["conclusion"], bold=True) + self.run(" ") + self.inline(it["basis"]), after=110, num=n))
        k = 0
        if s["question"] or s["background"]:
            k += 1; self.h1(f'{k}. {L["background_question"] if s["background"] else L["question"]}')
            if s["background"]: self.add(self.p(self.inline(s["background"])))
            if s["question"]: self.add(self.p(self.inline(s["question"])))
        sa = s["short_answer"]
        if sa["answer"] or sa["conditions"]:
            k += 1; self.h1(f'{k}. {L["short_answer"]}')
            self.add(self.p(self.inline(sa["answer"], bold=True) + self.run(" ") + self.inline(sa["conditions"])))
        if s["facts"]:
            k += 1; self.h1(f'{k}. {L["facts"]}')
            point = {r["id"]: r["point"] for r in s["risks"]}
            for it in s["facts"]:
                runs = self.inline(it["text"])
                if it["changes_answer"] and point.get(it["risk"]):
                    runs += self.run(" " + L["if_not"].format(p=M.plain(point[it["risk"]])), italic=True, color=MUTED, size=z["body"] - 2)
                self.add(self.p(runs, after=80, line=290, num=1))
        if s["analysis"] or s["decision_table"]:
            k += 1; self.h1(f'{k}. {L["analysis"]}')
            for j, it in enumerate(s["analysis"], 1):
                self.h2(f'{k}.{j} {it["heading"]}')
                for key in ("rule", "application", "conclusion", "confirm"):
                    if not it[key]: continue
                    self.add(self.p(self.run(L[key] + ("  " if ko else " "), "sans" if ko else "body", bold=True,
                                             color=MUTED if key == "confirm" else INK, size=z["body"] - (1 if ko else 0))
                                    + self.inline(it[key]), after=90))
            dt = s["decision_table"]
            if dt and dt["columns"] and dt["rows"]:
                self.h2(dt["title"] or L["decision"])
                n = len(dt["columns"]); first = min(3600, W // n + 600) if n > 1 else W
                ws = [first] + [(W - first) // (n - 1)] * (n - 1) if n > 1 else [W]
                ws[-1] += W - sum(ws)
                rows = [[self.hd(c, ws[i]) for i, c in enumerate(dt["columns"])]]
                for r in dt["rows"]:
                    r = (r + [""] * n)[:n]
                    rows.append([self.tc(c, ws[i], bold=(i == n - 1)) for i, c in enumerate(r)])
                self.table(ws, rows)
        calc = s["calculation"]
        if calc:
            k += 1; self.h1(f'{k}. {L["calculation"]}')
            if calc["rows"]: self.calc_table(calc["rows"], calc["currency"])
            for sc in calc["scenarios"]:
                if not sc["rows"]: continue
                self.add(self.p(self.inline(sc["title"], notes=False, font="sans", size=18, bold=True, color=MUTED), before=200, after=80, line=0, keep=True))
                self.calc_table(sc["rows"], calc["currency"])
            if calc["note"]: self.add(self.p(self.inline(calc["note"], color=MUTED, size=z["body"] - 2), before=120))
        if s["risks"]:
            k += 1; self.h1(f'{k}. {L["risks"]}')
            ws = [1100, 2700, 5226]
            rows = [[self.hd(L["priority"], ws[0]), self.hd(L["point"], ws[1]), self.hd(L["why"], ws[2])]]
            for r in s["risks"]:
                rank = M.PRIORITIES[self.lang].index(r["priority"]) if r["priority"] in M.PRIORITIES[self.lang] else 1
                fill, color = TAG[rank]
                why = r["why"] + ((" " if r["why"] else "") + L["check"] + " " + r["check"] if r["check"] else "")
                rows.append([self.cell(self.run(r["priority"], "sans", 16, bold=True, color=color), ws[0], fill),
                             self.tc(r["point"], ws[1]), self.tc(why, ws[2])])
            self.table(ws, rows)
        if s["next_steps"]:
            k += 1; self.h1(f'{k}. {L["next_steps"]}'); n = self.new_list()
            for it in s["next_steps"]:
                tail = "; ".join(x for x in ((f'{L["owner"]}: {it["owner"]}' if it["owner"] else ""), (f'{L["by"]}: {it["deadline"]}' if it["deadline"] else "")) if x)
                self.add(self.p(self.inline(it["action"]) + (self.run(f" ({tail})", color=MUTED, size=z["body"] - 2) if tail else ""), after=110, num=n))
        if s["prepared_how"]:
            self.rule()
            self.add(self.p(self.run(L["how"] + " ", bold=True, size=18, color=MUTED) + self.inline(s["prepared_how"], notes=False, size=18, color=MUTED), line=280))
        return self

    # ── 파일 조각 ──
    def document(self):
        sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId5"/>'
                f'<w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
                f'<w:pgMar w:top="{MARGIN_TB}" w:right="{MARGIN_LR}" w:bottom="{MARGIN_TB}" w:left="{MARGIN_LR}" w:header="708" w:footer="600" w:gutter="0"/></w:sectPr>')
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>{"".join(self.body)}{sect}</w:body></w:document>'

    def footnotes(self):
        out = ['<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>',
               '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>']
        for n, text in enumerate(self.notes, 1):
            ref = '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>'
            body = self.run(" ", size=self.z["note"]) + self.inline(text, notes=False, size=self.z["note"])
            out.append(f'<w:footnote w:id="{n}"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/><w:spacing w:after="60"/></w:pPr>{ref}{body}</w:p></w:footnote>')
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
                '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
                '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="300" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr>{fonts(sans)}<w:b/><w:bCs/><w:color w:val="{ACCENT}"/><w:sz w:val="23"/><w:szCs w:val="23"/></w:rPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="180" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr>{fonts(sans)}<w:b/><w:bCs/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
                '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/></w:style>'
                '<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/>'
                f'<w:pPr><w:spacing w:after="60" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="{z["note"]}"/><w:szCs w:val="{z["note"]}"/></w:rPr></w:style>'
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
