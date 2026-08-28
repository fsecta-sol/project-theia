# OpenDesign Prompt — Add Detail to the “Positions” Menu

Modify ONLY the **Positions** menu of the existing Theia dashboard.

## Context

`theia-dashboard.html` is the main dashboard artifact. The dashboard already has the shell,
sidebar, topbar, dark/light theme, i18n EN/ID/JP, and a **Positions** menu (`view-v5`).
Do not change the look or behavior of any other menu: Overview, Pipeline, Wallets, Screening,
Edge Lab, Knowledge, and Ops must stay exactly as they are.

The current Next.js implementation lives in:

- `dashboard/src/components/views/PaperPositions.tsx`
- `dashboard/src/app/AppShell.tsx` (`view-v5` renders `PaperPositions`)
- `dashboard/src/lib/types.ts`
- `dashboard/src/lib/data.tsx`
- The existing API, if the payload actually supports it: `/api/pipeline`

Do not invent endpoints, numbers, tokens, prices, mcaps, timestamps, or trades. If data is not
yet available from an API/source table, show an honest empty state and leave clear placeholder
hooks for a future payload.

## Goal

Turn the **Positions** menu from a “Phase 5 locked” placeholder into a detailed paper-trade
ledger. This page must become the primary place to answer:

- which token was entered;
- when the signal appeared and when the simulated entry happened;
- the token price at entry;
- the market cap at entry;
- the position size in SOL;
- which wallet triggered the entry;
- the entry reason / rule;
- the safety screening result;
- the stop-loss and targets;
- the simulation costs;
- the position status and exit result.

Keep the **paper only** principle. No signing keys and no real transactions.

## Views to build

### 1. Header and summary

Keep the dashboard's existing design language: same panels/cards, same borders and radii,
mono numerals, `.hint`, status pills, and the status colors already in use.

Add a header with:

- title: `Paper Positions & Entry Journal`;
- a `paper only` status;
- a `last updated` timestamp from the payload;
- a scope control: `Open · All · Last 24h`;
- summary cards:
  - open positions;
  - entries today;
  - parked/blocked signals;
  - realized net PnL, only if that data actually exists.

If there are no fills yet, do not show synthetic numbers. Use `—`, `0`, or an empty state as the
field's meaning requires, and explain `No paper fills recorded yet`.

### 2. Detailed entry/position table

Build a responsive table with one row per paper entry. Minimum columns:

- `Token`: symbol/name if available + a copyable mint address;
- `Signal ts`;
- `Entry ts`;
- `Latency` between signal and entry;
- `Entry price`;
- `Entry mcap`;
- `Size SOL`;
- `Trigger wallet`;
- `Wallet score` or the wallet metrics that actually exist;
- `Hypothesis / rule`;
- `Screen` (`pass`/`veto`);
- `Stop`;
- `TP1`, `TP2`, `TP3`;
- `Current price` and `unrealized PnL %` for open positions;
- `State`: `open`, `parked`, `blocked`, or `closed`.

Never use a time countdown as the primary entry/hold logic. Show price, market cap, price
action, volume/liquidity, and guard status when available.

### 3. Entry rationale detail

Every row with status `open`, `closed`, or `parked` must have a detail affordance
(expandable row, drawer, or small modal). The detail must show:

- the trigger wallet and why it qualified;
- signal time and signal age at entry;
- the rule/hypothesis ID and rule name;
- the price-action/mcap entry condition, if available;
- mcap and price at signal time and at entry;
- the volume/liquidity used;
- the safety veto result: honeypot, tax, mint/freeze authority, LP, top-10 share, wash/rug score;
- the reason if parked/blocked;
- the source table/API for each data group;
- the snapshot of inputs used for the simulated fill.

Use explicit copy when a field is not yet available, e.g.:
`Entry rationale unavailable — source payload has not recorded it yet.`
Never fill the reason with generic text that pretends to come from real data.

### 4. Open position card

For open positions, show a scannable card/summary:

