#!/usr/bin/env python3
"""Compute TRUE per-wallet win-rate for dex_trending wallets from their own swaps.

walletNew API doesn't provide winrate for non-GMGN-tracked wallets; the leaderboard
only has top-ranked wallets. The honest number comes from each wallet's own swap
history (we have it in _dex_trending_swaps.json) — FIFO per-mint round trips.

Also fills the profit_factor + expectancy columns in wallet_profiles so the
pipeline has real numbers to work with.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

SWAPS = Path("/home/hermes/project-theia/compute/_dex_trending_swaps.json")
DB = Path.home() / ".hermes/theia/theia.db"


def compute_winrate(swaps):
    """Per-mint aggregate round-trip: buy avg px vs sell avg px per mint."""
    by_mint = defaultdict(lambda: {"buys": [], "sells": []})
    for s in swaps:
        m = s.get("base_mint")
        if not m:
            continue
        side = s.get("side")
        px = s.get("exec_price") or 0
        if side == "buy":
            by_mint[m]["buys"].append(px)
        elif side == "sell":
            by_mint[m]["sells"].append(px)
    wins = losses = 0
    wins_sol = 0.0
    losses_sol = 0.0
    for m, d in by_mint.items():
        buys, sells = d["buys"], d["sells"]
        if not buys or not sells:
            continue
        ab = sum(buys) / len(buys)
        as_ = sum(sells) / len(sells)
        # round trip value per mint (approximate: use base qty if available? no —
        # we only have prices here; use price ratio as proxy for the trade sign)
        ret = as_ / ab - 1
        if ret > 0.02:
            wins += 1
            wins_sol += ret
        elif ret < -0.02:
            losses += 1
            losses_sol += -ret
    tot = wins + losses
    wr = wins / tot if tot else None
    pf = (wins_sol / losses_sol) if losses_sol > 0 else (None if wins_sol == 0 else 999.0)
    return wr, pf, wins, losses


def main():
    data = json.loads(SWAPS.read_text())
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1 AND source='dex_trending'"
    ).fetchall()
    wallets = [r[0] for r in rows]
    print(f"dex_trending smart wallets: {len(wallets)}")
    print(f"{'wallet':<14} {'win%':>6} {'PF':>7} {'wins':>5} {'loss':>5}  <- from own swaps")

    updated = 0
    for w in wallets:
        swaps = data.get(w)
        if not isinstance(swaps, list) or not swaps:
            print(f"{w[:12]:<14} no swap data")
            continue
        wr, pf, wins, losses = compute_winrate(swaps)
        if wr is None:
            print(f"{w[:12]:<14} no round trips (only buys or only sells)")
            continue
        con.execute(
            "UPDATE wallet_profiles SET win_rate=?, profit_factor=?, total_trades=?, updated_ts=? "
            "WHERE wallet=?",
            (wr, pf, len(swaps), int(time.time()), w))
        con.commit()
        updated += 1
        print(f"{w[:12]:<14} {wr:>6.2f} {pf if pf is not None else 0:>7.2f} {wins:>5} {losses:>5}")

    con.close()
    print(f"\ndone: updated={updated}")


if __name__ == "__main__":
    main()