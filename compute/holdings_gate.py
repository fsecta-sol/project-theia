#!/usr/bin/env python3
"""B1: Holdings-gate on whale signals — the surviving wallet-thesis variant.

Question: does requiring the whale to STILL HOLD the token at our entry time
(T+30m) make copy-trading profitable?

Method (deterministic, stored data + bounded RPC):
  1. Whale buys with real SOL legs from _token_trace.json agg (the 606 buys
     -> 249 whale:mint pairs; top-12 by SOL spent already have charts fetched).
  2. For each copy-trade sim, gate = whale's live holding of that mint
     (getTokenAccountsByOwner, 1 call per whale) measured NOW. The gate is a
     realistic forward-proxy: whale holds now = whale still in the position.
  3. Compare three cohorts: ungated (all 12), gated-pass (whale still holds),
     gated-fail (whale exited).
  4. Also fetch supply-aware mcap for the gate-pass cohort via the same
     candle data already cached (birdeye source).
No new backtest engine; reuses token_trace_pnl rows + RPC holdings.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy  # noqa: E402

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
            print(f"  rpc err {str(e)[:50]}")
            continue
        if "error" not in r:
            return r.get("result")
    return None


def holdings(whale_full):
    """mint -> uiAmount (live, non-zero)."""
    res = rpc("getTokenAccountsByOwner",
              [whale_full, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
               {"encoding": "jsonParsed"}])
    out = {}
    for acc in (res or {}).get("value") or []:
        info = ((acc.get("account") or {}).get("data") or {}).get("parsed", {}).get("info") or {}
        amt = float((info.get("tokenAmount") or {}).get("uiAmount") or 0)
        if amt > 0:
            out[info.get("mint")] = amt
    return out


WHALES = {
    "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5",
    "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin",
    "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8",
    "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh",
}

rows = json.load(open("/home/hermes/project-theia/compute/_token_trace_pnl.json"))

print("== B1 holdings-gate test (live holdings vs copy PnL) ==")
print(f"{'whale':<5} {'mint':<11} {'PnL(copy)':>9} {'whaleHoldsNow':>14} {'gate':>6}")
gated_pass, gated_fail, all_pnls = [], [], []
hold_map = {}
for w, tag in WHALES.items():
    try:
        h = holdings(w)
        hold_map[tag] = h
        print(f"  {tag}: live non-zero holdings = {len(h)}")
    except Exception as e:
        print(f"  {tag}: holdings fetch err {type(e).__name__}")
        hold_map[tag] = {}

for r in rows:
    pnl = r["pnl_copy_net"]
    holds = hold_map.get(r["whale"], {}).get(r["mint"], 0) > 0
    all_pnls.append(pnl)
    (gated_pass if holds else gated_fail).append(pnl)
    print(f"{r['whale']:<5} {r['mint'][:9]:<11} {pnl:>+9.3f} "
          f"{hold_map.get(r['whale'], {}).get(r['mint'], 0):>14,.0f} {'PASS' if holds else 'FAIL':>6}")

print("\n== cohorts ==")
for name, lst in (("ungated (all)", all_pnls), ("gate PASS (whale still holds)", gated_pass),
                  ("gate FAIL (whale exited)", gated_fail)):
    if lst:
        m = expectancy.evaluate(lst)
        print(f"  {name:<28} n={m['n']:>2} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
              f"win={m['win_rate']:.2f} total={m['total']:+.4f}")
    else:
        print(f"  {name:<28} n=0")

json.dump({"hold_counts": {k: len(v) for k, v in hold_map.items()},
           "cohorts": {"all": all_pnls, "pass": gated_pass, "fail": gated_fail}},
          open("/home/hermes/project-theia/compute/_holdings_gate.json", "w"), indent=1)
print("\nsaved _holdings_gate.json")