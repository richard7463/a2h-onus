"""
verify_claim — the orchestrator that wires L1 (provenance) -> L3 (judgment) -> L4 (policy).

This is a working reference. Swap in your real chain/API cross-checks where marked TODO.
The design rules are enforced here and MUST NOT be relaxed:
  - grade < E3 never auto-passes (grade gate lives in policy.decide)
  - provenance is deterministic; the model never sees what code can settle
  - judgment outputs probabilities; policy decides the verdict
  - every verdict ships a replayable receipt
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from .provenance import run_provenance, GRADE_ORDER
from .judgment import judge, JudgmentUnavailable
from .policy import decide, build_receipt

_PACK_DIR = Path(__file__).parent / "policy_packs"


def _load_pack(evidence_type: str) -> dict:
    fname = {
        "x_post": "x_post.json",
        "onchain_tx": "onchain_tx.json",
        "url": "url.json",
        "text": "text.json",
        "structured": "text.json",
    }.get(evidence_type, "text.json")
    return json.loads((_PACK_DIR / fname).read_text(encoding="utf-8"))


def _combine_posterior(per_question: dict, pack: dict) -> float:
    """Conjunctive combine: the weakest independent criterion caps the posterior.
    We deliberately use min(), not mean() — averaging lets one strong signal
    mask a failing one (see docs/four-traps.md, trap 1)."""
    noul_ps = []
    for qname, ans in per_question.items():
        # Only conjoin the yes/no (noul) criteria. score questions
        # (e.g. evidence_quality) are diagnostic, not gating.
        if ans.get("type") and ans.get("type") != "noul":
            continue
        dist = ans.get("distribution") or {}
        p_true = dist.get("true", dist.get("True", ans.get("confidence")))
        # legacy guard for packs without explicit type
        if ans.get("type") is None and (qname == "evidence_quality" or "priority" in qname):
            continue
        if p_true is not None:
            try:
                noul_ps.append(float(p_true))
            except (TypeError, ValueError):
                pass
    return min(noul_ps) if noul_ps else 0.0


def _assemble(verdict, posterior, grade, per_criterion, reasons,
              model_id, questions, distribution, receipt=None):
    if receipt is None:
        receipt = build_receipt(evidence_grade=grade, model_id=model_id,
                                questions=questions, distribution=distribution,
                                pipeline=["provenance", "judgment", "policy"])
    return {
        "verdict": verdict,
        "confidence": round(float(posterior), 4),
        "evidence_grade": grade,
        "posterior": {"per_criterion": per_criterion, "overall": round(float(posterior), 4)},
        "reasons": reasons,
        "receipt": receipt,
    }


def verify_claim(claim: str, evidence: dict, acceptance_criteria: list[str] | None = None,
                 value_usd: float = 0.0, nonce: str | None = None) -> dict:
    """Verify a claim. Returns verdict + confidence + replayable receipt.
    Does NOT create a task and does NOT move funds."""
    acceptance_criteria = acceptance_criteria or [claim]

    # --- L1 provenance (deterministic) ---
    prov = run_provenance(claim, evidence, nonce)
    grade = prov["grade"]

    if prov["hard_reason"]:
        verdict, reasons = decide(0.0, value_usd, grade, prov["hard_reason"])
        return _assemble(verdict, 0.0, grade, [], reasons, "deterministic", {}, {})

    # --- L2 perception not implemented: image evidence routes to review ---
    if evidence.get("type") == "image":
        return _assemble("needs_review", 0.0, grade, [],
                         ["perception_not_implemented"], "deterministic", {}, {})

    # --- E4 deterministic fast path: no model, near-zero cost ---
    if grade == "E4" and prov["signals"].get("api_verified"):
        verdict, reasons = decide(1.0, value_usd, grade, None)
        return _assemble(verdict, 1.0, grade,
                         [{"criterion": "deterministic", "p": 1.0}], reasons,
                         "deterministic", {}, {})

    # --- L3 judgment (pluggable backend) ---
    pack = _load_pack(evidence.get("type", "text"))
    state = {
        "claim": claim,
        "acceptance_criteria": acceptance_criteria,
        "evidence_content": evidence.get("content", ""),
        "l1_signals": prov["signals"],
    }
    try:
        jr = judge(state, pack["questions"])
    except JudgmentUnavailable:
        return _assemble("needs_review", 0.0, grade, [],
                         ["judgment_unavailable"], "unavailable",
                         pack["questions"], {})

    posterior = _combine_posterior(jr["per_question"], pack)
    per_criterion = [{"criterion": q, "p": (a.get("confidence") or 0.0)}
                     for q, a in jr["per_question"].items()]

    # --- L4 policy (the only layer that decides) ---
    verdict, reasons = decide(posterior, value_usd, grade, None)

    # When the grade gate overrules the judgment, the raw posterior is NOT the
    # decision confidence — the score was set aside. Report it honestly: surface
    # confidence 0.0 for the decision, but keep the raw model score in the
    # receipt (gated_posterior) so it stays auditable. (Fixes the misleading
    # "conf=0.75 + grade_gate_block" display found in testing.)
    reported_conf = posterior
    if "grade_gate_block" in reasons:
        reported_conf = 0.0

    result = _assemble(verdict, reported_conf, grade, per_criterion, reasons,
                       jr["model_id"], pack["questions"], jr["raw"])
    if "grade_gate_block" in reasons:
        result["gated_posterior"] = round(float(posterior), 4)
    return result


def verify_batch(items: list[dict]) -> dict:
    """Verify many claims in one call — the common case when an agent has a
    stream of outputs to check. Each item is a dict of verify_claim kwargs:
        {"claim": ..., "evidence": {...}, "value_usd": ..., "nonce": ...}
    Returns per-item results plus a summary (auto-approve rate, review rate,
    reject rate) — the numbers you'd actually put on a dashboard.

    Note: this is a convenience wrapper; each item is verified independently so
    one bad item can't corrupt the others. A future version can batch the
    judgment-layer calls into a single System One request for lower latency.
    """
    results = []
    counts = {"approved": 0, "rejected": 0, "needs_review": 0}
    for it in items:
        r = verify_claim(
            claim=it.get("claim", ""),
            evidence=it.get("evidence", {}),
            acceptance_criteria=it.get("acceptance_criteria"),
            value_usd=it.get("value_usd", 0.0),
            nonce=it.get("nonce"),
        )
        results.append(r)
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    n = len(results) or 1
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "approved": counts["approved"],
            "rejected": counts["rejected"],
            "needs_review": counts["needs_review"],
            "auto_approve_rate": round(counts["approved"] / n, 4),
            "review_rate": round(counts["needs_review"] / n, 4),
            "reject_rate": round(counts["rejected"] / n, 4),
        },
    }
