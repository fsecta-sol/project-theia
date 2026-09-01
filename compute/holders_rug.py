#!/usr/bin/env python3
"""C2: early-holders concentration -> rug prediction (B2).

Question: does the early-holder distribution (top-10 share, Gini, whale share)
predict which tokens rug vs survive?

Data:
  - early_holders: 6,390 rows / 636 mints (wallet, amount_usd, first_seen_ts,
    source=moon-scan-M02) — early snapshots taken at token discovery.
  - Outcome per mint: from token_corpus (graduated/dead/bonding) + OHLCV
    drawdown (max drop from ATH after the snapshot window) + pools liq now.
Labels:
  rug     = token had a catastrophic drawdown (>70% drop from its post-snapshot
            high with volume collapse) or corpus dead
  survive = still has liquidity + price within normal decay range
Features (computed from the holder snapshot per mint):
  top10_share (USD of top-10 wallets / total USD), whale_share (>5k USD
  holders' share), n_holders, mean_holder_usd, gini.
Then: bucket analysis + simple threshold sweep for a veto rule. All local data,
no API.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

DB = "/home/hermes/.hermes/theia/theia.db"
OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"


def load_ohlcv(mint_prefixes):
    """mint -> sorted candles for mints matching prefixes (organic only)."""
    new_files = {f.stem[:-4] for f in OHLCV.iterdir()
                 if f.is_file() and f.stem.endswith("_now")}
    out = {}
    for f in OHLCV.iterdir():
        if not f.is_file():
            continue
        stem = f.stem
        mint = stem
        for p in ("gecko_", "bird_", "dex_"):
            if mint.startswith(p):
                mint = mint[len(p):]
        # strip trailing bucket markers
        if mint.endswith("_now") or mint.endswith("_24h"):
            mint = mint.rsplit("_", 1)[0]
        parts = mint.split("_")
        if len(parts) > 1 and parts[-1].isdigit():
            mint = "_".join(parts[:-1])
        if not any(mint.startswith(p) for p in mint_prefixes):
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        rows = data.get("rows", data) if isinstance(data, dict) else data
        clean = []
        for r in rows:
            try:
                clean.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                              float(r[4]), float(r[5]) if len(r) > 5 else 0.0])
            except Exception:
                continue
        if len(clean) >= 30:
            cur = out.get(mint)
            if cur is None:
                out[mint] = sorted(clean, key=lambda x: x[0])
            else:
                by_ts = {r[0]: r for r in cur}
                for r in clean:
                    by_ts[r[0]] = by_ts.get(r[0], r)
                out[mint] = sorted(by_ts.values(), key=lambda x: x[0])
    return out


def gini(amounts):
    s = sorted(amounts)
    n = len(s)
    tot = sum(s)
    if tot == 0 or n == 0:
        return 0.0
    cum = 0.0
    for i, v in enumerate(s):
        cum += (i + 1) * v
    return (2 * cum) / (n * tot) - (n + 1) / n


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # holder snapshot per mint
    hrows = con.execute("SELECT mint, wallet, amount_usd, first_seen_ts FROM early_holders").fetchall()
    per_mint = defaultdict(list)
    for r in hrows:
        per_mint[r["mint"]].append({"wallet": r["wallet"], "usd": r["amount_usd"] or 0})
    corpus = {r["mint"]: r["graduation_status"] for r in
              con.execute("SELECT mint, graduation_status FROM token_corpus")}
    con.close()

    features = {}
    for mint, holders in per_mint.items():
        usds = [h["usd"] for h in holders]
        if not usds or sum(usds) <= 0:
            continue
        s = sorted(usds, reverse=True)
        top10 = sum(s[:10]) / sum(usds)
        whale_share = sum(v for v in usds if v > 5000) / sum(usds)
        features[mint] = {
            "n_holders": len(usds),
            "total_usd": sum(usds),
            "top10_share": top10,
            "whale_share": whale_share,
            "mean_usd": sum(usds) / len(usds),
            "gini": gini(usds),
            "corpus": corpus.get(mint, "unknown"),
        }
    print(f"mints with holder features: {len(features)}")

    # outcome: max drawdown from post-snapshot high using OHLCV (organic keys only)
    charts = load_ohlcv(set(features.keys()))
    print(f"mints with organic charts: {len(charts)}")

    outcomes = {}
    for mint, rows in charts.items():
        closes = [r[4] for r in rows]
        peak = max(closes)
        if peak <= 0:
            continue
        # post-snapshot high: only consider candles after first 20 (warmup)
        late_peak = max(closes[20:]) if len(closes) > 20 else peak
        final = closes[-1]
        dd = final / late_peak - 1.0
        lab = corpus.get(mint, "unknown")
        if dd <= -0.70 or lab == "dead":
            outcomes[mint] = "rug"
        elif lab == "graduated":
            outcomes[mint] = "survived"
        elif dd >= -0.55:
            outcomes[mint] = "survived"
        else:
            outcomes[mint] = "mid"  # ambiguous middle
    print(f"labeled outcomes: {len(outcomes)} "
          f"(rug={sum(1 for v in outcomes.values() if v=='rug')}, "
          f"survived={sum(1 for v in outcomes.values() if v=='survived')}, "
          f"mid={sum(1 for v in outcomes.values() if v=='mid')})")

    # bucket analysis on top10_share (only mints present in features)
    common = [m for m in outcomes if m in features]
    outcomes = {m: outcomes[m] for m in common}
    buckets = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]
    print(f"\n{'top10_share bucket':<20} {'n':>4} {'rug%':>6} {'surv%':>6} {'mid%':>6}")
    for lo, hi in buckets:
        grp = [features[m] for m in outcomes if lo <= features[m]["top10_share"] < hi]
        n = len(grp)
        if not n:
            continue
        rug = sum(1 for m in outcomes if lo <= features[m]["top10_share"] < hi
                  and outcomes[m] == "rug") / n
        surv = sum(1 for m in outcomes if lo <= features[m]["top10_share"] < hi
                   and outcomes[m] == "survived") / n
        mid = sum(1 for m in outcomes if lo <= features[m]["top10_share"] < hi
                  and outcomes[m] == "mid") / n
        print(f"  {lo:.2f}-{hi:.2f}{'':<10} {n:>4} {rug:>6.0%} {surv:>6.0%} {mid:>6.0%}")

    # same for whale_share (>5k USD holders)
    print(f"\n{'whale_share bucket':<20} {'n':>4} {'rug%':>6} {'surv%':>6} {'mid%':>6}")
    wb = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    for lo, hi in wb:
        n = sum(1 for m in outcomes if lo <= features[m]["whale_share"] < hi)
        if not n:
            continue
        rug = sum(1 for m in outcomes if lo <= features[m]["whale_share"] < hi
                  and outcomes[m] == "rug") / n
        surv = sum(1 for m in outcomes if lo <= features[m]["whale_share"] < hi
                   and outcomes[m] == "survived") / n
        mid = sum(1 for m in outcomes if lo <= features[m]["whale_share"] < hi
                  and outcomes[m] == "mid") / n
        print(f"  {lo:.2f}-{hi:.2f}{'':<10} {n:>4} {rug:>6.0%} {surv:>6.0%} {mid:>6.0%}")

    json.dump({"features": features, "outcomes": outcomes},
              open("/home/hermes/project-theia/compute/_holders_rug.json", "w"),
              indent=1, default=str)
    print("\nsaved _holders_rug.json")


if __name__ == "__main__":
    main()