---
name: theia-learn-solana
description: Deepen Theia's Solana mechanics knowledge by researching a topic, verifying every claim against a source, auto-discovering related concepts (red-string graph), and dropping a sourced input into the vault inbox. Use when Theia has idle/API-free budget or a mechanic a hypothesis depends on is not yet documented.
---

# Theia — Learn Solana (feed the second brain + auto-discovery)

Build compound understanding of Solana mechanics. This is API-free work: run it whenever
discovery/screening is rate-limited or a hypothesis needs a mechanic that isn't documented yet.

## Rule (grounding)

Every claim needs a **source** (docs URL, an on-chain tx, an API response) and must answer
**why**, not just what. A claim you cannot source or explain is not written — flag it
`[NEEDS-SOURCE]` / `[NEEDS-WHY]`.

## Procedure

### 1. Pick or auto-discover the next topic

**Auto-discovery (red strings):**
- Query `theia-store.get_knowledge_links(note, direction='both')` for the current seed topic.
- If links exist, pick the highest-confidence unseen topic as next target.
- If no links, run deterministic auto-scrape:
  ```python
  from compute.knowledge_graph import fetch_and_discover
  result = fetch_and_discover("AMM", "https://docs.meteora.ag/dlmm", known_notes=[...])
  ```
  This returns related concepts (e.g., DLMM, Orca, concentrated liquidity) with confidence scores.
- Persist discovered links: `theia-store.add_knowledge_link(from_note, to_note, link_type='related', source=url, confidence=score)`.
- The graph now auto-grows: AMM → DLMM → Meteora → bin-based pricing → ...

### 2. Research the topic
- Web + on-chain examples via `theia-chainrpc`/`theia-dexdata`.
- Capture 2–3 independent sources.
- While reading, scan for **new red strings** (related concepts not yet in the vault).
  If found, immediately `add_knowledge_link(...)` so the graph stays connected.

### 3. Write sourced input
- Concise input file into the vault inbox: `00-Inbox/_knowledge/<topic-slug>.md`.
- Bullet the mechanism, the *why*, and cite sources.
- Include a **"Related Concepts"** section listing red-string links discovered.
- Do **not** write into `03-Areas/concepts/` directly — that is the curator's job.

### 4. Index and link
- `theia-store.index_note(note_path, topic, status='draft', sources=[...])`.
- For each related concept found, `add_knowledge_link(note_path, related_note, link_type, source, confidence)`.

### 5. Auto-crawl trigger
- After indexing, check: are there high-confidence (>0.6) related topics not yet covered?
- If yes and API budget is free, auto-queue a `theia-learn-solana` task for that topic
  via `theia-store` task queue (type='learn', payload={'topic': ...}).

## Curriculum (seed order)

```
1 Solana fundamentals   account model · SPL token · PDA · CU & fees · slots/finality
2 DEX & swap mechanics   Raydium CPMM/CLMM · Jupiter routing · pump.fun bonding curve
3 Token lifecycle        creation · launch · mint/freeze authority · LP · graduation
4 Failure modes          rug · honeypot · wash trade · sniper/MEV
```

The graph is **not** limited to this curriculum — auto-discovery can branch to any Solana
concept found in docs (e.g., DLMM, governance, NFT standards).

## Budget

| Operation | Cost | Frequency |
|-----------|------|-----------|
| knowledge_graph.fetch_and_discover | 1 HTTP GET | per new seed topic |
| add_knowledge_link | DB write (free) | per red string found |
| get_knowledge_links | DB read (free) | per learn cycle |

Escalate to the human when a mechanic materially changes a strategy assumption.
