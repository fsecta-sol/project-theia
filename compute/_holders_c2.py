#!/usr/bin/env python3
"""C2 analysis redo: usable early-holder features given snapshot depth (~10-13
holders per mint makes top10_share degenerate). Test: total_usd (early dollar
interest), n_holders (snapshot depth = early breadth), mean holder size."""
import json

d = json.load(open("compute/_holders_rug.json"))
feats = d["features"]
outs = d["outcomes"]
common = {m: outs[m] for m in outs if m in feats}
print("labeled+featured:", len(common))


def pct(name, keyfn, buckets):
    print(f"\n== {name} ==")
    print(f"{'bucket':<16} {'n':>4} {'rug%':>6} {'surv%':>6} {'mid%':>6}")
    for lo, hi in buckets:
        grp = [m for m in common if lo <= keyfn(feats[m]) < hi]
        n = len(grp)
        if not n:
            continue
        rug = sum(1 for m in grp if common[m] == "rug") / n
        surv = sum(1 for m in grp if common[m] == "survived") / n
        mid = sum(1 for m in grp if common[m] == "mid") / n
        print(f"  {str(lo)}-{str(hi):<12} {n:>4} {rug:>6.0%} {surv:>6.0%} {mid:>6.0%}")


pct("total_usd (early $ interest)", lambda f: f["total_usd"],
    [(0, 200), (200, 500), (500, 1500), (1500, 5000), (5000, 1e12)])
pct("n_holders (early breadth)", lambda f: f["n_holders"],
    [(1, 5), (5, 10), (10, 11), (11, 12), (12, 99)])
pct("mean holder size", lambda f: f["mean_usd"],
    [(0, 20), (20, 50), (50, 120), (120, 1e12)])
