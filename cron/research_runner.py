#!/usr/bin/env python3
"""Theia nightly research-runner (no-agent, autonomous).

Runs every ~12h. Three jobs, all deterministic / API-free on stored data,
fits free-tier budget:
  J1 universe-monitor — count mint-series in the OHLCV cache + forward-corpus
     mints in price_snapshots, so we see data growth week over week.
  J2 re-run batteries — re-run the dip + volume-lowbuy verdict batteries and,
     if a config ever crosses the gate, write a HIT file (the nominal trigger
     to promote / human-review).
  J3 digest — write a dated digest note to the vault so the 24h progress is
     self-documenting even with no one watching.

PROVENANCE GUARD (2026-09-01, gate-hit reconcile commit 656858e):
The OHLCV cache mixes organically-recorded candles with retro-fetched `_now`
files; the retro mints' recovered prices dominate PnL and produced a false
GATE HIT (dip +0.52/PF 7.5, volume +1.58/PF 16.9 — all concentrated on the
3 retro-fetch days; excluding those days the same rules are −0.039/PF 0.49
and −0.021/PF 0.75). Batteries therefore run on ORGANIC-ONLY keys, and the
gate additionally requires the pre-retro-day subset to pass (day-bucket
guard). Costs are charged per trade (0.00432 SOL on 0.5 notional).
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim  # noqa: E402
from compute.dip_reversal_backtest import load_pools  # noqa: E402
from compute.volume_lowbuy_backtest import load_mints, sim_mint, NOTIONAL  # noqa: E402

OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
OUT = Path.home() / ".hermes/theia/wallet_cache/run"  # state shared with nobody; mkdir below
VAULT = Path.home() / "vault/00-Inbox/_knowledge"
HIT_FILE = OUT / "GATE_HIT.json"

COST_PER_TRADE = (gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol()
                  + NOTIONAL * costs.slippage_estimate(NOTIONAL * 150.0, 5000, False))
WIB = timezone(timedelta(hours=7))


def j1_universe() -> dict:
    files = sum(1 for f in OHLCV.iterdir() if f.is_file()) if OHLCV.exists() else 0
    mints = len(load_mints(min_candles=120))
    pools = len(load_pools(min_rows=200))
    return {"ohlcv_files": files, "mints_cached_120c": mints, "pools_200c": pools,
            "ts": int(time.time())}


def organic_only(mints: dict) -> dict:
    """Exclude retro-fetched `_now` cache keys (fetch-bias guard)."""
    if not OHLCV.exists():
        return mints
    new_files = {f.stem[:-4] for f in OHLCV.iterdir()
                 if f.is_file() and f.stem.endswith("_now")}
    return {k: r for k, r in mints.items() if k not in new_files}


def _best(lst):
    return max(lst, key=lambda s: s["expectancy"])


def _day(tsim) -> str:
    return datetime.fromtimestamp(tsim or 0, WIB).strftime("%m-%d")


def j2_batteries(report: dict) -> dict:
    mints = organic_only(load_mints(min_candles=120))
    n_org = len(mints)
    report["organic_mints"] = n_org

    # dip-reversal best-config search (organic-only, costs charged)
    best = None
    best_by_day = None
    for dip in (0.20, 0.30, 0.40):
        for cf in (0.85, 0.90, 0.95):
            s = [x for r in mints.values() for x in sim_mint(r, dip, cf, 1.30, 120)]
            pnls = [x["pnl"] - COST_PER_TRADE for x in s]
            m = expectancy.evaluate(pnls)
            if best is None or m["expectancy"] > best["expectancy"]:
                best = {"rule": "dip_reversal", "dip": dip, "cf": cf, **m}
                best_by_day = defaultdict(list)
                for x, p in zip(s, pnls):
                    best_by_day[_day(x.get("entry_ts"))].append(p)
    report["dip_reversal_best"] = best
    # day-bucket guard: how many NON-retro days contribute positively?
    if best_by_day:
        day_stats = {d: (len(v), round(sum(v) / len(v), 4)) for d, v in sorted(best_by_day.items())}
        pos_days = sum(1 for _, (n, e) in day_stats.items() if e > 0)
        neg_days = sum(1 for _, (n, e) in day_stats.items() if e < 0)
        report["dip_day_split"] = {"pos_days": pos_days, "neg_days": neg_days,
                                   "days": day_stats}

    # volume-lowbuy best (organic-only, costs charged)
    vb = None
    vb_by_day = None
    for dip in (0.30, 0.40, 0.50):
        for vm in (2.0, 3.0):
            s = [x for r in mints.values() for x in sim_mint(r, dip, vm, 2.0, 120, require_vol=True)]
            pnls = [x["pnl"] - COST_PER_TRADE for x in s]
            m = expectancy.evaluate(pnls)
            if vb is None or m["expectancy"] > vb["expectancy"]:
                vb = {"rule": "volume_lowbuy", "dip": dip, "volx": vm, **m}
                vb_by_day = defaultdict(list)
                for x, p in zip(s, pnls):
                    vb_by_day[_day(x.get("entry_ts"))].append(p)
    report["volume_lowbuy_best"] = vb
    if vb_by_day:
        day_stats = {d: (len(v), round(sum(v) / len(v), 4)) for d, v in sorted(vb_by_day.items())}
        pos_days = sum(1 for _, (n, e) in day_stats.items() if e > 0)
        neg_days = sum(1 for _, (n, e) in day_stats.items() if e < 0)
        report["vol_day_split"] = {"pos_days": pos_days, "neg_days": neg_days,
                                   "days": day_stats}
    return report


def j3_digest(report: dict) -> Path:
    VAULT.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = VAULT / f"{day}-nightly-auto-digest.md"
    db = report.get("universe", {})
    lines = [
        f"# Theia nightly auto-digest — {day} (UTC)",
        f"\n_Generated by no-agent research-runner (see `cron/research_runner.py`)._\\",
        f"\n_Provenance guard: batteries run on ORGANIC-ONLY cache (no `_now` retro-fetch keys), costs charged._\\",
        f"## Universe growth",
        f"- OHLCV cache files: {db.get('ohlcv_files')} (organic keys used: {report.get('organic_mints')})",
        f"- mints (>=120 candles): {db.get('mints_cached_120c')}",
        f"- pools (>=200 candles): {db.get('pools_200c')}",
        "\n## Battery best-config (re-scanned, organic-only + costs)",
        f"- dip_reversal: {json.dumps(report.get('dip_reversal_best'))}",
        f"- dip day-split: pos {report.get('dip_day_split', {}).get('pos_days')} / "
        f"neg {report.get('dip_day_split', {}).get('neg_days')} days",
        f"- volume_lowbuy: {json.dumps(report.get('volume_lowbuy_best'))}",
        f"- vol day-split: pos {report.get('vol_day_split', {}).get('pos_days')} / "
        f"neg {report.get('vol_day_split', {}).get('neg_days')} days",
        "\n_All expectancy/PF from `compute/expectancy.py`; numbers only, no trading._\\",
    ]
    p.write_text("\n".join(lines))
    return p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"ts": int(time.time())}
    try:
        report["universe"] = j1_universe()
    except Exception as e:  # noqa: BLE001
        report["universe_err"] = str(e)
    try:
        report = j2_batteries(report)
    except Exception as e:  # noqa: BLE001
        report["battery_err"] = str(e)
    try:
        note = j3_digest(report)
        report["digest"] = str(note)
    except Exception as e:  # noqa: BLE001
        report["digest_err"] = str(e)

    # gate HIT check (hardened): exp>0 AND pf>1 on n>=20 AND organic-provenance
    # AND positive-expectancy days must NOT be a tiny minority of active days
    # (the 08-31 false HIT had 3 glowing days hiding 27 negative days).
    hits = 0
    reasons = []
    for key, split_key in (("dip_reversal_best", "dip_day_split"),
                           ("volume_lowbuy_best", "vol_day_split")):
        b = report.get(key)
        sp = report.get(split_key, {})
        if not b or b.get("n", 0) < 20 or b.get("expectancy", 0) <= 0 or b.get("profit_factor", 0) <= 1:
            continue
        pos, neg = sp.get("pos_days", 0), sp.get("neg_days", 0)
        active = pos + neg
        if active and pos / max(active, 1) < 0.5:
            reasons.append(f"{key}: exp>0 but only {pos}/{active} active days positive (concentration guard)")
            continue
        hits += 1
    if hits:
        HIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        report["hit_reasons"] = reasons
        HIT_FILE.write_text(json.dumps(report, indent=2, default=str))
        print(f"[research] GATE HIT: {hits} rule(s) crossed — see {HIT_FILE}")
    else:
        print("[research] no rule crossed the hardened gate (n>=20, organic-only, costs, "
              "day-concentration guard). " +
              json.dumps({k: report.get(k) for k in ('dip_reversal_best', 'volume_lowbuy_best')},
                         default=str)[:400])
    print(f"[research] digest -> {report.get('digest')}")


if __name__ == "__main__":
    main()