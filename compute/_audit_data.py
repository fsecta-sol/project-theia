#!/usr/bin/env python3
"""Audit available data for a post-graduation / mcap-dip backtest."""
import sqlite3

DB = "/home/hermes/.hermes/theia/theia.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row


def rows(sql, *a):
    return [dict(r) for r in c.execute(sql, a)]


# schemas
for t in ["tokens", "price_snapshots_v2", "token_corpus", "price_snapshots", "pools"]:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(f"### {t}: {cols}")

print("\n== token_corpus counts ==")
for r in rows("select graduation_status, death_reason, count(*) n from token_corpus group by graduation_status, death_reason"):
    print(" ", r)

print("\n== price_snapshots_v2 counts ==")
for r in rows("select count(*) n, min(ts) mn, max(ts) mx, count(distinct mint) mints from price_snapshots_v2"):
    print(" ", r)

print("\n== price_snapshots counts ==")
for r in rows("select count(*) n, min(ts) mn, max(ts) mx, count(distinct pool_addr) pools from price_snapshots"):
    print(" ", r)

print("\n== tokens counts ==")
print("  schema:", [r[1] for r in c.execute("PRAGMA table_info(tokens)")])
for r in rows("select count(*) n, count(distinct mint) mints from tokens"):
    print(" ", r)
for r in rows("select graduation_status, count(*) n from tokens group by graduation_status"):
    print("  grad_status:", r)

print("\n== corpus sample ==")
for r in rows("select * from token_corpus limit 5"):
    print(" ", r)