"""Expectancy & payoff metrics from a list of per-trade P&L (the SUCCESS metric).

Target: expectancy > 0 AND profit_factor > 1. Win-rate is reported but is a milestone,
never the goal — a high win-rate with a bad payoff ratio still loses.
"""
from __future__ import annotations

from .wilson import wilson_lower_bound


def evaluate(trade_pnls: list[float]) -> dict:
    """Roll up per-trade P&L into the metrics that decide a hypothesis."""
    n = len(trade_pnls)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "wilson_low": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0, "max_drawdown": 0.0,
                "total": 0.0, "passes": False}
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p <= 0]
    win_rate = len(wins) / n
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    # max drawdown on cumulative P&L
    cum = peak = dd = 0.0
    for p in trade_pnls:
        cum += p
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {
        "n": n, "win_rate": round(win_rate, 4),
        "wilson_low": round(wilson_lower_bound(len(wins), n), 4),
        "expectancy": expectancy, "profit_factor": pf,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "gross_profit": gross_profit, "gross_loss": gross_loss,
        "max_drawdown": dd, "total": sum(trade_pnls),
        # the gate: positive expectancy AND payoff > 1
        "passes": expectancy > 0 and pf > 1.0,
    }
