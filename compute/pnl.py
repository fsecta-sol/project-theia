"""FIFO realized/unrealized P&L over a wallet/strategy's per-token swap lots.

A 'trade' = one round-trip per token: opened 0→+, closed when >=95% of peak qty sold.
Win = realized P&L > 0. Gas subtracted. Feed the returned per-trade P&L list into
expectancy.evaluate().

wallet_pnl_summary(): aggregate wallet-level stats (realized, unrealized, per-token).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class WalletPnl:
    wallet: str
    total_realized: float           # quote units
    total_unrealized: float         # quote units (computed if prices provided)
    total_cost_basis: float         # total spent on still-open positions
    n_trades: int                   # closed round-trips
    n_wins: int                     # round-trips with P&L > 0
    n_active_positions: int         # tokens with open balance > 0
    per_token: list[dict] = field(default_factory=list)  # per-mint breakdown
    realized_trade_pnls: list[float] = field(default_factory=list)


def fifo_trade_pnls(swaps: list[dict]) -> list[float]:
    """swaps: [{ts, side ('buy'|'sell'), base_mint, base_qty, quote_qty, gas_quote?}].
    Returns per-closed-trade realized P&L in quote units."""
    by_token: dict[str, list[dict]] = defaultdict(list)
    for s in swaps:
        by_token[s["base_mint"]].append(s)

    out: list[float] = []
    for lots in by_token.values():
        lots.sort(key=lambda s: s.get("ts") or 0)
        fifo: deque[tuple[float, float]] = deque()  # (qty, unit_cost incl gas)
        peak = held = trade_pnl = 0.0
        open_ = False
        for s in lots:
            gq = float(s.get("gas_quote", 0) or 0)
            if s["side"] == "buy":
                q = float(s["base_qty"])
                if q <= 0:
                    continue
                fifo.append((q, (float(s["quote_qty"]) + gq) / q))
                held += q
                peak = max(peak, held)
                open_ = True
            else:
                if not open_ or float(s["base_qty"]) <= 0:
                    continue
                remaining = float(s["base_qty"])
                proceeds_unit = float(s["quote_qty"]) / remaining
                matched_cost = 0.0
                while remaining > 1e-12 and fifo:
                    lq, lc = fifo[0]
                    take = min(lq, remaining)
                    matched_cost += take * lc
                    remaining -= take
                    fifo[0] = (lq - take, lc)
                    if fifo[0][0] <= 1e-12:
                        fifo.popleft()
                sold = float(s["base_qty"]) - remaining
                trade_pnl += sold * proceeds_unit - matched_cost - gq
                held -= sold
                if peak > 0 and held <= 0.05 * peak:
                    out.append(trade_pnl)
                    fifo.clear()
                    peak = held = trade_pnl = 0.0
                    open_ = False
    return out


def wallet_pnl_summary(
    swaps: list[dict],
    prices: dict[str, float] | None = None,
    quote_symbol: str = "SOL",
) -> WalletPnl:
    """Aggregate wallet-level P&L from swap history.

    swaps: [{side, base_mint, base_qty, quote_mint, quote_qty, exec_price, ts}, ...]
    prices: {base_mint: current_price_in_quote} — optional, for unrealized P&L.
    quote_symbol: what the P&L is denominated in (SOL by default).

    Returns WalletPnl with realized + unrealized + per-token breakdown.
    """
    prices = prices or {}
    by_token: dict[str, list[dict]] = defaultdict(list)
    for s in swaps:
        by_token[s["base_mint"]].append(s)

    result = WalletPnl(wallet="", total_realized=0.0, total_unrealized=0.0,
                       total_cost_basis=0.0, n_trades=0, n_wins=0,
                       n_active_positions=0)

    for mint, lots in by_token.items():
        lots.sort(key=lambda s: s.get("ts") or 0)
        fifo: deque[tuple[float, float]] = deque()
        peak = held = token_realized = 0.0
        open_ = False

        for s in lots:
            if s["side"] == "buy":
                q = float(s["base_qty"])
                if q <= 0:
                    continue
                fifo.append((q, float(s["quote_qty"]) / q))
                held += q
                peak = max(peak, held)
                open_ = True
            else:
                if not open_ or float(s["base_qty"]) <= 0:
                    continue
                remaining = float(s["base_qty"])
                proceeds_unit = float(s["quote_qty"]) / remaining
                matched_cost = 0.0
                while remaining > 1e-12 and fifo:
                    lq, lc = fifo[0]
                    take = min(lq, remaining)
                    matched_cost += take * lc
                    remaining -= take
                    fifo[0] = (lq - take, lc)
                    if fifo[0][0] <= 1e-12:
                        fifo.popleft()
                sold = float(s["base_qty"]) - remaining
                token_realized += sold * proceeds_unit - matched_cost
                held -= sold
                if peak > 0 and held <= 0.05 * peak:
                    result.realized_trade_pnls.append(token_realized)
                    result.total_realized += token_realized
                    result.n_trades += 1
                    if token_realized > 0:
                        result.n_wins += 1
                    fifo.clear()
                    peak = held = token_realized = 0.0
                    open_ = False

        # If still holding → compute unrealized
        if open_ and held > 1e-12:
            cost_basis = 0.0
            remaining = held
            for lq, lc in fifo:
                take = min(lq, remaining)
                cost_basis += take * lc
                remaining -= take
                if remaining <= 0:
                    break

            current_price = prices.get(mint, 0.0)
            unrealized = (held * current_price - cost_basis) if current_price > 0 else 0.0

            result.total_cost_basis += cost_basis
            result.total_unrealized += unrealized
            result.n_active_positions += 1

            # Only include unclosed token P&L in realized if a round-trip was completed
            if token_realized != 0.0:
                result.realized_trade_pnls.append(token_realized)
                result.total_realized += token_realized
                result.n_trades += 1
                if token_realized > 0:
                    result.n_wins += 1

        result.per_token.append({
            "mint": mint,
            "quote": quote_symbol,
            "realized": round(token_realized, 6),
            "unrealized": round(unrealized if open_ else 0, 6),
            "cost_basis": round(cost_basis if open_ else 0, 6),
            "held": round(held, 6),
            "current_price": round(current_price if open_ else 0, 10),
        })

    result.total_realized = round(result.total_realized, 6)
    result.total_unrealized = round(result.total_unrealized, 6)
    result.total_cost_basis = round(result.total_cost_basis, 6)

    return result
