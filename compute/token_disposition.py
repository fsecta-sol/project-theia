#!/usr/bin/env python3
"""Do the tokens the whales buy 'fly away'? Current holdings (RPC ground truth)
vs decoded lot flows — disposition per mint: SOLD (round-trip), HELD, or
VANISHED (net>0 but holding 0 = moved out without a classified sell)."""
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

KEY = ""
secret = Path("/home/hermes/project-theia/.secret")
if secret.exists():
    for line in secret.read_text().splitlines():
        if line.strip().startswith("HELIUS_API_KEY"):
            KEY = line.split("=", 1)[1].split(",")[0].strip()
URLS = ([f"https://mainnet.helius-rpc.com/?api-key={KEY}"] if KEY else []) + \
       ["https://api.mainnet-beta.solana.com"]


def rpc(method, params):
    for url in URLS:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                r = json.loads(resp.read())
        except Exception as e:
            print(f"  rpc err ({url.split('?')[0]}): {str(e)[:60]}")
            continue
        if "error" not in r:
            return r.get("result")
    return None


def current_holdings(w):
    """mint -> {amount, decimals} from live token accounts."""
    res = rpc("getTokenAccountsByOwner",
              [w, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
               {"encoding": "jsonParsed"}])
    out = {}
    for acc in (res or {}).get("value") or []:
        info = ((acc.get("account") or {}).get("data") or {}).get("parsed", {}).get("info") or {}
        ts = info.get("tokenAmount") or {}
        amt = float(ts.get("uiAmount") or 0)
        if amt > 0:
            out[info.get("mint")] = {"amount": amt, "decimals": ts.get("decimals")}
    return out


WHALES = {
    "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh",
    "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5",
    "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin",
    "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8",
}

LOTS_SOURCES = {
    "suqh": "/home/hermes/project-theia/compute/_suqh_lots.json",
    "others": "/home/hermes/project-theia/compute/_whale_lots_v2.json",
}

suqh_lots = json.load(open(LOTS_SOURCES["suqh"]))
v2 = json.load(open(LOTS_SOURCES["others"]))

summary = {}
for w, tag in WHALES.items():
    lots = suqh_lots if tag == "suqh" else (v2.get(w) or {}).get("lots", [])
    # signed net per mint (qty already signed: +delta / -delta)
    per_mint = defaultdict(float)
    bought = defaultdict(float)   # positive deltas
    sold = defaultdict(float)     # negative deltas
    for l in lots:
        q = l["qty"]
        per_mint[l["mint"]] += q
        if q > 0:
            bought[l["mint"]] += q
        else:
            sold[l["mint"]] += -q
    hold_now = current_holdings(w)
    hold_mints = set(hold_now.keys())
    # disposition of mints the whale ACQUIRED (net or bought > 0)
    acquired = [m for m in per_mint if bought[m] > 0 or per_mint[m] > 0]
    disp = {"round_tripped": 0, "still_held": 0, "vanished": 0}
    vanished_mints, held_mints = [], []
    for m in acquired:
        net = per_mint[m]
        if net <= 0.0001 and m not in hold_mints:
            disp["round_tripped"] += 1
        elif m in hold_mints:
            disp["still_held"] += 1
            held_mints.append(m)
        elif net > 0 and m not in hold_mints:
            disp["vanished"] += 1
            vanished_mints.append(m)
    n = len(acquired)
    print(f"== {tag} ==")
    print(f"  decoded lots: {len(lots)} | mints touched: {len(per_mint)} | acquired-mints: {n}")
    print(f"  disposition: SOLD/round-trip {disp['round_tripped']} ({100*disp['round_tripped']/max(n,1):.0f}%) | "
          f"STILL HELD {disp['still_held']} ({100*disp['still_held']/max(n,1):.0f}%) | "
          f"VANISHED (net>0, holding 0) {disp['vanished']} ({100*disp['vanished']/max(n,1):.0f}%)")
    print(f"  live token accounts (non-zero): {len(hold_mints)}")
    if held_mints[:5]:
        print(f"  still-held sample: {[(m[:8], round(hold_now[m]['amount'], 1)) for m in held_mints[:5]]}")
    if vanished_mints[:5]:
        print(f"  vanished sample (net>0 but 0 holdings): {[(m[:8], round(per_mint[m], 0)) for m in vanished_mints[:5]]}")
    # total SOL out/in on the real trades
    sol_out = sum(l["sol_out"] for l in lots)
    sol_in = sum(l["sol_in"] for l in lots)
    print(f"  SOL legs over window: out {sol_out:.1f} / in {sol_in:.1f} (net {sol_in - sol_out:+.1f})")
    summary[tag] = {"mints": len(per_mint), "acquired": n, **disp,
                    "holdings_now": len(hold_mints)}

json.dump(summary, open("/home/hermes/project-theia/compute/_token_disposition.json", "w"), indent=1)
print("\nsaved _token_disposition.json")