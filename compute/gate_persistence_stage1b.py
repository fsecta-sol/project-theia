#!/usr/bin/env python3
"""Gate-persistence stage 1b — longitudinal decay from stored scan_history (FREE).

Wallets are scanned repeatedly; each scan's realized_profit_7d is a rolling 7d
window. Between scans ~24h apart, the window shifts by one day, so the DELTA
across consecutive scans ≈ that day's realized PnL (plus window re-base).

Measures (pass cohort = latest gate_pass=1 in the 6d window; fail cohort = pass=0):
  A. rPnl7d trajectory per wallet: first vs last scan in window, and the share
     of consecutive-scan deltas that are NEGATIVE (decay proxy).
  B. Fail-cohort counter-evidence: wallets whose later scans show big positive
     rPnl7d (false negatives — gate rejected a wallet that later printed).
  C. Aggregate: mean delta per day, pass vs fail.
Deterministic, API-free, wallet_scan_history only.
"""
import json
import sqlite3
import statistics
import time
from collections import defaultdict
from pathlib import Path

DB = Path.home() / ".hermes/theia/theia.db"
NOW = int(time.time())
WIN_LO = NOW - 6 * 86400
WIN_HI = NOW - 1 * 86400

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT wallet, scan_ts, gate_pass, gate_reason, realized_profit_7d, pnl_7d, "
    "winrate_7d, txs_7d FROM wallet_scan_history "
    "WHERE scan_ts BETWEEN ? AND ? ORDER BY wallet, scan_ts", (WIN_LO, WIN_HI)).fetchall()
con.close()

by_wallet = defaultdict(list)
for r in rows:
    if r["realized_profit_7d"] is None:
        continue
    by_wallet[r["wallet"]].append({
        "ts": r["scan_ts"], "gp": r["gate_pass"], "r7": r["realized_profit_7d"],
        "wr": r["winrate_7d"], "txs": r["txs_7d"],
    })

# classify wallets by their LAST scan verdict in the window (the "current" gate call)
pass_w = {w: seq for w, seq in by_wallet.items() if seq[-1]["gp"] == 1}
fail_w = {w: seq for w, seq in by_wallet.items() if seq[-1]["gp"] == 0}
print(f"wallets w/ rPnl series: pass={len(pass_w)} fail={len(fail_w)}")


def decay_stats(seq):
    """Consecutive-scan deltas of rPnl7d (~24h apart)."""
    deltas = []
    for a, b in zip(seq, seq[1:]):
        if b["ts"] - a["ts"] < 30 * 60:  # scans closer than 30m → same window, skip
            continue
        deltas.append(b["r7"] - a["r7"])
    if not deltas:
        return None
    return {
        "n_deltas": len(deltas),
        "neg_share": sum(1 for d in deltas if d < 0) / len(deltas),
        "mean_delta": statistics.mean(deltas),
        "first": seq[0]["r7"], "last": seq[-1]["r7"],
        "drift": seq[-1]["r7"] - seq[0]["r7"],
    }


# A. pass cohort decay
print("\n== A. PASS cohort — rPnl7d trajectory (rolling 7d, scans ~daily) ==")
pass_decay = {}
for w, seq in pass_w.items():
    d = decay_stats(seq)
    if d:
        pass_decay[w] = d
if pass_decay:
    neg_shares = [d["neg_share"] for d in pass_decay.values()]
    mean_deltas = [d["mean_delta"] for d in pass_decay.values()]
    drifts = [d["drift"] for d in pass_decay.values()]
    print(f"  wallets with series: {len(pass_decay)}")
    print(f"  median neg-delta share: {statistics.median(neg_shares):.2f} "
          f"(1.0 = always decaying, 0.0 = always rising)")
    print(f"  median daily delta (rPnl7d shift): {statistics.median(mean_deltas):+.0f} SOL/day")
    print(f"  median total drift over window: {statistics.median(drifts):+.0f} SOL")
    rising = sum(1 for d in drifts if d > 0)
    print(f"  wallets whose rPnl7d ROSE over window: {rising}/{len(drifts)}")

# B. fail cohort counter-evidence
print("\n== B. FAIL cohort — false negatives (failed gate but later printed) ==")
fn = []
for w, seq in fail_w.items():
    d = decay_stats(seq)
    if d and d["last"] > 1000 and d["drift"] > 500:  # material late profit
        fn.append((w[:12], d["first"], d["last"], d["drift"], len(seq)))
fn.sort(key=lambda x: -x[3])
print(f"  candidates (last r7>1000 AND drift>+500): {len(fn)}")
for w, f0, f1, dr, n in fn[:10]:
    print(f"  {w:<14} first={f0:>9.0f} last={f1:>10.0f} drift={dr:>10.0f} scans={n}")

# C. aggregate pass vs fail daily delta
print("\n== C. aggregate daily delta (pass vs fail) ==")
for name, cohort in (("PASS", pass_w), ("FAIL", fail_w)):
    ds = []
    for seq in cohort.values():
        d = decay_stats(seq)
        if d:
            ds.append(d["mean_delta"])
    if ds:
        print(f"  {name}: wallets={len(ds)} median daily delta={statistics.median(ds):+.0f} SOL")

# fail cohort top: how many have ANY scan with rPnl7d > 1000?
big_fail = sum(1 for seq in fail_w.values() if max(s["r7"] for s in seq) > 1000)
print(f"\n  FAIL wallets that at ANY scan had rPnl7d > +1000: {big_fail}/{len(fail_w)}")