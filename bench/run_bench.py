"""정확도 측정 — 정답지: 국세청 「2025 세법해석 사례집」 96건(쟁점 ↔ 문서번호, 국세청이 짝지음).

1) 검색: 쟁점 문장으로 search → 사례집 문서번호가 상위 k 안에 있는지 (Recall@5, @10)
2) 인용 검증: 실제 번호 96개 → '확인', 일련번호를 바꾼 가짜 96개 → '미확인'
실행: python bench/run_bench.py  → bench/RESULTS.md
"""
import json, random, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from korean_tax_mcp import casebook, cite, ntis

cases = json.loads(casebook.IDX.read_text())
key = lambda t: re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")
t0 = time.time()
hits5 = hits10 = 0; miss = []
for c in cases:
    try: rs = ntis.search(c["쟁점"][:80], ("해석",), None, "정확도", 10)
    except Exception: rs = []
    ks = [key(r["문서번호"]) for r in rs]; g = key(c["문서번호"])
    hits5 += g in ks[:5]; hits10 += g in ks[:10]
    if g not in ks[:10]: miss.append(c["문서번호"])
n = len(cases)
random.seed(7)
def fake(no):
    m = re.search(r"(\d+)(?!.*\d)", no)
    if not m: return no + "9"
    w = len(m.group(1)); nv = str((int(m.group(1)) + random.randint(301, 899)) % (10 ** w)).zfill(w)
    return no[:m.start(1)] + nv + no[m.end(1):]
real_res = [cite._check_doc(c["문서번호"]) for c in cases]
real_ok = sum(r["결과"] == "확인" for r in real_res)
real_miss = [r["인용"] for r in real_res if r["결과"] != "확인"]
fake_res = [cite._check_doc(fake(c["문서번호"])) for c in cases]
fake_flag = sum(r["결과"] != "확인" for r in fake_res)
res = f"""# 정확도 측정 결과

- 정답지: 국세청 「2025 세법해석 사례집」 {n}건 (쟁점 ↔ 문서번호, 국세청이 짝지음)
- 측정일: {time.strftime('%Y-%m-%d')} · 소요 {int(time.time()-t0)}초 · 대상: 국세법령정보시스템 실시간 조회

| 항목 | 결과 |
|---|---|
| 검색 Recall@5 — 쟁점 문장으로 찾을 때 그 해석이 상위 5건 안 | **{hits5}/{n} ({hits5/n:.0%})** |
| 검색 Recall@10 | **{hits10}/{n} ({hits10/n:.0%})** |
| 인용 검증 — 실제 문서번호를 '확인' | **{real_ok}/{n} ({real_ok/n:.0%})** |
| 인용 검증 — 가짜 번호를 '미확인'으로 걸러냄 | **{fake_flag}/{n} ({fake_flag/n:.0%})** |

- 검색 상위 10건에 못 든 문서: {', '.join(miss) or '없음'}
- 실제 번호인데 '확인' 못 한 것: {', '.join(real_miss) or '없음'}

참고: 쟁점 문장을 그대로 넣은 검색이라 실제 질문(사실관계 서술)과는 다를 수 있음. 가짜 번호는 실제 번호의 일련번호만 바꾼 것이라 우연히 실존 번호와 겹칠 수 있음.
"""
Path(__file__).with_name("RESULTS.md").write_text(res); print(res)
