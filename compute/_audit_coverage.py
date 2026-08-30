#!/usr/bin/env python3
"""Coverage histogram of price_snapshots per pool + check for fresh pools."""
import sqlite3
from collections import Counter

c = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
hist = Counter()
for (n,) in c.execute("select count(*) from price_snapshots group by pool_addr"):
    hist[min(n // 100, 10)] += 1
print("rows-per-pool histogram (bucket x100 rows):")
for k in sorted(hist):
    print(f"  {k*100}-{k*100+99}: {hist[k]} pools")

# pools with >= 200 rows (enough for a chart signal + forward window)
pools = [r[0] for r in c.execute(
    "select pool_addr from price_snapshots group by pool_addr having count(*)>=200")]
print(f"\npools with >=200 rows: {len(pools)}")

# distinct mints among those pools (need pools.mint join)
mints = [r[0] for r in c.execute(
    "select distinct p.mint from pools p join price_snapshots ps on ps.pool_addr=p.pool_addr "
    "group by ps.pool_addr having count(*)>=200")]
print(f"distinct mints among them: {len(mints)}")
