"""gitlawb evidence: what a signed push record actually proves, settled in code.

Three claims against the same repository:

  1. the tip of a signed push, by the owner   -> E4, no model call
  2. a commit that is on the branch, but no certificate names it
                                              -> record only, routed to review
  3. a hash that is not on the network at all -> rejected / review

The middle one is the point. gitlawb signs every push, and each certificate
carries a ``pusher_did`` separately from the owner DID — so "a record exists" and
"the owner is accountable for it" are two different checks, and most pipelines
only do the first.
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

real_sha = commits[0]["hash"]                      # tip of the last signed push
fake_sha = "0" * 40

# A commit that is genuinely on the branch but no certificate names it. Pick it
# by asking, rather than assuming position in the list — a tag push also produces
# a certificate, so "oldest commit" is not a safe guess.
older_sha = next((c["hash"] for c in commits[1:]
                  if gitlawb.cert_for(OWNER, REPO, c["hash"], NODE) is None), None)

print(f"node: {NODE}")
print(f"repo: {OWNER}/{REPO}  ({len(commits)} commits visible)")
print(f"head: {real_sha[:12]}  {commits[0]['message'][:64]}")
print()

cases = [("tip of a signed push, by the owner", real_sha)]
if older_sha:
    cases.append(("on the branch, but no certificate names it", older_sha))
cases.append(("not on the network at all", fake_sha))

for label, sha in cases:
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

print(json.dumps({"note": "only the first reached E4, and it never called a model. "
                          "The second is real but unattributable from the "
                          "certificate list, so it is downgraded rather than "
                          "assumed; the third does not exist."},
                 indent=2))
