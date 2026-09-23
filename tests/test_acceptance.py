"""Tests mirror the 7 acceptance criteria in the spec.
Run with: JUDGMENT_BACKEND=mock python -m pytest tests/ -v
"""
import os
os.environ["JUDGMENT_BACKEND"] = "mock"

from a2h_onus import verify_claim
from a2h_onus.verify.policy import decide


def test_grade_gate_blocks_high_confidence_low_grade():
    """AC5: E1 evidence with posterior 0.99 must still be needs_review."""
    verdict, reasons = decide(0.99, value_usd=0.02, grade="E1", hard_reason=None)
    assert verdict == "needs_review"
    assert "grade_gate_block" in reasons


def test_image_routes_to_review():
    """AC3: image evidence -> needs_review (perception not implemented)."""
    r = verify_claim("did the thing", {"type": "image", "content": "photo",
                                       "artifact_hash": "0ximg1"})
    assert r["verdict"] == "needs_review"
    assert "perception_not_implemented" in r["reasons"]


def test_duplicate_evidence_hard_rejects():
    """AC4: same artifact_hash twice -> reject."""
    ev = {"type": "text", "content": "x", "artifact_hash": "0xdup_test_unique"}
    first = verify_claim("c", ev, value_usd=0.01)
    second = verify_claim("c", ev, value_usd=0.01)
    assert second["verdict"] == "rejected"
    assert "duplicate_evidence" in second["reasons"]


def test_receipt_is_reproducible_shape():
    """AC7: receipt carries the required fields."""
    r = verify_claim("c", {"type": "text", "content": "y",
                           "artifact_hash": "0xrcpt_test"}, value_usd=0.01)
    rc = r["receipt"]
    assert rc["replayable"] is True
    assert "hash" in rc and rc["hash"].startswith("0x")
    assert rc["pipeline"][0] == "provenance"


def test_e0_no_artifact_rejects():
    r = verify_claim("c", {"type": "text", "content": ""}, value_usd=0.01)
    assert r["verdict"] == "rejected"


def test_image_never_exceeds_e1():
    """Regression: an artifact_hash must NOT inflate a screenshot to E2.
    Images cap at E1 regardless of hash."""
    from a2h_onus.verify.provenance import run_provenance
    r = run_provenance("x", {"type": "image", "content": "photo",
                             "artifact_hash": "0ximg_grade"}, nonce=None)
    assert r["grade"] == "E1", f"image graded {r['grade']}, expected E1"


def test_e2_requires_metadata_not_just_hash():
    """Regression: bare text with a hash but no binding is E1, not E2.
    E2 requires genuine metadata/identity."""
    from a2h_onus.verify.provenance import run_provenance
    bare = run_provenance("x", {"type": "text", "content": "blah",
                                "artifact_hash": "0xbare"}, nonce=None)
    assert bare["grade"] == "E1"
    bound = run_provenance("x", {"type": "text", "content": "blah",
                                 "artifact_hash": "0xbound",
                                 "identity": {"handle": "@a"}}, nonce=None)
    assert bound["grade"] == "E2"


def test_parses_official_response_shape():
    """Regression: parse the exact response shape from TypeSafe's docs.
    Guards against the field-name guess that was wrong before."""
    from a2h_onus.verify.judgment import _parse_answers
    official = {  # real reply from jev-1.13.0, 2026-09-23
        "model": "jev-1.13.0",
        "answers": {
            "refund": {"type": "noul", "noul": 0.98},
            "dept": {"type": "choice", "choice": "billing", "confidence": 1.0,
                     "probabilities": {"technical": 0.0, "billing": 1.0, "sales": 0.0}},
            "urgency": {"type": "score", "score": 1.45, "confidence": 0.49,
                        "legend": {"0": "can wait", "1": "this week", "2": "today", "3": "right now"},
                        "probabilities": {"0": 0.03, "1": 0.52, "2": 0.42, "3": 0.03}},
        },
        "usage": {"input_tokens": 392, "output_tokens": 69},
    }
    pq = _parse_answers(official, "jev-1.13")
    assert pq["refund"]["type"] == "noul"
    assert pq["refund"]["confidence"] == 0.98
    assert pq["refund"]["distribution"]["true"] == 0.98
    assert pq["dept"]["value"] == "billing"
    assert pq["dept"]["confidence"] == 1.0
    assert pq["urgency"]["value"] == 1.45        # float position, not an int level
    assert pq["urgency"]["confidence"] == 0.49   # the reply's own confidence, not max(probs)
    """Regression: when the grade gate overrules the model, reported confidence
    must be 0.0 (not the raw posterior), with the raw score kept in
    gated_posterior for audit."""
    r = verify_claim("x", {"type": "text", "content": "a screenshot",
                           "artifact_hash": "0xgated"}, value_usd=0.02)
    if "grade_gate_block" in r["reasons"]:
        assert r["confidence"] == 0.0
        assert "gated_posterior" in r


def test_verify_batch_summary():
    """verify_batch returns per-item results and a dashboard summary."""
    from a2h_onus import verify_batch
    out = verify_batch([
        {"claim": "a", "evidence": {"type": "text", "content": ""}, "value_usd": 0.01},
        {"claim": "b", "evidence": {"type": "image", "content": "s.png",
                                    "artifact_hash": "0xbatch2"}, "value_usd": 0.02},
    ])
    assert out["summary"]["total"] == 2
    rates = out["summary"]["auto_approve_rate"] + out["summary"]["review_rate"] + out["summary"]["reject_rate"]
    assert abs(rates - 1.0) < 1e-6
    assert len(out["results"]) == 2
