#!/usr/bin/env python3
"""Final follow-the-money verdict: compose all traces into the conclusion."""
import json

trace = json.load(open("/home/hermes/project-theia/compute/_money_trace.json"))
proxy = json.load(open("/home/hermes/project-theia/compute/_proxy_scores.json"))

# how many fee-payers passed gate v2?
passes = [(p, d) for p, d in proxy.items() if d.get("ok") and "PASS" in str(d.get("verdict", ""))]
fails = [(p, d) for p, d in proxy.items() if p not in [x[0] for x in passes]]
print(f"fee-payers refetched: {len(proxy)} | PASS gate v2: {len(passes)} | FAIL: {len(fails)}")
print()
for p, d in proxy.items():
    print(f"  {p[:16]:<18} {d.get('verdict','?')}")
print()
# notable: FHpcNSe6tb = 6G8's top payer, real whale (+18,201 rPnl7d, 19,031 txs) — failed only wr7=None
for p, d in proxy.items():
    if d.get("txs7", 0) > 1000:
        print(f"  HIGH-ACTIVITY payer: {p[:16]} txs7={d.get('txs7')} rPnl7d={d.get('rp7'):,.0f} vol7={d.get('vol7'):,.0f} verdict={d.get('verdict')}")
print()
# shared infrastructure across whales?
whale_map = {}
for p, d in proxy.items():
    pass
# from trace
shared = {}
for tag, d in trace["whales"].items():
    for p in (d.get("fee_payers") or {}):
        shared.setdefault(p, []).append(tag)
shared = {p: t for p, t in shared.items() if len(t) > 1}
print(f"fee-payers SHARED across whales: {shared}")
print()
print("== FINAL: follow-the-money verdict ==")
print(f"  fee-payers total: {len(proxy)}")
print(f"  gate v2 PASS: {len(passes)}")
print(f"  shared infra across whales: {list(shared.keys())}")
print(f"  conclusion: whale addresses = attribution endpoints; the real traders ride")
print(f"  rotating temp payers invisible to our gates; follow-the-wallet is dead as a mechanism.")