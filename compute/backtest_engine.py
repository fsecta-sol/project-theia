"""Backtest engine — point-in-time walk-forward over stored price history.

Deterministic. No LLM. Every trade is reconstructable from stored inputs.

Core flow per mint:
  1. Walk rows sorted by time.
  2. At row i, evaluate entry filter using ONLY data with ts <= row[i].ts.
  3. On pass, apply detection lag (fill at row[i+k]).
  4. Entry fill via amm_sim.buy_fill() against row[i+k] reserves.
  5. Exit via exit_engine.simulate_exit() over the forward path.
  6. Net PnL = (tokens * exit_price - notional) - gas - slippage_penalty.
  7. Feed per-trade PnL list into expectancy.evaluate().

Leakage guard: no post-decision data touches the entry step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import amm_sim, exit_engine, gas_sim, expectancy, costs


@dataclass
class BacktestTrade:
    mint: str
    entry_ts: int
    exit_ts: int
    entry_price: float       # SOL per token (quote/base)
    exit_price: float        # weighted avg realized exit price
    notional_sol: float
    tokens_bought: float
    gas_sol: float
    slippage_penalty_sol: float
    raw_pnl_sol: float
    net_pnl_sol: float
    exit_reason: str
    hold_secs: int


# ── Helpers ────────────────────────────────────────────────────────────────


def _latest_screen_before(mint: str, ts: int, screens: list[dict]) -> dict | None:
    """Latest screen result for mint with screen_ts <= ts."""
    candidates = [s for s in screens if s.get("mint") == mint and s.get("screen_ts", 0) <= ts]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.get("screen_ts", 0))


def _to_exit_row(row: dict) -> list:
    """Convert price snapshot dict to exit_engine row: [ts, o, h, l, c, v]."""
    return [
        row["ts"],
        row.get("o", row.get("c", 0)),
        row.get("h", row.get("c", 0)),
        row.get("l", row.get("c", 0)),
        row.get("c", 0),
        row.get("volume_24h", 0),
    ]


def _check_entry(rule: dict, mint: str, ts: int, price_row: dict,
                 screen: dict | None, pools: dict[str, dict] | None,
                 wallet_signals: dict[str, list[dict]] | None) -> bool:
    """Point-in-time entry filter. Uses ONLY data available at or before ts."""
    e = rule.get("entry", {})

    # Liquidity floor
    if price_row.get("liquidity_usd", 0) < e.get("min_liquidity_usd", 0):
        return False

    # Screen verdict
    if e.get("screen_verdict"):
        if not screen or screen.get("verdict") != e["screen_verdict"]:
            return False

    # Graduation status
    if e.get("graduated") is not None and pools:
        p = pools.get(mint, {})
        grad = p.get("graduation_status", "bonding")
        if e["graduated"] and grad != "graduated":
            return False
        if not e["graduated"] and grad == "graduated":
            return False

    # Age in minutes
    launch = price_row.get("launch_ts", ts)
    age_min = (ts - launch) / 60.0
    if age_min < e.get("min_age_min", 0):
        return False
    if age_min > e.get("max_age_min", float("inf")):
        return False

    # Wallet conviction filter
    wf = rule.get("wallet_filter", {})
    if wf.get("enabled"):
        lag = wf.get("lag_sec", 300)  # default 5 min
        signals = wallet_signals or {}
        has_signal = False
        for wallet, sigs in signals.items():
            for s in sigs:
                if s.get("mint") == mint and 0 <= (ts - s.get("buy_ts", 0)) <= lag:
                    has_signal = True
                    break
            if has_signal:
                break
        if not has_signal:
            return False

    return True


# ── Public API ─────────────────────────────────────────────────────────────


def run(rule_spec: dict,
        price_data: list[dict],
        screens: list[dict],
        pools: dict[str, dict] | None = None,
        wallet_signals: dict[str, list[dict]] | None = None,
        detection_lag_sec: int = 30,
        sol_usd: float = 150.0) -> dict:
    """Walk-forward backtest.

    Args:
        rule_spec: hypothesis rule_spec JSON (entry, size, exit, wallet_filter).
        price_data: list of rows per mint. Each row:
            {mint, ts, o, h, l, c, volume_24h, liquidity_usd,
             reserves_base, reserves_quote, launch_ts, amm_model?}
        screens: list of screen results: {mint, screen_ts, verdict, ...}
        pools: {mint: {graduation_status, ...}} — optional.
        wallet_signals: {wallet: [{mint, buy_ts}]} — optional.
        detection_lag_sec: seconds between signal detection and fill.
        sol_usd: SOL/USD price — converts the SOL notional into USD for the
            slippage-vs-liquidity model (costs.slippage_estimate is USD-based).

    Returns:
        dict with trade_pnls, metrics (expectancy), trades, counts.
    """
    if not price_data:
        return _empty_result()

    # Group by mint and sort by time
    by_mint: dict[str, list[dict]] = {}
    for r in price_data:
        by_mint.setdefault(r.get("mint", ""), []).append(r)
    for mint in by_mint:
        by_mint[mint].sort(key=lambda r: r["ts"])

    trades: list[BacktestTrade] = []
    entered_mints: set[str] = set()
    skipped_reserves_mints: set[str] = set()  # mints whose stored history lacks reserves

    size_rule = rule_spec.get("size", {})
    notional_default = size_rule.get("notional_sol", 0.5)
    max_pct_liq = size_rule.get("max_pct_liquidity", 0.02)
    exit_params = rule_spec.get("exit", {})

    for mint, rows in by_mint.items():
        if not rows:
            continue
        for i, row in enumerate(rows):
            ts = row["ts"]
            if mint in entered_mints:
                break  # one entry per mint

            # Point-in-time screen
            screen = _latest_screen_before(mint, ts, screens)

            if not _check_entry(rule_spec, mint, ts, row, screen, pools, wallet_signals):
                continue

            # Detection lag: find fill row at or after ts + lag
            fill_idx = i
            target_ts = ts + detection_lag_sec
            while fill_idx < len(rows) and rows[fill_idx]["ts"] < target_ts:
                fill_idx += 1
            if fill_idx >= len(rows):
                continue  # not enough forward data for fill

            fill_row = rows[fill_idx]

            # Sizing + liquidity guard
            notional = notional_default
            liq = fill_row.get("liquidity_usd", 0)
            if liq > 0 and notional > liq * max_pct_liq:
                continue

            # Entry fill via AMM sim. Reserves MUST be stored/derivable —
            # we never fabricate them, so every simulated fill is reconstructable.
            base_r = fill_row.get("reserves_base", 0)
            quote_r = fill_row.get("reserves_quote", 0)
            if base_r <= 0 or quote_r <= 0:
                skipped_reserves_mints.add(mint)
                continue

            entry_fill = amm_sim.buy_fill(notional, base_r, quote_r)
            entry_price = entry_fill["fill_price"]

            # Gas (entry + ATA rent for first buy)
            gas_entry = gas_sim.swap_fee_sol(first_buy=True)

            # Forward exit path: rows after fill_idx
            forward = rows[fill_idx + 1:]
            if not forward:
                continue
            exit_path = [_to_exit_row(r) for r in forward]

            exit_result = exit_engine.simulate_exit(
                entry_price, fill_row["ts"], exit_path, exit_params
            )

            # Gas per exit fill (conservative: one tx per exit bucket)
            n_exits = len(exit_result["exits"])
            gas_exit = gas_sim.swap_fee_sol() * max(1, n_exits)

            # Conservative slippage penalty on exit.
            # costs model is USD-denominated: trade size = SOL notional × SOL price.
            is_bonding = (fill_row.get("amm_model", "v2") != "v2")
            slip_pct = costs.slippage_estimate(
                trade_size_usd=notional * sol_usd,
                liquidity_usd=max(liq, 100),
                is_bonding_curve=is_bonding,
            )
            slippage_penalty = notional * slip_pct

            # PnL in SOL
            tokens = entry_fill["tokens_out"]
            sol_returned = tokens * exit_result["realized_price"]
            raw_pnl = sol_returned - notional
            net_pnl = raw_pnl - gas_entry - gas_exit - slippage_penalty

            trade = BacktestTrade(
                mint=mint,
                entry_ts=fill_row["ts"],
                exit_ts=fill_row["ts"] + exit_result["hold_secs"],
                entry_price=entry_price,
                exit_price=exit_result["realized_price"],
                notional_sol=notional,
                tokens_bought=tokens,
                gas_sol=gas_entry + gas_exit,
                slippage_penalty_sol=slippage_penalty,
                raw_pnl_sol=raw_pnl,
                net_pnl_sol=net_pnl,
                exit_reason=exit_result["final_reason"],
                hold_secs=exit_result["hold_secs"],
            )
            trades.append(trade)
            entered_mints.add(mint)
            break  # one round-trip per mint

    trade_pnls = [t.net_pnl_sol for t in trades]
    metrics = expectancy.evaluate(trade_pnls)

    return {
        "trade_pnls": trade_pnls,
        "metrics": metrics,
        "trades": [t.__dict__ for t in trades],
        "n_candidates": len(by_mint),
        "n_entered": len(trades),
        "n_skipped_no_reserves": len(skipped_reserves_mints),
    }


def _empty_result() -> dict:
    return {
        "trade_pnls": [],
        "metrics": expectancy.evaluate([]),
        "trades": [],
        "n_candidates": 0,
        "n_entered": 0,
        "n_skipped_no_reserves": 0,
    }
