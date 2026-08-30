# OpenDesign Prompt — Upgrade the "Wallets" Menu with a Discovery Analytics Visualization

## Context

Theia is a paper-trading research dashboard for the Solana memecoin market. The existing
dashboard (`theia-dashboard.html`) already has a complete shell: sidebar, topbar, dark/light
theme, i18n structure (EN default, ID/JP supported), and these menus: **Overview, Pipeline,
Wallets, Positions, Screening, Edge Lab, Knowledge, Ops**.

This task changes **ONLY the Wallets menu**. Everything else must stay exactly as it is.

The Wallets menu currently shows a **smart-wallet roster**: a table of candidate wallets with
their win rate, PnL, trade counts, tags, PnL distribution, and a watched/filtered/discarded
state, plus a wallet-detail view. **Keep that roster intact.** This task *extends* the menu
with a new visualization section: the **discovery scan history**.

## Important: use SAMPLE / DUMMY DATA

This is a **design mockup** — you do NOT need real data and you must NOT try to fetch or
compute anything. Fill the design with **realistic-looking sample values** (plausible wallet
addresses, percentages, counts, timestamps), and make it **visually obvious that it is sample
data** (e.g. a small `sample data` pill in the section header, a footnote, or a dashed outline
on the panel). Never present the mock values as live production numbers.

You do not need to know where the real data will come from. All you need is the data *meaning*
below so the design is self-explanatory.

## What the data means (plain language)

Every hour the system scans ~250 candidate wallets from a smart-money leaderboard. Each scan
captures, per wallet:

- **Identity**: wallet address, nickname / X handle if known.
- **Performance 7d**: win rate, realized PnL, total volume, number of trades (buys/sells),
  average holding time (hours).
- **Performance 30d**: win rate (consistency check).
- **PnL distribution** — 5 buckets of past trades: `>5x`, `2–5x`, `<2x`, `−0.5–0x`, `<−0.5x`
  (the "shape" of the wallet's wins/losses).
- **Tags** (e.g. `kol`, `photon`, `top_followed`, `bot`, `wash_trader`).
- **Gate verdict**: `pass` or `fail`, with a short reason such as:
  - `win rate 7d too low` (e.g. 0.51 < 0.60)
  - `win rate 30d too low`
  - `too few trades` (e.g. 37 < 150)
  - `holding too long` (e.g. 134h)
  - `flagged wash_trader / bot`

Only wallets that pass all criteria become **tracked**.

## Goal

Design a **"Scan History / Discovery Analytics"** section inside the Wallets menu that makes it
easy to answer, at a glance:

1. How many wallets were scanned each hour, and how many passed the gate?
2. Where in the funnel do wallets get rejected, and why?
3. Which wallets are currently tracked, and what are their latest metrics?
4. How does a single wallet's metrics evolve across scans (does it improve or degrade)?
5. (Nice to have) How would the pass rate change if a threshold were relaxed/tightened?

## Views to design (all inside the Wallets menu)

### 0. Menu structure
Add a tab row in the Wallets menu: **Roster** (the existing table — unchanged) and
**Scan History** (the new section). The Scan History tab holds everything below.

### 1. Section header + summary + time filter
- Title: `Wallet Discovery — Scan History`; subtitle: `hourly scan · smart-money leaderboard`.
- A `sample data` pill + `paper only` pill.
- **Time range filter: `24h · 7d · 30d · all`** — this filter must visually apply to every
  view below (charts, funnel, table, histograms all respond to it).
- Summary cards: scans total, unique wallets, latest run scanned / passed, tracked count,
  wallets flagged as wash/bot.

### 2. Scan run-over-time chart
- Line/area chart, x = scan time (hourly), y = count, two series: **scanned** and **passed**.
- If an hour is missing (gap), show the gap honestly on the axis (e.g. dashed segment).
- Hover tooltip per point: run time, scanned, passed, fail, top reject reasons.

### 3. Gate funnel + reject reason breakdown
- Funnel with the real gate stages and labels: `scanned → tag-clean → win rate 7d ≥ 0.60 →
  win rate 30d ≥ 0.50 → trades ≥ 150 → holding < 48h → passed`.
- Beside it, a donut/bar of **reject reasons** over the selected range (win rate / trades /
  holding / wash-bot tag), with counts.

### 4. Wallet scan ledger (the main table)
- One row per (wallet, scan) within the range. Columns: wallet (short address + copy button),
  scan time, win rate 7d, win rate 30d, trades (buys/sells), holding (h), volume 7d, realized
  PnL 7d, tags (veto tags visually struck through), gate pill (pass/fail), reject reason.
- Sortable columns; filter by gate (pass/fail), by tag, by free text.
- Pagination (many rows — never render thousands at once).
- The same wallet appearing in multiple scans = separate rows, but visually grouped/colored by
  wallet so the eye can follow one wallet over time.

### 5. Wallet detail drawer
Clicking a wallet row opens a drawer with:
- **Time series across scans**: win rate 7d/30d, trades, realized PnL over time (small sparkline
  or mini chart) — shows whether the wallet is improving or degrading.
- Latest snapshot vs first-seen snapshot (delta arrows).
- **Gate history**: pass/fail flips over time.
- **PnL distribution** (5 buckets) rendered as bars.
- Note that the values are sample data.

### 6. Threshold sensitivity panel (nice to have, read-only)
- Small panel: "if the 7d win-rate threshold were 0.55 / 0.60 / 0.65 / 0.70, N wallets would
  pass" — computed from the sample dataset and clearly labeled `sensitivity · sample data`.
- Histograms of win rate, trades, and holding time across the range.

## Design rules

1. Keep the dashboard's existing design language exactly: same panels/cards, borders and radii,
   mono numerals, `.hint` text, status pills, status colors, provenance markers
   (`◆ provider` / `= compute` style) already in use. The new section must look native.
2. Change **only the Wallets menu** and the small styles strictly required by it. Do not touch
   Overview, Pipeline, Positions, Screening, Edge Lab, Knowledge, or Ops.
3. Dark/light theme aware; responsive: horizontal table scroll on tablet, stacked cards on
   mobile.
4. Interactions: hover states, focus states, sortable headers, filterable table, copyable
   address, tooltips on fields whose meaning is not self-evident, expandable drawer.
5. Sample data must be clearly labeled as sample — never styled as authoritative production
   numbers.
6. Honest empty states (e.g. `no scans in this range`) — do not fill gaps with fake activity.
7. i18n: default copy in natural English; keep the existing i18n pattern (ID/JP optional).

## Output

**One complete OpenDesign HTML artifact** containing the full existing dashboard with **only
the Wallets menu upgraded** (roster kept, Scan History section added), plus a short rationale
of what changed in that view. Do not output code snippets, frameworks, or backend logic as the
deliverable — this is a visual design, ready for a coding agent to wire up later.

## Acceptance criteria

- The Wallets menu shows the new **Scan History** tab next to the existing Roster, and the
  roster still works as before.
- All six views render with realistic sample data; the time filter visibly applies across
  charts, funnel, and table.
- The design reads as a native part of the dashboard (same design language), responsive and
  accessible.
- No visual/functional regression in any other menu.
- The rationale explains what was added and which parts use sample data.
