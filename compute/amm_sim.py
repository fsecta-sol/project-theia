"""Constant-product (Uniswap-v2 style) fill model — conservative default for Solana
AMMs and pump.fun bonding curves (flag amm_model to refine). Position size feeds fill
price, so oversizing a thin pool self-penalizes."""
from __future__ import annotations


def buy_fill(quote_in: float, base_reserve: float, quote_reserve: float,
             fee: float = 0.01) -> dict:
    """Buy base with quote_in against reserves (x=base, y=quote)."""
    spot = quote_reserve / base_reserve
    dy = quote_in * (1.0 - fee)
    tokens_out = base_reserve * dy / (quote_reserve + dy)
    fill_price = quote_in / tokens_out
    return {"tokens_out": tokens_out, "fill_price": fill_price,
            "slippage": fill_price / spot - 1.0, "spot": spot}


def sell_fill(base_in: float, base_reserve: float, quote_reserve: float,
              fee: float = 0.01) -> dict:
    """Sell base_in base for quote against reserves."""
    spot = quote_reserve / base_reserve
    dx = base_in * (1.0 - fee)
    quote_out = quote_reserve * dx / (base_reserve + dx)
    fill_price = quote_out / base_in
    return {"quote_out": quote_out, "fill_price": fill_price,
            "slippage": fill_price / spot - 1.0, "spot": spot}


def backout_reserves(dy_quote_in: float, p_exec: float, spot_p0: float,
                     fee: float = 0.01) -> dict | None:
    """Recover reserves from an observed buy (exec price) + pre-trade spot (OHLCV open):
    p_exec/spot = (1/(1-f))*(1+dy_eff/y). Approximate — labelled as such."""
    if dy_quote_in <= 0 or p_exec <= 0 or spot_p0 <= 0:
        return None
    denom = (p_exec / spot_p0) * (1.0 - fee) - 1.0
    if denom <= 0:
        return None
    y = dy_quote_in * (1.0 - fee) / denom
    x = y / spot_p0
    if x <= 0 or y <= 0:
        return None
    return {"base_reserve": x, "quote_reserve": y, "spot": spot_p0,
            "method": "single-swap-backout+ohlcv-spot"}
