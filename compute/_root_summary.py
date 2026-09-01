#!/usr/bin/env python3
"""Compose root-trace results into a readable summary."""
import json

r = json.load(open("/home/hermes/project-theia/compute/_root_trace.json"))
for k, v in r.items():
    print(f"--- {k} ---")
    print(f"  wallet: {v.get('wallet')}")
    print(f"  txs: {v.get('txs')}, first_ts: {v.get('first_ts')}")
    print(f"  funders (top): {v.get('funders')}")
    print(f"  outbound (top): {v.get('outbound')}")
    print(f"  initial funder: {v.get('initial_funder')} ({v.get('initial_amt')} SOL)")
