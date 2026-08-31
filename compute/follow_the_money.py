#!/usr/bin/env python3
"""Follow-the-money (re-run, analysis saved FIRST, DB cross-check after).

hop1: each whale's fee-payers (SWAP-type txs), inbound SOL senders, inbound token senders.
hop2: the top fee-payer's own tx mix (3 pages).
All bounded (8 pages/whale + 3/hop2). suqh uses the stored 4,400-tx file (0 calls).
"""
import datetime
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chainrpc", "/home/hermes/.hermes/theia/mcp/theia-chainrpc/server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TZ = datetime.timezone(datetime.timedelta(hours=7))
WHALES = {
    "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh",
    "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5",
    "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin",
    "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8",
}
PAGES = 8
OUT = Path("/home/hermes/project-theia/compute/_money_trace.json")


def fetch_txs(w, pages):
    txs, before = [], None
    for _ in range(pages):
        url = (m.ENHANCED + f"/addresses/{w}/transactions?api-key={m._key()}&limit=100"
               + (f"&before={before}" if before else ""))
        batch = None
        for attempt in range(3):
            try:
                batch = m.request_json(url, throttle=("helius-enh", 0.6)) or []
                break
            except Exception:
                import time
                time.sleep(3 * (attempt + 1))
        if batch is None:
            break
        txs += batch
        before = batch[-1].get("signature")
    return txs


def analyze(w, txs):
    fee_payers = Counter()
    sol_in = defaultdict(float)
    tok_senders = Counter()
    for t in txs:
        if t.get("type") == "SWAP":
            fp = t.get("feePayer") or ""
            if fp and fp != w:
                fee_payers[fp] += 1
        for nt in (t.get("nativeTransfers") or []):
            if (nt.get("toUserAccount") or "") == w:
                amt = (nt.get("amount") or 0) / 1e9
                if amt > 0.01:
                    sol_in[nt.get("fromUserAccount") or ""] += amt
        for x in (t.get("tokenTransfers") or []):
            if (x.get("toUserAccount") or "") == w:
                tok_senders[x.get("fromUserAccount") or ""] += 1
    return fee_payers, sol_in, tok_senders


report = {}
all_discovered = set()
for w, tag in WHALES.items():
    if tag == "suqh":
        txs = json.load(open("/home/hermes/project-theia/compute/_suqh_enhanced.json"))
    else:
        txs = fetch_txs(w, PAGES)
    fp, sin, tsnd = analyze(w, txs)
    print(f"\n== {tag} ({w[:10]}..) — {len(txs)} txs ==")
    print(f"  fee-payers: {[(p[:10], n) for p, n in fp.most_common(5)]}")
    print(f"  top SOL senders: {[(p[:10], round(v, 2)) for p, v in sorted(sin.items(), key=lambda kv: -kv[1])[:5]]}")
    print(f"  top token senders: {[(p[:10], n) for p, n in tsnd.most_common(5)]}")
    report[tag] = {"fee_payers": dict(fp.most_common(8)),
                   "sol_in": {k: round(v, 3) for k, v in sorted(sin.items(), key=lambda kv: -kv[1])[:8]},
                   "token_senders": dict(tsnd.most_common(8))}
    all_discovered |= set(fp) | set(sin) | set(tsnd)
    all_discovered.discard(w)
    all_discovered.discard("")

hop2 = {}
print("\n== HOP 2 — each whale's top fee-payer behavior (3 pages) ==")
for w, tag in WHALES.items():
    fps = report[tag]["fee_payers"]
    if not fps:
        continue
    top = max(fps, key=fps.get)
    txs2 = fetch_txs(top, 3)
    fp2, sin2, tsnd2 = analyze(top, txs2)
    n_swap = sum(1 for t in txs2 if t.get("type") == "SWAP")
    whale_pays = sum(1 for t in txs2 if (t.get("feePayer") or "") == w)
    print(f"  {tag}: top payer {top[:10]} — txs={len(txs2)} SWAP-type={n_swap} "
          f"own-payers={[(p[:10], n) for p, n in fp2.most_common(3)]} whale-pays-here={whale_pays}")
    hop2[f"{tag}:{top[:10]}"] = {"addr": top, "txs": len(txs2), "swap_type": n_swap,
                                 "own_payers": dict(fp2.most_common(5)), "whale_pays": whale_pays}
    all_discovered.add(top)

# SAVE FIRST (DB independent)
OUT.write_text(json.dumps({"whales": report, "hop2": hop2,
                           "discovered_count": len(all_discovered)}))
print(f"\nsaved _money_trace.json ({len(all_discovered)} discovered wallets)")

# DB cross-check
import sqlite3
con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
con.row_factory = sqlite3.Row
print("\n== discovered wallets already in wallet_scan_history ==")
hits = 0
unknown = []
for addr in sorted(all_discovered):
    sh = con.execute(
        "SELECT scan_ts, gate_pass, winrate_7d, txs_7d, realized_profit_7d, tags "
        "FROM wallet_scan_history WHERE wallet=? ORDER BY scan_ts DESC LIMIT 1",
        (addr,)).fetchone()
    prof = con.execute(
        "SELECT is_smart_money, track_enabled FROM wallet_profiles WHERE wallet=?",
        (addr,)).fetchone()
    if sh:
        hits += 1
        ts = datetime.datetime.fromtimestamp(sh["scan_ts"], TZ).strftime("%m-%d %H:%M")
        track = " TRACKED" if (prof and prof["track_enabled"]) else ""
        print(f"  {addr[:16]:<18} scan@{ts} gate={sh['gate_pass']} wr7={sh['winrate_7d']} "
              f"r7={sh['realized_profit_7d']:.0f} txs7={sh['txs_7d']} "
              f"tags={(sh['tags'] or '')[:30]}{track}")
    else:
        unknown.append(addr)
print(f"  ({hits} known / {len(unknown)} never-scanned)")
con.close()
Path("/home/hermes/project-theia/compute/_money_unknowns.json").write_text(
    json.dumps(unknown))
print(f"saved {len(unknown)} unknown wallets -> _money_unknowns.json")