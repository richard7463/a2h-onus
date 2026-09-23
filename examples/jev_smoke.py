"""Step 1 with a real key: call Jev once and print the RAW reply.

    export TYPESAFE_API_KEY=你的key
    python examples/jev_smoke.py

Paste the printed JSON back (NOT the key) so the parser can be checked
against the real noul / choice / score shapes.
"""
import json
import os
import sys
import time

import requests

key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
if not key:
    sys.exit("先设置 key:  export TYPESAFE_API_KEY=你的key")

base = os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai")
model = os.environ.get("JEV_MODEL", "jev-1.13.0")

body = {
    "model": model,
    "state": "My card was charged twice for invoice INV-9921.",
    "questions": {
        "billing": {"type": "noul",
                    "instructions": "The message is about a billing problem."},
        "team": {"type": "choice", "instructions": "Which team should handle this?",
                 "criteria": {"billing": "Payments", "technical": "Bugs", "sales": "Pricing"}},
        "urgency": {"type": "score", "instructions": "How urgent?",
                    "criteria": ["can wait", "this week", "today", "right now"]},
    },
}

t0 = time.perf_counter()
r = requests.post(f"{base}/v1/systemone",
                  headers={"Authorization": f"Bearer {key}",
                           "Content-Type": "application/json"},
                  json=body, timeout=15)
ms = (time.perf_counter() - t0) * 1000

print(f"HTTP {r.status_code}  ·  {ms:.0f} ms  ·  model={model}")
try:
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except ValueError:
    print(r.text[:2000])

if r.status_code == 400 and "model" in r.text.lower():
    print("\n模型名不对？试试: export JEV_MODEL=jev-1.13  或  jev-latest")
