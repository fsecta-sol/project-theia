#!/usr/bin/env python3
"""Final hop: resolve F1ZLkFyTnz — HF3s' own funder (+688.9 SOL in, 199.8 back).
This is the deepest root candidate. One bounded trace to origin (10 pages)."""
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
TARGET = "F1ZLkFyTnz5wWpNA6tpQazSFNcLYRQWxP9jRFe8Ncwzp"


def ts_str(ts):
    return datetime.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M") if ts else "?"


def fetch_back(w, max_pages):
    txs, before = [], None
    for page in range(max_pages):
        url = (m.ENHANCED + f"/addresses/{w}/transactions?api-key={m._key()}&limit=100"
               + (f"&before={before}" if before else ""))
        batch = None
        for attempt in range(3):
            try:
                batch = m.request_json(url, throttle=("helius-enh", 0.6)) or []
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        if batch is None:
            break
        txs += batch
        if not batch:
            break
        before = batch[-1].get("signature")
        last_ts = batch[-1].get("timestamp") or 0
        if len(batch) < 100:
            break
        if page % 5 == 4:
            print(f"    page {page+1}: {len(txs)} txs, oldest {ts_str(last_ts)}")
    return txs


print(f"== F1ZLkFyTnz (root candidate, funding HF3s +688.9) — fetching to origin ==")
txs = fetch_back(TARGET, 15)
sol_in = defaultdict(float)
sol_out = defaultdict(float)
first_ts = None
n_swap = 0
for t in txs:
    ts = t.get("timestamp") or 0
    if ts and (first_ts is None or ts < first_ts):
        first_ts = ts
    if t.get("type") == "SWAP":
        n_swap += 1
    for nt in (t.get("nativeTransfers") or []):
        frm = nt.get("fromUserAccount") or ""
        to = nt.get("toUserAccount") or ""
        amt = (nt.get("amount") or 0) / 1e9
        if to == TARGET and amt > 0.01:
            sol_in[frm] += amt
        if frm == TARGET and amt > 0.01:
            sol_out[to] += amt
print(f"  oldest tx: {ts_str(first_ts)} | txs={len(txs)} | SWAP-type={n_swap}")
print(f"  funders (top): {[(p[:10], round(v,1)) for p,v in sorted(sol_in.items(), key=lambda kv:-kv[1])[:6]]}")
print(f"  outbound (top): {[(p[:10], round(v,1)) for p,v in sorted(sol_out.items(), key=lambda kv:-kv[1])[:6]]}")
# does it fund other whales / our shared payers?
print(f"  funds HF3s? {sol_out.get('HF3s85NVgpVXQLtL94RWXUhxegViFRdaNxZ12WQBtpi8', 0):.1f} SOL")
print(f"  funds suqh? {sol_out.get('suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK', 0):.1f} SOL")
print(f"  funds 2fg5? {sol_out.get('2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f', 0):.1f} SOL")
print(f"  funds shared payers? 4sWP={sol_out.get('4sWPwW2BwGgGX7L4eGe5XCsAe4fLVU8yCjusH1icH6MW', 0):.1f} "
      f"9LXV={sol_out.get('9LXVVAWBkSjNVChAuWTUvX5p182fgaD1sR1dWCo2qcGD', 0):.1f}")

Path("/home/hermes/project-theia/compute/_root3.json").write_text(json.dumps({
    "wallet": TARGET, "txs": len(txs), "first_ts": first_ts, "swap_txs": n_swap,
    "funders": {k: round(v, 3) for k, v in sorted(sol_in.items(), key=lambda kv: -kv[1])[:8]},
    "outbound": {k: round(v, 3) for k, v in sorted(sol_out.items(), key=lambda kv: -kv[1])[:10]},
}, indent=1))
print("\nsaved _root3.json")