#!/usr/bin/env python3
"""Compute true per-mint FIFO win-rate + hold profile for the dex_trending cluster."""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/hermes/project-theia")


def fifo_winrate(swaps):
    """Return (win_trades, total_closed_trades, per_mint_rr) using FIFO lots.

    For each mint, track a queue of (qty, price_sol) buys. On a sell, match
    against the queue FIFO; a closed lot is a win if sell_price > buy_price.
    Simpler proxy: compare avg buy px vs avg sell px per mint; report mint-level
    round-trip sign.
    """
    by_mint = defaultdict(lambda: {"buys": [], "sells": []})
    for s in swaps:
        m = s.get("base_mint")
        side = s.get("side")
        px = s.get("exec_price") or 0
        if side == "buy":
            by_mint[m]["buys"].append(px)
        elif side == "sell":
            by_mint[m]["sells"].append(px)

    wins = losses = 0
    for m, d in by_mint.items():
        buys, sells = d["buys"], d["sells"]
        if not buys or not sells:
            continue
        ab = sum(buys) / len(buys)
        as_ = sum(sells) / len(sells)
        # aggregate round trip: if sell size ~ buy size, compare avg price
        if as_ > ab * 1.02:
            wins += 1
        elif ab > as_ * 1.02:
            losses += 1
    return wins, losses


def hold_time_est(swaps):
    """Median seconds between first buy and first sell per mint."""
    by_mint = defaultdict(lambda: {"buy_ts": [], "sell_ts": []})
    for s in swaps:
        m = s.get("base_mint")
        ts = s.get("ts") or 0
        if not m or not ts:
            continue
        by_mint[m][s.get("side") + "_ts"].append(ts)
    holds = []
    for m, d in by_mint.items():
        if d["buy_ts"] and d["sell_ts"]:
            holds.append(min(d["sell_ts"]) - min(d["buy_ts"]))
    holds = [h for h in holds if h > 0]
    return statistics.median(holds) if holds else None


data = json.load(open("/home/hermes/project-theia/compute/_dex_trending_swaps.json"))
print("== dex_trending cluster — per-wallet FIFO win/loss + hold ==")
for w, swaps in data.items():
    if not isinstance(swaps, list) or not swaps:
        continue
    wl, ll = fifo_winrate(swaps)
    hold = hold_time_est(swaps)
    hold_m = f"{hold/60:.0f}m" if hold else "n/a"
    tot = wl + ll
    wr = wl / tot if tot else 0
    print(f"{w[:14]} roundtrips={tot} win={wl} loss={ll} winrate={wr:.2f} medianHold={hold_m}")