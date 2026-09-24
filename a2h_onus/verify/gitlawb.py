"""gitlawb evidence source.

Reads a gitlawb node's public HTTP API and turns a repository's record into
deterministic provenance signals. Public repos are readable without an identity,
so this needs no keypair and no registration.

What this proves, precisely:

  1. the commit hash is present in the repo's commit list on this node;
  2. the node holds a ref-update certificate whose ``new_sha`` is exactly that
     commit — i.e. this commit was the tip of a signed ref update;
  3. that certificate's ``pusher_did`` equals the repository's owner DID.

All three are required before anything here is called verified. A commit that is
merely present in the list is **not** enough: gitlawb's own documentation states
that write authorization is not owner-enforced by default
(``GITLAWB_ENFORCE_OWNER_PUSH`` defaults to false), so "a valid signature exists"
and "the owner authorised this" are different statements. ``pusher_did ==
owner_did`` is the closest the public API lets us get to the second one.

What it still does not prove: that the node would have *blocked* a non-owner
push. That is a node policy we cannot read from the API, so it is reported as
``gitlawb_owner_push_enforced: None`` (unknown) rather than assumed.

One more property worth knowing before you rely on it: the certificate list
tracks the ref tips the node currently lists, not the whole history. Push again
and the previous tip's certificate rolls off. So owner attribution is a
statement about **now**, not a permanent property of the commit — which is why
``gitlawb_cert_list_is_snapshot`` is set to True on every result. Persist the
verdict (and its receipt) at the time you check it, rather than re-deriving it
later and expecting the same answer.

And it is a record check, not a quality check. A commit that exists tells you
nothing about whether the work in it is any good — that is the judge's job, one
layer up.

Endpoints used (all verified against node.gitlawb.com, gl 0.7.1):

    GET /api/v1/repos/{owner}/{repo}          repo metadata
    GET /api/v1/repos/{owner}/{repo}/commits  commit list
    GET /api/v1/repos/{owner}/{repo}/pulls    pull requests
    GET /api/v1/repos/{owner}/{repo}/certs    Ed25519-signed ref certificates

Set ``GITLAWB_CHECK=0`` to disable the network read entirely (tests, airgapped
runs). The check fails closed: any error means "not verified", never "verified".
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

GITLAWB_NODE_DEFAULT = "https://node.gitlawb.com"
TIMEOUT_S = 5.0


def enabled() -> bool:
    return os.environ.get("GITLAWB_CHECK", "1") not in ("0", "false", "no")


def _get(path: str, node: str = GITLAWB_NODE_DEFAULT) -> dict | None:
    url = f"{node.rstrip('/')}{path}"
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "a2h-onus"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError):
        return None


def fetch_repo(owner: str, repo: str, node: str = GITLAWB_NODE_DEFAULT) -> dict | None:
    return _get(f"/api/v1/repos/{owner}/{repo}", node)


def fetch_commits(owner: str, repo: str, node: str = GITLAWB_NODE_DEFAULT) -> list[dict]:
    data = _get(f"/api/v1/repos/{owner}/{repo}/commits", node)
    return (data or {}).get("commits", []) if data else []


def fetch_pulls(owner: str, repo: str, node: str = GITLAWB_NODE_DEFAULT) -> list[dict]:
    data = _get(f"/api/v1/repos/{owner}/{repo}/pulls", node)
    return (data or {}).get("pulls", []) if data else []


def fetch_certs(owner: str, repo: str, node: str = GITLAWB_NODE_DEFAULT) -> list[dict]:
    data = _get(f"/api/v1/repos/{owner}/{repo}/certs", node)
    return (data or {}).get("certificates", []) if data else []


def commit_on_network(owner: str, repo: str, sha: str,
                      node: str = GITLAWB_NODE_DEFAULT) -> bool:
    """Is this commit in the node's list for that repo?

    A full 40-character hash must match exactly. A shorter string is treated as a
    prefix, so the usual 7-12 character abbreviation still resolves — but the
    input is never truncated, because trimming a full hash to 12 characters and
    then prefix-matching would let one commit stand in for another.
    """
    if not sha:
        return False
    want = sha.lower()
    for c in fetch_commits(owner, repo, node):
        got = (c.get("hash") or "").lower()
        if got == want or (len(want) < 40 and got.startswith(want)):
            return True
    return False


def _bare(did: str) -> str:
    """DIDs are compared as bare keys: 'did:key:z6Mk...' and 'z6Mk...' are equal."""
    return (did or "").strip().removeprefix("did:key:")


def cert_for(owner: str, repo: str, sha: str,
             node: str = GITLAWB_NODE_DEFAULT) -> dict | None:
    """The ref-update certificate whose ``new_sha`` is exactly this commit, if any.

    One push produces one certificate, covering the ref transition
    (old_sha -> new_sha). So a certificate exists for the *tip* of each signed
    push. A commit that only ever appeared mid-push has none, and cannot be
    owner-attributed from the certificate list alone.
    """
    if not sha:
        return None
    want = sha.lower()
    for c in fetch_certs(owner, repo, node):
        got = (c.get("new_sha") or "").lower()
        if got == want or (len(want) < 40 and got.startswith(want)):
            return c
    return None


def check(content: dict, node: str | None = None) -> dict:
    """Cross-check a gitlawb claim against the node and return L1 signals.

    ``content`` is the evidence payload:

        {"owner": "z6Mk...", "repo": "a2h-onus", "sha": "4249f27...",
         "branch": "main"}

    Returns a signal block. ``api_verified`` is True only when the node
    positively confirmed the record **and** attributed the ref update to the
    repository owner. Anything short of that fails closed.
    """
    node = node or os.environ.get("GITLAWB_NODE", GITLAWB_NODE_DEFAULT)
    owner = (content or {}).get("owner", "")
    repo = (content or {}).get("repo", "")
    sha = (content or {}).get("sha", "")

    signals = {
        "gitlawb_node": node,
        "gitlawb_owner": owner,
        "gitlawb_repo": repo,
        "gitlawb_repo_found": False,
        "gitlawb_commit_found": False,
        "gitlawb_cert_present": False,
        "gitlawb_pusher_did": None,
        "gitlawb_pusher_is_owner": False,
        # The node's own enforcement policy is not visible through the API.
        # Reported as unknown rather than assumed to be on.
        "gitlawb_owner_push_enforced": None,
        # Certificates cover the ref tips the node currently lists. A later push
        # moves the tip and the previous certificate rolls off, so attribution
        # describes the present state, not the moment the commit landed.
        "gitlawb_cert_list_is_snapshot": True,
        "gitlawb_certificates": 0,
        "api_verified": False,
    }
    if not owner or not repo:
        return signals

    info = fetch_repo(owner, repo, node)
    if not info:
        return signals
    signals["gitlawb_repo_found"] = True
    signals["gitlawb_public"] = bool(info.get("public", True))
    signals["gitlawb_certificates"] = len(fetch_certs(owner, repo, node))

    if not sha:
        # No hash to pin: the repo existing is not enough to verify a claim.
        return signals

    signals["gitlawb_commit_found"] = commit_on_network(owner, repo, sha, node)
    if not signals["gitlawb_commit_found"]:
        return signals

    cert = cert_for(owner, repo, sha, node)
    if not cert:
        # The commit is on the branch, but no signed ref update names it as the
        # tip — so we cannot attribute the push to anyone. Record, not proof.
        return signals

    signals["gitlawb_cert_present"] = True
    signals["gitlawb_pusher_did"] = cert.get("pusher_did")
    signals["gitlawb_pusher_is_owner"] = _bare(cert.get("pusher_did")) == _bare(
        info.get("owner_did") or owner
    )
    signals["api_verified"] = bool(
        signals["gitlawb_cert_present"] and signals["gitlawb_pusher_is_owner"]
    )
    return signals
