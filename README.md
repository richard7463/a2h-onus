# ai2human Onus

*A2H Onus · 铁证 — by [ai2human](https://ai2human.io)*

> **The burden of proof is on the evidence.** 举证靠铁证，不靠自信。

**An open verification engine for AI agents — one call turns a claim + evidence into a verdict and a replayable receipt. Built on Jev/System One, with the guardrails production needs.**

> Your agent says the task is done. Do you believe it?
> Self-reported logs can't be trusted. Sending every output to a frontier model to review is slow and costs more than the task. Onus is the layer in between: `verify_claim(claim, evidence)` → `approved | rejected | needs_review` + a receipt anyone can replay.

---

## Why this exists

Agents produce claims all day — "tests pass", "the post is live", "the payment cleared", "the record matches". Something has to decide whether each claim is true before code acts on it. Today that's either brittle hand-written rules or an expensive LLM call that still gets forged evidence wrong.

Onus makes verification a **primitive**: call it, get a typed verdict and a receipt. It uses Jev for the semantic judgment — and it's designed around the fact that **Jev will sometimes be confidently wrong**. That assumption is the whole point:

1. **"Zero hallucination" is a wording trick.** Jev can't return an option outside your schema. It *can* confidently pick the wrong valid one. A 0.95 wrong verdict is still wrong.
2. **Don't let it compute what code can.** Nonce checks, timestamps, hash dedup — deterministic code, never the model.
3. **Confidence can't rescue weak evidence.** Forged-image detection tops ~80% even for frontier models. So evidence below a binding threshold never auto-passes, no matter the score.
4. **No single closed API is load-bearing.** The judgment backend is swappable: Jev, kev (local, free), or a model you train on your own logs.

---

## The architecture: four layers, each does one job

```
verify_claim(claim, evidence)
        │
        ▼
┌─────────────────────────────────────────────┐
│ L1  Provenance   — pure code, no model       │
│     nonce present? identity bound?           │
│     hash seen before? timestamp in window?   │
│     → assigns evidence grade E0–E4           │
├─────────────────────────────────────────────┤
│ L2  Perception   — (not in this release)     │
│     VLM extracts structured facts from images│
├─────────────────────────────────────────────┤
│ L3  Judgment     — Jev / kev (pluggable)     │
│     typed questions → probability + confidence│
│     only answers "is this genuine / does it  │
│     meet the criteria" — never touches money │
├─────────────────────────────────────────────┤
│ L4  Policy       — pure code, the only layer │
│     that decides. grade < E3 → never auto-   │
│     pass. (posterior, value, grade) → verdict│
└─────────────────────────────────────────────┘
        │
        ▼
  verdict + confidence + replayable receipt
```

**The design rules, one line each:**

- **Provenance in code, semantics in the model.** What a string match or a chain query can settle, the model never sees.
- **Judgment ≠ settlement.** The model outputs probabilities. Code decides the money.
- **The grade gate is absolute.** Evidence below E3 never auto-passes, no matter how confident Jev is.
- **The backend is pluggable.** `JUDGMENT_BACKEND=kev` (local, free) or `jev`. Speak "System One-compatible", not "Jev".
- **Every verdict ships a receipt.** Grade, model version, full distribution, hash. Anyone can replay *why* it passed.

---

## Quickstart

```bash
git clone https://github.com/richard7463/a2h-onus
cd a2h-onus
pip install -e .

# runs offline out of the box with a mock judge (no key, no server):
JUDGMENT_BACKEND=mock python examples/verify_x_post.py
JUDGMENT_BACKEND=mock python examples/verify_onchain.py   # E4, no model call
JUDGMENT_BACKEND=mock python examples/grade_gate_demo.py  # E1 @0.99 → review
```

**To run a real Jev judgment** (no TypeSafe waitlist needed — via OpenRouter):

```bash
export JUDGMENT_BACKEND=jev
export JEV_BASE_URL=https://openrouter.ai/api
export JEV_API_KEY=sk-or-...        # your OpenRouter key
export JEV_MODEL=jev-1.13.0           # pinned; never 'latest'
python examples/verify_x_post.py
```

Full walkthrough — key, first curl, first real receipt: [`docs/connect-jev.md`](docs/connect-jev.md).

As an MCP tool any agent can call:

```bash
python -m a2h_onus.mcp_server   # exposes verify_claim over MCP
```

---

## Measured on live Jev (jev-1.13.0, 2026-09-23)

| metric | value |
|---|---|
| judgment latency | ~0.4 s per check (30-case A/B set: 11.6–13.0 s total) |
| tokens per check | ~520–570 input on the `x_post` / `text` / `url` packs; ~390 on the 3-question smoke set |
| cost | ~$0.02 per 1,000 checks (at $0.042 / M input tokens, output free) |
| off-topic / low-effort submissions caught | 5/5 |
| pass threshold | 0.55, calibrated on the 30-case gate A/B set (`tests/gate_ab_bench.py`) — see note below |

**On the pass threshold.** Genuine submissions score 0.51–0.56, right on the
0.55 bar, so the auto-approve rate is noisy: four consecutive runs on
2026-09-23 gave 2, 3, 4 and 4 genuine approvals out of 10. The fraud figure is
stable: judge-alone approved 1/20 fraudulent submissions (5%) in every run, and
0/20 once the evidence-grade gate applies. Treat the auto-approve rate as
uncalibrated until it has a larger sample.

Small sample, reported as measured. Re-run `python -m tests.gate_ab_bench` with your own key to reproduce.

## Known limitations (read before relying on it)

This is an early release. Be clear about what it does **not** do yet:

- **Identity is not verified yet.** An account handle in `evidence.identity` is currently taken as given. A submitter can type any handle. Real binding (OAuth / wallet signature checked against your platform's records) is the next milestone.
- **Content is not fetched from the source yet.** For `x_post` and `url`, the text is whatever the submitter sends. Fetching the post / page ourselves is on the roadmap.
- **On-chain checks are stubbed.** The E4 path exists, but the RPC lookup is not wired in.
- **Duplicate detection is exact-match.** Change one character and it's a new hash.
- **No image understanding.** Screenshots always route to human review.

What it *is* good for today: a cheap first-pass filter — flag off-topic and low-effort submissions, never auto-approve screenshots, and send humans only what's left.

---

## The four traps, in detail

See [`docs/four-traps.md`](docs/four-traps.md) — the long version, with the specific failure each guardrail was built to catch.

---

## What this is not

- Not a task marketplace and not settlement — it decides *whether* a claim holds; what you do with the verdict is yours.
- Not an image forensics tool — L2 perception isn't in this release; image evidence routes to review.
- Not tied to Jev — kev, NanoJev, or a model you train on your own logs all drop in.

---

## License

MIT. Clone it, gut it, ship your own. The judgment logs you accumulate are the real moat — not this code.
