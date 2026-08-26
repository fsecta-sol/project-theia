"""Volume/liquidity-aware exit state machine (M-04 POC D, rule sets B/C).

Per-bar liquidity is NOT stored in the OHLCV files (rows are [ts,o,h,l,c,v]),
so every rule here uses BAR VOLUME as the liquidity proxy — the report must
state this explicitly. All rules keep baseline params (hard_stop -0.35,
tp_ladder [(2.0,0.5),(4.0,0.5)], trail 0.25, time_stop 30m) and only ADD a
volume-conditioned exit behavior, so a rule's effect is isolated.

Rules (mode):
  liq_collapse     exit when the trailing 5-bar volume SUM falls below
                   `vol_floor` * (peak 5-bar sum seen since entry) — exit at
                   that bar's close. Contract VAL-LIQ-COLLAPSE-005: "rolling
                   volume drops below X% of peak rolling volume since entry";
                   thresholds tested: 0.30 and 0.50. exit_reason = "liq_collapse".
  vol_deterioration exit when the CURRENT BAR volume falls below `vol_floor` *
                   the rolling peak volume since entry (single-bar drop, not a
                   rolling sum). VAL-VOL-DETERIORATION-006; thresholds 0.20 and
                   0.40. exit_reason = "vol_deterioration".
  liq_trail        trailing stop distance adapts to the volume regime:
                   trail_drop = 0.30 (loose) while trailing-5-bar volume >=
                   `vol_scale` * rolling mean volume since entry (deep), else
                   0.15 (tight). VAL-LIQ-TRAIL-007. exit_reason = "trail".
  vol_peak_partial sell 50% at the close of any bar whose volume is a new
                   running peak since entry; the rest continues under baseline
                   rules. VAL-PARTIAL-VOL-PEAK-008. The partial exit's event
                   reason is "vol_peak_partial"; the final exit_reason is the
                   event that closes the remainder (hard_stop/time_stop/trail/
                   tp_2x/tp_4x/path_end). Entry-side exit_cost is scaled by the
                   number of exit events (each event is one tx).

Order within a bar (conservative, mirrors exit_engine.py): hard stop, then
time stop, then volume-triggered exits (they use the bar CLOSE), then TP
ladder, then trail. A volume-trigger is evaluated once per bar (one event max)
and uses the close of that bar.

Deterministic: no RNG, pure function of (entry_price, entry_ts, path, params).
"""
from __future__ import annotations


def _params(p: dict) -> dict:
    out = {
        "mode": "liq_collapse",
        "hard_stop": -0.35,
        "tp_ladder": [(2.0, 0.5), (4.0, 0.5)],
        "trail_drop": 0.25,
        "time_stop_secs": 1800,
        "vol_window": 5,
        "vol_floor": 0.30,     # liq_collapse / vol_deterioration threshold
        "vol_scale": 1.0,      # liq_trail regime divider vs rolling mean
        "trail_tight": 0.15,   # liq_trail thin-volume trail
        "trail_loose": 0.30,   # liq_trail deep-volume trail
        "partial_frac": 0.50,  # vol_peak_partial fraction at new volume peak
    }
    out.update(p or {})
    return out


