"""
Onus verification benchmark — labeled test set.

Each case has ground-truth `expected` verdict. We measure how the
deterministic defense (provenance + grade gate + policy) handles known
attack patterns. Judgment layer is mock here — so these numbers are the
DETERMINISTIC-LAYER BASELINE, not a semantic-accuracy claim.

Categories:
  genuine        — legitimate submissions that SHOULD pass or review
  replay         — resubmitting previously-seen evidence (dup hash)
  stolen_id      — evidence without proper identity binding
  no_nonce       — claims a nonce task but evidence lacks the nonce
  bare_screenshot— pure image / low-grade, must never auto-pass
  empty          — no artifact at all
"""

CASES = [
    # ---- genuine (well-formed, high grade) ----
    {"id": "gen-1", "category": "genuine",
     "claim": "replied to @brand launch post with nonce",
     "evidence": {"type": "x_post", "content": "Great launch! #A2H-7F3K",
                  "artifact_hash": "0xgen1", "identity": {"handle": "@alice"}},
     "nonce": "#A2H-7F3K", "value_usd": 0.02,
     "expected_not": ["rejected"]},   # should be approved or review, never rejected

    {"id": "gen-2", "category": "genuine",
     "claim": "held >= 100 USDC at block",
     "evidence": {"type": "onchain_tx",
                  "content": {"tx": "0x1", "amount": "247.5"},
                  "artifact_hash": "0xgen2",
                  "identity": {"wallet": "0x7a3"}},
     "nonce": None, "value_usd": 0.01, "api_verified": True,
     "expected": "approved"},

    {"id": "gen-3", "category": "genuine",
     "claim": "submitted structured report with binding",
     "evidence": {"type": "structured", "content": {"field": "value"},
                  "artifact_hash": "0xgen3", "identity": {"handle": "@bob"}},
     "nonce": None, "value_usd": 0.05,
     "expected_not": ["rejected"]},

    # ---- replay (duplicate evidence) ----
    {"id": "rep-1", "category": "replay",
     "claim": "replied with nonce",
     "evidence": {"type": "x_post", "content": "ok #A2H-1", "artifact_hash": "0xREPLAY",
                  "identity": {"handle": "@a"}},
     "nonce": "#A2H-1", "value_usd": 0.02, "expected": "rejected",
     "preload_hash": "0xREPLAY"},   # mark as already-seen before running

    {"id": "rep-2", "category": "replay",
     "claim": "onchain proof reused",
     "evidence": {"type": "onchain_tx", "content": {"tx": "0x2"},
                  "artifact_hash": "0xREPLAY2", "identity": {"wallet": "0x9"}},
     "nonce": None, "value_usd": 0.10, "expected": "rejected",
     "preload_hash": "0xREPLAY2"},

    # ---- stolen_id / unbound ----
    {"id": "sid-1", "category": "stolen_id",
     "claim": "replied with nonce but no identity binding",
     "evidence": {"type": "x_post", "content": "ok #A2H-2", "artifact_hash": "0xsid1"},
     "nonce": "#A2H-2", "value_usd": 0.02, "expected": "needs_review"},  # grade downgraded -> gate

    # ---- no_nonce (claims nonce task, evidence lacks it) ----
    {"id": "non-1", "category": "no_nonce",
     "claim": "claims completion but nonce absent from content",
     "evidence": {"type": "x_post", "content": "done, trust me",
                  "artifact_hash": "0xnon1", "identity": {"handle": "@a"}},
     "nonce": "#A2H-3", "value_usd": 0.02, "expected": "needs_review"},

    # ---- bare_screenshot (must never auto-pass) ----
    {"id": "scr-1", "category": "bare_screenshot",
     "claim": "screenshot of completed work",
     "evidence": {"type": "image", "content": "screenshot.png", "artifact_hash": "0xscr1"},
     "nonce": None, "value_usd": 0.02, "expected": "needs_review"},

    {"id": "scr-2", "category": "bare_screenshot",
     "claim": "photo proof, high value task",
     "evidence": {"type": "image", "content": "photo.jpg", "artifact_hash": "0xscr2"},
     "nonce": None, "value_usd": 100.0, "expected": "needs_review"},

    # ---- empty ----
    {"id": "emp-1", "category": "empty",
     "claim": "verbal claim only",
     "evidence": {"type": "text", "content": ""},
     "nonce": None, "value_usd": 0.02, "expected": "rejected"},

    # ---- more genuine, varied grades ----
    {"id": "gen-4", "category": "genuine",
     "claim": "url resource with binding",
     "evidence": {"type": "url", "content": "published page with #A2H-9 nonce",
                  "artifact_hash": "0xgen4", "identity": {"handle": "@c"}},
     "nonce": "#A2H-9", "value_usd": 0.03, "expected_not": ["rejected"]},
    {"id": "gen-5", "category": "genuine",
     "claim": "onchain micro-payment",
     "evidence": {"type": "onchain_tx", "content": {"tx": "0x5", "amount": "10"},
                  "artifact_hash": "0xgen5", "identity": {"wallet": "0x5"}},
     "nonce": None, "value_usd": 0.005, "api_verified": True,
     "expected": "approved"},

    # ---- more replay ----
    {"id": "rep-3", "category": "replay",
     "claim": "text report resubmitted",
     "evidence": {"type": "text", "content": "same report",
                  "artifact_hash": "0xREPLAY3", "identity": {"handle": "@d"}},
     "nonce": None, "value_usd": 0.02, "expected": "rejected",
     "preload_hash": "0xREPLAY3"},

    # ---- more bare screenshots at various values ----
    {"id": "scr-3", "category": "bare_screenshot",
     "claim": "screenshot, tiny value",
     "evidence": {"type": "image", "content": "s.png", "artifact_hash": "0xscr3"},
     "nonce": None, "value_usd": 0.001, "expected": "needs_review"},

    # ---- stolen id, onchain without signature binding ----
    {"id": "sid-2", "category": "stolen_id",
     "claim": "onchain claim without wallet binding",
     "evidence": {"type": "onchain_tx", "content": {"tx": "0x8"},
                  "artifact_hash": "0xsid2"},
     "nonce": None, "value_usd": 0.05, "expected": "needs_review"},

    # ---- HARD: boundary/ambiguous cases that expose real limits ----
    # These are where the deterministic layer alone is INSUFFICIENT and the
    # design correctly defers to review rather than guessing. A benchmark that
    # only shows wins is a benchmark you can't trust.
    {"id": "hard-1", "category": "hard_ambiguous",
     "claim": "E2 evidence, mid value — genuinely needs a human",
     "evidence": {"type": "text", "content": "partial completion, unclear",
                  "artifact_hash": "0xhard1", "identity": {"handle": "@e"}},
     "nonce": None, "value_usd": 2.0, "expected": "needs_review",
     "note": "correct behavior is deferral, not a confident auto-decision"},
    {"id": "hard-2", "category": "hard_ambiguous",
     "claim": "nonce present but content otherwise thin",
     "evidence": {"type": "x_post", "content": "#A2H-H2",
                  "artifact_hash": "0xhard2", "identity": {"handle": "@f"}},
     "nonce": "#A2H-H2", "value_usd": 50.0, "expected": "needs_review",
     "note": "high value forces stricter threshold -> review even at E3"},
]
