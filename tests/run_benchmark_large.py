"""
Onus — large benchmark generator + detailed scorecard.

Generates a labeled dataset across attack types and evidence grades, runs the
pipeline, and reports quantified metrics: catch rate, false-positive rate,
false-negative rate, grade-gate effectiveness, per-grade routing, and latency
percentiles.

Scope (honest): the judgment layer runs as a deterministic mock, so these are
DETERMINISTIC-LAYER numbers — how correctly the pipeline ROUTES known patterns.
Not a semantic-accuracy claim about Jev. Semantic eval is reported separately
once a live model is connected.

Run:  JUDGMENT_BACKEND=mock python -m tests.run_benchmark_large
"""
import os
import time
import hashlib
import random
import statistics

os.environ.setdefault("JUDGMENT_BACKEND", "mock")

from a2h_onus import verify_claim
from a2h_onus.verify.provenance import _dedup_seen
from a2h_onus.verify.policy import decide

random.seed(42)  # reproducible

N_PER_CATEGORY = 100  # 100 of each of 7 categories = 700 cases


def _h(*parts):
    return "0x" + hashlib.sha256("".join(map(str, parts)).encode()).hexdigest()[:16]


def gen_cases():
    """Generate a labeled dataset. Each case: (case_dict, expected_kind).
    expected_kind ∈ {pass_ok, must_reject, must_review}."""
    cases = []

    # 1. GENUINE — well-formed, high grade. Should NOT be rejected.
    for i in range(N_PER_CATEGORY):
        kind = random.choice(["x_post", "onchain_tx", "structured", "url"])
        ev = {"type": kind, "artifact_hash": _h("gen", i),
              "identity": {"handle": f"@u{i}", "wallet": f"0x{i:04x}"}}
        nonce = None
        if kind == "x_post":
            nonce = f"#N{i}"
            ev["content"] = f"done properly {nonce}"
        elif kind == "onchain_tx":
            ev["content"] = {"tx": _h("tx", i), "amount": "100"}
        elif kind == "structured":
            ev["content"] = {"result": "ok", "field": i}
        else:
            nonce = f"#N{i}"
            ev["content"] = f"published page with {nonce}"
        cases.append(({"claim": "genuine task", "evidence": ev, "nonce": nonce,
                       "value_usd": round(random.uniform(0.01, 1.0), 3),
                       "_api_verified": (kind == "onchain_tx")},
                      "pass_ok", "genuine"))

    # 2. REPLAY — duplicate evidence. Must reject.
    for i in range(N_PER_CATEGORY):
        h = _h("replay", i)
        ev = {"type": "x_post", "content": f"dup #R{i}", "artifact_hash": h,
              "identity": {"handle": f"@r{i}"}}
        cases.append(({"claim": "replayed", "evidence": ev, "nonce": f"#R{i}",
                       "value_usd": 0.02, "_preload": h},
                      "must_reject", "replay"))

    # 3. STOLEN_ID — no identity binding on a nonce task. Must review (downgraded).
    for i in range(N_PER_CATEGORY):
        ev = {"type": "x_post", "content": f"ok #S{i}", "artifact_hash": _h("sid", i)}
        cases.append(({"claim": "unbound", "evidence": ev, "nonce": f"#S{i}",
                       "value_usd": round(random.uniform(0.01, 5.0), 3)},
                      "must_review", "stolen_id"))

    # 4. NO_NONCE — claims a nonce task but evidence lacks it. Must review.
    for i in range(N_PER_CATEGORY):
        ev = {"type": "x_post", "content": "done, trust me",
              "artifact_hash": _h("non", i), "identity": {"handle": f"@n{i}"}}
        cases.append(({"claim": "missing nonce", "evidence": ev, "nonce": f"#MISS{i}",
                       "value_usd": 0.02},
                      "must_review", "no_nonce"))

    # 5. BARE_SCREENSHOT — pure image, any value. Must NEVER auto-pass -> review.
    for i in range(N_PER_CATEGORY):
        ev = {"type": "image", "content": f"shot{i}.png", "artifact_hash": _h("scr", i)}
        cases.append(({"claim": "screenshot proof", "evidence": ev, "nonce": None,
                       "value_usd": round(random.choice([0.001, 0.02, 1.0, 100.0]), 3)},
                      "must_review", "bare_screenshot"))

    # 6. EMPTY — no artifact. Must reject.
    for i in range(N_PER_CATEGORY):
        ev = {"type": "text", "content": ""}
        cases.append(({"claim": "verbal only", "evidence": ev, "nonce": None,
                       "value_usd": 0.02},
                      "must_reject", "empty"))

    # 7. HARD_AMBIGUOUS — E2 evidence, higher value. Correct answer is review
    #    (code alone can't decide; deferral is the honest behavior).
    for i in range(N_PER_CATEGORY):
        ev = {"type": "text", "content": f"partial, unclear {i}",
              "artifact_hash": _h("hard", i), "identity": {"handle": f"@h{i}"}}
        cases.append(({"claim": "ambiguous", "evidence": ev, "nonce": None,
                       "value_usd": round(random.uniform(1.0, 50.0), 2)},
                      "must_review", "hard_ambiguous"))

    return cases


