#!/usr/bin/env python3
"""Deep-dive price_snapshots: granularity, per-pool rows, currency, liquidity presence."""
import sqlite3

DB = "/home/hermes/.hermes/theia/theia.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row


def rows(sql, *a):
    return [dict(r) for r in c.execute(sql, a)]


print("== per-pool rows (top 15 by count) ==")
for r in rows("select pool_addr, count(*) n, min(ts) mn, max(ts) mx, "
              "round((max(ts)-min(ts))/count(*),0) sec_per_row "
              "from price_snapshots group by pool_addr order by n desc limit 15"):
    print(" ", r)

print("\n== sample rows ==")
for r in rows("select * from price_snapshots order by ts desc limit 5"):
    print(" ", r)

print("\n== currency distribution ==")
for r in rows("select currency, count(*) n from price_snapshots group by currency"):
    print(" ", r)

print("\n== pools table join (sample) ==")
for r in rows("select p.pool_addr, p.mint, p.dex, p.amm_model, p.liquidity_usd, "
              "p.reserves_base, p.reserves_quote, p.price, p.launch_ts "
              "from pools p join (select distinct pool_addr from price_snapshots) s "
              "on p.pool_addr = s.pool_addr limit 10"):
    print(" ", r)

print("\n== how many snapshots have liquidity / volume? ==")
for r in rows("select count(*) n from price_snapshots"):
    print("  rows:", r["n"])