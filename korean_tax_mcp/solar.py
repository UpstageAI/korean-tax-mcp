"""Solar 호출 — Upstage 클라우드 또는 온프렘(망분리) 설치 Solar. OpenAI 호환 /chat/completions.

환경변수
- KOREAN_TAX_MCP_SOLAR_BASE_URL: 온프렘 Solar 주소(예: http://10.0.0.5:8000/v1). 없으면 https://api.upstage.ai/v1
- KOREAN_TAX_MCP_SOLAR_KEY: 온프렘 키(없으면 UPSTAGE_API_KEY, 온프렘에서 키가 필요 없으면 비워도 됨)
- KOREAN_TAX_MCP_MODEL: 모델 이름(기본 solar-pro4 — 온프렘 설치 이름에 맞게)
- KOREAN_TAX_MCP_SOLAR_VERIFY=0: 사내 자체 인증서일 때 TLS 검증 끄기
"""
import json
import os
import ssl
import urllib.request

CLOUD = "https://api.upstage.ai/v1"


def config():
    base = os.environ.get("KOREAN_TAX_MCP_SOLAR_BASE_URL", "").strip().rstrip("/") or CLOUD
    key = os.environ.get("KOREAN_TAX_MCP_SOLAR_KEY", "").strip() or os.environ.get("UPSTAGE_API_KEY", "").strip()
    return base, key, os.environ.get("KOREAN_TAX_MCP_MODEL", "solar-pro4"), base != CLOUD


def available():
    base, key, _, onprem = config()
    return onprem or bool(key)


def mode():
    """'solar_onprem' | 'solar_cloud' | 'host_ai'(Solar 설정 없음 — 판단은 사용자 AI가)."""
    base, key, _, onprem = config()
    return "solar_onprem" if onprem else "solar_cloud" if key else "host_ai"


def chat_json(prompt, max_tokens=1600, timeout=120):
    base, key, model, onprem = config()
    if not onprem and not key:
        raise RuntimeError("Solar 설정이 없습니다 — UPSTAGE_API_KEY(클라우드) 또는 KOREAN_TAX_MCP_SOLAR_BASE_URL(온프렘 Solar 주소)")
    ctx = ssl.create_default_context()
    if os.environ.get("KOREAN_TAX_MCP_SOLAR_VERIFY", "1") == "0":
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    h = {"Content-Type": "application/json"}
    if key: h["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(), method="POST", headers=h)
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        t = json.loads(r.read())["choices"][0]["message"]["content"]
    t = t[t.find("{"):t.rfind("}") + 1] if "{" in t else t   # 온프렘 모델이 JSON 앞뒤에 글을 붙이는 경우
    return json.loads(t)


def where(lang="ko"):
    base, _, model, onprem = config()
    if lang == "en": return f"{'on-prem' if onprem else 'Upstage cloud'} Solar ({model})"
    return f"{'온프렘' if onprem else 'Upstage 클라우드'} Solar ({model})"
