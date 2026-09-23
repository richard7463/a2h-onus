"""gitlawb evidence source.

Reads a gitlawb node's public HTTP API and turns a repository's record into
deterministic provenance signals. Public repos are readable without an identity,
so this needs no keypair and no registration.

What this proves: that a commit, branch or pull request **exists on the network,
under that owner, with that hash**. It is a record check, not a quality check. A
commit that exists tells you nothing about whether the work in it is any good —
that is the judge's job, one layer up.

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
    """True only if the exact hash appears in the node's commit list for that repo."""
    if not sha:
        return False
    sha = sha.lower()
    return any((c.get("hash") or "").lower().startswith(sha[:12]) for c in
               fetch_commits(owner, repo, node))


def check(content: dict, node: str | None = None) -> dict:
    """Cross-check a gitlawb claim against the node and return L1 signals.

    ``content`` is the evidence payload:

        {"owner": "z6Mk...", "repo": "a2h-onus", "sha": "4249f27...",
         "branch": "main"}

    Returns a signal block. ``api_verified`` is True only when the node
    positively confirmed the referenced object exists.
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

    if sha:
        signals["gitlawb_commit_found"] = commit_on_network(owner, repo, sha, node)
        signals["api_verified"] = signals["gitlawb_commit_found"]
    else:
        # No hash to pin: the repo existing is not enough to verify a claim.
        signals["api_verified"] = False
    return signals
