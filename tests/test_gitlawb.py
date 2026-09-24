"""gitlawb evidence source tests.

The HTTP layer is stubbed, so these run offline and deterministically. They
assert the two properties that matter: a confirmed record reaches E4 without a
model call, and anything unconfirmed fails closed into review.

Run with: JUDGMENT_BACKEND=mock python -m pytest tests/test_gitlawb.py -v
"""
import os
import tempfile

os.environ["JUDGMENT_BACKEND"] = "mock"
os.environ["DEDUP_DB"] = os.path.join(tempfile.mkdtemp(), "dedup.sqlite")

from a2h_onus import verify_claim
from a2h_onus.verify import gitlawb

OWNER = "z6MkTestOwnerAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
OTHER = "z6kTestStrangerZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
REPO = "demo"
REAL_SHA = "4249f27c4126fcb15d7fadd9ba954ccdf4090871"
OLD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"

# The fake node: REAL_SHA was the tip of a signed push by the owner; OLD_SHA is
# present on the branch but no certificate names it.
PUSHER = OWNER


def _fake_get(path, node=gitlawb.GITLAWB_NODE_DEFAULT):
    if path.endswith("/commits"):
        return {"commits": [
            {"author": "richard7463", "date": "2026-09-23T09:24:27+00:00",
             "hash": REAL_SHA, "message": "docs: English-only repository"},
            {"author": "richard7463", "date": "2026-09-22T09:24:27+00:00",
             "hash": OLD_SHA, "message": "older commit, never a ref tip"},
        ]}
    if path.endswith("/certs"):
        return {"certificates": [
            {"id": "8aa3b951", "issued_at": "2026-09-23",
             "new_sha": REAL_SHA, "old_sha": "0" * 40,
             "pusher_did": f"did:key:{PUSHER}",
             "ref_name": "refs/heads/main"},
        ]}
    if path.endswith("/pulls"):
        return {"count": 0, "pulls": []}
    return {"id": "2f8c001c", "name": REPO, "owner_did": OWNER, "public": True}


def _stub(monkey):
    monkey(gitlawb, "_get", _fake_get)


def test_commit_on_network_matches_exact_hash():
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    assert gitlawb.commit_on_network(OWNER, REPO, REAL_SHA) is True
    assert gitlawb.commit_on_network(OWNER, REPO, "0" * 40) is False


def test_confirmed_record_reaches_e4_without_a_model():
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    r = verify_claim(
        "Commit 4249f27c4126 was pushed to demo",
        {"type": "gitlawb_commit",
         "content": {"owner": OWNER, "repo": REPO, "sha": REAL_SHA},
         "artifact_hash": "0xtest_gitlawb_real"},
        acceptance_criteria=["the commit is present in the record"],
        value_usd=0.50,
    )
    assert r["evidence_grade"] == "E4"
    assert r["verdict"] == "approved"
    assert r["receipt"]["model_id"] == "deterministic"


def test_commit_without_a_certificate_is_not_owner_attributable():
    """Present on the branch is not enough — no signed ref update names it."""
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    signals = gitlawb.check({"owner": OWNER, "repo": REPO, "sha": OLD_SHA})
    assert signals["gitlawb_commit_found"] is True
    assert signals["gitlawb_cert_present"] is False
    assert signals["api_verified"] is False


def test_a_non_owner_pusher_does_not_verify():
    """The certificate names a pusher that is not the owner -> never E4."""
    def fake(path, node=gitlawb.GITLAWB_NODE_DEFAULT):
        if path.endswith("/certs"):
            return {"certificates": [{"id": "x", "new_sha": REAL_SHA,
                                      "pusher_did": f"did:key:{OTHER}"}]}
        return _fake_get(path, node)

    original = gitlawb._get
    try:
        gitlawb._get = fake
        signals = gitlawb.check({"owner": OWNER, "repo": REPO, "sha": REAL_SHA})
    finally:
        gitlawb._get = original
    assert signals["gitlawb_cert_present"] is True
    assert signals["gitlawb_pusher_is_owner"] is False
    assert signals["api_verified"] is False


def test_owner_push_enforcement_is_reported_unknown_not_assumed():
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    signals = gitlawb.check({"owner": OWNER, "repo": REPO, "sha": REAL_SHA})
    assert signals["api_verified"] is True
    assert signals["gitlawb_owner_push_enforced"] is None


def test_unconfirmed_record_fails_closed():
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    r = verify_claim(
        "Commit does not exist",
        {"type": "gitlawb_commit",
         "content": {"owner": OWNER, "repo": REPO, "sha": "0" * 40},
         "artifact_hash": "0xtest_gitlawb_fake"},
        value_usd=0.50,
    )
    assert r["evidence_grade"] == "E1"
    assert r["verdict"] == "needs_review"
    assert "grade_gate_block" in r["reasons"]


def test_missing_owner_or_repo_is_not_verified():
    _stub(lambda mod, name, fn: setattr(mod, name, fn))
    assert gitlawb.check({"repo": REPO})["api_verified"] is False
    assert gitlawb.check({"owner": OWNER})["api_verified"] is False


def test_network_failure_never_verifies():
    _stub(lambda mod, name, fn: setattr(mod, name, lambda *a, **k: None))
    signals = gitlawb.check({"owner": OWNER, "repo": REPO, "sha": REAL_SHA})
    assert signals["gitlawb_repo_found"] is False
    assert signals["api_verified"] is False
