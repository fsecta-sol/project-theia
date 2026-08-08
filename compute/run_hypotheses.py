"""Phase 1 backtest orchestrator — exploratory analysis only.

NO out-of-sample split (too little data for 1 week).
H1: creator blacklist analysis
H5: time regime descriptive stats  
H6: discovery filter optimization
H2/H3/H4 deferred to Phase 2.
"""
from __future__ import annotations

from .creator_reputation import creator_blacklist
from .time_regime import graduation_by_regime
from .discovery_filter import optimize_discovery_filter


def run_phase1(corpus: list[dict],
               discovery_metrics: dict[str, dict] | None = None) -> dict:
    """Run all Phase 1 hypotheses on the labeled corpus.

    Args:
        corpus: list of token_corpus dicts from theia-store.get_corpus().
        discovery_metrics: optional mint→{liq,vol} map for H6.
                           Populated from price_snapshots_v2 earliest snapshot.
    """
    return {
        "phase": 1,
        "corpus_size": len(corpus),
        "n_graduated": sum(1 for t in corpus
                           if t.get("graduation_status") == "graduated"),
        "n_dead": sum(1 for t in corpus
                      if t.get("graduation_status") == "dead"),
        "hypotheses": {
            "H1": {
                "name": "Creator Blacklist",
                "type": "exclusion_filter",
                "blacklist": creator_blacklist(corpus, min_tokens=3),
            },
            "H5": {
                "name": "Time Regime",
                "type": "descriptive",
                **graduation_by_regime(corpus),
            },
            "H6": {
                "name": "Discovery Filter",
                "type": "exclusion_filter",
                **optimize_discovery_filter(corpus, discovery_metrics),
            },
        },
        "note": (
            "Phase 1 = exploratory. No OOS split. "
            "H2/H3/H4 deferred to Phase 2."
        ),
    }
