# Onus — Verification Benchmark

*Reproduce:* `JUDGMENT_BACKEND=mock python -m tests.run_benchmark_large`
*(seed=42, fully deterministic — you get the same numbers.)*

## Scope (read this first)

This benchmark tests the **deterministic defense layer** — provenance grading,
duplicate detection, the evidence-grade gate, and policy routing — against **700
labeled cases** across 7 attack categories.

**It measures:** does the pipeline *route* each kind of submission correctly —
reject replays and empty claims, refuse to auto-pass low-grade evidence, defer
ambiguous cases to human review, and let well-formed evidence through.

**It does NOT measure:** semantic accuracy of the judgment model. The judgment
layer runs as a mock here. Whether Jev correctly tells a genuine reply from a
fabricated one requires a live model and is reported separately (see "Pending"
below). **Do not read these numbers as "our AI is 100% accurate."**

## Results — 700 cases

| category | n | correct | rate | how it routed |
|---|---|---|---|---|
| genuine (well-formed) | 100 | 100 | 100% | approved 25 · review 75 |
| replay (duplicate) | 100 | 100 | 100% | rejected 100 |
| stolen_id (unbound) | 100 | 100 | 100% | review 100 |
| no_nonce (missing nonce) | 100 | 100 | 100% | review 100 |
| bare_screenshot (low grade) | 100 | 100 | 100% | review 100 |
| empty (no artifact) | 100 | 100 | 100% | rejected 100 |
| hard_ambiguous (boundary) | 100 | 100 | 100% | review 100 |
| **total** | **700** | **700** | **100%** | |

### Headline (deterministic layer)

| metric | value |
|---|---|
| overall correct routing | 700/700 (100%) |
| fraud/attack caught (not auto-approved) | 500/500 (100%) |
| **false-approval of fraud** | **0/500 (0.00%)** |
| genuine not wrongly rejected | 100/100 (100%) |
| bare screenshots auto-passed | **0** (grade gate) |

### Latency (deterministic layer, excludes the model call)

| pctile | ms |
|---|---|
| mean | 0.72 |
| p50 | 0.90 |
| p95 | 1.25 |
| p99 | 1.40 |
| max | 2.33 |

## What's honest to say from this

- **"0 fraudulent submissions out of 500 were auto-approved."** True, and it's
  the number that matters — the grade gate + provenance checks let nothing through.
- **"Every bare screenshot, at any value, routed to review — zero auto-passed."**
  True. This is the forged-image defense.
- **"Deterministic routing runs under 1.5ms at p95."** True.

- **The 25% auto-approve rate on genuine cases is a MOCK artifact, not a product
  number.** The mock judge is deliberately conservative, so many genuine cases
  land in the review band. The real rate depends on Jev's actual scores and can
  only be measured with a live model. Don't publish "25% auto-approve" as a
  product metric.

## Pending — measured once live Jev is connected

These require a live model + labeled genuine/forged samples:

- **Real auto-approve rate** (what % of genuine submissions clear without a human)
- **Judgment accuracy vs. human labels** on genuine-vs-forged content
- **Calibration**: does stated confidence match observed accuracy on our data
- **Adversarial**: confidence collapse under deliberately forged evidence

Each will be reported with the same scoping discipline.

---

*Dataset generator: `tests/run_benchmark_large.py` (700 cases, seed 42).
Small hand-labeled set: `tests/benchmark_cases.py` (17 cases).
Judgment backend: mock. Deterministic layer: production code path.*
