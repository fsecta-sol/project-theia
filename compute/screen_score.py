"""Deterministic screening — the survival edge. Turn raw signals into rug/wash/screen
scores + a verdict. Most memecoins die to zero; rejecting the −100% tail raises
expectancy without needing speed. Thresholds are a first pass, tuned via hypotheses.
"""
from __future__ import annotations

TAX_CAP = 0.10
MIN_LIQ_USD = 30_000


def rug_score(sig: dict) -> tuple[float, list[str]]:
    """sig: {mint_auth_live, freeze_auth_live, lp_locked, top10_share}. Higher = riskier."""
    s, why = 0.0, []
    if sig.get("mint_auth_live"):
        s += 0.4; why.append("mint-authority-live")
    if sig.get("freeze_auth_live"):
        s += 0.4; why.append("freeze-authority-live")
    if not sig.get("lp_locked", False):
        s += 0.2; why.append("lp-not-locked")
    top10 = float(sig.get("top10_share", 0) or 0)
    if top10 > 0.5:
        s += 0.2; why.append(f"holder-concentration-{top10:.0%}")
    return min(s, 1.0), why


def wash_score(mkt: dict) -> tuple[float, list[str]]:
    """mkt: {unique_buyers, total_buys, volume_24h_usd, liquidity_usd, top_wallet_vol_share}.
    Higher = more manufactured volume."""
    s, why = 0.0, []
    ub, tb = float(mkt.get("unique_buyers", 0) or 0), float(mkt.get("total_buys", 0) or 0)
    if tb > 0:
        r = ub / tb
        if r < 0.5:
            s += (0.5 - r); why.append(f"few-buyers/many-trades({r:.2f})")
    liq = float(mkt.get("liquidity_usd", 0) or 0)
    vol = float(mkt.get("volume_24h_usd", 0) or 0)
    if liq > 0 and vol / liq > 20:
        s += 0.3; why.append(f"vol/liq={vol/liq:.0f}x")
    share = float(mkt.get("top_wallet_vol_share", 0) or 0)
    if share > 0.4:
        s += 0.3; why.append(f"top-wallet-vol-{share:.0%}")
    return min(s, 1.0), why


def screen(sig: dict, mkt: dict, tax_cap: float = TAX_CAP,
           min_liq: float = MIN_LIQ_USD) -> dict:
    """Combine into a verdict: reject | watch | pass, with reasons. Hard rejects first."""
    reasons = []
    if sig.get("is_honeypot"):
        reasons.append("honeypot")
    if float(sig.get("buy_tax", 0) or 0) > tax_cap or float(sig.get("sell_tax", 0) or 0) > tax_cap:
        reasons.append("tax>cap")
    if sig.get("mint_auth_live"):
        reasons.append("mint-authority-live")
    if sig.get("freeze_auth_live"):
        reasons.append("freeze-authority-live")
    liq = float(mkt.get("liquidity_usd", 0) or 0)
    if liq < min_liq:
        reasons.append(f"liquidity<{min_liq:.0f}")

    rug, rug_why = rug_score(sig)
    wash, wash_why = wash_score(mkt)
    # composite: lower is better; 0..1
    screen = min(1.0, 0.5 * rug + 0.5 * wash)

    if reasons:
        verdict = "reject"
    elif rug >= 0.5 or wash >= 0.6:
        verdict = "watch"
    else:
        verdict = "pass"
    return {"verdict": verdict, "rug_score": round(rug, 3), "wash_score": round(wash, 3),
            "screen_score": round(screen, 3),
            "reject_reason": ",".join(reasons), "flags": rug_why + wash_why}