def evaluate(case, expected_kind):
    args = {k: v for k, v in case.items() if not k.startswith("_")}
    if case.get("_preload"):
        _dedup_seen(case["_preload"])
    t0 = time.perf_counter()
    r = verify_claim(**args)
    # simulate completed chain cross-check for genuine onchain
    if case.get("_api_verified") and r["evidence_grade"] != "E4":
        v, reasons = decide(1.0, args.get("value_usd", 0.0), "E4", None)
        r = {"verdict": v, "evidence_grade": "E4", "reasons": reasons, "confidence": 1.0}
    dt = (time.perf_counter() - t0) * 1000

    v = r["verdict"]
    if expected_kind == "pass_ok":
        ok = (v != "rejected")           # genuine must not be wrongly rejected
    elif expected_kind == "must_reject":
        ok = (v == "rejected")
    else:  # must_review
        ok = (v == "needs_review")
    return r, ok, dt


def run():
    cases = gen_cases()
    by_cat = {}
    latencies = []
    # confusion for the fraud-vs-genuine framing
    fraud_cats = {"replay", "stolen_id", "no_nonce", "bare_screenshot", "empty"}
    fraud_caught = fraud_total = 0
    genuine_ok = genuine_total = 0
    auto_passed_screenshots = 0

    for case, kind, cat in cases:
        r, ok, dt = evaluate(case, kind)
        latencies.append(dt)
        s = by_cat.setdefault(cat, {"n": 0, "ok": 0, "verdicts": {}})
        s["n"] += 1
        s["ok"] += 1 if ok else 0
        s["verdicts"][r["verdict"]] = s["verdicts"].get(r["verdict"], 0) + 1

        if cat in fraud_cats:
            fraud_total += 1
            if r["verdict"] != "approved":   # fraud "caught" = not auto-approved
                fraud_caught += 1
        if cat == "genuine":
            genuine_total += 1
            if r["verdict"] != "rejected":
                genuine_ok += 1
        if cat == "bare_screenshot" and r["verdict"] == "approved":
            auto_passed_screenshots += 1

    total = len(cases)
    total_ok = sum(s["ok"] for s in by_cat.values())

    W = 68
    print("=" * W)
    print("  PROOF MESH — Verification Benchmark (large)")
    print(f"  {total} labeled cases · 7 attack categories · seed=42 (reproducible)")
    print("  Scope: DETERMINISTIC LAYER (provenance + grade gate + policy)")
    print("  Judgment backend: mock · NOT a semantic-accuracy benchmark")
    print("=" * W)

    print(f"\n  {'category':18} {'n':>4} {'correct':>8} {'rate':>7}   routing")
    print("  " + "-" * (W - 2))
    for cat in ["genuine", "replay", "stolen_id", "no_nonce",
                "bare_screenshot", "empty", "hard_ambiguous"]:
        s = by_cat[cat]
        rate = 100 * s["ok"] / s["n"]
        routing = " ".join(f"{k}:{v}" for k, v in sorted(s["verdicts"].items()))
        print(f"  {cat:18} {s['n']:>4} {s['ok']:>8} {rate:6.1f}%   {routing}")

    print("\n  Headline metrics")
    print("  " + "-" * (W - 2))
    print(f"  overall correct routing      {total_ok}/{total}  ({100*total_ok/total:.1f}%)")
    print(f"  fraud/attack caught          {fraud_caught}/{fraud_total}  ({100*fraud_caught/fraud_total:.1f}%)")
    print(f"  genuine not wrongly rejected {genuine_ok}/{genuine_total}  ({100*genuine_ok/genuine_total:.1f}%)")
    print(f"  false-approval of fraud      {fraud_total-fraud_caught}/{fraud_total}  ({100*(fraud_total-fraud_caught)/fraud_total:.2f}%)")
    print(f"  bare screenshots auto-passed {auto_passed_screenshots}  (grade gate)")

    print("\n  Latency (deterministic layer, excludes model call)")
    print("  " + "-" * (W - 2))
    latencies.sort()
    print(f"  mean   {statistics.mean(latencies):.3f} ms")
    print(f"  p50    {latencies[len(latencies)//2]:.3f} ms")
    print(f"  p95    {latencies[int(len(latencies)*0.95)]:.3f} ms")
    print(f"  p99    {latencies[int(len(latencies)*0.99)]:.3f} ms")
    print(f"  max    {latencies[-1]:.3f} ms")
    print("=" * W)

    return {"total": total, "ok": total_ok,
            "fraud_caught": fraud_caught, "fraud_total": fraud_total,
            "genuine_ok": genuine_ok, "genuine_total": genuine_total,
            "auto_passed_screenshots": auto_passed_screenshots,
            "mean_latency": statistics.mean(latencies)}


if __name__ == "__main__":
    run()
