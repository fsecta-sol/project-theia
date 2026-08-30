#!/usr/bin/env python3
"""Universe-wide pool OHLCV recorder (API-frugal, no-agent cron).

Fixes the selection-bias gap: `price_snapshots` only ever held pools the
smart-wallet pipeline touched, so every backtest was conditioned on smart-wallet
picks. This job samples pools from the broad `pools` table (all pools we've ever
seen), picks a rotating batch each run, and records their 1-min OHLCV into
`price_snapshots` (with volume+mcap via the v1.1 columns) so future base-rate
and rule backtests run on a *representative* universe.

Design (deterministic, bounded, free-tier friendly):
- Every run: pick up to N=6 pools from `pools` that (a) have >=80 rows already
  or (b) are the newest by updated_ts (covers fresh pools), prioritizing ones
  we have NO cached history for yet (least-covered first).
- For each chosen pool, resolve mint via `pools.mint`, fetch 1-min OHLCV
  (birdeye→gecko→dexscreener, same ladder as wallet_common.ohlcv_for), and
  record via the same INSERT as the pipeline (v, mcap captured when present).
- Skips pools with no mint / no OHLCV source / already fresh (< 30m old last row).
Budget: N<=6 pools/run, 1 OHLCV fetch per pool (cached 5m), ~once per hour.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

DB = Path.home() / ".hermes/theia/theia.db"
sys.path.insert(0, str(Path.home() / ".hermes/profiles/theia/scripts"))
from wallet_common import ohlcv_for, _call_with_timeout  # noqa: E402 (reuse pipeline ladder)

N_PER_RUN = 6
FRESH_IF_SECONDS = 30 * 60
FETCH_TIMEOUT = 25.0  # hard per-pool fetch budget


def pick_pools(con, n: int = N_PER_RUN) -> list[tuple[str, str]]:
    """Return [(pool_addr, mint), ...] — least-covered-first, newest bias.

    Targets pools with ZERO recorded candles first (that's the coverage gap);
    then pools with some but old history. Skips freshly-recorded pools.
    """
    rows = con.execute("""
        SELECT p.pool_addr, p.mint, p.updated_ts,
               (SELECT COUNT(*) FROM price_snapshots ps
                 WHERE ps.pool_addr = p.pool_addr) AS have
        FROM pools p
        WHERE p.mint IS NOT NULL AND p.mint != ''
        ORDER BY have ASC, p.updated_ts DESC
    """).fetchall()
    out = []
    for pool, mint, _upd, have in rows:
        if len(out) >= n:
            break
        if not pool or not mint:
            continue
        # fresh check: skip if our most recent recorded candle is <30m old
        last = con.execute(
            "SELECT MAX(ts) FROM price_snapshots WHERE pool_addr=?",
            (pool,)).fetchone()[0]
        if last and time.time() - last < FRESH_IF_SECONDS:
            continue
        out.append((pool, mint, have))
    # prefer have==0 first, then fewest rows, keep newest bias within groups
    out.sort(key=lambda x: (x[2] > 0, x[2]))
    return [(p, m) for p, m, _ in out[:n]]


def main():
    con = sqlite3.connect(DB)
    picked = pick_pools(con)
    if not picked:
        print("[universe] no pools to sample")
        con.close()
        return

    # load the MCP servers for ohlcv fetch (same as pipeline)
    import importlib.util
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    DEPLOY = Path.home() / ".hermes/theia/mcp"
    chainrpc = load("chainrpc", DEPLOY / "theia-chainrpc" / "server.py")
    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")

    recorded_total = 0
    for pool, mint in picked:
        try:
            rows, src = _call_with_timeout(
                ohlcv_for, dexdata, birdeye, mint, before_ts=0, ttl=300)
            if not rows:
                src = str(src)
        except Exception as e:
            print(f"[universe] {mint[:10]} OHLCV err {e}")
            continue
        if not rows:
            print(f"[universe] {mint[:10]} no rows (src={src})")
            continue
        n = 0
        for r in rows:
            try:
                ts = int(r[0])
                o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
                mcap = float(r[6]) if len(r) > 6 and r[6] is not None else 0.0
            except (TypeError, ValueError, IndexError):
                continue
            cur = con.execute(
                "SELECT 1 FROM price_snapshots WHERE pool_addr=? AND ts=?",
                (pool, ts)).fetchone()
            if cur:
                continue
            con.execute(
                "INSERT OR IGNORE INTO price_snapshots "
                "(pool_addr, ts, o, h, l, c, currency, v, mcap) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pool, ts, o, h, l, c, "token", v, mcap))
            n += 1
        recorded_total += n
        print(f"[universe] {mint[:12]} +{n} rows (src={src})")
        con.commit()

    con.commit()
    con.close()
    print(f"[universe] done — recorded {recorded_total} new rows across {len(picked)} pools")


if __name__ == "__main__":
    main()