"""Fee & slippage model for memecoin trades.

Conservative estimates: bonding curve slippage caps at 50%, AMM at 10%.
Better to over-estimate costs than under-estimate — a model profitable
with 20% slippage will thrive at 5%; the reverse won't.
"""
from __future__ import annotations


def slippage_estimate(trade_size_usd: float, liquidity_usd: float,
                      is_bonding_curve: bool = True) -> float:
    """Conservative slippage estimate.

    Bonding curve (Pump.fun): superlinear model, cap 50%.
    AMM (Raydium/Orca): linear model, cap 10%.
    """
    liq = max(liquidity_usd, 100)  # floor 100 USD to avoid div/0
    ratio = trade_size_usd / liq

    if is_bonding_curve:
        slippage = min(0.50, (ratio ** 1.5) * 0.5)
    else:
        slippage = min(0.10, ratio * 0.3)

    return round(slippage, 4)


def simulate_costs(trade_size_usd: float, liquidity_usd: float,
                   is_bonding_curve: bool = True,
                   entry: bool = True, exit: bool = True) -> dict:
    """Estimate round-trip costs for a memecoin trade.

    Returns dict with entry_cost_usd, exit_cost_usd, total_cost_usd,
    entry_slippage_pct, exit_slippage_pct.
    """
    priority_tip_usd = 0.15          # conservative for fast inclusion
    base_tx_fee_usd = 0.001          # ~5000 lamports in USD
    fixed_per_tx = priority_tip_usd + base_tx_fee_usd

    dex_fee_pct = 0.0025             # 0.25% per swap (Raydium standard)
    dex_fee_usd = trade_size_usd * dex_fee_pct

    entry_slip_pct = slippage_estimate(trade_size_usd, liquidity_usd, is_bonding_curve)
    entry_slip_usd = trade_size_usd * entry_slip_pct

    # Exit: assume liquidity is 70% of original (conservative — lower post-pump)
    exit_slip_pct = slippage_estimate(trade_size_usd, liquidity_usd * 0.7, is_bonding_curve)
    exit_slip_usd = trade_size_usd * exit_slip_pct

    entry_cost = (fixed_per_tx + dex_fee_usd + entry_slip_usd) if entry else 0
    exit_cost = (fixed_per_tx + dex_fee_usd + exit_slip_usd) if exit else 0

    return {
        "entry_cost_usd": round(entry_cost, 4),
        "exit_cost_usd": round(exit_cost, 4),
        "total_cost_usd": round(entry_cost + exit_cost, 4),
        "entry_slippage_pct": entry_slip_pct,
        "exit_slippage_pct": exit_slip_pct,
    }
