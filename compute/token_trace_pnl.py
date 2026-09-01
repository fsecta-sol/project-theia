#!/usr/bin/env python3
"""Token-level trace table: for the top whale-buys, fetch Birdeye 1m OHLCV
(entry price at whale buy ts, price 30m later, price now), compute our copy
PnL (0.5 SOL notional, T+30m entry, 30m hold, costs charged) and mcap at
entry/exit (price * supply from the RPC, supply already known for top 12).

Data: whale buy events from _token_trace.json agg (real SOL legs only).
Price source: Birdeye token_ohlcv via theia-birdeye MCP (browser-free, cached
5m in wallet_cache/ohlcv as bird_<mint>_now_24h.json — wallet_common ladder).
Bounded: 12 mints, 1 fetch each.
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")
sys.path.insert(0, "/home/hermes/.hermes/profiles/theia/scripts")

from compute import costs, expectancy, gas_sim  # noqa: E402

NOTIONAL = 0.5
ENTRY_LAG = 30 * 60
HOLD_CANDLES = 30
TZ = timezone(timedelta(hours=7))

trace = json.load(open('compute/_token_trace.json'))
agg = trace['agg']       # "whale:mint" -> {sol, n, first_ts, qty}
supply = trace['supply_top12']
WSOL = "So11111111111111111111111111111111111111112"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DEPLOY = Path.home() / ".hermes/theia/mcp"
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")
wc = load("wc", Path.home() / ".hermes/profiles/theia/scripts/wallet_common.py")

# top by SOL spent
rows = []
for key, a in agg.items():
    w, mint = key.split(':', 1)
    rows.append((w, mint, a))
rows.sort(key=lambda r: -r[2]['sol'])

print(f"{'whale':<5} {'mint':<11} {'SOLout':>6} {'mcap@buy':>10} {'mcap@copy':>10} {'mcap@exit':>10} "
      f"{'PnL(copy)':>9} {'now/buy':>7}")
results = []
for w, mint, a in rows[:12]:
    try:
        candles, src = wc.ohlcv_for(dexdata, birdeye, mint, before_ts=0, ttl=300)
    except Exception as e:
        print(f"  {mint[:10]} fetch err {type(e).__name__}")
        continue
    if not candles or len(candles) < 5:
        print(f"  {mint[:10]} no candles (src={src})")
        continue
    sup = (supply.get(mint) or {}).get('uiAmount') or 0
    dec = (supply.get(mint) or {}).get('decimals') or 6

    def at(ts):
        for r in candles:
            if r[0] >= ts:
                return r
        return None

    buy_ts = a['first_ts'] or 0
    buy_c = at(buy_ts)
    if not buy_c or buy_c[4] <= 0:
        continue
    # SOL price for USD mcap
    try:
        usd = wc.sol_usd(dexdata)
        if not (50 <= usd <= 250):
            usd = 150.0
    except Exception:
        usd = 150.0
    mcap_at_buy = buy_c[4] * sup * usd
    copy_c = at(buy_ts + ENTRY_LAG)
    if not copy_c or copy_c[4] <= 0:
        continue
    mcap_at_copy = copy_c[4] * sup * usd
    fwd = [r for r in candles if r[0] > copy_c[0]]
    exit_c = fwd[min(HOLD_CANDLES, len(fwd) - 1)] if fwd else None
    if not exit_c or exit_c[4] <= 0:
        continue
    mcap_at_exit = exit_c[4] * sup * usd
    pnl = (exit_c[4] / copy_c[4] - 1.0) * NOTIONAL
    slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
    cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip
    pnl_net = pnl - cost
    last = candles[-1][4]
    now_vs = last / buy_c[4] - 1.0 if buy_c[4] > 0 else 0
    print(f"{w:<5} {mint[:9]:<11} {a['sol']:>6.1f} {mcap_at_buy:>10,.0f} {mcap_at_copy:>10,.0f} "
          f"{mcap_at_exit:>10,.0f} {pnl_net:>+9.3f} {now_vs:>+7.1%}")
    results.append({"whale": w, "mint": mint, "sol": a['sol'], "src": src,
                    "mcap_buy": mcap_at_buy, "mcap_copy": mcap_at_copy,
                    "mcap_exit30m": mcap_at_exit, "pnl_copy_net": pnl_net,
                    "now_vs_buy": now_vs})

print("\n== aggregate copy PnL (12 top whale-buys, T+30m entry, 30m hold, net costs) ==")
pnls = [r['pnl_copy_net'] for r in results]
if pnls:
    m = expectancy.evaluate(pnls)
    print(f"  n={m['n']} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
          f"win={m['win_rate']:.2f} total={m['total']:+.3f}")

json.dump(results, open('compute/_token_trace_pnl.json', 'w'), indent=1, default=str)
print("\nsaved _token_trace_pnl.json")