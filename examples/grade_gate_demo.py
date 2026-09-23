"""The grade gate: even a 0.99 posterior on E1 evidence must NOT auto-pass."""
import json
from a2h_onus.verify.policy import decide

# pretend the model was very confident (0.99) but evidence is only E1
verdict, reasons = decide(posterior=0.99, value_usd=0.02, grade="E1", hard_reason=None)
print(json.dumps({
    "posterior": 0.99,
    "evidence_grade": "E1",
    "verdict": verdict,          # -> needs_review
    "reasons": reasons,          # -> ["grade_gate_block"]
    "lesson": "confidence is cheap; evidence grade is the gate."
}, indent=2))
