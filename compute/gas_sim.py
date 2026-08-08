"""Solana transaction cost (verified fee structure). Returns SOL (quote units).

fee = 5000 lamports/sig (50% burned) + ceil(cu_price_microlamports*cu_limit/1e6) (tip).
First buy of a new token also pays ~0.002 SOL ATA rent, once.
"""
from __future__ import annotations

import math

LAMPORTS_PER_SOL = 1_000_000_000
BASE_LAMPORTS_PER_SIG = 5000
ATA_RENT_SOL = 0.00203928


def swap_fee_sol(cu_price_microlamports: float = 50_000.0, cu_limit: int = 200_000,
                 n_sigs: int = 1, first_buy: bool = False) -> float:
    base = BASE_LAMPORTS_PER_SIG * n_sigs
    priority = math.ceil(cu_price_microlamports * cu_limit / 1e6)
    fee = (base + priority) / LAMPORTS_PER_SOL
    return fee + (ATA_RENT_SOL if first_buy else 0.0)
