"""Golden tests for compute/wallet_profiler.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from compute.wallet_profiler import match_trades, profile_wallet, profile_all  # noqa: E402


def _swap(ts, side, mint="MINT_A", quote_qty=1.0, base_qty=1000.0):
    price = quote_qty / base_qty if base_qty else 0
    return {"ts": ts, "side": side, "base_mint": mint, "base_qty": base_qty,
            "quote_mint": "SOL", "quote_qty": quote_qty, "exec_price": price}


def test_match_simple_round_trip():
    swaps = [_swap(1000, "buy", quote_qty=1.0), _swap(1900, "sell", quote_qty=2.0)]
    rts = match_trades(swaps)
    assert len(rts) == 1
    assert rts[0]["hold_min"] == 15  # 900s / 60
    assert abs(rts[0]["pnl_sol"] - 1.0) < 1e-9
    assert abs(rts[0]["pnl_pct"] - 100.0) < 1e-9


def test_match_fifo_order():
    # Two buys then two sells — first sell matches first buy
    swaps = [
        _swap(1000, "buy", quote_qty=1.0),
        _swap(1600, "buy", quote_qty=1.0),
        _swap(2000, "sell", quote_qty=1.5),   # matches buy@1000 → +0.5
        _swap(3000, "sell", quote_qty=0.5),   # matches buy@1600 → −0.5
    ]
    rts = match_trades(swaps)
    assert len(rts) == 2
    assert abs(rts[0]["pnl_sol"] - 0.5) < 1e-9
    assert abs(rts[1]["pnl_sol"] - (-0.5)) < 1e-9


def test_unmatched_buy_ignored():
    swaps = [_swap(1000, "buy", quote_qty=1.0)]  # never sold
    assert match_trades(swaps) == []


def test_profile_classification_high_freq():
    # 20 buys in 1 hour, median hold <60min, median size 0.5 SOL
    swaps = []
    for i in range(20):
        swaps.append(_swap(1000 + i * 120, "buy", mint=f"M{i}", quote_qty=0.5))
        swaps.append(_swap(1000 + i * 120 + 600, "sell", mint=f"M{i}", quote_qty=0.6))
    p = profile_wallet("W1", swaps)
    assert p["pattern_cluster"] == "high_freq_scalper"
    assert p["total_trades"] == 40
    assert p["win_rate"] == 1.0
    assert p["expectancy_sol"] > 0


def test_profile_classification_dust_bot():
    swaps = [_swap(1000 + i * 60, "buy", mint=f"M{i}", quote_qty=0.01) for i in range(10)]
    p = profile_wallet("W2", swaps)
    assert p["pattern_cluster"] == "dust_bot"


def test_profile_empty():
    p = profile_wallet("W3", [])
    assert p["pattern_cluster"] == "inactive"
    assert p["total_trades"] == 0


def test_profile_all_sorted():
    a = [_swap(1000, "buy", quote_qty=1.0), _swap(1600, "sell", quote_qty=2.0)]  # +1
    b = [_swap(1000, "buy", quote_qty=1.0), _swap(1600, "sell", quote_qty=0.5)]  # −0.5
    out = profile_all({"WA": a, "WB": b})
    assert out[0]["wallet"] == "WA"  # winner first
    assert out[0]["total_pnl_sol"] > out[1]["total_pnl_sol"]
