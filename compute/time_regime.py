"""H5: Time regime classification + descriptive statistics.

Phase 1: DESCRIPTIVE ONLY. No trading signal.
Needs 2000+ token corpus for statistical significance.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


def classify_regime(launch_ts: int) -> str:
    """Classify token launch time into a trading regime.

    UTC → EST mapping (EST = UTC-5 standard time):
      18:00 EST = 23:00 UTC    00:00 EST = 05:00 UTC    09:00 EST = 14:00 UTC
    """
    dt = datetime.fromtimestamp(launch_ts, tz=timezone.utc)
    hour = dt.hour
    weekday = dt.weekday()  # 0=Mon, 6=Sun

    if weekday >= 5:
        return "weekend"

    if 23 <= hour or hour < 5:
        return "us_evening_night"       # 18:00-00:00 EST — peak memecoin hours
    if 5 <= hour < 14:
        return "us_morning_asia"        # 00:00-09:00 EST — Asia dominance
    if 14 <= hour < 22:
        return "asia_eu"                # 09:00-17:00 EST — Asia+EU overlap
    return "eu_us_overlap"              # 17:00-18:00 EST — transition


def graduation_by_regime(corpus: list[dict]) -> dict:
    """H5: Graduation rate per time regime. DESCRIPTIVE ONLY."""
    regime_data: defaultdict[str, dict] = defaultdict(
        lambda: {"total": 0, "graduated": 0, "dead": 0})

    for t in corpus:
        regime = t.get("time_regime", "unknown")
        regime_data[regime]["total"] += 1
        if t.get("graduation_status") == "graduated":
            regime_data[regime]["graduated"] += 1
        elif t.get("graduation_status") == "dead":
            regime_data[regime]["dead"] += 1

    result = {}
    for regime, data in regime_data.items():
        if data["total"] >= 20:  # minimum sample for reporting
            result[regime] = {
                "total": data["total"],
                "graduated": data["graduated"],
                "dead": data["dead"],
                "grad_rate": round(data["graduated"] / data["total"], 4),
            }

    return {
        "hypothesis": "time_regime",
        "type": "descriptive",
        "note": (
            "NOT a trading signal. "
            "Needs 2000+ token corpus for statistical significance."
        ),
        "regimes": result,
    }
