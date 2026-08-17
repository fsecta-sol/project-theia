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

### 1. Pick the next topic

**First boot (seed mode):**
- Read `SEED_QUESTIONS.md` from the vault via `theia-obsidian`.
- If it exists and has unanswered questions: pick the next question, run one learn cycle.
- After all 10 questions are answered: rename the file to `SEED_QUESTIONS_DONE.md` (auto-discovery takes over).

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
- **All web fetch goes through `theia-webscraper`** (single gate):
  - `theia-webscraper.fetch_page(url)` — tiered: curl_cffi (fast) → StealthyFetcher (CF bypass)
  - `theia-webscraper.extract_text(html)` — clean text extraction
  - `theia-webscraper.detect_protection(url)` — quick CF probe before heavy fetch
- On-chain examples via `theia-chainrpc`/`theia-dexdata`.
- Capture 2–3 independent sources.
- While reading, scan for **new red strings** (related concepts not yet in the vault).
  If found, immediately `add_knowledge_link(...)` so the graph stays connected.

### 3. Write sourced input (via theia-obsidian)
- Use `theia-obsidian` to create or append to the vault inbox.
   - If note does not exist: `theia-obsidian.write_note(path="00-Inbox/_knowledge/<topic-slug>.md", content=..., frontmatter={concept, type-hint, why-to-nail, sources, tags, note})` — **no `connects` field** (graph lives in `theia-store.knowledge_links`)
  - If note exists (red-string update): `theia-obsidian.append_to_note(path="00-Inbox/_knowledge/<topic-slug>.md", content=..., section="Related Concepts")`
- Bullet the mechanism, the *why*, and cite sources.
- Include a **"Related Concepts"** section listing red-string links discovered.
- Do **not** write into `03-Areas/concepts/` directly — the guard will deny it; that is the curator's job.

### 4. Index and link
- `theia-store.index_note(note_path, topic, status='draft', sources=[...])`.
- For each related concept found, `theia-store.add_knowledge_link(note_path, related_note, link_type, source, confidence)`.

### 5. Auto-crawl trigger
- After indexing, check: are there high-confidence (>0.6) related topics not yet covered?
- If yes and API budget is free, auto-queue a `theia-learn-solana` task for that topic
  via `theia-store` task queue (type='learn', payload={'topic': ...}).

## Budget

| Operation | Cost | Frequency |
|-----------|------|-----------|
| knowledge_graph.fetch_and_discover | 1 HTTP GET | per new seed topic |
| add_knowledge_link | DB write (free) | per red string found |
| get_knowledge_links | DB read (free) | per learn cycle |

When a mechanic materially changes a strategy assumption, escalate to the human via the Hermes channel:
```python
# Escalation via Hermes native delivery (cron job deliver target is set to telegram thread)
# The scheduler auto-delivers the full report; for urgent standalone pings use:
# hermes send --to "telegram:-1003928226918:644" "🚨 Strategy assumption changed by {topic}"
```
