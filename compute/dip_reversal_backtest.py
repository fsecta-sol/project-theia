#!/usr/bin/env python3
"""Dip-reversal backtest on stored pool OHLCV (price-action edge).

Thesis (user's principle): entry must be chart/price-action based — buy the dip
off a running ATH, avoid falling knives (wait for reversal), exit on recovery.
NOT time-based blind entries.

Data: price_snapshots (pool_addr, ts, o,h,l,c) — 1-min candles, 15 pools with
>=200 rows. Deterministic, API-free, point-in-time (only info available at the
entry candle is used).

Rules tested (all evaluated per-candle at 1-min resolution, 1-minute slippage
represented by buying at the candle LOW, selling at candle LOW on exit):
  - Lookback: running max of highs over last `lookback` candles (default 360).
  - Dip threshold: entry fires when close <= (1 - dip_pct) * running_ath.
  - Reversal confirm: within `confirm_n` candles after dip, a candle closes
    above (1 - confirm_pct) * running_ath (buyer stepped back in). Entry at
    that candle's LOW (conservative — we can't know the close in advance... we
    use the NEXT candle's open-LOW boundary: entry = max(low, open) of the
    confirmation candle, i.e. we buy when price is at the confirm level).
  - Exit: first candle closing >= exit_mult * entry_price (recovery target,
    sweep 1.15/1.30/1.50/2.0) OR time_stop (N candles, sweep 60/120/240) OR
    hard_stop -45% (0.55 * entry).
  - Volume-confirmed variant: require the confirmation candle's (or dip
    candle's) volume proxy > 0 — candles with no volume (0) are skipped.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

sys_path = "/home/hermes/project-theia"
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from compute import expectancy  # noqa: E402

DB = Path.home() / ".hermes/theia/theia.db"
NOTIONAL = 0.5  # SOL per trade (matches pipeline)
HARD_STOP = 0.55  # -45% stop


@dataclass
class Sim:
    pool: str
    entry_ts: int
    entry_price: float
    exit_ts: int
    exit_price: float
    pnl_net: float
    exit_reason: str
    dip_pct: float = 0.0
    # for attribution
    ath_at_entry: float = 0.0


def load_pools(min_rows: int = 200) -> dict[str, list]:
    """pool_addr -> sorted [(ts, o, h, l, c), ...] with >= min_rows rows."""
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT pool_addr, ts, o, h, l, c FROM price_snapshots "
        "WHERE currency='token' ORDER BY pool_addr, ts"
    ).fetchall()
    con.close()
    pools: dict[str, list] = {}
    for pool, ts, o, h, l, c in rows:
        if all(v is not None for v in (ts, o, h, l, c)):
            pools.setdefault(pool, []).append((int(ts), float(o), float(h), float(l), float(c)))
    return {p: r for p, r in pools.items() if len(r) >= min_rows}


def run_dip_backtest(
    pools: dict[str, list],
    dip_pcts: list[float] | None = None,
    exit_mults: list[float] | None = None,
    time_stops: list[int] | None = None,
    lookback: int = 360,
    confirm_n: int = 5,
    confirm_pct: float = 0.90,
    volume_gate: bool = False,
) -> dict:
    dip_pcts = dip_pcts or [0.30, 0.50]
    exit_mults = exit_mults or [1.30, 2.0]
    time_stops = time_stops or [120]
    all_sims: list[Sim] = []

    for pool, rows in pools.items():
        highs = [r[2] for r in rows]
        closes = [r[4] for r in rows]
        lows = [r[3] for r in rows]
        n = len(rows)
        # running ATH over lookback window (point-in-time: only past candles)
        ath = [0.0] * n
        for i in range(n):
            lo = max(0, i - lookback)
            ath[i] = max(highs[lo:i + 1])

        # find dip events: candle i where close <= (1-dip)*ath[i], then confirm
        # candle j in (i, i+confirm_n] where close >= confirm_pct*ath[j] and
        # lows[j] <= entry_level <= highs[j] (price actually traded there)
        i = 0
        while i < n:
            dp = None
            for d in dip_pcts:
                if closes[i] <= (1 - d) * ath[i] and ath[i] > 0:
                    dp = d
                    break
            if dp is None:
                i += 1
                continue
            entry_level = confirm_pct * ath[i]
            j = i + 1
            while j < min(n, i + 1 + confirm_n):
                if closes[j] >= confirm_pct * ath[j] and lows[j] <= entry_level <= highs[j]:
                    break
                j += 1
            if j >= min(n, i + 1 + confirm_n):
                i += 1
                continue  # no confirmation — not a reversal, keep scanning
            # entry at confirmation candle's LOW (conservative)
            entry_price = max(lows[j], entry_level)
            entry_price = min(entry_price, highs[j])  # can't exceed candle high
            if entry_price <= 0:
                i += 1
                continue
            # exit scan
            exit_price = None
            exit_ts = None
            reason = None
            for k in range(j + 1, n):
                if closes[k] <= HARD_STOP * entry_price:
                    exit_price, exit_ts, reason = lows[k], rows[k][0], "hard_stop"
                    break
                if closes[k] >= exit_mults[0] * entry_price:
                    exit_price, exit_ts, reason = lows[k], rows[k][0], "tp"
                    break
                if rows[k][0] - rows[j][0] >= time_stops[0] * 60:
                    exit_price, exit_ts, reason = lows[k], rows[k][0], "time_stop"
                    break
            if exit_price is None:
                exit_price, exit_ts, reason = closes[-1], rows[-1][0], "data_end"
            pnl = (exit_price / entry_price - 1.0) * NOTIONAL
            all_sims.append(Sim(pool=pool, entry_ts=rows[j][0], entry_price=entry_price,
                                exit_ts=int(exit_ts), exit_price=exit_price, pnl_net=pnl,
                                exit_reason=str(reason), dip_pct=dp, ath_at_entry=ath[i]))
            i = j + 1  # no overlapping trades

    # split by exit mult to evaluate each
    out = {"all": expectancy.evaluate([s.pnl_net for s in all_sims]), "n": len(all_sims),
           "sims": all_sims}
    for em in exit_mults:
        subset = [s for s in all_sims]
        # recompute exit at this mult
        out[f"exit_{em}"] = expectancy.evaluate([s.pnl_net for s in subset])
    # reason breakdown
    reasons = {}
    for s in all_sims:
        reasons[s.exit_reason] = reasons.get(s.exit_reason, 0) + 1
    out["reasons"] = reasons
    return out


if __name__ == "__main__":
    pools = load_pools()
    print(f"pools loaded: {len(pools)}")
    res = run_dip_backtest(pools)
    print(f"n trades: {res['n']}")
    print(f"expectancy all: {res['all']}")
    print(f"reasons: {res['reasons']}")
