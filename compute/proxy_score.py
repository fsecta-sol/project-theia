#!/usr/bin/env python3
"""Follow-the-money — hop 3: refetch GMGN walletNew 7d for the 15 REAL fee-payer
wallets (the actual actors behind the whales), gate-v2 score them, and compare
with the whales themselves. Bounded: 1 call per wallet, 1.5s sleep."""
import json
import sqlite3
import time
from pathlib import Path

CACHE = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE.mkdir(parents=True, exist_ok=True)

try:
    from scrapling.fetchers import StealthyFetcher
except ImportError:
    print("ERROR: run with theia-webscraper venv", file=None)
    raise SystemExit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period=7d"

trace = json.load(open("/home/hermes/project-theia/compute/_money_trace.json"))
fee_payers = {}
for tag, d in trace["whales"].items():
    for p, n in (d.get("fee_payers") or {}).items():
        fee_payers.setdefault(p, []).append((tag, n))

con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
con.row_factory = sqlite3.Row

sf = StealthyFetcher()
results = {}
print(f"fee-payer wallets to refetch: {len(fee_payers)}\n")
for i, (p, whales) in enumerate(sorted(fee_payers.items(), key=lambda kv: -max(n for _, n in kv[1]))):
    cp = CACHE / f"{p}_7d_proxy.json"
    if cp.exists() and (time.time() - cp.stat().st_mtime) < 3600:
        r = json.loads(cp.read_text())
        ok = r.get("ok")
        print(f"[{i+1}/{len(fee_payers)}] {p[:14]} (cached ok={ok})")
    else:
        try:
            resp = sf.fetch(API.format(addr=p), solve_cloudflare=True, timeout=45000,
                            headless=True, network_idle=False, load_dom=False)
            ok = resp.status == 200
            r = {"ok": ok, "addr": p}
            if ok:
                r["data"] = json.loads(resp.body.decode("utf-8", errors="replace"))
                cp.write_text(json.dumps(r))
        except Exception as e:
            r = {"ok": False, "err": str(e)}
        time.sleep(1.5)
        print(f"[{i+1}/{len(fee_payers)}] {p[:14]} fetch ok={r.get('ok')}")
    if not r.get("ok"):
        results[p] = {"ok": False}
        continue
    d = (r.get("data") or {}).get("data") or {}
    rp7 = d.get("realized_profit_7d") or 0
    txs7 = (d.get("buy_7d") or 0) + (d.get("sell_7d") or 0)
    vol7 = d.get("volume_7d") or 0
    hold = (d.get("avg_holding_peroid") or 0) / 3600
    wr7 = d.get("winrate")
    tags = {str(t).lower() for t in (d.get("tags") or [])}
    # gate v2 quick score
    reasons = []
    if tags & {"wash_trader", "bot", "bundler", "dev", "sniper", "mev"}:
        reasons.append("bad_tag")
    if wr7 is not None:
        if wr7 < 0.30:
            reasons.append(f"wr7={wr7:.2f}")
        elif wr7 > 0.80 and txs7 < 500:
            reasons.append("scalper")
    else:
        reasons.append("wr7=None(non-tracked)")
    if txs7 < 500:
        reasons.append(f"txs7={txs7}")
    if rp7 < 10000:
        reasons.append(f"rPnl7d={rp7:.0f}")
    if vol7 < 100000:
        reasons.append(f"vol7d={vol7:.0f}")
    if hold > 48:
        reasons.append(f"hold={hold:.1f}h")
    verdict = "PASS" if not reasons else "FAIL:" + ";".join(reasons)
    print(f"   rPnl7d={rp7:>10,.0f} txs7={txs7:>6} vol7={vol7:>12,.0f} hold={hold:>5.1f}h "
          f"wr7={wr7 if wr7 is not None else 'None'} -> {verdict}")
    results[p] = {"ok": True, "rp7": rp7, "txs7": txs7, "vol7": vol7, "hold_h": hold,
                  "wr7": wr7, "tags": sorted(tags), "verdict": verdict, "whales": whales}

con.close()
Path("/home/hermes/project-theia/compute/_proxy_scores.json").write_text(json.dumps(results, indent=1))
n_pass = sum(1 for r in results.values() if r.get("ok") and r.get("verdict") == "PASS")
print(f"\nproxy wallets gate-v2 PASS: {n_pass}/{len(results)}")
print("saved _proxy_scores.json")