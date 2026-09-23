# Four traps in putting Jev where a wrong answer costs money

> Four traps collected while designing Onus, and the countermeasure for each. Some
> conclusions come from measuring real Jev; the numbers are in the README.
> If you plan to put Jev anywhere a wrong answer has real consequences, read this
> first.

## The setting

One example: you run a giveaway — "reply to our post, get $1" — and 1,000 replies
land overnight. Onus filters first. Off-topic and low-effort replies are flagged,
screenshot-only evidence goes to a human, and only what is left reaches review.

```
submission (claim + evidence) → code checks → Jev judges → code decides: approve / reject / review
```

Jev does the judging. Code does everything else.

---

## Trap 1: "zero hallucination" is a wording trick

Every Jev pitch leads with "zero hallucination". The claim is true, but not in the way
you probably assume.

**What it actually means:** Jev will not return an option outside your schema, will
not emit garbage, will not hand you prose you cannot parse. The format is always
valid.

**What it does not promise:** that the judgment is correct. It can pick a
schema-valid, factually wrong option at 0.95 confidence.

In a settlement setting that means a wrong "approved" at 0.95 pays a fraudster who did
no work. A valid schema is not a correct judgment.

### Countermeasure

Never trust the answer blindly. Trust the **stated confidence**, and use it only to
triage:

- high confidence plus strong evidence → auto-approve
- middle band → human review
- low confidence → reject

That gate — triage on confidence, never trust it outright — exists to catch the
judgments Jev is confident about and wrong about.

One line to remember: **Jev does not hand you an answer, it hands you how sure it is.
Use the certainty to route, and keep your guard up about the answer itself.**

---

## Trap 2: don't make it compute what code can

TypeSafe publishes its own list of model weaknesses. In plain terms: Jev does not do
arithmetic, does not count, cannot order dates, and gets confused when there is too
much in front of it. It recognises what an answer roughly looks like. It is not
actually counting.

So a check like "is the submission timestamp inside the task window" must never go to
Jev. To Jev a date is a string, and it cannot tell which one comes first.

### Countermeasure

Pull out everything **code can compute deterministically** and keep it away from Jev:

- is the nonce in the evidence → string match
- is the timestamp valid, and in window → code comparison
- has this evidence been submitted before → hash dedup
- is the amount correct → exact arithmetic

Jev does the one thing it is genuinely good at: judging whether the content looks real.

This is not only an accuracy question, it is an **attribution question**. Provenance
checks belong to code, semantic judgment belongs to the model, and the two stay apart.
When something goes wrong you know immediately which layer is at fault, instead of
staring at a black box.

---

## Trap 3: a bare screenshot is never trustworthy, however confident

A lot of evidence arrives as screenshots. This was the most expensive trap.

A study called TextFake measured exactly this: **even the strongest models top out
around 80% on forged rich-text screenshots, and collapse towards random under
adversarial attack.** Real screenshots are identified 97% of the time; forged ones
only 38%.

In plain language: when Jev tells you a photoshopped screenshot is real at 0.9,
**that 0.9 is not trustworthy**. Believing it is exactly what the forger is counting
on. Confidence is actively harmful here, because it hands you a false sense of safety.

### Countermeasure

One rule, written into the policy layer, not overridable:

> **Evidence below the grade threshold — a bare screenshot, no account binding, no
> task code — never releases money automatically, however confident Jev is.**

Then spend the effort on **raising the evidence grade**, not on making the model see
better:

- if you can query the platform API, never look at a screenshot (an API check is E4,
  deterministic)
- if you can require a task code, never rely on the eye (a nonce is a string match,
  deterministic)
- if you can require an account signature, never trust an unowned image

**Pushing evidence up the grade scale beats making the model more accurate, by a wide
margin.** The best verification is the verification the task design made unnecessary.

---

## Trap 4: don't bet the pipeline on one closed API

Jev is strong, but it is closed, paid, and returns 529 under load. In production one
outage stops the whole line.

More to the point: people have already measured that a small purpose-trained model can
match or beat Jev at lower cost. "Only Jev can do this" is an illusion. What it sells
is not "most accurate" but "good enough, fast and cheap" — a position others can take.

### Countermeasure

Make the judgment layer **pluggable**. Say "System One compatible", not "tied to Jev":

- default to the open-source `kev` (local, free, API compatible)
- fall back automatically on Jev 429/529 so one outage does not take the line down
- pin the version (reject `latest`) and record which model answered every judgment

Most important: **the judgment logs you accumulate in production are the real moat.**
With enough labelled data you can train your own judgment model and drop the closed
API. Swap the engine, keep the pipeline and the data.

---

## Summary

Jev is fast, rough intuition (System One), not a reliable referee. Put it in the right
place:

- **it judges**, and code handles what can be computed
- **humans take the hard cases**, the middle band goes to review
- **evidence is graded**, and low grades never auto-pass
- **the backend is swappable**, and the logs become your own model

Placed correctly, it makes verifying a real-world claim cheap enough to be routine,
and makes work that was never worth verifying verifiable.

Placed wrongly, it will confidently pay your money to a fraudster at 0.95.

---

*The code is in this repository, MIT. Clone it, change it, ship your own.*
*Everyone else uses Jev to score things. Onus asks first: does this evidence deserve to
be believed.*
