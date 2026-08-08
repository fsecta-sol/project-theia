---
name: theia-xscraper
description: >
  Gather intelligence from X.com (profile stats, tweets, timelines) to discover
  whale wallets, track smart-trader narratives, and surface memecoin sentiment —
  the information edge. Keyless for profiles; cookie-auth optional for full search.
  Call BEFORE screening a token to enrich the candidate with social context.
---

# Theia — X.com Intelligence Gathering

No advantage in speed, capital, or insider info — but we CAN beat the market by being
**better informed**. Many memecoin plays start as a tweet from a known trader, or a
wallet that called the last 3 runners. This skill teaches Theia when and how to mine
that signal.

## When to use this skill

| Trigger | What to do |
|---------|------------|
| New token discovered (DEX) | Look up the deployer's X profile — any credibility? |
| Whale wallet identified (Birdeye) | Get their X handle + recent tweets — what are they talking about? |
| Trader caught a 10x (Birdeye top_traders) | Check their profile + timeline — do they post entries? |
| Market regime shifts | Search for "solana memecoin" sentiment |
| Before entering a paper trade | Scan X for rug warnings on the mint address or ticker |
| Weekly review | Aggregate: which 5 accounts were most right this week? |

**Do NOT** scrape X.com for generic "alpha" or idle browsing. Every hit costs quota.
Theia learns by connecting **on-chain signals to social identity** — use X to close
the loop between a wallet address and a human reason to trade.

## Procedure

### 1. Profile lookup (always available, keyless)

`theia-xscraper.profile_lookup(username)` → display_name, bio, followers.

Use this **first** on any new username/handle. Cache is 5min — re-lookups are free.

```python
profile = theia-xscraper.profile_lookup("blknoiz06")
# { "ok": true, "display_name": "Ansem 🐂🀄️ (@blknoiz06)", "bio": "..." }
```

If `ok` is false, the profile is suspended, deleted, or rate-limited. Record that fact.

### 2. Rich user resolution (needs cookie auth — Phase 2)

`theia-xscraper.user_by_login(username)` → id, followers, following, description, created.

More detail than profile_lookup. Falls back to profile_lookup if cookies missing.

```python
user = theia-xscraper.user_by_login("blknoiz06")
# { "id": "123456", "followers": 520000, "description": "..." }
```

### 3. Timeline scraping (needs cookie auth)

`theia-xscraper.user_tweets(username, limit=10)` → recent tweets with text, likes, retweets.

Use to answer: *what is this trader talking about right now?* Cache 5min — backtest runs
may replay from cache without hitting the API again.

```python
timeline = theia-xscraper.user_tweets("blknoiz06", limit=5)
# { "found": 5, "tweets": [{ "id": "...", "text": "...", "likes": 42, ... }] }
```

### 4. Keyword search (needs cookie auth for full results)

`theia-xscraper.search_tweets(query, limit=10)` → tweets matching keyword.

Limit this to **2-3 searches per screening cycle**. Cache 2min — use the cache during
backtest replay so you don't burn quota on repeated queries.

```python
result = theia-xscraper.search_tweets("solana memecoin", limit=10)
```

Without cookies, falls back to keyless HTTP (may return 0 tweets — JS-rendered page).

## Connecting X to on-chain

The real edge: **linking a tweet to a wallet**.

```
Birdeye top_traders(token) → wallet address
  → theia-xscraper.profile_lookup(find_handle_from_wallet)
  → theia-xscraper.user_tweets(handle)
  → theia-chainrpc.wallet_swaps(wallet)  # verify they actually traded
  → Record in theia-store as an "informed trader" note
```

A wallet that tweeted about a token BEFORE it pumped + has on-chain history of buying it
early → this is signal Theia can use.

## Budget management

| Operation | Cost (per call) | Cache TTL | Max/day (safe) |
|-----------|-----------------|-----------|----------------|
| profile_lookup | free (keyless) | 5min | ~200 |
| user_by_login (cookie) | 1 API hit | 10min | ~50 |
| user_tweets (cookie) | 1 API hit | 5min | ~30 |
| search_tweets (cookie) | 1 API hit | 2min | ~15 |

Stay under 100 total X API hits/day. The `theia-xscraper.health()` tool reports
cookie auth status and available tools.

## Guardrails

- **No user contact.** Theia reads public tweets only — no DMs, no posts, no follows.
- **No speculation from tweet text.** A tweet is a *hint*, not a trade signal. Always
  pair with on-chain verification (`theia-chainrpc.wallet_swaps`, Birdeye PnL).
- **Cookie auth is optional.** Without it, profile_lookup still works for discovery.
- **Cache everything.** The server already caches at the boundary. When backtesting,
  replay from cache — don't re-scrape X for historical data.
- **Surface anomalies.** If a known trader deletes their account, changes handle, or
  goes silent → flag it as a market signal, not an error.
