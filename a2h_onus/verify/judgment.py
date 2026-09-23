"""
L3 Judgment layer — reference skeleton (NOT final code).

Pluggable backend: kev (default, local, free) or jev (official API).
Same (state, questions) -> distributions contract for both.

Key rules enforced here:
  - version pinned; NEVER 'latest'
  - single in-flight per call (this function is synchronous, one request)
  - 10s timeout
  - jev 429/529 -> fall back to kev once -> else raise JudgmentUnavailable
"""
from __future__ import annotations
import os
import json

try:
    import requests   # or httpx; match your existing stack
except ImportError:
    requests = None

# JUDGMENT_BACKEND: kev (default, local, free) | jev (paid API) | mock (offline demo)
JUDGMENT_BACKEND = os.environ.get("JUDGMENT_BACKEND", "kev")
KEV_URL = os.environ.get("KEV_URL", "http://127.0.0.1:4827")
KEV_MODEL = os.environ.get("KEV_MODEL", "kev-0.8b")

# Jev via any System One-compatible gateway. Defaults to the official TypeSafe
# origin; set JEV_BASE_URL to a gateway if you don't have a TypeSafe key:
#   OpenRouter:  https://openrouter.ai/api
#   Opper:       https://api.opper.ai/v3/compat
#   LLMGateway:  https://api.llmgateway.io
# All expose POST {base}/v1/systemone with Bearer auth and the same shapes.
JEV_BASE_URL = os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai")
JEV_API_KEY = os.environ.get("JEV_API_KEY", os.environ.get("TYPESAFE_API_KEY", ""))
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")   # pin; never 'latest'

TIMEOUT_S = 10


class JudgmentUnavailable(Exception):
    pass


def _serialize_state(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def _reject_latest(model: str) -> str:
    if "latest" in model.lower():
        raise ValueError("floating alias 'latest' is forbidden — pin an exact version")
    return model


def _call_systemone(base_url: str, model: str, state: dict, questions: dict,
                    api_key: str | None = None) -> dict:
    _reject_latest(model)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model, "state": _serialize_state(state), "questions": questions}
    resp = requests.post(f"{base_url}/v1/systemone" if not base_url.endswith("/v1/systemone") else base_url,
                         headers=headers, json=body, timeout=TIMEOUT_S)
    if resp.status_code in (429, 529):
        raise _Overloaded(resp.status_code)
    resp.raise_for_status()
    return resp.json()


class _Overloaded(Exception):
    def __init__(self, code): self.code = code


def _call_kev(state: dict, questions: dict) -> tuple[dict, str]:
    data = _call_systemone(KEV_URL, KEV_MODEL, state, questions)
    return data, KEV_MODEL


def _call_jev(state: dict, questions: dict) -> tuple[dict, str]:
    data = _call_systemone(f"{JEV_BASE_URL}/v1/systemone", JEV_MODEL, state, questions,
                           api_key=JEV_API_KEY)
    return data, JEV_MODEL


def judge(state: dict, questions: dict) -> dict:
    """
    Returns:
      {
        "per_question": { qname: {"distribution": {...}, "confidence": float} },
        "model_id": "jev-1.13.0" | "kev-0.8b",
        "raw": <full backend response>
      }
    Raises JudgmentUnavailable if no backend can serve.
    """
    backend = JUDGMENT_BACKEND

    # mock backend: offline heuristic so `git clone && run` works with no server.
    # NOT for production — it only lets the examples/tests run without kev/jev.
    if backend == "mock":
        return _mock_judge(state, questions)

    if requests is None:
        raise JudgmentUnavailable("requests not installed; use JUDGMENT_BACKEND=mock for offline")

    try:
        if backend == "jev":
            data, model_id = _call_jev(state, questions)
        else:
            data, model_id = _call_kev(state, questions)
    except _Overloaded:
        # jev overloaded -> fall back to kev once
        if backend == "jev":
            try:
                data, model_id = _call_kev(state, questions)
            except Exception as e:
                raise JudgmentUnavailable(f"jev overloaded, kev fallback failed: {e}")
        else:
            raise JudgmentUnavailable("kev overloaded")
    except (requests.Timeout, requests.ConnectionError) as e:
        raise JudgmentUnavailable(str(e))

    # Normalize the REAL TypeSafe System One response shape (see _parse_answers).
    per_question = _parse_answers(data, model_id)
    resolved_model = data.get("model", model_id)
    return {"per_question": per_question, "model_id": resolved_model, "raw": data}