def simulate_vol_exit(entry_price: float, entry_ts: int, path: list,
                      params: dict | None = None) -> dict:
    """Simulate one trade under a volume-conditioned exit rule.

    path rows: [ts, o, h, l, c, v] (v = bar volume, the liquidity proxy).
    """
    p: dict = _params(params or {})
    mode = p["mode"]
    win = max(1, int(p["vol_window"]))

    remaining = 1.0
    exits = []                     # (frac, price, reason)
    events = []                    # {fraction, price, reason, ts}
    peak = entry_price
    hard_stop_px = entry_price * (1 + p["hard_stop"])
    ladder = list(p["tp_ladder"])

    # rolling-volume state (per-bar volume, the liquidity proxy)
    roll_win = []                  # window of per-bar volumes
    roll_sum = 0.0                 # current window sum
    roll_peak = 0.0                # peak window-sum since entry
    peak_vol = 0.0                 # running peak single-bar volume (deterioration)
    vol_mean = 0.0                 # running mean single-bar volume
    vol_n = 0

    partial_done = False
    last_ts, last_close = entry_ts, entry_price

    def close(frac, price, reason, ts):
        nonlocal remaining
        frac = min(frac, remaining)
        if frac <= 1e-12:
            return
        exits.append((frac, price, reason))
        events.append({"fraction": round(frac, 6), "price": price,
                       "reason": reason, "ts": ts})
        remaining -= frac

    for row in path:
        ts, hi, lo, c = row[0], row[2], row[3], row[4]
        v = row[5] if len(row) > 5 else 0.0
        last_ts, last_close = ts, c
        peak = max(peak, hi)

        # time stop first (order mirrors exit_engine.py: time -> hard -> TP -> trail)
        if ts - entry_ts >= p["time_stop_secs"] and remaining > 1e-9:
            close(remaining, c, "time_stop", ts)
            break

        # hard stop (conservative, mirrors exit_engine.py)
        if lo <= hard_stop_px and remaining > 1e-9:
            close(remaining, hard_stop_px, "hard_stop", ts)
            break

        # ── volume-conditioned behaviors (use this bar's close) ──
        vol_n += 1
        vol_mean = (vol_mean * (vol_n - 1) + v) / vol_n
        roll_win.append(v)
        roll_sum += v
        if len(roll_win) > win:
            roll_sum -= roll_win.pop(0)
        if roll_sum > roll_peak:
            roll_peak = roll_sum
        prior_peak = peak_vol
        if v > peak_vol:
            peak_vol = v

        if mode == "liq_collapse" and roll_peak > 0 and remaining > 1e-9:
            # 5-bar volume SUM drops below floor * peak 5-bar sum since entry
            if roll_sum < p["vol_floor"] * roll_peak:
                close(remaining, c, "liq_collapse", ts)
                break
        elif mode == "vol_deterioration" and peak_vol > 0 and remaining > 1e-9:
            # current single-bar volume < floor * running peak bar volume
            if v < p["vol_floor"] * peak_vol:
                close(remaining, c, "vol_deterioration", ts)
                break
        elif mode == "vol_peak_partial" and remaining > 1e-9 and not partial_done:
            # bar exceeds all PRIOR bars since entry (needs >=1 prior bar)
            # -> sell partial_frac at close; rest continues under baseline rules
            if vol_n >= 2 and v > prior_peak:
                partial_done = True
                close(p["partial_frac"], c, "vol_peak_partial", ts)

        # TP ladder
        while ladder and hi >= entry_price * ladder[0][0] and remaining > 1e-9:
            mult, frac = ladder.pop(0)
            close(min(frac, remaining), entry_price * mult, f"tp_{mult:g}x", ts)

        # trailing stop (adaptive if liq_trail)
        if not ladder and remaining > 1e-9:
            td = p["trail_drop"]
            if mode == "liq_trail":
                # deep volume (>= scale * rolling mean) -> loose trail, else tight
                td = p["trail_loose"] if (v >= p["vol_scale"] * vol_mean) else p["trail_tight"]
            trail_px = peak * (1 - td)
            if lo <= trail_px:
                close(remaining, trail_px, "trail", ts)
                break

    if remaining > 1e-9:
        close(remaining, last_close, "path_end", last_ts)

    realized = sum(f * pr for f, pr, _ in exits)
    exit_ts = events[-1]["ts"] if events else entry_ts
    return {
        "realized_price": realized,
        "return_mult": realized / entry_price if entry_price else 0.0,
        "final_reason": exits[-1][2] if exits else "none",
        "hold_secs": exit_ts - entry_ts,
        "exit_ts": exit_ts,
        "exits": exits,
        "exit_events": events,
        "n_exit_events": len(events),
    }
