"""tp_comparability_review 정확도 — 판례 정답 세트(tests/fixtures/tp_review_gold.json)를 Solar로 판정해 판례 결론과 대조.

실행: UPSTAGE_API_KEY(또는 KOREAN_TAX_MCP_SOLAR_BASE_URL)를 환경변수로 두고
    python eval/tp_review_eval.py [--out 결과.json]
지표
- 방향 정확도: 판례가 부적정이라 한 후보에 '포함', 적정이라 한 후보에 '제외 후보'를 내지 않은 비율(허용 권고 안)
- 권고 일치: 정답 권고와 같은 비율
- 신호 일치: 정답 신호 중 모델 몫(문장 신호)의 판정이 같은 비율
- 근거 대조: 모델이 낸 근거 문장 중 원문에 그대로 있는 비율(없으면 도구가 불명으로 낮춤)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from korean_tax_mcp import solar  # noqa: E402
from korean_tax_mcp import tp_review as T  # noqa: E402

GOLD = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "tp_review_gold.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if solar.mode() == "host_ai":
        sys.exit("Solar 설정이 없습니다 — UPSTAGE_API_KEY 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL")
    items = json.load(open(GOLD, encoding="utf-8"))["문항"]
    rows, ok_dir, ok_rec, sig_hit, sig_n, q_ok, q_n = [], 0, 0, 0, 0, 0, 0
    for g in items:
        r = T.review(g["tested"], [g["candidate"]])
        if "error" in r:
            rows.append({"id": g["id"], "error": r["error"]})
            continue
        rec = r["후보별 권고"][0]
        got = {s["신호"]: s for s in rec["신호"]}
        d = rec["권고"] in g["허용 권고"]
        e = rec["권고"] == g["정답 권고"]
        ok_dir += d
        ok_rec += e
        miss = []
        for k, v in g["정답 신호"].items():
            if k in T.TEXT_SIGNALS and got.get(k, {}).get("판정 주체") != "도구(숫자)":
                sig_n += 1
                if got.get(k, {}).get("판정") == v:
                    sig_hit += 1
                else:
                    miss.append(f"{k}: 정답 {v} / 모델 {got.get(k, {}).get('판정')}")
        for s in rec["신호"]:
            if s.get("판정 주체") == "AI(문장)" and s.get("근거 문장"):
                q_n += 1
                q_ok += s.get("원문 확인") == "원문 일치"
        rows.append({"id": g["id"], "사건": g["사건"], "정답": g["정답 권고"], "권고": rec["권고"], "방향": d, "일치": e,
                     "확신도": rec["확신도"], "신호 불일치": miss, "이유": rec["이유"]})
    n = len(items)
    summary = {"문항": n, "방향 정확도": f"{ok_dir}/{n}", "권고 일치": f"{ok_rec}/{n}", "신호 일치": f"{sig_hit}/{sig_n}",
               "근거 대조(원문 일치)": f"{q_ok}/{q_n}", "모델": solar.where()}
    out = {"요약": summary, "문항별": rows}
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    for x in rows:
        print(json.dumps({k: x.get(k) for k in ("id", "정답", "권고", "방향", "신호 불일치", "error")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
