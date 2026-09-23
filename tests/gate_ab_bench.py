"""Gate A/B benchmark — the number that matters.

Same judge, same evidence, two policies:
  A) judge alone:      approve whenever the model's score clears the bar
  B) judge + Onus: provenance checks + evidence-grade gate on top

Run against real Jev:
    export JUDGMENT_BACKEND=jev TYPESAFE_API_KEY=your-key
    python -m tests.gate_ab_bench

Or offline (mock judge, only checks the script runs):
    JUDGMENT_BACKEND=mock python -m tests.gate_ab_bench

What the set contains:
  genuine      — convincing post, nonce present, account bound
  forged_copy  — the SAME convincing text, but submitted without a bound
                 account (copied someone else's post / borrowed account).
                 Semantically perfect; only provenance can tell.
  forged_story — a convincing written story of having done the task,
                 no nonce, no account. Also semantically plausible.
  off_task     — account bound + nonce present, but the content does not
                 actually do the task. This one tests the JUDGE itself.
"""
import os
import tempfile
import time

# fresh dedup store every run so replays from earlier runs don't interfere
os.environ["DEDUP_DB"] = os.path.join(tempfile.mkdtemp(), "ab.sqlite")

from a2h_onus import verify_claim            # noqa: E402
from a2h_onus.verify.policy import tau_pass  # noqa: E402

VALUE = 0.02
CLAIM = "Replied under @nova_labs's launch post, congratulating the team, including the task code"
CRITERIA = ["the reply congratulates the team on the launch",
            "the reply includes the task code"]

GOOD_TEXTS = [
    "Huge congrats to the @nova_labs team on the launch, the demo looks great! {n}",
    "Congrats on shipping v1 @nova_labs, been waiting for this one {n}",
    "Massive milestone, congratulations to everyone at @nova_labs {n}",
    "Well deserved launch @nova_labs, congrats team! {n}",
    "Congratulations on the launch! The onboarding flow is so clean {n}",
    "Big congrats @nova_labs, excited to try it this weekend {n}",
    "Congrats to the whole team, launch day energy is real {n}",
    "Congratulations @nova_labs, this is a great release {n}",
    "So happy for the team, congrats on going live {n}",
    "Congrats on the launch, @nova_labs! Rooting for you {n}",
]
STORIES = [
    "I replied to the launch post this morning congratulating the team, it's there under my account.",
    "Done! I left a congratulations reply under the Nova launch post a few hours ago.",
    "Posted my reply with congrats on the launch, you can check the thread.",
    "Completed: replied under the launch tweet, congratulated the team and added the code.",
    "I already did it, my congrats reply is live under their announcement.",
]
OFF_TASK = [
    "gm {n}",
    "Anyone know a good pizza place in Austin? {n}",
    "This project is a scam, stay away {n}",
    "{n}",
    "Following for updates {n}",
]


def build_cases():
    cases = []
    for i, t in enumerate(GOOD_TEXTS):
        n = f"#A2H-G{i:02d}"
        cases.append(("genuine", n, {"type": "x_post", "content": t.format(n=n),
                      "identity": {"platform": "x", "handle": f"@real_user_{i}"}}))
    for i, t in enumerate(GOOD_TEXTS):
        n = f"#A2H-C{i:02d}"
        cases.append(("forged_copy", n, {"type": "x_post", "content": t.format(n=n)}))
    for i, s in enumerate(STORIES):
        cases.append(("forged_story", f"#A2H-S{i:02d}", {"type": "text", "content": s}))
    for i, t in enumerate(OFF_TASK):
        n = f"#A2H-O{i:02d}"
        cases.append(("off_task", n, {"type": "x_post", "content": t.format(n=n),
                      "identity": {"platform": "x", "handle": f"@user_{i}"}}))
    return cases


def main():
    backend = os.environ.get("JUDGMENT_BACKEND", "kev")
    bar = tau_pass(VALUE)
    rows = []
    t0 = time.perf_counter()
    for cat, nonce, ev in build_cases():
        r = verify_claim(CLAIM, ev, acceptance_criteria=CRITERIA,
                         value_usd=VALUE, nonce=nonce)
        score = r.get("gated_posterior", r["confidence"])
        judge_only = ("approved" if (score >= bar and "duplicate_evidence" not in r["reasons"]
                                     and "no_artifact" not in r["reasons"]) else "not approved")
        rows.append((cat, score, judge_only, r["verdict"], r["evidence_grade"]))
    secs = time.perf_counter() - t0

    def rate(cat, col):
        sel = [x for x in rows if x[0] == cat]
        hit = sum(1 for x in sel if x[col] == "approved")
        return hit, len(sel)

    print("=" * 64)
    print(f"  Gate A/B benchmark · judge backend: {backend} · bar={bar:.3f}")
    print("=" * 64)
    print(f"  {'category':14}{'approved: judge alone':>24}{'with Onus':>20}")
    for cat in ["genuine", "forged_copy", "forged_story", "off_task"]:
        a, n = rate(cat, 2)
        b, _ = rate(cat, 3)
        print(f"  {cat:14}{f'{a}/{n}':>24}{f'{b}/{n}':>20}")

    fraud = [x for x in rows if x[0] != "genuine"]
    fa = sum(1 for x in fraud if x[2] == "approved")
    fb = sum(1 for x in fraud if x[3] == "approved")
    print("-" * 64)
    print(f"  fraud wrongly approved   judge alone {fa}/{len(fraud)} ({100*fa/len(fraud):.0f}%)"
          f"   ->   with Onus {fb}/{len(fraud)} ({100*fb/len(fraud):.0f}%)")
    print(f"  {len(rows)} cases in {secs:.1f}s")
    if backend == "mock":
        print("\n  (mock judge — numbers are meaningless; run with JUDGMENT_BACKEND=jev)")

    print("\n  per case: category | judge score | judge alone | with Onus | grade")
    for cat, s, a, b, g in rows:
        print(f"  {cat:13} {s:6.3f}  {a:13} {b:13} {g}")


if __name__ == "__main__":
    main()
