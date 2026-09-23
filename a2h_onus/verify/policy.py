"""
L4 Policy layer + receipt — reference skeleton (NOT final code).

Pure code. This is the ONLY layer that decides the verdict.
The judgment layer gives probabilities; this layer decides money-adjacent actions.
"""
from __future__ import annotations
import math
import os
import json
import hashlib
from datetime import datetime, timezone

GRADE_ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}

TAU_REJECT = float(os.environ.get("TAU_REJECT", "0.30"))

# Pass bar. Calibrated 2026-09-23 against live jev-1.13.0 on the 30-case
# gate A/B set (tests/gate_ab_bench.py): real genuine scores landed 0.51-0.56,
# so the old 0.90 placeholder rejected everything. At 0.55 four consecutive
# runs approved 2, 3, 4 and 4 genuine cases out of 10 while fraudulent
# auto-approvals stayed at 0/20 -- genuine sits ON the bar, so that rate is
# noisy run to run and needs a larger sample. Override with TAU_PASS_BASE.
# Re-calibrate whenever the model version or the question packs change.
TAU_PASS_BASE = float(os.environ.get("TAU_PASS_BASE", "0.55"))


def tau_pass(value_usd: float) -> float:
    """Bar rises gently with the money at stake."""
    return min(0.99, TAU_PASS_BASE + 0.02 * math.log10(max(value_usd, 0.01) + 1))


def decide(posterior: float, value_usd: float, grade: str,
           hard_reason: str | None) -> tuple[str, list[str]]:
    """
    Returns (verdict, reasons).
    Order matters — grade gate sits ABOVE the posterior thresholds.
    """
    reasons: list[str] = []

    if hard_reason:
        return "rejected", [hard_reason]

    # --- GRADE GATE (hard rule): grade < E3 can never auto-pass ---
    if GRADE_ORDER.get(grade, 0) < GRADE_ORDER["E3"]:
        reasons.append("grade_gate_block")
        return "needs_review", reasons

    if posterior >= tau_pass(value_usd):
        reasons.append("auto_approved")
        return "approved", reasons

    if posterior < TAU_REJECT:
        reasons.append("low_posterior")
        return "rejected", reasons

    reasons.append("mid_band_review")
    return "needs_review", reasons


def build_receipt(*, evidence_grade: str, model_id: str, questions: dict,
                  distribution: dict, pipeline: list[str]) -> dict:
    record = {
        "evidence_grade": evidence_grade,
        "model_id": model_id,
        "questions": questions,
        "distribution": distribution,
        "pipeline": pipeline,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "replayable": True,
    }
    # stable stringify, exclude the hash itself, then SHA256
    stable = json.dumps(record, sort_keys=True, ensure_ascii=False)
    record["hash"] = "0x" + hashlib.sha256(stable.encode("utf-8")).hexdigest()
    return record


# ---- example glue: how verify_claim ties L1 -> L3 -> L4 ----
#
# def verify_claim(claim, evidence, acceptance_criteria=None, value_usd=0.0, nonce=None):
#     prov = run_provenance(claim, evidence, nonce)
#     grade = prov["grade"]
#
#     if prov["hard_reason"]:
#         verdict, reasons = decide(0.0, value_usd, grade, prov["hard_reason"])
#         return _assemble(verdict, 0.0, grade, {}, reasons, "deterministic", {}, {})
#
#     if evidence.get("type") == "image":
#         return _assemble("needs_review", 0.0, grade, {}, ["perception_not_implemented"],
#                          "deterministic", {}, {})
#
#     # E4 deterministic fast path (onchain_tx fully verified in L1)
#     if grade == "E4" and prov["signals"].get("api_verified"):
#         verdict, reasons = decide(1.0, value_usd, grade, None)
#         return _assemble(verdict, 1.0, grade, {"overall": 1.0}, reasons,
#                          "deterministic", {}, {})
#
#     pack = load_policy_pack(evidence["type"])
#     state = build_state(claim, acceptance_criteria, evidence, prov["signals"])
#     try:
#         jr = judge(state, pack["questions"])
#     except JudgmentUnavailable as e:
#         return _assemble("needs_review", 0.0, grade, {}, ["judgment_unavailable"],
#                          "unavailable", pack["questions"], {})
#
#     posterior = combine_posterior(jr["per_question"], pack["posterior_rule"])  # min(), not avg
#     verdict, reasons = decide(posterior, value_usd, grade, None)
#     receipt = build_receipt(evidence_grade=grade, model_id=jr["model_id"],
#                             questions=pack["questions"], distribution=jr["raw"],
#                             pipeline=["provenance", "judgment", "policy"])
#     return _assemble(verdict, posterior, grade, {"overall": posterior}, reasons,
#                      jr["model_id"], pack["questions"], jr["raw"], receipt)
