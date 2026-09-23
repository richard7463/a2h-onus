"""
L1 Provenance layer — reference skeleton (NOT final code).

Pure deterministic. NO model calls here, ever.
Rewrite/extend to match your existing ai2human_mcp conventions.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import os
from datetime import datetime, timezone, timedelta

from . import gitlawb

GRADE_ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}

DEDUP_DB = os.environ.get("DEDUP_DB", "./verify_dedup.sqlite")


def _dedup_seen(artifact_hash: str) -> bool:
    """Return True if this hash was seen before; record it if new."""
    conn = sqlite3.connect(DEDUP_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS seen (h TEXT PRIMARY KEY, ts TEXT)")
    row = conn.execute("SELECT 1 FROM seen WHERE h=?", (artifact_hash,)).fetchone()
    if row:
        conn.close()
        return True
    conn.execute("INSERT INTO seen (h, ts) VALUES (?, ?)",
                 (artifact_hash, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return False


def _content_hash(content) -> str:
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False) if isinstance(content, dict) else str(content)
    return "0x" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _in_window(ts: str, window_hours: float | None) -> bool:
    if not ts or window_hours is None:
        return True  # window not enforced by default
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - t) <= timedelta(hours=window_hours)


def run_provenance(claim: str, evidence: dict, nonce: str | None,
                   window_hours: float | None = None) -> dict:
    """
    Returns:
      {
        "grade": "E0".."E4",          # effective grade (after downgrades)
        "declared_grade": "...",
        "provenance_pass": bool,
        "hard_reason": str | None,    # set => hard reject, skip judgment
        "signals": {...}
      }
    """
    etype = evidence.get("type", "text")
    content = evidence.get("content", "")
    identity = evidence.get("identity") or {}
    ts = evidence.get("timestamp")

    artifact_hash = evidence.get("artifact_hash") or _content_hash(content)

    content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)

    signals = {
        "nonce_present": bool(nonce) and (nonce in content_str),
        "identity_bound": bool(identity.get("handle") or identity.get("wallet")),
        "timestamp_in_window": _in_window(ts, window_hours),
        "hash_unique": None,   # filled below
        "api_verified": False, # set True only after a real API/RPC cross-check
    }

    # --- gitlawb: a real API cross-check, and the only one wired today ---
    # A public node read needs no keypair, so we can confirm that a specific
    # commit exists under a specific owner. That proves the record, not the
    # quality of the work. Any failure leaves api_verified False: fail closed.
    if etype == "gitlawb_commit" and gitlawb.enabled():
        signals.update(gitlawb.check(content if isinstance(content, dict) else {}))

    # --- declared grade from evidence type (before downgrade) ---
    # E2 is NOT granted just because an artifact_hash exists — every submission
    # has one (we compute it). E2 requires genuine structured metadata on
    # non-image evidence. Images always cap at E1 (a hash of a screenshot is
    # still a screenshot). This is the grade the whole gate depends on, so it
    # must not be inflatable.
    has_metadata = (
        isinstance(content, dict)                       # structured payload
        or bool(identity.get("handle") or identity.get("wallet"))  # some binding
    )
    caller_supplied_hash = bool(evidence.get("artifact_hash"))

    if etype in ("onchain_tx", "x_post"):
        declared = "E4"   # only if you actually cross-check via API/RPC below
    elif etype == "gitlawb_commit":
        declared = "E4" if signals.get("api_verified") else "E1"
    elif nonce and signals["nonce_present"] and signals["identity_bound"]:
        declared = "E3"
    elif etype == "image":
        declared = "E1"   # images never exceed E1, hash or not
    elif etype in ("structured",) and has_metadata and caller_supplied_hash:
        declared = "E2"
    elif etype in ("text", "url") and has_metadata and caller_supplied_hash:
        declared = "E2"
    elif not content:
        declared = "E0"
    else:
        declared = "E1"

    # --- E0 hard reject ---
    if declared == "E0":
        return {"grade": "E0", "declared_grade": "E0", "provenance_pass": False,
                "hard_reason": "no_artifact", "signals": signals}

    # --- dedup (hard reject on duplicate) ---
    signals["hash_unique"] = not _dedup_seen(artifact_hash)
    if not signals["hash_unique"]:
        return {"grade": declared, "declared_grade": declared, "provenance_pass": False,
                "hard_reason": "duplicate_evidence", "signals": signals}

    # --- cross-check for E4 ---
    # gitlawb_commit is cross-checked above. Still TODO:
    #   For onchain_tx: query chain, verify tx hash / amount / address
    #   For x_post:     query platform API, verify post exists under target thread
    # If cross-check unavailable, DOWNGRADE (do not claim E4 you can't prove).
    if declared == "E4" and not signals["api_verified"]:
        declared = "E3" if (signals["nonce_present"] and signals["identity_bound"]) else "E1"

    # --- downgrade when E3 bindings fail ---
    effective = declared
    if declared == "E3" and not (signals["nonce_present"] and signals["identity_bound"]):
        effective = "E1"
    elif declared == "E2" and not signals["hash_unique"]:
        effective = "E1"

    # --- timestamp hard reject (only when window enforced) ---
    if window_hours is not None and not signals["timestamp_in_window"] and effective != "E4":
        return {"grade": effective, "declared_grade": declared, "provenance_pass": False,
                "hard_reason": "timestamp_out_of_window", "signals": signals}

    return {
        "grade": effective,
        "declared_grade": declared,
        "provenance_pass": True,
        "hard_reason": None,
        "signals": signals,
        "artifact_hash": artifact_hash,
    }
