"""Creator/LP veto labels for the M-05 POC C overlay (deterministic).

Deterministic decision function over STORED + cached evidence. No network
calls here; network I/O lives in the worker driver (which persists raw API
responses to creator_cache.json and passes them in).

Rule (see mission contract VAL-VETO-001 and AGENTS.md):
  1. GoPlus flags  -> skip if any flag (honeypot / mint_authority_live /
     freeze_authority_live). An EMPTY flag list is NOT evidence of safety
     (it means the query returned nothing at harvest time) — treated as
     no-information for the veto decision.
  2. Creator track record -> skip if the creator is blacklisted by
     creator_reputation.creator_blacklist semantics: >= min_tokens tokens
     created with 0% graduation. pass if we have positive evidence the
     creator is healthy: >= min_tokens tokens with >= 1 graduated.
  3. Anything else (creator unresolved, or track record too thin to judge)
     -> unknown.

Every label maps to a documented source + threshold; "unknown" is never
treated as "pass".

Deterministic: same inputs -> same outputs (pure function, no randomness).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Thresholds (reconstructable, matches creator_reputation.py defaults)
MIN_TOKENS_BLACKLIST = 3      # >=3 tokens, 0 graduated -> blacklist
MIN_TOKENS_HEALTHY = 3        # >=3 tokens, >=1 graduated -> healthy evidence
GOPLUS_VETO_FLAGS = ("honeypot", "mint_authority_live", "freeze_authority_live")

# Graduation statuses used by the corpus (see compute/corpus.py)
GRADUATED = "graduated"


def load_goplus_flags(path: str | Path) -> dict[str, list[str]]:
    """Load stored GoPlus veto cache {mint: [flag,...]}. Tolerates missing file."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def creator_blacklist_from_corpus(corpus: list[dict[str, Any]],
                                  min_tokens: int = MIN_TOKENS_BLACKLIST) -> set[str]:
    """Creators with >=min_tokens tokens and 0 graduated (serial-rugger rule).

    Corpus rows must carry creator_wallet + graduation_status. Same semantics
    as compute/creator_reputation.py::creator_blacklist.
    """
    by_creator: dict[str, dict[str, int]] = {}
    for t in corpus:
        cw = (t.get("creator_wallet") or "").strip()
        if not cw:
            continue
        st = by_creator.setdefault(cw, {"total": 0, "graduated": 0})
        st["total"] += 1
        if t.get("graduation_status") == GRADUATED:
            st["graduated"] += 1
    return {cw for cw, st in by_creator.items()
            if st["total"] >= min_tokens and st["graduated"] == 0}


def healthy_creators(corpus: list[dict[str, Any]],
                     min_tokens: int = MIN_TOKENS_HEALTHY) -> set[str]:
    """Creators with >=min_tokens tokens and >=1 graduated (positive evidence)."""
    by_creator: dict[str, dict[str, int]] = {}
    for t in corpus:
        cw = (t.get("creator_wallet") or "").strip()
        if not cw:
            continue
        st = by_creator.setdefault(cw, {"total": 0, "graduated": 0})
        st["total"] += 1
        if t.get("graduation_status") == GRADUATED:
            st["graduated"] += 1
    return {cw for cw, st in by_creator.items()
            if st["total"] >= min_tokens and st["graduated"] >= 1}


