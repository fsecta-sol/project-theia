"""H1: Creator Blacklist — exclusion filter, not a trading signal.

With small sample sizes, false negatives are much safer than false positives.
A creator with 0/3 is far more likely to be a serial rugger than a creator
with 2/2 is a "good" creator.

Phase 1: only blacklist (exclusion). Phase 2+: whitelist with larger corpus.
"""
from __future__ import annotations

from collections import Counter, defaultdict


def creator_blacklist(corpus: list[dict], min_tokens: int = 3) -> list[dict]:
    """Blacklist creators with N+ tokens and 0% graduation rate.

    Args:
        corpus: list of token_corpus dicts (must have creator_wallet,
                graduation_status, mint, death_reason).
        min_tokens: minimum tokens created to qualify for blacklist.

    Returns list sorted by total_tokens descending.
    """
    by_creator: defaultdict[str, dict] = defaultdict(
        lambda: {"total": 0, "graduated": 0, "dead": 0, "tokens": []})

    for t in corpus:
        cw = t.get("creator_wallet", "")
        if not cw:
            continue
        by_creator[cw]["total"] += 1
        by_creator[cw]["tokens"].append(t["mint"])
        if t.get("graduation_status") == "graduated":
            by_creator[cw]["graduated"] += 1
        elif t.get("graduation_status") == "dead":
            by_creator[cw]["dead"] += 1

    blacklist = []
    for cw, stats in by_creator.items():
        if stats["total"] >= min_tokens and stats["graduated"] == 0:
            blacklist.append({
                "creator": cw,
                "total_tokens": stats["total"],
                "dead_tokens": stats["dead"],
                "death_reasons": _death_reasons(corpus, stats["tokens"]),
                "signal": "BLACKLIST",
                "note": (
                    f"Serial rugger? {stats['total']} tokens, 0 graduated"
                ),
            })

    blacklist.sort(key=lambda b: b["total_tokens"], reverse=True)
    return blacklist


def _death_reasons(corpus: list[dict], mints: list[str]) -> dict:
    """Count death reasons for a set of token mints."""
    reasons: Counter[str] = Counter()
    for t in corpus:
        if t["mint"] in mints and t.get("death_reason"):
            reasons[t["death_reason"]] += 1
    return dict(reasons)
