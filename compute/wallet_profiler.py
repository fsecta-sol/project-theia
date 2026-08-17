"""Wallet profiler — deterministic trade-pattern statistics from swap history.

Input: list of swaps [{ts, side, base_mint, quote_mint, base_qty, quote_qty, exec_price}, ...]
Output: profile dict — frequency, size, hold-time, PnL, pattern classification.

No LLM math. All numbers reconstructable from the swap list.
"""
from __future__ import annotations

import math


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def match_trades(swaps: list[dict]) -> list[dict]:
    """FIFO-match buys to subsequent sells of the same mint.

    Returns list of round-trips: {mint, buy_ts, sell_ts, hold_min, buy_sol,
    sell_sol, pnl_sol, pnl_pct}. Partial fills matched in order.
    """
    by_mint: dict[str, list[dict]] = {}
    for s in swaps:
        mint = s.get("base_mint")
        if not mint:
            continue
        by_mint.setdefault(mint, []).append(s)

    round_trips = []
    for mint, txs in by_mint.items():
        txs = sorted(txs, key=lambda x: x.get("ts", 0))
        open_buys: list[dict] = []
        for tx in txs:
            if tx.get("side") == "buy":
                open_buys.append(tx)
            elif tx.get("side") == "sell" and open_buys:
                buy = open_buys.pop(0)  # FIFO
                buy_sol = buy.get("quote_qty", 0) or 0
                sell_sol = tx.get("quote_qty", 0) or 0
                hold_min = (tx.get("ts", 0) - buy.get("ts", 0)) / 60
                pnl_sol = sell_sol - buy_sol
                pnl_pct = (pnl_sol / buy_sol * 100) if buy_sol > 0 else None
                round_trips.append({
                    "mint": mint,
                    "buy_ts": buy.get("ts"),
                    "sell_ts": tx.get("ts"),
                    "hold_min": hold_min,
                    "buy_sol": buy_sol,
                    "sell_sol": sell_sol,
                    "pnl_sol": pnl_sol,
                    "pnl_pct": pnl_pct,
                })
    return round_trips


def profile_wallet(wallet: str, swaps: list[dict]) -> dict:
    """Full trade-pattern profile for one wallet."""
    if not swaps:
        return {"wallet": wallet, "total_trades": 0, "pattern_cluster": "inactive"}

    buys = [s for s in swaps if s.get("side") == "buy"]
    sells = [s for s in swaps if s.get("side") == "sell"]
    ts_all = [s.get("ts", 0) for s in swaps if s.get("ts")]
    span_hr = (max(ts_all) - min(ts_all)) / 3600 if len(ts_all) > 1 else 0

    buy_sizes = [s.get("quote_qty", 0) for s in buys if s.get("quote_qty")]
    unique_tokens = len({s.get("base_mint") for s in buys})

    rts = match_trades(swaps)
    pnls = [r["pnl_sol"] for r in rts]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0)
    expectancy = _mean(pnls)
    win_rate = len(wins) / len(pnls) if pnls else None

    trades_per_hour = len(swaps) / span_hr if span_hr > 0 else len(swaps)
    med_hold = _median([r["hold_min"] for r in rts])
    med_buy = _median(buy_sizes)

    # ── pattern classification (rule-based, deterministic) ─────────────────
    if med_buy is not None and med_buy < 0.05:
        cluster = "dust_bot"
    elif med_buy is not None and med_buy > 10:
        cluster = "whale"
    elif trades_per_hour >= 10 and (med_hold is None or med_hold < 60):
        cluster = "high_freq_scalper"
    elif trades_per_hour < 5 and med_hold is not None and med_hold >= 240:
        cluster = "position_trader"
    else:
        cluster = "mixed"

    return {
        "wallet": wallet,
        "first_seen_ts": min(ts_all) if ts_all else None,
        "last_active_ts": max(ts_all) if ts_all else None,
        "total_trades": len(swaps),
        "total_buys": len(buys),
        "total_sells": len(sells),
        "unique_tokens": unique_tokens,
        "trades_per_hour": trades_per_hour,
        "span_hours": span_hr,
        "median_buy_sol": med_buy,
        "mean_buy_sol": _mean(buy_sizes),
        "median_hold_min": med_hold,
        "median_pnl_pct": _median([r["pnl_pct"] for r in rts if r["pnl_pct"] is not None]),
        "n_round_trips": len(rts),
        "win_rate": win_rate,
        "profit_factor": pf,
        "expectancy_sol": expectancy,
        "total_pnl_sol": sum(pnls) if pnls else 0,
        "pattern_cluster": cluster,
    }


def profile_all(swaps_by_wallet: dict[str, list[dict]]) -> list[dict]:
    """Profile every wallet; return list sorted by total_pnl_sol desc."""
    profiles = [profile_wallet(w, txs) for w, txs in swaps_by_wallet.items()]
    return sorted(profiles, key=lambda p: -(p.get("total_pnl_sol") or 0))
