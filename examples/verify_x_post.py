"""E3 social-post verification: nonce + identity bound -> judgment -> policy."""
import os, json
os.environ.setdefault("JUDGMENT_BACKEND", "mock")  # offline demo
from a2h_onus import verify_claim

result = verify_claim(
    claim="Replied to @brand's launch post with the task nonce",
    evidence={
        "type": "x_post",
        "content": 'Great launch! #A2H-7F3K',
        "artifact_hash": "0xdemo_xpost_001",
        "timestamp": "2026-09-22T10:00:00Z",
        "identity": {"platform": "x", "handle": "@alice"},
    },
    acceptance_criteria=["reply exists under the target post",
                         "reply contains the task nonce"],
    value_usd=0.02,
    nonce="#A2H-7F3K",
)
print(json.dumps(result, indent=2, ensure_ascii=False))
