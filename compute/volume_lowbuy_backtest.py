#!/usr/bin/env python3
"""Volume-confirmed LOW-BUY backtest — the user's actual edge hypothesis.

User principle (from profile/memory): buy-low-sell-high by mcap; entry when
price is LOW in its range (small mcap / near support), buy the dip confirmed by
VOLUME (buyer ramai = strong hands stepping in), avoid the falling knife.

This DIFFERS from the naive dip test (which entered at the low with no volume
gate and bought into the knife). Here entry only fires on a bull reversal candle
with volume ABOVE its rolling average — evidence real buyers arrived.

Rule (deterministic, point-in-time, API-free on disk cache):
  - rolling high/low over `lookback` candles (default 180)
  - ENTRY CANDIDATE: candle i where close <= high*0.6 (already dipped ≥40%
    off the high — "small mcap / low in range")
  - instead of entering at i, look for confirmation: within next `confirm_n`
    candles, a BULL reversal candle j (close>open) whose volume > vol_mult ×
    rolling-average-volume-of-last-20 → buyers showed up. Entry at candle j
    OPEN (conservative: we decide after the close, fill next open), capped to
    the candle low..high range.
  - EXIT: first candle close >= exit_mult × entry (sweep) OR time_stop (sweep)
    OR hard stop 0.55 × entry.
  - volume_rel scanner also reports how much discrimination requiring vol>avg
    actually adds vs no-volume-gate.
Notional 0.5 SOL (matches live pipeline).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy  # noqa: E402

OHLCV = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
HARD_STOP = 0.55
NOTIONAL = 0.5


def _parse_mint(stem: str) -> str:
    """Extract the real mint address from a cache filename stem.

    Filenames are `<mint>_<dayBucket|now>.json` (gecko/now variant),
    `bird_<mint>_now_24h.json` / `bird_<mint>_<dayBucket>_24h.json` (birdeye
    variant), or `dex_<mint>_<bucket>.json`. The trailing `_<digits>` is the
    before_ts//86400 day bucket and `_now`/`_24h` are window markers — none are
    part of the mint. Return the bare mint address.
    """
    s = stem
    for p in ("gecko_", "bird_", "dex_"):
        if s.startswith(p):
            s = s[len(p):]
            break
    # strip trailing tokens that are not mint characters: _now, _<digits>, _24h, _60h
    parts = s.split("_")
    while len(parts) > 1 and (parts[-1] == "now" or parts[-1].lstrip("-").isdigit()
                              or parts[-1].endswith("h")):
        parts.pop()
    return "_".join(parts)


def load_mints(min_candles: int = 120) -> dict[str, list]:
    """mint -> sorted [[ts,o,h,l,c,v], ...].

    Keys by the REAL mint (not the day-bucket suffix). Multiple day-window caches
    for the same mint are merged into one continuous series, deduped by ts
    (keeps the deepest/canonical row), sorted ascending.
    """
    mints: dict[str, list] = {}
    for f in OHLCV.iterdir():
        if not f.is_file():
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
            except (TypeError, ValueError, IndexError):
                continue
        if len(clean) < min_candles:
            continue
        key = _parse_mint(f.stem)
        if not key:
            continue
        cur = mints.get(key)
        if cur is None:
            mints[key] = sorted(clean, key=lambda x: x[0])
        else:
            # merge by ts, keep every timestamp (append + resort + dedupe ts)
            by_ts = {r[0]: r for r in cur}
            for r in clean:
                by_ts[r[0]] = by_ts.get(r[0], r)
            mints[key] = sorted(by_ts.values(), key=lambda x: x[0])
    return mints


def sim_mint(rows, dip_off_high, vol_mult, exit_mult, time_stop,
             lookback=180, confirm_n=10, vol_lookback=20, require_vol=True):
    n = len(rows)
    closes = [r[4] for r in rows]
    opens = [r[1] for r in rows]
    lows = [r[3] for r in rows]
    highs = [r[2] for r in rows]
    vols = [max(r[5], 0.0) for r in rows]

    hh = [0.0] * n
    for i in range(n):
        hh[i] = max(highs[max(0, i - lookback):i + 1])

    vol_avg = [0.0] * n
    for i in range(n):
        w = vols[max(0, i - vol_lookback):i]
        vol_avg[i] = (sum(w) / len(w)) if w else 0.0

    sims = []
    i = 0
    while i < n:
        # candidate: dipped enough off the high (low in range)
        if not (hh[i] > 0 and closes[i] <= (1 - dip_off_high) * hh[i]):
            i += 1
            continue
        # find bull reversal confirmation with volume
        j = i + 1
        found = None
        while j < min(n, i + confirm_n + 1):
            vol_ok = (vols[j] > vol_mult * vol_avg[j]) if (require_vol and vol_avg[j] > 0) else True
            if opens[j] < closes[j] and vol_ok:
                found = j
                break
            j += 1
        if found is None:
            i += 1
            continue
        # entry at next candle open after the confirming close (conservative),
        # ETF-style: we act on confirmed close, fill at next candle's open
        k = found + 1
        if k >= n:
            i += 1
            continue
        entry_price = opens[k]
        if entry_price <= 0:
            i += 1
            continue
        # exit scan
        exit_price = exit_ts = None
        reason = None
        for e in range(k + 1, n):
            if closes[e] <= HARD_STOP * entry_price:
                exit_price, exit_ts, reason = lows[e], rows[e][0], "hard_stop"
                break
            if closes[e] >= exit_mult * entry_price:
                exit_price, exit_ts, reason = lows[e], rows[e][0], "tp"
                break
            if rows[e][0] - rows[found][0] >= time_stop * 60:
                exit_price, exit_ts, reason = lows[e], rows[e][0], "time_stop"
                break
        if exit_price is None:
            exit_price, exit_ts, reason = closes[-1], rows[-1][0], "data_end"
        sims.append({"mint": "", "entry_ts": rows[k][0], "pnl": (exit_price / entry_price - 1.0) * NOTIONAL,
                     "reason": reason, "entry_price": entry_price, "found": found})
        i = found + 1  # no overlap
    return sims


def main():
    mints = load_mints(min_candles=120)
    print(f"mints with >=120 candles + volume: {len(mints)}")

    # 1. does volume-gating actually change results? (vs no volume on same rule)
    print("\n=== A) volume-gate vs no-volume (dip40 vol×2 exit=1.3 tstop=120) ===")
    for rv in (False, True):
        sims = [s for r in mints.values() for s in sim_mint(r, 0.40, 2.0, 1.3, 120, require_vol=rv)]
        m = expectancy.evaluate([s["pnl"] for s in sims])
        print(f"  require_vol={rv}: n={len(sims):5d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 2. sweep the real uncertainty: vol_mult, dip_off_high, exit_mult, time_stop
    print("\n=== B) parameter sweep (volume-gated) ===")
    for dip in (0.30, 0.40, 0.50):
        for vm in (1.5, 2.0, 3.0):
            sims = [s for r in mints.values() for s in sim_mint(r, dip, vm, 1.3, 120)]
            m = expectancy.evaluate([s["pnl"] for s in sims])
            print(f"  dip={dip:.2f} volx={vm}: n={len(sims):5d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    print("\n=== C) exit sweep (dip=0.40 volx=2) ===")
    for em in (1.15, 1.3, 1.5, 2.0):
        for ts in (60, 120, 240):
            sims = [s for r in mints.values() for s in sim_mint(r, 0.40, 2.0, em, ts)]
            m = expectancy.evaluate([s["pnl"] for s in sims])
            print(f"  exit={em} tstop={ts}: n={len(sims):5d} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 3. outlier removal on best config
    print("\n=== D) outlier removal (dip=0.40 volx=2 exit=1.3 tstop=120) ===")
    sims = [s for r in mints.values() for s in sim_mint(r, 0.40, 2.0, 1.3, 120)]
    pnls = sorted([s["pnl"] for s in sims], reverse=True)
    for k in (1, 2, 5, 10):
        m = expectancy.evaluate(pnls[k:])
        print(f"  drop top-{k}: n={len(pnls)-k} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # 4. split-half by time
    print("\n=== E) split-half (dip=0.40 volx=2) ===")
    half1, half2 = [], []
    for key, r in mints.items():
        mid = len(r) // 2
        for s in sim_mint(r[:mid+1], 0.40, 2.0, 1.3, 120):
            half1.append(s)
        for s in sim_mint(r, 0.40, 2.0, 1.3, 120):
            if s["entry_ts"] >= r[mid][0]:
                half2.append(s)
    for name, sims in (("first_half", half1), ("second_half", half2)):
        m = expectancy.evaluate([s["pnl"] for s in sims])
        print(f"  {name}: n={len(sims)} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")


if __name__ == "__main__":
    main()