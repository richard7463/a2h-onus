"""ai2human Onus (A2H Onus) — open verification layer for AI agents.

The burden of proof is on the evidence.

Built on Jev/System One, with the guardrails production taught us:
the grade gate, provenance-in-code, judgment-not-settlement, and a
pluggable backend so no single closed API is load-bearing.
"""
from .verify import verify_claim, verify_batch

__all__ = ["verify_claim", "verify_batch"]
__version__ = "0.1.0"
