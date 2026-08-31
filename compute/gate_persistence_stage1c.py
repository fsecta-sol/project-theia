#!/usr/bin/env python3
"""Gate-persistence stage 1c — the REAL cohort comparison (API-free).

Previous runs had a cohort-definition flaw: pass/fail was defined by the LAST
scan in the window, but most wallets get re-scanned daily, so "last scan" ≈
"today's gate call" — good. However the FAIL cohort includes wallets that were
rejected for bad tags/wash OR txs<150 OR wr7<0.6 — very different reasons. To
answer "does the gate have predictive validity", compare cohorts that fail for
the SAME criterion the pass cohort passes (wr7>=0.6 + txs7>=150 + hold<48h):

  PASS_A: wallet whose LATEST scan passes (wr7>=0.6 & txs7>=150 & hold<48h & no bad tag)
  FAIL_B: wallet whose LATEST scan fails ONLY on wr7 in [0.45, 0.60) (near-miss,
          txs7>=150, no bad tag) — same trading regime, wr just below threshold.
  FAIL_C: wallet that fails on bad_tag (wash/bot) with profitable rPnl7d — the
          gate's anti-wash protection.

For each group measure forward outcome = max rPnl7d drift over the window
(positive drift AFTER the gate call = wallet kept printing after selection).

All from wallet_scan_history (append-only, stored daily scans) — API-free.
"""
import sqlite3
import statistics
import time
from collections import defaultdict

DB = "/home/hermes/.hermes/theia/theia.db"
NOW = int(time.time())
WIN_LO = NOW - 6 * 86400
WIN_HI = NOW - 1 * 86400
BAD_TAGS = {"wash_trader", "bot", "bundler", "sniper"}

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT wallet, scan_ts, gate_pass, gate_reason, realized_profit_7d, winrate_7d, "
    "txs_7d, avg_holding_period_7d, tags FROM wallet_scan_history "
    "WHERE scan_ts BETWEEN ? AND ? ORDER BY wallet, scan_ts", (WIN_LO, WIN_HI)).fetchall()
con.close()

series = defaultdict(list)
for r in rows:
    if r["realized_profit_7d"] is None:
        continue
    tags = set()
    try:
        import json as _json
        tags = set(_json.loads(r["tags"] or "[]"))
    except Exception:
        pass
    series[r["wallet"]].append({
        "ts": r["scan_ts"], "gp": r["gate_pass"], "gr": r["gate_reason"] or "",
        "r7": r["realized_profit_7d"], "wr": r["winrate_7d"],
        "txs": r["txs_7d"], "hold": r["avg_holding_period_7d"], "tags": tags,
    })


def has_bad_tag(seq):
    return any(s["tags"] & BAD_TAGS for s in seq)


def outcome(seq):
    """Forward outcome after the FIRST scan: max drift of r7 after first scan."""
    r0 = seq[0]["r7"]
    later = [s["r7"] for s in seq[1:]] or [r0]
    return max(later) - r0, len(seq)


groups = {"PASS_A": [], "FAIL_B_nearmiss": [], "FAIL_C_badtag": [], "FAIL_other": []}
for w, seq in series.items():
    last = seq[-1]
    bad = has_bad_tag(seq)
    wr_ok = (last["wr"] or 0) >= 0.60
    txs_ok = (last["txs"] or 0) >= 150
    hold_ok = (last["hold"] or 0) < 48 * 3600
    if last["gp"] == 1 and wr_ok:
        groups["PASS_A"].append((w, seq))
    elif bad:
        groups["FAIL_C_badtag"].append((w, seq))
    elif txs_ok and hold_ok and 0.45 <= (last["wr"] or 0) < 0.60:
        groups["FAIL_B_nearmiss"].append((w, seq))
    else:
        groups["FAIL_other"].append((w, seq))

print(f"{'group':<18} {'wallets':>8} {'median outdrift':>16} {'share +ve':>10} {'top5 drift':>12}")
for name, members in groups.items():
    outs = [outcome(seq) for w, seq in members]
    drifts = [d for d, _ in outs]
    if not drifts:
        print(f"{name:<18} {0:>8}")
        continue
    pos = sum(1 for d in drifts if d > 0) / len(drifts)
    top = sorted(drifts, reverse=True)[:5]
    print(f"{name:<18} {len(members):>8} {statistics.median(drifts):>+16.0f} {pos:>10.1%} {statistics.median(top):>+12.0f}")

# PASS_A detail: their drift
print("\n== PASS_A detail (each wallet's forward drift after gate) ==")
for w, seq in groups["PASS_A"]:
    d, n = outcome(seq)
    wr = seq[-1]["wr"] or 0
    print(f"  {w[:12]:<14} wr7={wr:.2f} scans={n:>2} fwd_drift={d:+9.0f}")

# the key question: PASS_A vs FAIL_B drift distributions
print("\n== Head-to-head: PASS_A (wr>=0.6) vs FAIL_B (wr 0.45-0.59, same regime) ==")
for name in ("PASS_A", "FAIL_B_nearmiss"):
    outs = [outcome(seq)[0] for w, seq in groups[name]]
    if outs:
        print(f"  {name}: n={len(outs)} median={statistics.median(outs):+.0f} "
              f"mean={statistics.mean(outs):+.0f} share+ve={sum(1 for d in outs if d>0)/len(outs):.0%}")