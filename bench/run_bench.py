"""정확도 측정 — 정답지: 국세청 「2025 세법해석 사례집」 96건(쟁점 ↔ 문서번호, 국세청이 짝지음).

1) 검색: 쟁점 문장으로 search → 사례집 문서번호가 상위 k 안에 있는지 (Recall@5, @10)
2) 인용 검증: 실제 번호 96개 → '확인', 일련번호를 바꾼 가짜 96개 → '미확인' (정확도·오탐)
실행: python bench/run_bench.py  → bench/RESULTS.md
"""
import json, random, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from korean_tax_mcp import casebook, cite, ntis

cases = json.loads(casebook.IDX.read_text())
key = lambda t: re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")
t0 = time.time()

# 1) 검색
hits5 = hits10 = 0; miss = []
for c in cases:
    try: rs = ntis.search(c["쟁점"][:80], ("해석",), None, "정확도", 10)
    except Exception: rs = []
    ks = [key(r["문서번호"]) for r in rs]; g = key(c["문서번호"])
    if g in ks[:5]: hits5 += 1
    if g in ks[:10]: hits10 += 1
    else: miss.append(c["문서번호"])
n = len(cases)

# 2) 인용 검증
random.seed(7)
def fake(no):
    m = re.search(r"(\d+)(?!.*\d)", no)
    if not m: return no + "9"
    v = int(m.group(1)); nv = str((v + random.randint(301, 899)) % (10 ** len(m.group(1)))).zfill(len(m.group(1)))
    return no[:m.start(1)] + nv + no[m.end(1):]
real_ok = sum(1 for c in cases if cite._check_doc(c["문서번호"])["결과"] == "확인")
fakes = [fake(c["문서번호"]) for c in cases]
fake_flag = sum(1 for f in fakes if cite._check_doc(f)["결과"] != "확인")

res = f"""# 정확도 측정 결과

- 정답지: 국세청 「2025 세법해석 사례집」 {n}건 (쟁점 ↔ 문서번호)
- 측정일: {time.strftime('%Y-%m-%d')} · 소요 {int(time.time()-t0)}초

| 항목 | 결과 |
|---|---|
| 검색 Recall@5 (쟁점 문장 → 그 문서가 상위 5건 안) | **{hits5}/{n} ({hits5/n:.0%})** |
| 검색 Recall@10 | **{hits10}/{n} ({hits10/n:.0%})** |
| 인용 검증 — 실제 문서번호를 '확인' | **{real_ok}/{n} ({real_ok/n:.0%})** |
| 인용 검증 — 가짜 번호를 '미확인'으로 걸러냄 | **{fake_flag}/{n} ({fake_flag/n:.0%})** |

검색에서 상위 10건에 못 든 문서: {', '.join(miss[:20])}{' …' if len(miss) > 20 else ''}

참고: 쟁점 문장을 그대로 넣은 검색이라 실제 질문(사실관계 서술)과는 다를 수 있음. 가짜 번호는 실제 번호의 일련번호만 바꾼 것 — 우연히 실존 번호가 될 수 있음.
"""
Path(__file__).with_name("RESULTS.md").write_text(res)
print(res)
