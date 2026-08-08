"""Agent harness — deterministic supervisory wrapper around every LLM invocation.

Four parts (per ARCHITECTURE.md v2):
  1. GROUNDING VERIFIER — anti-hallucination: every claim needs source/compute ref
  2. POLICY GATE — ALLOW / DENY / ESCALATE before any consequential action
  3. CONTEXT WINDOW TRACKER — store, measure, budget token usage per shot
  4. BUDGET BREAKER — per-model spend; degrade/shift when limit hit

Every LLM shot is logged to theia-store (llm_shots) so the whole reasoning chain
is reconstructable. The LLM proposes; the harness verifies and gates.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal

# ── Constants ──────────────────────────────────────────────────────────────

PolicyDecision = Literal["ALLOW", "DENY", "ESCALATE"]

# Approximate costs (USD per 1K tokens) — conservative over-estimate
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.0001, 0.0002),   # (input, output) per 1K — placeholder
    "deepseek-v4-pro": (0.0005, 0.0010),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
}

_DEFAULT_TOKEN_BUDGET = 200_000   # tokens per session window
_DEFAULT_DOLLAR_BUDGET = 2.0      # USD per day per model profile

# Regexes for policy gate
_MONEY_MATH_RE = re.compile(
    r"(?i)(pnl|profit|loss|expectancy|profit factor|sharpe|roi|return|"
    r"cost basis|position size|sizing|slippage|gas fee|priority fee)"
)
_SOURCE_CITE_RE = re.compile(r"(?i)(source|sourced|cited?|url|https?|tx|signature|"
                              r"block|slot|on-chain|helius|birdeye|dexscreener|goplus)")


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class GroundingCheck:
    has_source: bool = False
    has_computation_ref: bool = False
    money_math_source: str = ""   # compute lib name, or "LLM" if found untraced
    missing_why: list[str] = field(default_factory=list)


@dataclass
class PolicyResult:
    decision: PolicyDecision = "ALLOW"
    reason: str = ""
    checks: GroundingCheck = field(default_factory=GroundingCheck)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LlmShot:
    shot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str = ""
    ts: int = 0
    skill: str = ""
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    grounding: GroundingCheck = field(default_factory=GroundingCheck)
    policy: PolicyResult = field(default_factory=PolicyResult)
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    cost_usd: float = 0.0


# ── Grounding Verifier ─────────────────────────────────────────────────────

_COMPUTE_LIBS = {
    "pnl", "expectancy", "wilson", "gas_sim", "amm_sim",
    "exit_engine", "screen_score", "costs", "discovery_filter",
    "time_regime", "creator_reputation", "corpus",
}


def verify_grounding(outputs_text: str, skill: str = "") -> GroundingCheck:
    """Scan LLM output for hallucination signals.

    Returns GroundingCheck with flags:
      - has_source: found a citation pattern (URL, on-chain ref, API name)
      - has_computation_ref: found reference to a compute lib
      - money_math_source: where a money number came from (lib name or 'LLM')
      - missing_why: list of flags like ["no-source", "llm-money-math"]
    """
    g = GroundingCheck()
    text = outputs_text if isinstance(outputs_text, str) else json.dumps(outputs_text)

    # 1. Source check
    g.has_source = bool(_SOURCE_CITE_RE.search(text))

    # 2. Computation reference check
    found_libs = [lib for lib in _COMPUTE_LIBS if lib in text.lower()]
    g.has_computation_ref = len(found_libs) > 0

    # 3. Money math tracing
    if _MONEY_MATH_RE.search(text):
        if found_libs:
            g.money_math_source = found_libs[0]  # pick first; log all in caller
        else:
            g.money_math_source = "LLM"
            g.missing_why.append("llm-money-math")
    else:
        g.money_math_source = "none"

    if not g.has_source and "learn" not in skill.lower():
        # Learning skill may draft notes before sourcing — exempt
        g.missing_why.append("no-source")

    return g


# ── Policy Gate ──────────────────────────────────────────────────────────────

_CONSEQUENTIAL_SKILLS = {
    "theia-paper-trade", "theia-monitor", "theia-evaluate-expectancy",
    "theia-form-hypothesis", "theia-backtest", "theia-archive",
}


def policy_gate(skill: str, grounding: GroundingCheck,
                outputs_text: str, emergency_signals: list[str] | None = None
                ) -> PolicyResult:
    """Deterministic ALLOW / DENY / ESCALATE.

    Rules (order matters — first match wins):
      1. Emergency signals (rug, LP pull, mint live) → ESCALATE
      2. Consequential skill + LLM money math → DENY
      3. Consequential skill + no source citation → ESCALATE
      4. Default → ALLOW
    """
    p = PolicyResult(checks=grounding)
    text = outputs_text.lower() if isinstance(outputs_text, str) else json.dumps(outputs_text).lower()
    emerg = [e.lower() for e in (emergency_signals or [])]

    # Rule 1 — emergency
    if any(sig in text for sig in emerg):
        p.decision = "ESCALATE"
        p.reason = f"emergency signal hit: {[s for s in emerg if s in text][:2]}"
        return p

    is_consequential = skill in _CONSEQUENTIAL_SKILLS

    # Rule 2 — LLM did money math on a consequential skill
    if is_consequential and grounding.money_math_source == "LLM":
        p.decision = "DENY"
        p.reason = "money math without compute-lib reference on consequential skill"
        return p

    # Rule 3 — no source on consequential skill
    if is_consequential and not grounding.has_source and "learn" not in skill.lower():
        p.decision = "ESCALATE"
        p.reason = "consequential action without reconstructable source"
        return p

    p.decision = "ALLOW"
    p.reason = "all checks passed"
    return p


# ── Cost / Token Budget ─────────────────────────────────────────────────────


def estimate_cost(model: str, usage: TokenUsage) -> float:
    """Rough USD cost from token usage. Over-estimates by ~20% as safety margin."""
    inp, out = _MODEL_COSTS.get(model, (0.0, 0.0))
    raw = (usage.prompt_tokens * inp + usage.completion_tokens * out) / 1000.0
    return round(raw * 1.2, 6)   # 20% margin


def budget_status(used_usd: float, limit_usd: float = _DEFAULT_DOLLAR_BUDGET) -> dict:
    remaining = limit_usd - used_usd
    return {
        "used_usd": round(used_usd, 4),
        "limit_usd": limit_usd,
        "remaining_usd": round(remaining, 4),
        "degrade": used_usd >= 0.8 * limit_usd,
        "deny": used_usd >= limit_usd,
    }


# ── Session context window ───────────────────────────────────────────────────

@dataclass
class ContextWindow:
    session_id: str
    last_shot_id: str = ""
    summary: str = ""            # rolling compressed summary of the session
    token_budget_remaining: int = _DEFAULT_TOKEN_BUDGET
    shots_count: int = 0
    updated_ts: int = 0


def context_digest(shots: list[LlmShot], max_tokens: int = 800) -> str:
    """Compress a list of shots into a cheap summary for the next prompt.
    Uses deterministic heuristics, never another LLM call."""
    if not shots:
        return ""
    lines = [f"Session: {shots[0].session_id} | {len(shots)} shots"]
    # Keep only last N shots that fit budget
    kept = []
    tokens_used = 0
    for s in reversed(shots):
        line = f"[{s.skill}] policy={s.policy.decision} cost=${s.cost_usd}"
        t = len(line.split()) * 1.3  # rough token estimate
        if tokens_used + t > max_tokens:
            break
        tokens_used += t
        kept.append(line)
    lines.extend(reversed(kept))
    return "\n".join(lines)


# ── Serialize for DB ─────────────────────────────────────────────────────────


def shot_to_dict(s: LlmShot) -> dict:
    return {
        "shot_id": s.shot_id,
        "session_id": s.session_id,
        "ts": s.ts,
        "skill": s.skill,
        "inputs": json.dumps(s.inputs, default=str),
        "outputs": json.dumps(s.outputs, default=str),
        "grounding_verdict": json.dumps(asdict(s.grounding), default=str),
        "policy_decision": s.policy.decision,
        "policy_reason": s.policy.reason,
        "model": s.model,
        "prompt_tokens": s.usage.prompt_tokens,
        "completion_tokens": s.usage.completion_tokens,
        "total_tokens": s.usage.total_tokens,
        "cost_usd": s.cost_usd,
    }


def shot_from_dict(d: dict) -> LlmShot:
    g = GroundingCheck(**json.loads(d.get("grounding_verdict", "{}")))
    p = PolicyResult(
        decision=d.get("policy_decision", "ALLOW"),
        reason=d.get("policy_reason", ""),
        checks=g,
    )
    u = TokenUsage(
        prompt_tokens=d.get("prompt_tokens", 0),
        completion_tokens=d.get("completion_tokens", 0),
        total_tokens=d.get("total_tokens", 0),
    )
    return LlmShot(
        shot_id=d["shot_id"],
        session_id=d["session_id"],
        ts=d.get("ts", 0),
        skill=d.get("skill", ""),
        inputs=json.loads(d.get("inputs", "{}")),
        outputs=json.loads(d.get("outputs", "{}")),
        grounding=g,
        policy=p,
        usage=u,
        model=d.get("model", ""),
        cost_usd=d.get("cost_usd", 0.0),
    )
