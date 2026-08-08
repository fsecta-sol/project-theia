"""H6: Liquidity/Volume Discovery Filter.

Grid-search over liquidity and volume thresholds at discovery to find
the cutoff that best separates graduated from dead tokens.

Tokensor below the optimal threshold die ~95% of the time —
just skip them entirely.
"""
from __future__ import annotations


def optimize_discovery_filter(corpus: list[dict],
                              discovery_metrics: dict[str, dict] | None = None
                              ) -> dict:
    """Find the liquidity/volume threshold that best separates grads from deads.

    Args:
        corpus: list of token_corpus dicts.
        discovery_metrics: dict of mint -> {liq, vol} at discovery time.
                           If None, the function returns a placeholder.

    Returns dict with optimal threshold and metrics.
    """
    # Build samples from discovery_metrics
    samples = []
    if discovery_metrics:
        for t in corpus:
            mint = t["mint"]
            if mint not in discovery_metrics:
                continue
            dm = discovery_metrics[mint]
            samples.append({
                "liq": dm.get("liq", 0),
                "vol": dm.get("vol", 0),
                "is_graduated": t.get("graduation_status") == "graduated",
            })

    if not samples:
        return {
            "hypothesis": "discovery_filter",
            "type": "exclusion_filter",
            "note": "Tokens below this threshold die 95%+ of the time — just skip them entirely",
            "result": None,
            "error": "No discovery metrics available — need price_snapshots_v2 data",
        }

    # Grid search over thresholds (granular at low end — where 90% tokens live)
    liq_candidates = [0, 100, 250, 500, 750, 1000, 1500, 2000,
                      3000, 5000, 7500, 10000, 20000]
    vol_candidates = [0, 50, 100, 250, 500, 750, 1000, 2500, 5000, 10000]

    best = {"threshold": None, "dead_eliminated_pct": 0,
            "grad_retained_pct": 0, "score": 0}

    for liq in liq_candidates:
        for vol in vol_candidates:
            passes = [s for s in samples if s["liq"] >= liq and s["vol"] >= vol]
            fails = [s for s in samples if s["liq"] < liq or s["vol"] < vol]

            if not passes or not fails:
                continue

            # What % of dead tokens get eliminated?
            fail_dead = sum(1 for s in fails if not s["is_graduated"])
            total_dead = sum(1 for s in samples if not s["is_graduated"])
            dead_elim = (fail_dead / total_dead) if total_dead > 0 else 0

            # What % of graduated tokens are retained?
            pass_grad = sum(1 for s in passes if s["is_graduated"])
            total_grad = sum(1 for s in samples if s["is_graduated"])
            grad_ret = (pass_grad / total_grad) if total_grad > 0 else 0

            # Prioritize dead elimination (70/30 split)
            score = dead_elim * 0.7 + grad_ret * 0.3
            if score > best.get("score", 0):
                best = {
                    "threshold": {"min_liquidity_usd": liq, "min_volume_usd": vol},
                    "dead_eliminated_pct": round(dead_elim, 4),
                    "grad_retained_pct": round(grad_ret, 4),
                    "n_pass": len(passes),
                    "n_fail": len(fails),
                    "score": round(score, 4),
                }

    return {
        "hypothesis": "discovery_filter",
        "type": "exclusion_filter",
        "note": "Tokens below this threshold die 95%+ of the time — just skip them entirely",
        "result": best,
    }
