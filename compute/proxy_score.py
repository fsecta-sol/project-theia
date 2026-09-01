#!/usr/bin/env python3
"""Follow-the-money trace to the end: score the whale trade networks.

Extracts the actual fee-payer wallets (the real actors behind the whales) from
the trace, gate-v2 scores them via fresh GMGN walletNew 7d, and checks whether
any of the proxy wallets themselves are tradable targets. Bounded: 1 call per
wallet, 1.5s sleep.
"""
import json
import time
from pathlib import Path

CACHE = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE.mkdir(parents=True, exist_ok=True)

trace = json.load(open("/home/hermes/project-theia/compute/_money_trace.json"))
fee_payers = {}
for tag, d in trace["whales"].items():
    for p, n in (d.get("fee_payers") or {}).items():
        fee_payers.setdefault(p, []).append((tag, n))

print(f"fee-payer wallets to refetch: {len(fee_payers)}\n")
results = {}
for i, (p, whales) in enumerate(sorted(fee_payers.items(), key=lambda kv: -max(n for _, n in kv[1]))):
    cp = Path(f"/home/hermes/.hermes/theia/wallet_cache/gmgn_stats/{p}_7d_proxy.json")
    if cp.exists() and (time.time() - cp.stat().st_mtime) < 3600:
        r = json.loads(cp.read_text())
        print(f"[{i+1}/{len(fee_payers)}] {p[:14]} (cached ok={r.get('ok')})")
    else:
        try:
            import urllib.request
            url = (f"https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/"
                   f"{p}?period=7d")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                ok = resp.status == 200
                body = resp.read().decode("utf-8", errors="replace")
            r = {"ok": ok, "addr": p}
            if ok:
                r["data"] = json.loads(body)
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
    verdict = "PASS" if not reasons else "FAIL:" + ";".join(reasons)
    print(f"   rPnl7d={rp7:>10,.0f} txs7={txs7:>6} vol7={vol7:>12,.0f} "
          f"wr7={wr7 if wr7 is not None else 'None'} -> {verdict}")
    results[p] = {"ok": r.get("ok"), "rp7": rp7, "txs7": txs7, "vol7": vol7,
                  "wr7": wr7, "tags": sorted(tags), "verdict": verdict}
