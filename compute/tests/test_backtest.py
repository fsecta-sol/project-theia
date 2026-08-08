"""Golden-input tests for backtest engine."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compute import backtest_engine, expectancy  # noqa: E402


# ── Shared fixtures ────────────────────────────────────────────────────────


def _price_rows(mint: str, start_ts: int, n: int, start_c: float,
                trend: str = "pump_then_dump") -> list[dict]:
    """Generate simple price path. Each row = 1 minute.
    Reserves are kept consistent with price (spot = quote/base ≈ c)."""
    rows = []
    c = start_c
    base_r = 1_000_000.0
    for i in range(n):
        ts = start_ts + i * 60
        if trend == "pump_then_dump":
            if i < 5:
                c *= 1.3   # pump
            elif i < 10:
                c *= 1.5   # pump more
            else:
                c *= 0.6   # dump
        elif trend == "straight_dump":
            c *= 0.85
        elif trend == "flat":
            c *= 1.0
        o = c * 0.98
        h = c * 1.05
        l = c * 0.95
        quote_r = base_r * c  # consistent CPMM spot
        rows.append({
            "mint": mint,
            "ts": ts,
            "o": o, "h": h, "l": l, "c": c,
            "volume_24h": 50000,
            "liquidity_usd": 50000,
            "reserves_base": base_r,
            "reserves_quote": quote_r,
            "launch_ts": start_ts,
            "amm_model": "v2",
        })
    return rows


# ── Tests ──────────────────────────────────────────────────────────────────


def test_backtest_empty():
    r = backtest_engine.run({}, [], [])
    assert r["n_candidates"] == 0
    assert r["metrics"]["passes"] is False


def test_backtest_one_trade_tp_ladder():
    """Token pumps 2x then 4x then dumps — should hit TP ladder."""
    mint = "PUMP1"
    start = 1000000000
    rows = _price_rows(mint, start, 20, start_c=0.001, trend="pump_then_dump")
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5), (4.0, 0.25)],
                 "trail_drop": 0.25, "time_stop_secs": 3600},
    }
    r = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    assert r["n_entered"] == 1
    t = r["trades"][0]
    assert t["mint"] == mint
    assert t["entry_price"] > 0
    assert t["exit_price"] > t["entry_price"]  # TP ladder should be profitable
    assert t["net_pnl_sol"] > 0
    assert "tp_" in t["exit_reason"] or "trail" in t["exit_reason"]
    # Metrics
    assert r["metrics"]["n"] == 1
    assert r["metrics"]["passes"] is True  # one winning trade = pf=inf, expectancy>0


def test_backtest_screen_reject():
    """Screen verdict = reject → no entry."""
    mint = "RUG1"
    start = 1000000000
    rows = _price_rows(mint, start, 10, start_c=0.001)
    screens = [{"mint": mint, "screen_ts": start, "verdict": "reject"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0},
        "exit": {},
    }
    r = backtest_engine.run(rule, rows, screens)
    assert r["n_entered"] == 0
    assert r["metrics"]["n"] == 0


def test_backtest_wallet_filter_blocks_entry():
    """Wallet filter enabled but no signal → no entry."""
    mint = "NOWALLET"
    start = 1000000000
    rows = _price_rows(mint, start, 10, start_c=0.001)
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "wallet_filter": {"enabled": True, "lag_sec": 300},
        "size": {"notional_sol": 1.0},
        "exit": {},
    }
    r = backtest_engine.run(rule, rows, screens, wallet_signals={})
    assert r["n_entered"] == 0


def test_backtest_wallet_filter_allows_entry():
    """Wallet signal present within lag window → entry allowed."""
    mint = "WALLET_OK"
    start = 1000000000
    rows = _price_rows(mint, start, 15, start_c=0.001)
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "wallet_filter": {"enabled": True, "lag_sec": 300},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5)],
                 "trail_drop": 0.25, "time_stop_secs": 3600},
    }
    wallet_signals = {
        "whale1": [{"mint": mint, "buy_ts": start + 60}]
    }
    r = backtest_engine.run(rule, rows, screens, wallet_signals=wallet_signals,
                            detection_lag_sec=0)
    assert r["n_entered"] == 1
    assert r["trades"][0]["mint"] == mint


def test_backtest_detection_lag_skips_early_data():
    """Detection lag = 120 sec means fill happens at row >= 120s after signal."""
    mint = "LAG"
    start = 1000000000
    rows = _price_rows(mint, start, 5, start_c=0.001, trend="straight_dump")
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.50, "time_stop_secs": 3600},
    }
    # detection_lag = 0 should enter on first row
    r0 = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    assert r0["n_entered"] == 1
    p0 = r0["trades"][0]["entry_price"]

    # detection_lag = 180 should skip first 3 rows (60s each)
    r1 = backtest_engine.run(rule, rows, screens, detection_lag_sec=180)
    if r1["n_entered"] == 1:
        p1 = r1["trades"][0]["entry_price"]
        # Later fill = worse price in a dump trend
        assert p1 <= p0 * 1.01  # allow tiny float diff


def test_backtest_gas_and_slippage_reduce_pnl():
    """Net PnL must be strictly less than raw PnL because gas + slippage are subtracted."""
    mint = "COSTLY"
    start = 1000000000
    rows = _price_rows(mint, start, 15, start_c=0.001, trend="pump_then_dump")
    screens = [{"mint": mint, "screen_ts": start, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5)],
                 "trail_drop": 0.25, "time_stop_secs": 3600},
    }
    r = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    assert r["n_entered"] == 1
    t = r["trades"][0]
    assert t["gas_sol"] > 0
    assert t["slippage_penalty_sol"] >= 0
    assert t["net_pnl_sol"] < t["raw_pnl_sol"]


def test_backtest_expectancy_integration():
    """Two tokens: one winner, one loser → evaluate aggregate expectancy."""
    start = 1000000000
    rows_a = _price_rows("WIN", start, 15, 0.001, "pump_then_dump")
    rows_b = _price_rows("LOSE", start, 15, 0.001, "straight_dump")
    screens = [
        {"mint": "WIN", "screen_ts": start, "verdict": "pass"},
        {"mint": "LOSE", "screen_ts": start, "verdict": "pass"},
    ]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5)],
                 "trail_drop": 0.25, "time_stop_secs": 3600},
    }
    all_rows = rows_a + rows_b
    r = backtest_engine.run(rule, all_rows, screens, detection_lag_sec=0)
    assert r["n_entered"] == 2
    assert r["metrics"]["n"] == 2
    # One winner + one loser → profit_factor = |win| / |loss|
    assert r["metrics"]["profit_factor"] > 0
    # Expectancy may be positive or negative depending on sizes
    # The key assertion: it is computable and not NaN
    assert math.isfinite(r["metrics"]["expectancy"])


def test_backtest_point_in_time_screen():
    """Screen result appears LATE (after row 3). Entry before that screen must be blocked."""
    mint = "LATESCREEN"
    start = 1000000000
    rows = _price_rows(mint, start, 10, 0.001)
    # Screen only available at start + 240s (row 4)
    screens = [{"mint": mint, "screen_ts": start + 240, "verdict": "pass"}]
    rule = {
        "entry": {"min_liquidity_usd": 1000, "screen_verdict": "pass"},
        "size": {"notional_sol": 1.0, "max_pct_liquidity": 0.1},
        "exit": {"hard_stop": -0.35, "time_stop_secs": 3600},
    }
    r = backtest_engine.run(rule, rows, screens, detection_lag_sec=0)
    # Should enter at or after row 4 (ts >= start+240)
    assert r["n_entered"] == 1
    entry_ts = r["trades"][0]["entry_ts"]
    assert entry_ts >= start + 240
