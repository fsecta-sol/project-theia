#!/usr/bin/env python3
"""Token-level trace of whale buys: which token, entry price level, exit price
level, and our copy-trade PnL — using the data we actually have.

Availability reality (checked):
- 353 whale-buy mints; only 3 exist in our `pools` table; 0 have cached OHLCV
  wide rows; mcap column mostly 0 for them.
- So the honest path: for mints WITHOUT charts, report the whale's own SOL
  spent + qty + token identity + live holding status; for mints WITH cached
  charts (only 6G8's intersection), simulate the copy-trade PnL.
- ALSO: pull Birdeye OHLCV fresh for the TOP whale-buy mints (bounded: top 12
  by whale SOL spent, 1 call each) to get entry/exit prices — that's the table
  the user asked for (mcap at entry/exit if supply known via mint metadata from
  the RPC getAccountInfo supply call, bounded too).
"""
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

KEY = ""
secret = Path("/home/hermes/project-theia/.secret")
if secret.exists():
    for line in secret.read_text().splitlines():
        if line.strip().startswith("HELIUS_API_KEY"):
            KEY = line.split("=", 1)[1].split(",")[0].strip()
RPCS = ([f"https://mainnet.helius-rpc.com/?api-key={KEY}"] if KEY else []) + \
       ["https://api.mainnet-beta.solana.com"]


def rpc(method, params):
    for url in RPCS:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                r = json.loads(resp.read())
        except Exception as e:
            print(f"  rpc err: {str(e)[:50]}")
            continue
        if "error" not in r:
            return r.get("result")
    return None


suqh = json.load(open('compute/_suqh_lots.json'))
v2 = json.load(open('compute/_whale_lots_v2.json'))

# build whale buy events with real SOL legs
buys = []
for l in suqh:
    if l['side'] == 'buy' and l['sol_out'] > 0.01:
        buys.append({'whale': 'suqh', 'mint': l['mint'], 'ts': l['ts'],
                     'qty': l['qty'], 'sol': l['sol_out']})
for w, dd in v2.items():
    tag = {'2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f': '2fg5',
           'ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT': 'ardin',
           '6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk': '6G8'}.get(w, w[:6])
    for l in dd.get('lots', []):
        if l['side'] == 'buy' and l['sol_out'] > 0.01:
            buys.append({'whale': tag, 'mint': l['mint'], 'ts': l['ts'],
                         'qty': l['qty'], 'sol': l['sol_out']})

# aggregate per (whale, mint): total SOL spent, n buys, first ts
agg = defaultdict(lambda: {'sol': 0.0, 'n': 0, 'first_ts': None, 'qty': 0.0})
for b in buys:
    k = (b['whale'], b['mint'])
    a = agg[k]
    a['sol'] += b['sol']
    a['n'] += 1
    a['qty'] += b['qty']
    if a['first_ts'] is None or (b['ts'] or 0) < (a['first_ts'] or 0):
        a['first_ts'] = b['ts']

rows = sorted(agg.items(), key=lambda kv: -kv[1]['sol'])
print(f"whale buy events (real SOL legs): {len(buys)} | distinct (whale,mint): {len(agg)}")
print()
print(f"{'whale':<5} {'mint':<12} {'nBuy':>4} {'SOL spent':>9} {'first buy':<16}")
import datetime
for (w, m), a in rows[:25]:
    ts = datetime.datetime.fromtimestamp(a['first_ts'] or 0,
                                         datetime.timezone(datetime.timedelta(hours=7))).strftime('%m-%d %H:%M') if a['first_ts'] else '?'
    print(f"{w:<5} {m[:10]:<12} {a['n']:>4} {a['sol']:>9.2f} {ts:<16}")

# top 12 by SOL: get supply (RPC getTokenSupply) + price context from Birdeye later
top = [(w, m, a) for (w, m), a in rows[:12]]
print("\n== supply check (RPC getTokenSupply) for top 12 whale-buys ==")
sup = {}
for w, m, a in top:
    res = rpc("getTokenSupply", [m])
    if res:
        v = res.get("value") or {}
        sup[m] = {"uiAmount": v.get("uiAmount"), "decimals": v.get("decimals")}
        print(f"  {m[:10]:<12} supply={v.get('uiAmount'):,.0f} dec={v.get('decimals')}")

json.dump({"buys": buys, "agg": {f"{w}:{m}": a for (w, m), a in rows},
           "supply_top12": sup},
          open('compute/_token_trace.json', 'w'), indent=1, default=str)
print("\nsaved _token_trace.json")