- token and mint;
- entry price / mcap;
- current price / mcap;
- unrealized PnL %;
- stop distance;
- target distance;
- guard status based on conditions: price, dip, target, trailing state, or liquidity state;
- last monitor timestamp;
- wallet/hypothesis trigger.

If there are no open positions, show `0 open positions` and explain whether the cause is that
no fills exist yet or that data is unavailable.

### 5. Closed/archived trades

Add a history section for exits or archives with:

- token;
- entry ts and exit ts;
- entry price / exit price;
- entry mcap / exit mcap if available;
- hold duration;
- gross PnL;
- gas/priority fee;
- slippage;
- net realized PnL;
- ROI;
- `exit_reason`: stop, TP, trail, time stop, or whatever the payload actually contains;
- rule/hypothesis and trigger wallet.

Net PnL must be shown as the result of compute/source data, never a manual calculation in the UI.
If the cost data components do not exist yet, show `cost data pending` instead of an estimate.

### 6. Data contract and placeholder hooks

Use explicit types for the Positions payload. Reuse existing types/helpers where possible.
Never fake local data such as `SCREENED_TOKENS` as paper entries.

You may provide a documented placeholder interface, for example conceptually:

```ts
interface PositionsPayload {
  fetchedAt: number;
  positions: PaperPosition[];
  archives: ArchivedTrade[];
  summary: {
    open: number;
    entries24h: number;
    parked: number;
    blocked: number;
    realizedNetPnlSol: number | null;
  };
}
```

Final field names must follow the API/source tables that actually exist in the repository.
If no endpoint exists yet, the component must still build and show a no-data state without making
a fictional request. Leave TODO comments naming the payload/tables needed.

The preferred data sources are the real tables:
`paper_trades`, `archives`, `wallet_signals`, `screens`, `price_snapshots`, and the wallet
profile data the pipeline already uses. Do not add databases or external services.

### 7. Interaction and responsive behavior

- copy mint address;
- expand/collapse the entry rationale detail;
- filter by state: open/parked/blocked/closed;
- hover/focus states consistent with the dashboard;
- keyboard-accessible controls and rows;
- horizontal table scroll on tablet;
- stacked cards/timeline on mobile;
- tooltips on fields whose source or meaning is not self-evident;
- graceful stale/no-data states with `last updated`.

## Hard rules

1. Change only the Positions menu and the small styles strictly required by it.
2. Do not modify Pipeline, Screening, Sidebar, or other phase statuses.
3. Do not remove the paper-only principle.
4. Do not invent paper entries or PnL results.
5. Never call something an “entry” if it is only a signal, parked, or vetoed.
6. Entry rationale must be traceable to the wallet signal, hypothesis/rule, screening, and price
   snapshot.
7. Every amount, price, mcap, latency, PnL, fee, and slippage must come from the payload/backend
   or a reconstructable compute artifact.
8. If Phase 5 is still locked in the source of truth, do not fake positions; show an informative
   locked/no-data state and prepare the UI for when data arrives.
9. Keep i18n. Default artifact copy must be natural English; add ID/JP only if the current i18n
   structure supports it.
10. If the task asks for an OpenDesign artifact, do not output Next.js snippets as the main
    deliverable. The final result must be one complete HTML artifact with the old dashboard fully
    intact, only the Positions view changed, plus a short rationale.

## Acceptance criteria

- The Positions menu opens and is clearly the home of paper-entry details.
- When the payload exists, the user can see token, entry time, price, mcap, size, trigger wallet,
  rule, and status.
- The user can open the entry rationale for each position.
- Open and archived trades are clearly separated.
- Fees, gas, slippage, and net PnL are never hardcoded or casually computed.
- No-data/stale states are honest and do not fabricate activity.
- No visual/functional regression in other menus.
- The artifact stays responsive, accessible, and consistent with the existing design language.

## Output

One updated OpenDesign HTML artifact containing the full existing dashboard, with only the
Positions menu changed, plus a short rationale of what changed in that view. Do not output
Next.js code as the main deliverable; slicing into Next.js happens later.
