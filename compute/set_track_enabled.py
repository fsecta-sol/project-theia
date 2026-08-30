#!/usr/bin/env python3
"""Set pipeline tracking to the 6 verified smart wallets only.

Verified = win_rate >= 0.60 AND (PF > 1 from own swaps, or GMGN-tracked).
Others (churn bots, no round-trip data, inactive) get track_enabled=0 so the
pipeline stops polling them and their noisy signals.
"""
import sqlite3
from pathlib import Path

DB = Path.home() / ".hermes/theia/theia.db"

VERIFIED = {
    "2La7jt812VSqmQfLvNkdd8VCjCEzCKyai6NGsmEsTeTK",  # dex_trending win 0.71 PF 6.4
    "5YjAceHCD8t8XQRUhezWSXJxqxTphPfh2g6j1E1eEuGV",  # dex_trending win 0.65 PF 41
    "9hZSW1HbZdjDPSysFfjuPUGQGyDA2FnPjyrdskxCwGTJ",  # dex_trending win 0.60 PF 11
    "AE4MPGvpMeCA7MwUakAxAQZTzcijPAXcFsoAQmtLrL4V",  # gmgn_winrate win 0.97 PF 1.27
    "4j81GXrMf7njGXAyL92YdchWDkrmJXuWS6UJdtyQ6bTV",  # gmgn_winrate win 0.73 PF 0.54
    "77Uy6sLLggDg9ZB7Yu7xbtCShVTVvJsVNrPdyQFjLVD5",  # gmgn_winrate win 0.64 PF 0.13
}

con = sqlite3.connect(DB)
con.execute("UPDATE wallet_profiles SET track_enabled=0")
n = 0
for w in VERIFIED:
    cur = con.execute("UPDATE wallet_profiles SET track_enabled=1 WHERE wallet=?", (w,))
    n += cur.rowcount
con.commit()

print(f"track_enabled=1: {n} wallets")
print("remaining smart wallets now:")
for r in con.execute(
        "SELECT substr(wallet,1,12), source, round(win_rate,2), track_enabled "
        "FROM wallet_profiles WHERE is_smart_money=1 ORDER BY track_enabled DESC, win_rate DESC"):
    print(f"  {r[0]:<14} {r[1][:18]:<20} win={r[2] if r[2] is not None else 0:>5} track={r[3]}")
con.close()