def veto_decision(mint: str,
                  creator_wallet: str | None,
                  creator_evidence: dict[str, Any] | None,
                  goplus_flags: list[str] | None,
                  blacklist: set[str],
                  healthy: set[str],
                  ) -> dict[str, Any]:
    """Deterministic veto label for one mint.

    Args:
        mint: the token mint (baseline trade).
        creator_wallet: resolved creator wallet or None.
        creator_evidence: dict with creator_tokens (list of mints the creator
            launched) — used to reconstruct a corpus-like record. May be None.
        goplus_flags: stored GoPlus flags for this mint ([] = no info).
        blacklist: set of blacklisted creator wallets (serial ruggers).
        healthy: set of healthy creator wallets (positive evidence).

    Returns:
        {mint, creator_wallet, veto_decision: skip|pass|unknown,
         reason, source, threshold}.
    """
    # 1. GoPlus veto (only explicit flags veto; empty list = no information)
    flags = list(goplus_flags or [])
    if any(f in GOPLUS_VETO_FLAGS for f in flags):
        return {
            "mint": mint, "creator_wallet": creator_wallet,
            "veto_decision": "skip",
            "reason": f"goplus_flags={flags}",
            "source": "goplus_veto.json",
            "threshold": f"any flag in {list(GOPLUS_VETO_FLAGS)}",
        }
    if flags and not any(f in GOPLUS_VETO_FLAGS for f in flags):
        return {
            "mint": mint, "creator_wallet": creator_wallet,
            "veto_decision": "unknown",
            "reason": f"goplus_flags={flags} but none vetoed; creator evidence required",
            "source": "goplus_veto.json",
            "threshold": f"any flag in {list(GOPLUS_VETO_FLAGS)}",
        }

    # 2. Creator track record
    if not creator_wallet:
        return {
            "mint": mint, "creator_wallet": None,
            "veto_decision": "unknown",
            "reason": "creator_wallet unresolved (no helius/pumpfun data)",
            "source": "theia-chainrpc token_creator",
            "threshold": "n/a",
        }
    if creator_wallet in blacklist:
        return {
            "mint": mint, "creator_wallet": creator_wallet,
            "veto_decision": "skip",
            "reason": f"creator blacklisted: >= {MIN_TOKENS_BLACKLIST} tokens, 0 graduated",
            "source": "creator_history/creator_tokens via creator_reputation.blacklist",
            "threshold": f"total_created >= {MIN_TOKENS_BLACKLIST} and graduated == 0",
        }
    if creator_wallet in healthy:
        return {
            "mint": mint, "creator_wallet": creator_wallet,
            "veto_decision": "pass",
            "reason": f"healthy creator: >= {MIN_TOKENS_HEALTHY} tokens, >=1 graduated",
            "source": "creator_history/creator_tokens via graduation labels",
            "threshold": f"total_created >= {MIN_TOKENS_HEALTHY} and graduated >= 1",
        }
    # Creator resolved but track record unknown/thin
    n_created = 0
    if creator_evidence and isinstance(creator_evidence.get("creator_tokens"), list):
        n_created = len(creator_evidence["creator_tokens"])
    if n_created > 0:
        return {
            "mint": mint, "creator_wallet": creator_wallet,
            "veto_decision": "unknown",
            "reason": f"creator resolved but track record too thin to judge (created={n_created}, no graduation labels)",
            "source": "creator_history/creator_tokens",
            "threshold": f"blacklist needs >= {MIN_TOKENS_BLACKLIST} tokens; healthy needs >= {MIN_TOKENS_HEALTHY}",
        }
    return {
        "mint": mint, "creator_wallet": creator_wallet,
        "veto_decision": "unknown",
        "reason": "creator resolved but no creator history available",
        "source": "creator_history/creator_tokens",
        "threshold": f"blacklist needs >= {MIN_TOKENS_BLACKLIST} tokens; healthy needs >= {MIN_TOKENS_HEALTHY}",
    }


def label_all(mints: list[str],
              goplus_flags: dict[str, list[str]],
              creator_map: dict[str, dict[str, Any]],
              creator_evidence: dict[str, dict[str, Any]],
              blacklist: set[str],
              healthy: set[str],
              ) -> list[dict[str, Any]]:
    """Label every mint deterministically. Missing evidence -> unknown."""
    labels = []
    for mint in sorted(mints):
        cw = None
        cm = creator_map.get(mint) or {}
        cw = cm.get("creator_wallet")
        if not cw:
            cw = None
        labels.append(veto_decision(
            mint=mint,
            creator_wallet=cw,
            creator_evidence=creator_evidence.get(cw or "", {}),
            goplus_flags=goplus_flags.get(mint),
            blacklist=blacklist,
            healthy=healthy,
        ))
    return labels


def coverage_stats(labels: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {"skip": 0, "pass": 0, "unknown": 0}
    for l in labels:
        counts[l["veto_decision"]] = counts.get(l["veto_decision"], 0) + 1
    total = len(labels)
    return {"total": total, **counts,
            "skip_pct": round(100 * counts["skip"] / total, 1),
            "pass_pct": round(100 * counts["pass"] / total, 1),
            "unknown_pct": round(100 * counts["unknown"] / total, 1)}
