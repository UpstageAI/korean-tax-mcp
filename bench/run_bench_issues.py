"""쟁점별 검색 측정 — 사례집 96건을 3건씩 묶어 다쟁점 질문 32개로 만들고,
기존 search_tax_rulings(이은 문장 1회, n=15)와 search_rulings_by_issue(쟁점 3개, n_per=5)를 비교.
사전 등록: 세무사기출/실험기록.md "11/4 오전 · 쟁점별 판례 검색 측정 사전 등록".
실행: python bench/run_bench_issues.py → bench/RESULTS_issues.md, bench/issues_raw.json
"""
import json, random, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from korean_tax_mcp import casebook, server

cases = json.loads(casebook.IDX.read_text())
key = lambda t: re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")
order = list(range(len(cases))); random.Random(20261104).shuffle(order)
groups = [order[i:i + 3] for i in range(0, len(order), 3)]
t0 = time.time(); raw = []
a_hit = b_hit = b_hit_all = a_fail = b_fail = 0
for g in groups:
    issues = [cases[i]["쟁점"] for i in g]; golds = [key(cases[i]["문서번호"]) for i in g]
    ra = server.search_tax_rulings(query=" ".join(issues), sort="정확도", n=15)
    if "error" in ra: a_fail += 1; a_keys = []
    else: a_keys = [key(r["문서번호"]) for r in ra.get("결과", [])]
    rb = server.search_rulings_by_issue(issues=issues, n_per=5, recent_years=3)
    if "error" in rb: b_fail += 1; groups_b = []
    else: groups_b = rb.get("쟁점별", [])
    b_acc, b_all = [], []
    for grp in groups_b:
        if grp.get("오류"): b_fail += 1
        for r in grp.get("결과", []):
            k = key(r["문서번호"]); b_all.append(k)
            if r.get("선정") == "정확도": b_acc.append(k)
    ha = sum(gd in a_keys for gd in golds); hb = sum(gd in b_acc for gd in golds); hb2 = sum(gd in b_all for gd in golds)
    a_hit += ha; b_hit += hb; b_hit_all += hb2
    raw.append({"cases": g, "A_hits": ha, "B_hits": hb, "B_hits_with_recent": hb2, "A_n": len(a_keys), "B_acc_n": len(b_acc), "B_all_n": len(b_all)})
single_hit = single_fail = 0
for c in cases:
    r = server.search_rulings_by_issue(issues=[c["쟁점"][:80]], n_per=10, recent_years=0)
    grp = (r.get("쟁점별") or [{}])[0] if "error" not in r else {"오류": r["error"]}
    if grp.get("오류"): single_fail += 1
    single_hit += key(c["문서번호"]) in [key(x["문서번호"]) for x in grp.get("결과", [])]
n = len(cases); diff = (b_hit - a_hit) / n
ok = diff >= 0.10 and single_hit >= 89
Path(__file__).with_name("issues_raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1))
res = f"""# 쟁점별 검색 측정 결과

- 정답지: 국세청 「2025 세법해석 사례집」 {n}건을 3건씩 묶은 다쟁점 질문 {len(groups)}개 (seed 20261104)
- 측정일: {time.strftime('%Y-%m-%d %H:%M')} · 소요 {int(time.time()-t0)}초 · 국세법령정보시스템 실시간 조회

| 항목 | 결과 |
|---|---|
| 기존: 쟁점 3개를 이은 문장으로 1회 검색(15건) | **{a_hit}/{n} ({a_hit/n:.0%})** |
| 새 도구: 쟁점별 검색, 정확도 결과만(15건) | **{b_hit}/{n} ({b_hit/n:.0%})** |
| 새 도구: 최근 결과까지 포함 | {b_hit_all}/{n} ({b_hit_all/n:.0%}) |
| 회귀 확인: 쟁점 1개, 상위 10건 (기준선 91/96) | {single_hit}/{n} ({single_hit/n:.0%}) |

- 차이: {diff:+.0%}p · 통과선 +10%p 그리고 회귀 89건 이상 → **{'통과' if ok else '미통과'}**
- 호출 실패: 기존 {a_fail} · 새 도구 {b_fail} · 쟁점 1개 {single_fail}

참고: 사례집 쟁점 문장을 그대로 쓴 측정이라 실제 질문(사실관계 서술)과 다를 수 있음. 묶음은 무작위라 실제 한 문제 안의 쟁점들보다 서로 관계가 적음.
"""
Path(__file__).with_name("RESULTS_issues.md").write_text(res); print(res)
