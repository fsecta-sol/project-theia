"""Corpus labeling: death detection + graduation detection + label classifier.

Deterministic rules only — no LLM, no black-box API. Every label is
reconstructable from stored inputs.
"""
from __future__ import annotations


def is_dead(token: dict, now_ts: int) -> tuple[bool, str | None]:
    """Deterministic dead detection. Only 2 rules for Phase 1.

    Returns (is_dead, death_reason).
    """
    launch_ts = token.get("launch_ts", 0) or 0
    age_hours = (now_ts - launch_ts) / 3600
    grad_status = token.get("graduation_status", "bonding")

    # Rule 1: >24h since launch and never graduated
    if age_hours > 24 and grad_status != "graduated":
        return True, "natural_decay"

    # Rule 2: Price dropped >90% from ATH AND effectively no volume/liquidity
    ath = float(token.get("ath_usd", 0) or 0)
    price = float(token.get("price_usd", 0) or 0)
    volume = float(token.get("volume_24h", 0) or 0)
    liq = float(token.get("liquidity_usd", 0) or 0)
    if ath > 0 and price < ath * 0.1 and liq < 200 and volume < 500:
        return True, "liquidity_drain"

    return False, None


def detect_graduation(pairs: list[dict]) -> dict:
    """Check if token has a non-pump.fun DEX pool."""
    dex_ids = {p.get("dexId", "") for p in pairs}
    real_dexes = ["raydium", "orca", "meteora"]
    graduated = any(d in dex_ids for d in real_dexes)
    if graduated:
        grad_dex = next(d for d in real_dexes if d in dex_ids)
        grad_pair = next((p for p in pairs
                          if p.get("dexId") == grad_dex and p.get("priceUsd")), None)
        return {
            "status": "graduated",
            "dex": grad_dex,
            "price_usd": float(grad_pair.get("priceUsd", 0)) if grad_pair else 0,
        }
    return {"status": "bonding"}


def _extract_price(pairs: list[dict]) -> float:
    """Best price: prefer Raydium > Orca > Meteora > Pump.fun."""
    for dex in ["raydium", "orca", "meteora", "pump.fun"]:
        for p in pairs:
            if (p.get("dexId", "").lower() == dex
                    and p.get("priceUsd") and float(p.get("priceUsd", 0)) > 0):
                return float(p["priceUsd"])
    return 0.0


def _extract_liq(pairs: list[dict]) -> float:
    """Best liquidity: prefer Raydium > Orca > Meteora > Pump.fun."""
    for dex in ["raydium", "orca", "meteora", "pump.fun"]:
        for p in pairs:
            if p.get("dexId", "").lower() == dex:
                liq = (p.get("liquidity") or {}).get("usd", 0)
                if liq and float(liq) > 0:
                    return float(liq)
    return 0.0


def classify_label(token: dict, pairs: list[dict], now_ts: int) -> dict:
    """Full labeling: graduated, dead, or still bonding.

    token must have at minimum: launch_ts, graduation_status, ath_usd, price_usd,
    volume_24h, liquidity_usd.

    Returns dict suitable for upsert_corpus / update_graduation.
    """
    grad = detect_graduation(pairs)
    if grad["status"] == "graduated":
        return {"graduation_status": "graduated", "graduation_ts": now_ts,
                "death_reason": None, "final_price_usd": grad["price_usd"],
                "final_liquidity_usd": _extract_liq(pairs)}

    dead, reason = is_dead(token, now_ts)
    if dead:
        price = _extract_price(pairs)
        return {"graduation_status": "dead", "graduation_ts": now_ts,
                "death_reason": reason, "final_price_usd": price,
                "final_liquidity_usd": _extract_liq(pairs)}

    return {"graduation_status": "bonding", "graduation_ts": 0,
            "death_reason": None, "final_price_usd": _extract_price(pairs),
            "final_liquidity_usd": _extract_liq(pairs)}
