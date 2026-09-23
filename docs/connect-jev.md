# Connecting to Jev: your first real judgment

> Goal: make `verify_claim` actually call Jev once and come back with a **real**
> judgment and a real receipt.
> Every response shape below was taken from a live call on 2026-09-23, not from
> documentation.

---

## Getting a key

TypeSafe has self-serve signup. No waitlist, no invitation:

1. Open <https://console.typesafe.ai> — it redirects to the sign-in page.
2. Continue with Google, or choose "Email me a code instead" and enter the code.
3. Create an API key in the console.

TypeSafe origin: `https://api.typesafe.ai`. Keys are sent as
`Authorization: Bearer <key>`.

**Equivalent gateways.** The same `/v1/systemone` contract is offered by other
gateways, and this repository accepts any of them through `JEV_BASE_URL`:

- OpenRouter — `https://openrouter.ai/api`
- Opper — `https://api.opper.ai/v3/compat`
- LLMGateway — `https://api.llmgateway.io`

---

## Step 1: install and configure

```bash
cd a2h-onus
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

export JUDGMENT_BACKEND=jev
export TYPESAFE_API_KEY=...        # or JEV_API_KEY
export JEV_MODEL=jev-1.13.0        # pin it; never 'latest'
```

### Pick the model name carefully

This is the first thing that will bite you. `GET /v1/models` currently advertises
only two names:

```json
{"models":[
  {"name":"jev-latest", "description":"..."},
  {"name":"jev-preview","description":"..."}
]}
```

The **pinned** version is not in that list, but it is what works:

- `jev-1.13.0` → accepted, and this repository pins it
- `jev-1.13` → `400 {"error_type":"api_usage_error","message":"Unknown model: jev-1.13"}`

Do not use `latest`: a floating alias destroys replayability, which is the whole
point of the receipt.

---

## Step 2: one raw call, before any code of ours

Do not start with `verify_claim`. Call the API directly first, so you can see the real
response and isolate every later problem against it:

```bash
curl https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-1.13.0",
    "state": "My card was charged twice for invoice INV-9921.",
    "questions": {
      "billing": {"type":"noul",
                  "instructions":"The message is about a billing problem."},
      "team":    {"type":"choice",
                  "instructions":"Which team should handle this?",
                  "criteria":{"billing":"Payments","technical":"Bugs","sales":"Pricing"}},
      "urgency": {"type":"score",
                  "instructions":"How urgent is this?",
                  "criteria":["can wait","this week","today","right now"]}
    }
  }'
```

**Real response, trimmed** (this is what came back, verbatim in structure):

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "billing": { "type": "noul", "noul": 0.98 },
    "team":    { "type": "choice", "choice": "billing", "confidence": 1.0,
                 "probabilities": { "technical": 0.0, "billing": 1.0, "sales": 0.0 } },
    "urgency": { "type": "score", "score": 1.45, "confidence": 0.49,
                 "legend": { "0": "can wait", "1": "this week",
                             "2": "today", "3": "right now" },
                 "probabilities": { "0": 0.03, "1": 0.52, "2": 0.42, "3": 0.03 } }
  },
  "usage": { "input_tokens": 392, "output_tokens": 69 }
}
```

### Three things in there that documentation does not tell you

1. **`score` is a float, not an option index.** `1.45` sits between "this week" (1)
   and "today" (2), and `legend` maps indices back to labels. Do not cast it to an
   integer.
2. **`choice` and `score` carry their own `confidence`.** Use the value the model
   returned. Do not recompute it as `max(probabilities)` — on this response that
   gives 0.52 where the model said 0.49.
3. **`usage` has no `cost` field.** You get `input_tokens` and `output_tokens` only,
   so compute cost yourself from your own rate.

### Status codes

| code | meaning |
|---|---|
| 200 | worked — check that `answers.<name>.noul` is a number between 0 and 1 |
| 400 | malformed request, or `Unknown model` — see the model-name note above |
| 403 | `{"error_type":"authentication_error","message":"Must supply an API key!..."}` — key missing or wrong |
| 402 | out of credit |
| 429 / 529 | overloaded; try later, and this repository falls back to `kev` once |

---

## Step 3: the first real judgment through `verify_claim`

```bash
JUDGMENT_BACKEND=jev python examples/verify_x_post.py
```

Success looks like this: `model_id` in the receipt is `jev-1.13.0` and not
`mock-heuristic-0`, the confidence is a number Jev actually produced, and
`distribution` in the receipt holds the real probabilities. Save that receipt. It is
the first one that is real.

---

## Common questions

**The state is too long and it errors.**
Jev 1.13 limits state plus the longest question to 32k tokens, 64k total. Truncate or
summarise oversized evidence first, using a different model, not Jev.

**I want to go back to local and free.**
Run a `kev` server (Apache-2.0, API compatible) and set
`JUDGMENT_BACKEND=kev KEV_URL=http://127.0.0.1:4827`. No judgment logic changes.

**The judgments are not accurate enough.**
The wording of the questions in `policy_packs/` is the entire quality surface. Rewrite
the instructions, re-run, compare. This is "questions as code" — version them, and log
the question text alongside every answer in the receipt.

**Can I switch backends without touching code?**
Yes. That is the point of the `JUDGMENT_BACKEND` switch and of the requirement that
the request and response contract stay System One compatible.

---

## After you are connected

At that point you genuinely have: a Jev connection, a real judgment, and a real
receipt. The next honest step is to point it at your own evidence and record what it
does — the auto-approve rate, the fraud it stops, and the cost. Numbers you produced
yourself are the only ones worth publishing.
