"""gitlawb evidence: read the public node, verify a real record, no model call.

Two claims against the same repository:

  1. a commit hash that is actually on the network  -> E4, settled in code
  2. a commit hash that is not                      -> downgraded, needs review

The point is the first one. A public gitlawb read needs no keypair, so
"this commit exists under this owner" is a fact code can settle without asking
a model at all. It proves the record, not the quality of the work.
"""
import json
import os

os.environ.setdefault("JUDGMENT_BACKEND", "mock")
from a2h_onus import verify_claim
from a2h_onus.verify import gitlawb

NODE = os.environ.get("GITLAWB_NODE", gitlawb.GITLAWB_NODE_DEFAULT)
OWNER = os.environ.get("GITLAWB_OWNER",
                       "z6MkvzipRLJAmeUWiEbEB2efjNceD6eQZua4BZBvaJtGwKmg")
REPO = os.environ.get("GITLAWB_REPO", "a2h-onus")

commits = gitlawb.fetch_commits(OWNER, REPO, NODE)
if not commits:
    raise SystemExit(f"could not read {OWNER}/{REPO} from {NODE} - "
                     "check the node and that GITLAWB_CHECK is not 0")

real_sha = commits[0]["hash"]
fake_sha = "0" * 40

print(f"node: {NODE}")
print(f"repo: {OWNER}/{REPO}  ({len(commits)} commits visible)")
print(f"head: {real_sha[:12]}  {commits[0]['message'][:64]}")
print()

for label, sha in (("exists on the network", real_sha),
                   ("does not exist", fake_sha)):
    result = verify_claim(
        claim=f"Commit {sha[:12]} was pushed to {REPO} by the repo owner",
        evidence={
            "type": "gitlawb_commit",
            "content": {"owner": OWNER, "repo": REPO, "sha": sha},
            "artifact_hash": f"0xdemo_gitlawb_{sha[:12]}",
        },
        acceptance_criteria=["the commit is present in the repository record"],
        value_usd=0.50,
    )
    print(f"--- {label}  ({sha[:12]})")
    print(f"    verdict         {result['verdict']}")
    print(f"    evidence grade  {result['evidence_grade']}")
    print(f"    reasons         {result['reasons']}")
    print(f"    receipt model   {result['receipt']['model_id']}")
    print(f"    receipt hash    {result['receipt']['hash'][:22]}...")
    print()

print(json.dumps({"note": "the E4 path never called a model; the E1 path was "
                          "routed to review because the record did not check out"},
                 indent=2))
