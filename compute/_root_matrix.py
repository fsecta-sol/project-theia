#!/usr/bin/env python3
"""Compose the root-trace picture + quantify the operator network.

Findings to check:
  - HF3s (suqh's funder): FUNDS BOTH suqh (61 SOL out) AND 2fg5 (224.4 SOL out),
    and is funded by F1ZLkFyTnz (+688.9). Bidirectional with F1ZLkFyTnz (199.8 out
    back). It's an operator hub serving at least TWO of our whales.
  - 9u7y <-> 2fg5: closed 2-node loop (2fg5 sent 1,770.5 in, 9u7y sent 3,787.5
    back) — pure self-shuffling, no external origin visible in 3k txs.
  - 8LR8 <-> 6G8: closed loop as well (6G8→8LR8 1,233.7; 8LR8→6G8 1,690.3).
  - HF3s' own funder F1ZLkFyTnz = the next root candidate; HF3s' oldest tx is
    May 8 — a LONG-lived wallet (not a temp).
Output: funded-by matrix + loop detection + next-root candidate.
"""
import json
from collections import defaultdict

r1 = json.load(open("/home/hermes/project-theia/compute/_root_trace.json"))
r2 = json.load(open("/home/hermes/project-theia/compute/_root_trace2.json"))

def ts(x):
    import datetime
    if not x:
        return "?"
    return datetime.datetime.fromtimestamp(
        x, datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M")

short = lambda a: a[:10]

print("== ROOT-TRACE PICTURE ==")
print()
print("whale -> initial funders (from whale's own history):")
for tag in ("suqh", "2fg5", "ardin", "6G8"):
    d = r1[tag]
    print(f"  {tag:<6} first_seen={ts(d['first_ts'])} funders={list(d['funders'].keys())[:3]}")
print()

# operator matrix: who sends to whom
edges = defaultdict(float)
def add(a, b, amt):
    edges[(a, b)] += amt

# from whale root trace
suqh = r1["suqh"]; two = r1["2fg5"]; g6 = r1["6G8"]; ard = r1["ardin"]
# suqh flows
add("HF3s", short("suqh5sHtr8"), suqh["funders"].get(
    "HF3s85NVgpVXQLtL94RWXUhxegViFRdaNxZ12WQBtpi8", 0))
add(short("suqh5sHtr8"), "ExzT1wYj", suqh["outbound"].get(
    "ExzT1wYj2E9ywpE8Sa83F7tJxYHDKbToBBMMJu5dS8ru", 0))
# 2fg5 <-> 9u7y loop
add("9u7y", short("2fg5QD1eD7"), two["funders"].get(
    "9u7yHBjxWCZpDsGnCSpQbp4VQmyMu68eY47Zx6T8jNSZ", 0))
add(short("2fg5QD1eD7"), "9u7y", two["outbound"].get(
    "9u7yHBjxWCZpDsGnCSpQbp4VQmyMu68eY47Zx6T8jNSZ", 0))
# 6G8 <-> 8LR8 loop
add("8LR8", short("6G8Cu53PRg"), g6["funders"].get(
    "8LR8ECxm4ZC7DravqL9c5qoev91vyM3MkAcfwjsymfHB", 0))
add(short("6G8Cu53PRg"), "8LR8", g6["outbound"].get(
    "8LR8ECxm4ZC7DravqL9c5qoev91vyM3MkAcfwjsymfHB", 0))
# HF3s deep trace (r2)
hf = r2.get("HF3s(funder suqh)", {})
for f, v in hf.get("funders", {}).items():
    add(short(f), "HF3s", v)
for o, v in hf.get("outbound", {}).items():
    add("HF3s", short(o), v)

print("FLOW MATRIX (SOL, >0.5):")
for (a, b), v in sorted(edges.items(), key=lambda kv: -kv[1]):
    if v >= 0.5:
        print(f"  {a:<10} -> {b:<10} {v:>10.1f}")
print()
# who funds MULTIPLE whales/operator nodes?
funders_of = defaultdict(set)
for (a, b), v in edges.items():
    if v >= 1:
        funders_of[a].add(b)
multi = {a: bs for a, bs in funders_of.items() if len(bs) >= 2}
print("FUNDERS that touched >=2 nodes (operator candidates):")
for a, bs in sorted(multi.items()):
    print(f"  {a:<10} -> {sorted(bs)}")
print()
loops = [(a, b) for (a, b) in edges if (b, a) in edges and edges[(b, a)] > 0.5]
print("CLOSED LOOPS (bidirectional >=0.5 SOL both ways):")
for a, b in loops:
    print(f"  {a} <-> {b}: {edges[(a,b)]:.1f} / {edges[(b,a)]:.1f}")
