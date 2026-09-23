"""MCP server exposing verify_claim as a tool.

Any MCP client (Claude, Codex, etc.) can call verify_claim directly —
no task-market account, no REST docs. This is verification as a public primitive.

Uses fastmcp to match the existing ai2human-mcp stack. Run:
    python -m a2h_onus.mcp_server
"""
from __future__ import annotations

try:
    from fastmcp import FastMCP
except ImportError:
    raise SystemExit("pip install fastmcp  # required to run the MCP server")

from .verify import verify_claim as _verify_claim, verify_batch as _verify_batch

mcp = FastMCP("a2h-onus")


@mcp.tool()
def verify_claim(claim: str, evidence: dict,
                 acceptance_criteria: list[str] | None = None,
                 value_usd: float = 0.0,
                 nonce: str | None = None) -> dict:
    """Verify a claim against submitted evidence.

    Returns a verdict (approved | rejected | needs_review), a confidence,
    the evidence grade (E0-E4), and a replayable receipt. Does not create a
    task and does not move funds.

    evidence = {
      "type": "x_post" | "onchain_tx" | "url" | "text" | "structured" | "image",
      "content": str | dict,
      "artifact_hash": str,       # optional; computed from content if absent
      "timestamp": str,           # ISO8601, optional
      "identity": {"platform","handle","wallet","signature"}  # optional
    }
    """
    return _verify_claim(claim, evidence, acceptance_criteria, value_usd, nonce)


@mcp.tool()
def verify_batch(items: list[dict]) -> dict:
    """Verify many claims in one call. `items` is a list of verify_claim arg
    dicts: {"claim","evidence","value_usd","nonce","acceptance_criteria"}.
    Returns per-item results plus a summary (auto_approve_rate, review_rate,
    reject_rate) — the numbers for a dashboard."""
    return _verify_batch(items)


if __name__ == "__main__":
    mcp.run()
