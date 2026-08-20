"""Exit state machine over a historical price path (memecoin profile).

Wide hard stop + laddered take-profit + trailing runner + time stop. Within a bucket
the stop is checked before the TP (conservative). Prices are quote-per-base (SOL/token)
to match OHLCV currency=token. Path rows: [ts,o,h,l,c(,v)].
"""
from __future__ import annotations

DEFAULTS = {
    "hard_stop": -0.35,
    "tp_ladder": [(2.0, 0.5), (4.0, 0.25)],  # (mult, fraction)
    "trail_drop": 0.25,
    "time_stop_secs": 4 * 3600,
}


def simulate_exit(entry_price: float, entry_ts: int, path: list,
                  params: dict | None = None, follow_exit_ts: int | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    remaining = 1.0
    exits = []
    exit_events = []
    peak = entry_price
    hard_stop_px = entry_price * (1 + p["hard_stop"])
    ladder = list(p["tp_ladder"])
    last_ts, last_close = entry_ts, entry_price

    def close(frac, price, reason, ts):
        nonlocal remaining
        exits.append((frac, price, reason))
        exit_events.append({"fraction": frac, "price": price, "reason": reason, "ts": ts})
        remaining -= frac

    for row in path:
        ts, hi, lo, c = row[0], row[2], row[3], row[4]
        last_ts, last_close = ts, c
        peak = max(peak, hi)
        if follow_exit_ts is not None and ts >= follow_exit_ts and remaining > 1e-9:
            close(remaining, c, "follow_exit", ts); break
        if ts - entry_ts >= p["time_stop_secs"] and remaining > 1e-9:
            close(remaining, c, "time_stop", ts); break
        if lo <= hard_stop_px and remaining > 1e-9:
            close(remaining, hard_stop_px, "hard_stop", ts); break
        while ladder and hi >= entry_price * ladder[0][0] and remaining > 1e-9:
            mult, frac = ladder.pop(0)
            close(min(frac, remaining), entry_price * mult, f"tp_{mult:g}x", ts)
        if not ladder and remaining > 1e-9:
            trail_px = peak * (1 - p["trail_drop"])
            if lo <= trail_px:
                close(remaining, trail_px, "trail", ts); break

    if remaining > 1e-9:
        close(remaining, last_close, "path_end", last_ts)

    realized_price = sum(f * pr for f, pr, _ in exits)
    exit_ts = exit_events[-1]["ts"] if exit_events else entry_ts
    return {"realized_price": realized_price,
            "return_mult": realized_price / entry_price if entry_price else 0.0,
            "final_reason": exits[-1][2] if exits else "none",
            "hold_secs": exit_ts - entry_ts,
            "exit_ts": exit_ts,
            "exits": exits,
            "exit_events": exit_events}
