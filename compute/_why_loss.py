#!/usr/bin/env python3
"""Why do whale-buys lose when copied? Audit: whale's own sell timing vs our
copy entry, whale SOL in vs out per mint, and mcap trajectory."""
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/hermes/project-theia")
TZ = timezone(timedelta(hours=7))

rows = json.load(open("/home/hermes/project-theia/compute/_token_trace_pnl.json"))
trace = json.load(open("/home/hermes/project-theia/compute/_token_trace.json"))
agg = trace["agg"]
v2 = json.load(open("/home/hermes/project-theia/compute/_whale_lots_v2.json"))
suqh = json.load(open("/home/hermes/project-theia/compute/_suqh_lots.json"))


def whale_sells(mint):
    out = []
    for w, dd in v2.items():
        for l in dd.get("lots", []):
            if l["mint"] == mint and l["side"] == "sell" and l["sol_in"] > 0.01:
                out.append({"whale": w[:4], "ts": l["ts"], "sol_in": l["sol_in"],
                            "qty": l["qty"]})
    for l in suqh:
        if l["mint"] == mint and l["side"] == "sell" and l["sol_in"] > 0.01:
            out.append({"whale": "suqh", "ts": l["ts"], "sol_in": l["sol_in"],
                        "qty": l["qty"]})
    return out


print(f"{'mint':<11} {'PnL(copy)':>9} {'SOLout':>7} {'nSell':>5} {'SOLin':>7} {'whaleNet':>9}")
for r in sorted(rows, key=lambda x: x["pnl_copy_net"]):
    mint = r["mint"]
    sells = whale_sells(mint)
    sol_in = sum(s["sol_in"] for s in sells)
    net = sol_in - r["sol"]
    pnl = r["pnl_copy_net"]
    mark = "  <-- LOSS" if pnl < 0 else ""
    print(f"{mint[:9]:<11} {pnl:>+9.3f} {r['sol']:>7.1f} {len(sells):>5} {sol_in:>7.1f} {net:>+9.1f}{mark}")

print()
print("== TIMING: whale sells vs our copy entry (T+30m after whale's first buy) ==")
for r in sorted(rows, key=lambda x: x["pnl_copy_net"]):
    mint = r["mint"]
    key = next((k for k in agg if k.endswith(":" + mint)), None)
    a = agg.get(key, {})
    first_buy = a.get("first_ts") or 0
    copy_ts = first_buy + 1800
    sells = whale_sells(mint)
    before = [s for s in sells if (s["ts"] or 0) <= copy_ts]
    after = [s for s in sells if (s["ts"] or 0) > copy_ts]
    sol_before = sum(s["sol_in"] for s in before)
    sol_after = sum(s["sol_in"] for s in after)
    ts_b = datetime.fromtimestamp(copy_ts, TZ).strftime('%m-%d %H:%M')
    print(f"  {mint[:9]} pnl={r['pnl_copy_net']:+.3f} | sells BEFORE our entry: "
          f"{len(before)} ({sol_before:.1f} SOL) | AFTER: {len(after)} ({sol_after:.1f} SOL) "
          f"| copy@{ts_b}")

# mcap bucket: big whales bought at high mcap = pump already happened
print()
print("== mcap bucket of whale entries (are they buying tops?) ==")
buckets = {"<100k": 0, "100k-1M": 0, "1M-10M": 0, "10M+": 0}
for r in rows:
    mc = r["mcap_buy"]
    if mc < 100_000:
        buckets["<100k"] += 1
    elif mc < 1_000_000:
        buckets["100k-1M"] += 1
    elif mc < 10_000_000:
        buckets["1M-10M"] += 1
    else:
        buckets["10M+"] += 1
print(f"  whale entry mcap buckets: {buckets}")
wins_by_bucket = {"<100k": [], "100k-1M": [], "1M-10M": [], "10M+": []}
for r in rows:
    mc = r["mcap_buy"]
    k = "<100k" if mc < 100_000 else "100k-1M" if mc < 1_000_000 else "1M-10M" if mc < 10_000_000 else "10M+"
    wins_by_bucket[k].append(r["pnl_copy_net"])
for k, ps in wins_by_bucket.items():
    if ps:
        wins = sum(1 for p in ps if p > 0)
        print(f"  {k:<10} n={len(ps)} wins={wins} mean_pnl={sum(ps)/len(ps):+.3f}")