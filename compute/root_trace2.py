#!/usr/bin/env python3
"""Hop deeper: trace the root funders one more hop toward origin.

Targets (the real funders found in root_trace):
  HF3s85NVgp (suqh's funder, +19 SOL)
  9u7yHBjxWC (2fg5's funder, +7 SOL; 2fg5 sent 11.9 back = bidirectional!)
  8LR8ECxm4Z (6G8's funder, +1,456.5 SOL in, 1,041.6 out — the money hub)
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
TARGETS = {
    "HF3s85NVgpVXQLtL94RWXUhxegViFRdaNxZ12WQBtpi8": "HF3s(funder suqh)",
    "9u7yHBjxWCZpDsGnCSpQbp4VQmyMu68eY47Zx6T8jNSZ": "9u7y(funder 2fg5)",
    "8LR8ECxm4ZC7DravqL9c5qoev91vyM3MkAcfwjsymfHB": "8LR8(hub 6G8)",
}


def ts_str(ts):
    return datetime.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M") if ts else "?"


def fetch_back(w, max_pages=30):
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
        before = batch[-1].get("signature")
        last_ts = batch[-1].get("timestamp") or 0
        if len(batch) < 100:
            break
        if page % 5 == 4:
            print(f"    page {page+1}: {len(txs)} txs, oldest {ts_str(last_ts)}")
    return txs


def flows(w, txs):
    sol_in = defaultdict(float)
    sol_out = defaultdict(float)
    first_ts = None
    for t in txs:
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


report = {}
for w, tag in TARGETS.items():
    print(f"== {tag} ({w[:10]}..) — fetching to origin ==")
    txs = fetch_back(w)
    sol_in, sol_out, first_ts = flows(w, txs)
    funders = sorted(sol_in.items(), key=lambda kv: -kv[1])[:6]
    outbound = sorted(sol_out.items(), key=lambda kv: -kv[1])[:6]
    print(f"  oldest tx: {ts_str(first_ts)} | txs={len(txs)}")
    print(f"  funders: {[(p[:10], round(v, 1)) for p, v in funders]}")
    print(f"  outbound: {[(p[:10], round(v, 1)) for p, v in outbound]}")
    report[tag] = {"wallet": w, "txs": len(txs), "first_ts": first_ts,
                   "funders": {k: round(v, 3) for k, v in funders},
                   "outbound": {k: round(v, 3) for k, v in outbound}}

Path("/home/hermes/project-theia/compute/_root_trace2.json").write_text(json.dumps(report, indent=1))
print("\nsaved _root_trace2.json")