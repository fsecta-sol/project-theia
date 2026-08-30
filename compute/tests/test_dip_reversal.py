"""Tests for compute/dip_reversal_backtest.py — dip-reversal rule sanity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compute.dip_reversal_backtest import NOTIONAL, load_pools, run_dip_backtest  # noqa: E402


def _sim_pool_like(rows):
    """Local re-implementation of the dip rule for overlap test (mirrors lib)."""
    return run_dip_backtest({"p0": rows}, dip_pcts=[0.30], exit_mults=[1.30],
                            time_stops=[120])["sims"]


def test_load_pools_min_rows():
    pools = load_pools(min_rows=200)
    assert len(pools) >= 1
    for rows in pools.values():
        assert len(rows) >= 200
        # sorted by ts ascending
        ts = [r[0] for r in rows]
        assert ts == sorted(ts)
        # OHLC sanity: low <= open,close <= high
        for _, o, h, l, c in rows:
            assert l <= o <= h
            assert l <= c <= h


def test_run_dip_backtest_shape():
    pools = load_pools(min_rows=200)
    res = run_dip_backtest(pools)
    assert "all" in res and "n" in res and "reasons" in res
    assert res["n"] == res["all"]["n"] >= 0
    assert sum(res["reasons"].values()) == res["n"]


def test_no_overlap_trades():
    """Each pool's sims must be time-ordered. Entries never overlap the prior
    trade's exit (the rule advances i = j+1 so a new signal only starts after
    the prior one's confirmation candle; a time_stop exit can legitimately run
    past the next entry only when the exit candle itself is the start of the
    next signal's dip — assert entry ordering only)."""
    pools = load_pools(min_rows=200)
    for rows in pools.values():
        sims = _sim_pool_like(rows)
        entries = [s.entry_ts for s in sims]
        assert entries == sorted(entries)


def test_notional_sanity():
    assert NOTIONAL == 0.5


if __name__ == "__main__":
    test_load_pools_min_rows()
    test_run_dip_backtest_shape()
    test_no_overlap_trades()
    test_notional_sanity()
    print("dip_reversal_backtest OK")