def _parse_answers(data: dict, model_id: str) -> dict:
    """Parse the REAL TypeSafe System One response into our internal per_question form.
    Verified against official docs (2026-09). Response looks like:
      {"model": "...", "answers": {
          "refund":     {"type": "noul",   "noul": 0.98},
          "department": {"type": "choice", "choice": "billing",
                         "probabilities": {"billing": 0.9, "technical": 0.1}},
          "urgency":    {"type": "score",  "score": 3,
                         "probabilities": {"0":..., "3":...}}
       }, "usage": {...}}
    """
    per_question = {}
    answers = data.get("answers") or {}
    for qname, ans in answers.items():
        qtype = ans.get("type")
        if qtype == "noul":
            p_true = ans.get("noul")
            per_question[qname] = {
                "type": "noul",
                "distribution": {"true": p_true,
                                 "false": (1 - p_true) if p_true is not None else None},
                "confidence": p_true,
                "value": (p_true >= 0.5) if p_true is not None else None,
            }
        elif qtype == "choice":
            probs = ans.get("probabilities") or {}
            chosen = ans.get("choice")
            per_question[qname] = {
                "type": "choice",
                "distribution": probs,
                # real replies carry their own confidence; prefer it
                "confidence": (ans.get("confidence") if ans.get("confidence") is not None
                               else (probs.get(chosen) if chosen else (max(probs.values()) if probs else None))),
                "value": chosen,
            }
        elif qtype == "score":
            probs = ans.get("probabilities") or {}
            score = ans.get("score")
            per_question[qname] = {
                "type": "score",
                "distribution": probs,
                # probabilities may be keyed by level index or by level label;
                # fall back to the top probability if neither matches
                # score is a FLOAT position on the scale (e.g. 1.45 between
                # levels 1 and 2); the reply carries a separate confidence.
                "confidence": (ans.get("confidence") if ans.get("confidence") is not None
                               else (max(probs.values()) if probs else None)),
                "legend": ans.get("legend"),
                "value": score,
            }
        else:
            per_question[qname] = {"type": qtype, "distribution": {}, "confidence": None,
                                   "value": ans.get(qtype) if qtype else None, "raw": ans}
    return per_question


def _mock_judge(state: dict, questions: dict) -> dict:
    """Offline heuristic judge. Emits the REAL TypeSafe answers shape so the
    mock exercises the same parser path as live Jev. Derives a plausible
    probability from L1 signals to demonstrate the pipeline's SHAPE without a
    live model. Replace with kev/jev for anything real."""
    sig = state.get("l1_signals", {})
    p = 0.55
    if sig.get("nonce_present"):
        p += 0.15
    if sig.get("identity_bound"):
        p += 0.15
    if sig.get("hash_unique"):
        p += 0.05
    if sig.get("api_verified"):
        p = 0.97
    content = str(state.get("evidence_content", "")).lower()
    if "screenshot" in content and not sig.get("nonce_present"):
        p -= 0.25
    p = max(0.08, min(0.98, p))

    # Build a response in the real TypeSafe shape, then parse it the same way
    # a live response would be parsed.
    answers = {}
    for qname, q in questions.items():
        qtype = q.get("type", "noul")
        if qtype == "noul":
            answers[qname] = {"type": "noul", "noul": round(p, 3)}
        elif qtype == "score":
            lvl = min(3, int(p * 4))
            answers[qname] = {"type": "score", "score": lvl,
                              "probabilities": {str(lvl): round(p, 3)}}
        elif qtype == "choice":
            crit = list((q.get("criteria") or {}).keys()) or ["a", "b"]
            answers[qname] = {"type": "choice", "choice": crit[0],
                              "probabilities": {crit[0]: round(p, 3),
                                                crit[-1]: round(1 - p, 3)}}
    raw = {"model": "mock-heuristic-0", "answers": answers,
           "backend": "mock"}

    per_question = _parse_answers(raw, "mock-heuristic-0")
    return {"per_question": per_question, "model_id": "mock-heuristic-0", "raw": raw}
