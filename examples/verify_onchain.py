"""E4 deterministic path: on-chain facts settle in code, no model call.

In production, provenance would query the chain and set api_verified=True.
Here we simulate that verified state to show the near-zero-cost path."""
import os, json
os.environ.setdefault("JUDGMENT_BACKEND", "mock")
from a2h_onus.verify.provenance import run_provenance
from a2h_onus.verify.policy import decide, build_receipt

# simulate a provenance result where the chain query already passed
evidence = {
    "type": "onchain_tx",
    "content": {"tx_hash": "0xabc", "chain": "base", "amount": "247.50",
                "token": "USDC", "block": 18442000},
    "artifact_hash": "0xdemo_tx_001",
    "identity": {"wallet": "0x7a3...f2", "signature": "0xsig"},
}
prov = run_provenance("held >= 100 USDC at block 18442000", evidence, nonce=None)
# in real code the RPC cross-check sets this; we set it to demo the fast path
prov["signals"]["api_verified"] = True
prov["grade"] = "E4"

verdict, reasons = decide(1.0, value_usd=0.01, grade="E4", hard_reason=None)
receipt = build_receipt(evidence_grade="E4", model_id="deterministic",
                        questions={}, distribution={}, pipeline=["provenance", "policy"])
print(json.dumps({"verdict": verdict, "reasons": reasons,
                  "cost": "$0.000 (no model invoked)",
                  "receipt_hash": receipt["hash"]}, indent=2))
