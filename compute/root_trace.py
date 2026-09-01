#!/usr/bin/env python3
"""Root trace: who funded the whales FIRST, and is there a common root?

For each whale + shared fee-payers + top funders:
  1. Paginate enhanced /transactions BACKWARDS to the wallet's oldest tx
     (bounded 30 pages). Record: first_seen ts, ALL inbound SOL funders.
  2. initial_funder = the sender of the first meaningful inbound SOL (>0.05).
  3. Hop to root: fetch the initial funder's OWN oldest txs (3 pages) —
     if it's an exchange deposit wallet we'll see its pattern; if it's another
     private wallet, we get one more hop toward the root.
Cross-link: build funder -> {whales funded} matrix. A funder that seeded
multiple whales = common operator.
suqh uses the stored 4,400-tx file (0 API calls for hop 1).
"""
import datetime
import importlib.util
import json
import time
from collections import defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TZ = datetime.timezone(datetime.timedelta(hours=7))
OUT = Path("/home/hermes/project-theia/compute/_root_trace.json")
WHALES = {
    "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh",
    "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5",
    "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin",
    "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8",
}
SHARED_PAYERS = [
    "4sWPwW2BwGgGX7L4eGe5XCsAe4fLVU8yCjusH1icH6MW",
    "9LXVVAWBkSjNVChAuWTUvX5p182fgaD1sR1dWCo2qcGD",
]
TOP_FUNDERS = [
    "8LR8ECxm4ZC7Drav",  # 6G8's funder (+494.6 SOL) — resolve full addr from trace
]


def fetch_back_to_origin(w, max_pages=30):
    """Paginate enhanced txs backwards until exhausted or page cap."""
    txs, before = [], None
    for page in range(max_pages):
        url = (m.ENHANCED + f"/addresses/{w}/transactions?api-key={m._key()}&limit=100"
               + (f"&before={before}" if before else ""))
        batch = None
        for attempt in range(3):
            try:
                batch = m.request_json(url, throttle=("helius-enh", 0.6)) or []
                break
            except Exception as e:
                print(f"    retry {attempt+1} ({type(e).__name__})")
                time.sleep(3 * (attempt + 1))
        if batch is None:
            break
        txs += batch
        before = batch[-1].get("signature")
        last_ts = batch[-1].get("timestamp") or 0
        if len(batch) < 100:  # exhausted
            break
        if page % 5 == 4:
            print(f"    page {page+1}: {len(txs)} txs, oldest "
                  f"{datetime.datetime.fromtimestamp(last_ts, TZ).strftime('%m-%d %H:%M')}")
    return txs


def analyze_flows(w, txs):
    """All inbound/outbound SOL funders + first_seen + initial funder."""
    sol_in = defaultdict(float)
    sol_out = defaultdict(float)
    first_ts = None
    for t in txs:  # txs are newest-first from API; find oldest ts
        ts = t.get("timestamp") or 0
        if ts and (first_ts is None or ts < first_ts):
            first_ts = ts
    for t in txs:
        for nt in (t.get("nativeTransfers") or []):
            frm = nt.get("fromUserAccount") or ""
            to = nt.get("toUserAccount") or ""
            amt = (nt.get("amount") or 0) / 1e9
            if to == w and amt > 0.01:
                sol_in[frm] += amt
            if frm == w and amt > 0.01:
                sol_out[to] += amt
    return sol_in, sol_out, first_ts


def ts_str(ts):
    return datetime.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M") if ts else "?"


report = {}
for w, tag in WHALES.items():
    if tag == "suqh":
        txs = json.load(open("/home/hermes/project-theia/compute/_suqh_enhanced.json"))
        print(f"== {tag}: using stored {len(txs)} txs ==")
    else:
        print(f"== {tag}: fetching full history to origin ==")
        txs = fetch_back_to_origin(w)
    sol_in, sol_out, first_ts = analyze_flows(w, txs)
    top_funders = sorted(sol_in.items(), key=lambda kv: -kv[1])[:6]
    initial = top_funders[0] if top_funders else ("", 0)
    print(f"  oldest tx: {ts_str(first_ts)} | txs={len(txs)}")
    print(f"  funders (top): {[(p[:10], round(v, 1)) for p, v in top_funders]}")
    print(f"  outbound (top): {[(p[:10], round(v, 1)) for p, v in sorted(sol_out.items(), key=lambda kv: -kv[1])[:4]]}")
    report[tag] = {"wallet": w, "txs": len(txs), "first_ts": first_ts,
                   "funders": {k: round(v, 3) for k, v in top_funders},
                   "outbound": {k: round(v, 3) for k, v in
                                sorted(sol_out.items(), key=lambda kv: -kv[1])[:8]},
                   "initial_funder": initial[0], "initial_amt": round(initial[1], 2)}

# shared fee-payers: who funds THEM?
for p in SHARED_PAYERS:
    print(f"== shared payer {p[:10]}: fetching origin ==")
    txs = fetch_back_to_origin(p, max_pages=10)
    sol_in, sol_out, first_ts = analyze_flows(p, txs)
    top_funders = sorted(sol_in.items(), key=lambda kv: -kv[1])[:4]
    print(f"  oldest tx: {ts_str(first_ts)} | txs={len(txs)}")
    print(f"  funders: {[(x[:10], round(v, 1)) for x, v in top_funders]}")
    report[f"payer:{p[:10]}"] = {"wallet": p, "txs": len(txs), "first_ts": first_ts,
                                 "funders": {k: round(v, 3) for k, v in top_funders}}

OUT.write_text(json.dumps(report, indent=1))
print(f"\nsaved {OUT}")