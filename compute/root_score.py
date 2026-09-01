#!/usr/bin/env python3
"""GMGN walletNew stats for the ROOT cluster: F1ZLkFyTnz, HF3s85NVgp, 8LR8ECxm4Z,
9u7yHBjxWC + the whales themselves — one final score of the ROOT OPERATOR cluster.
Bounded: 1 call per wallet via the webscraper venv (CF-bypass)."""
import json
import sqlite3
import sys
import time
from pathlib import Path

CACHE = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE.mkdir(parents=True, exist_ok=True)

try:
    from scrapling.fetchers import StealthyFetcher
except ImportError:
    print("run with webscraper venv", file=sys.stderr)
    sys.exit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{a}?period=7d"

TARGETS = {
    "F1ZLkFyTnztPfYZ5VH6oLm6Zy5jToyzPAhamP6qWP8uZ": "F1ZL[root-funder, 441 swap-tx/30d]",
    "HF3s85NVgpVXQLtL94RWXUhxegViFRdaNxZ12WQBtpi8": "HF3s[operator-hub, funds suqh+2fg5]",
    "8LR8ECxm4ZC7DravqL9c5qoev91vyM3MkAcfwjsymfHB": "8LR8[6G8-hub, +494 SOL in]",
    "9u7yHBjxWCZpDsGnCSpQbp4VQmyMu68eY47Zx6T8jNSZ": "9u7y[2fg5-loop-payer]",
}

con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
con.row_factory = sqlite3.Row
sf = StealthyFetcher()
out = {}
print("ROOT cluster GMGN 7d stats:\n")
for w, tag in TARGETS.items():
    cp = CACHE / f"{w}_7d_root.json"
    if cp.exists() and (time.time() - cp.stat().st_mtime) < 7200:
        r = json.loads(cp.read_text())
    else:
        try:
            resp = sf.fetch(API.format(a=w), solve_cloudflare=True, timeout=45000,
                            headless=True, network_idle=False, load_dom=False)
            r = {"ok": resp.status == 200}
            if r["ok"]:
                r["data"] = json.loads(resp.body.decode("utf-8", errors="replace"))
                cp.write_text(json.dumps(r))
        except Exception as e:
            r = {"ok": False, "err": str(e)}
        time.sleep(1.5)
    if not r.get("ok"):
        print(f"  {tag:<38} fetch FAIL")
        out[tag] = {"ok": False}
        continue
    d = (r.get("data") or {}).get("data") or {}
    rp7 = d.get("realized_profit_7d") or 0
    txs7 = (d.get("buy_7d") or 0) + (d.get("sell_7d") or 0)
    vol7 = d.get("volume_7d") or 0
    hold = (d.get("avg_holding_peroid") or 0) / 3600
    wr7 = d.get("winrate")
    tags = {str(t).lower() for t in (d.get("tags") or [])}
    reasons = []
    if tags & {"wash_trader", "bot", "bundler", "dev", "sniper", "mev"}:
        reasons.append("bad_tag:" + ",".join(sorted(tags & {"wash_trader", "bot", "bundler", "dev", "sniper", "mev"})))
    if wr7 is not None and wr7 < 0.30:
        reasons.append(f"wr7={wr7:.2f}")
    if wr7 is not None and wr7 > 0.80 and txs7 < 500:
        reasons.append("scalper")
    if txs7 < 500:
        reasons.append(f"txs7={txs7}")
    if rp7 < 10000:
        reasons.append(f"rPnl7d={rp7:.0f}")
    if vol7 < 100000:
        reasons.append(f"vol7d={vol7:.0f}")
    if hold > 48:
        reasons.append(f"hold={hold:.1f}h")
    verdict = "PASS" if not reasons else "FAIL:" + ";".join(reasons)
    print(f"  {tag:<40} rPnl7d={rp7:>10,.0f} txs7={txs7:>6} vol7={vol7:>12,.0f} "
          f"hold={hold:>5.1f}h wr7={wr7 if wr7 is not None else 'None'}")
    print(f"    tags={sorted(tags)[:6]} -> {verdict}")
    out[tag] = {"rp7": rp7, "txs7": txs7, "vol7": vol7, "hold_h": hold, "wr7": wr7,
                "tags": sorted(tags), "verdict": verdict}
con.close()
Path("/home/hermes/project-theia/compute/_root_scores.json").write_text(json.dumps(out, indent=1))
n_pass = sum(1 for v in out.values() if v.get("verdict") == "PASS")
print(f"\nROOT cluster gate v2 PASS: {n_pass}/{len(out)}")
print("saved _root_scores.json")