import type { PhaseCellData, ExitCriterion, DigestLine, FunnelStage, ScreenedToken, BacktestWindow, Hypothesis, MCPServer, LLMShot, CronJob, ContextWindow, CostBar } from "./types";

export const PHASES: PhaseCellData[] = [
  { phase: 0, name: "Foundation & deploy", status: "done", statusLabel: "done" },
  { phase: 1, name: "Knowledge-first", status: "active", statusLabel: "current" },
  { phase: 2, name: "Discovery & screening", status: "locked", statusLabel: "locked" },
  { phase: 3, name: "Hypothesis & backtest", status: "locked", statusLabel: "locked" },
  { phase: 4, name: "Harness & guardrails", status: "locked", statusLabel: "locked" },
  { phase: 5, name: "Paper trade & monitor", status: "locked", statusLabel: "locked" },
  { phase: 6, name: "Scale via delegation", status: "locked", statusLabel: "locked" },
];

export const EXIT_CRITERIA: ExitCriterion[] = [
  { done: true, title: "10 seed questions answered, each with ≥ 1 source", sources: "4 answered · 3 partial · 3 unanswered", gate: true },
  { done: true, title: "Knowledge index versioned & synced to vault", sources: "obsidian · 2h ago" },
  { done: true, title: "Source attribution on every note", sources: "11 / 12 notes" },
  { done: false, title: "Auto-discovery link pass (weekly)", sources: "3 of 4 modules scanned" },
  { done: false, title: "All 10 seed questions fully sourced", sources: "3 remaining · needs-source" },
];

export const DIGEST_LINES: DigestLine[] = [
  {
    time: "00:00",
    text: <span>Scraped <b className="num">12,847</b> GMGN wallet profiles through the browser tier — Cloudflare let 3/4 probe cycles through. Harvest is the only stage at full volume.</span>,
  },
  {
    time: "00:40",
    text: <span>Filter collapsed harvest to <b className="num">473</b> wallets: <span className="num">9,842</span> had no real trade history, <span className="num">2,051</span> below the PnL floor. <span className="delta-flat">≈ yesterday</span></span>,
  },
  {
    time: "03:12",
    text: <span>Detected <b className="num">96</b> wallet buy signals; <span className="num">251</span> signals were stale by the ≤30 min latency budget and were dropped before screening.</span>,
  },
  {
    time: "04:05",
    text: <span>Safety veto held <b className="num">18</b> of 96: <span className="num">6</span> wash_trader, <span className="num">5</span> trade-count, <span className="num">4</span> liquidity gate, <span className="num">2</span> honeypot, <span className="num">1</span> rug-score. <b className="num">78</b> cleared the veto.</span>,
  },
  {
    time: "04:40",
    text: <span>Paper entry gate: <b className="num">78</b> signals parked at the phase gate — <span className="s s-locked">Phase 5 locked</span> — nothing entered, nothing exited. Expected behavior, not a fault.</span>,
  },
  {
    time: "05:20",
    text: <span>Knowledge: <b className="num">2</b> notes drafted, <span className="num">1</span> promoted to verified, <span className="num">12</span> machine-discovered links flagged for review.</span>,
  },
];

export const FUNNEL_STAGES: FunnelStage[] = [
  {
    seq: "01", name: "GMGN harvest", latency: "latency 24s · probe tier",
    barWidth: "100%", ct: "12,847", csub: "in",
    vd: "+6.2% in vs yday", vdClass: "delta-flat",
    drops: [{ label: "no drop at this stage" }],
  },
  {
    seq: "02", name: "Filter", latency: "latency 41s · compute",
    barWidth: "37%", ct: "473", csub: "out of 12,847",
    drops: [
      { bold: "9,842", label: "no real trade history" },
      { bold: "2,051", label: "below PnL floor" },
      { bold: "481", label: "activity too old" },
    ],
  },
  {
    seq: "03", name: "Buy signals", latency: "latency 6m 10s · on-chain match",
    barWidth: "23%", ct: "96", csub: "out of 473",
    vd: "−12% signals vs yday", vdClass: "delta-dn",
    drops: [
      { bold: "251", label: "stale signal (>30m)" },
      { bold: "82", label: "no on-chain buy match" },
      { bold: "44", label: "duplicate" },
    ],
  },
  {
    seq: "04", name: "Safety veto", latency: "latency 12s · security lib",
    barWidth: "21.5%", ct: "78", csub: "passed of 96",
    vd: "veto rate ≈ yesterday", vdClass: "delta-flat",
    drops: [
      { bold: "6", label: "wash_trader tag" },
      { bold: "5", label: "trade_count too low" },
      { bold: "4", label: "liquidity gate" },
      { bold: "2", label: "honeypot" },
      { bold: "1", label: "rug_score > threshold" },
    ],
  },
  {
    seq: "05", name: "Paper entry ≤ 30m", latency: "phase-gated",
    barWidth: "100%", ct: "78", csub: "waiting at gate",
    locked: true, locknote: "◌ Phase 5 locked",
    drops: [{ bold: "78", label: "phase gate: paper trading not enabled", gate: true }],
  },
  {
    seq: "06", name: "Exit", latency: "phase-gated",
    barWidth: "12%", ct: "0", csub: "trades",
    locked: true,
    drops: [{ label: "0 entered yesterday", gate: true }],
  },
  {
    seq: "07", name: "Archive", latency: "append-only ledger",
    barWidth: "12%", ct: "0", csub: "rows",
    locked: true,
    drops: [{ label: "empty until exits exist", gate: true }],
  },
];

export const SCREENED_TOKENS: ScreenedToken[] = [
  { addr: "SoLq…k1Mx", screen: 41, honeypot: "no", tax: "0.9 / 0.9", mint: "— / —", lp: "100%", top10: "34%", wash: 0.04, rug: 0.08, verdict: "pass", reason: "—" },
  { addr: "MeKp…7Qx2", screen: 37, honeypot: "yes", honeypotFail: true, tax: "9.8 / 22.4", taxFail: true, mint: "— / —", lp: "no", lpFail: true, top10: "68%", top10Fail: false, wash: 0.31, rug: 0.74, verdict: "veto", reason: "honeypot · sell_tax > 15%" },
  { addr: "Fr3y…wQp9", screen: 34, honeypot: "no", tax: "1.2 / 1.0", mint: "— / —", lp: "no", lpFail: true, top10: "91%", top10Fail: true, wash: 0.12, rug: 0.41, verdict: "veto", reason: "liquidity gate · top10_share > 85%" },
  { addr: "WdGe…8Tb4", screen: 29, honeypot: "no", tax: "0.8 / 0.9", mint: "— / —", lp: "100%", top10: "52%", wash: 0.86, washFail: true, rug: 0.63, verdict: "veto", reason: "wash_trader · wash_score > 0.8" },
  { addr: "GmVb…3Zq1", screen: 44, honeypot: "no", tax: "1.1 / 1.0", mint: "— / —", lp: "100%", top10: "41%", wash: 0.09, rug: 0.11, verdict: "pass", reason: "—" },
  { addr: "PxNv…9Lm4", screen: 23, honeypot: "no", tax: "2.4 / 3.1", mint: "— / —", lp: "100%", top10: "60%", wash: 0.22, rug: 0.52, verdict: "veto", reason: "rug_score > 0.5" },
];

export const BACKTEST_WINDOWS: BacktestWindow[] = [
  { label: "W1 · IS", n: 61, exp: "+0.42", pf: "1.31", win: "58%", maxdd: "−0.9" },
  { label: "W2 · IS", n: 74, exp: "+0.51", pf: "1.44", win: "61%", maxdd: "−0.6" },
  { label: "W3 · IS", n: 88, exp: "+0.27", pf: "1.18", win: "55%", maxdd: "−1.1" },
  { label: "W4 · IS", n: 97, exp: "+0.38", pf: "1.26", win: "59%", maxdd: "−0.8" },
  { label: "W5 · OOS", n: 92, exp: "+0.19", pf: "1.09", win: "54%", maxdd: "−1.3" },
];

export const HYPOTHESES: Hypothesis[] = [
  { id: "H-0003", title: "Follow verified-profitable wallets, ≤30m late", status: "backtesting", statusLabel: "backtesting", bestExp: "+0.51", bestPf: "1.44", bestWin: "61%" },
  { id: "H-0005", title: "Liquidity-gate veto (top10_share > 85%)", status: "promoted", statusLabel: "promoted", bestExp: "+0.12", bestPf: "1.07", bestWin: "52%" },
  { id: "H-0007", title: "Trailing-stop exit timing", status: "draft", statusLabel: "draft", bestExp: "—", bestPf: "—", bestWin: "—" },
  { id: "H-0008", title: "Wash-trade detection via wallet co-buy graph", status: "draft", statusLabel: "draft", bestExp: "—", bestPf: "—", bestWin: "—" },
];

export const MCP_SERVERS: MCPServer[] = [
  { server: "theia-store", status: "ok", tools: "4 / 4", rateLimit: "—", cacheHit: "—", notes: "local · main store" },
  { server: "chainrpc", status: "ok", tools: "5 / 5", rateLimit: "62%", cacheHit: "41%", notes: "helius · rpc" },
  { server: "dexdata", status: "degraded", tools: "3 / 4", rateLimit: "97%", cacheHit: "52%", notes: "1 tool unverified · rate-limited 3× today" },
  { server: "birdeye", status: "ok", tools: "4 / 4", rateLimit: "18%", cacheHit: "33%", notes: "price + ohlcv" },
  { server: "security", status: "ok", tools: "4 / 4", rateLimit: "9%", cacheHit: "88%", notes: "goplus · token checks" },
  { server: "xscraper", status: "degraded", tools: "3 / 3", rateLimit: "100%", cacheHit: "12%", notes: "cloudflare-gated · backoff engaged" },
  { server: "obsidian", status: "ok", tools: "3 / 3", rateLimit: "—", cacheHit: "—", notes: "vault sync · 2h ago" },
  { server: "webscraper", status: "ok", tools: "2 / 2", rateLimit: "24%", cacheHit: "19%", notes: "docs + pages" },
];

export const LLM_SHOTS: LLMShot[] = [
  { skill: "theia-learn", shots: 214, tokIn: "312k", tokOut: "41k", cost: "$0.96", policy: "allow", grounding: "cited", groundingStatus: "ok" },
  { skill: "task-runner", shots: 68, tokIn: "88k", tokOut: "12k", cost: "$0.58", policy: "allow", grounding: "cited", groundingStatus: "ok" },
  { skill: "journal", shots: 24, tokIn: "41k", tokOut: "9k", cost: "$0.21", policy: "allow", grounding: "uncited 3", groundingStatus: "warn" },
  { skill: "x-scraper", shots: 6, tokIn: "6k", tokOut: "1.2k", cost: "$0.07", policy: "escalate", grounding: "uncited 1", groundingStatus: "warn" },
  { skill: "backtest", shots: 1, tokIn: "1k", tokOut: "0.2k", cost: "$0.02", policy: "allow", grounding: "cited", groundingStatus: "ok" },
];

export const CRON_JOBS: CronJob[] = [
  { cron: "theia-learn", enabled: true, schedule: "*/20 min", lastRun: "06:00", nextRun: "06:20", lastStatus: "ok", phaseGate: "Phase 1" },
  { cron: "task-runner", enabled: true, schedule: "*/30 min", lastRun: "05:40", nextRun: "06:10", lastStatus: "ok", phaseGate: "Phase 1" },
  { cron: "gmgn-harvest", enabled: false, schedule: "*/60 min", lastRun: "05:00", nextRun: "—", lastStatus: "parked", phaseGate: "needs Phase 2" },
  { cron: "screener", enabled: false, schedule: "*/15 min", lastRun: "—", nextRun: "—", lastStatus: "locked", phaseGate: "needs Phase 2" },
  { cron: "backtest-wf", enabled: false, schedule: "06:00 daily", lastRun: "04:00", nextRun: "—", lastStatus: "manual", phaseGate: "run manually pre-Phase 3" },
  { cron: "theia-paper", enabled: false, schedule: "continuous", lastRun: "—", nextRun: "—", lastStatus: "locked", phaseGate: "needs Phase 5 · after GO gate" },
];

export const CONTEXT_WINDOWS: ContextWindow[] = [
  { name: "theia-learn", session: "session 09", pct: 61, tokens: "78,400 / 128k tokens · 6 shots", shots: 6, warn: true },
  { name: "task-runner", session: "session 14", pct: 22, tokens: "28,100 / 128k tokens · 2 shots", shots: 2 },
  { name: "journal", session: "session 03", pct: 8, tokens: "10,400 / 128k tokens · 1 shot", shots: 1 },
];

export const COST_BARS: CostBar[] = [
  { name: "theia-learn", width: "52%", cost: "$0.96", tokens: "312k tok in" },
  { name: "task-runner", width: "31%", cost: "$0.58", tokens: "88k tok in" },
  { name: "journal", width: "11%", cost: "$0.21", tokens: "41k tok in" },
  { name: "x-scraper", width: "4%", cost: "$0.07", tokens: "6k tok in" },
  { name: "backtest", width: "1%", cost: "$0.02", tokens: "1k tok in" },
];

export const SEED_QUESTIONS = [
  { done: true, title: "Does GMGN per-wallet PnL match on-chain reconstruction?", sources: "2 sources" },
  { done: true, title: "What is the observable latency of a wallet buy signal?", sources: "1 source" },
  { done: true, title: "How do priority fees behave at pump.fun launch?", sources: "2 sources" },
  { done: true, title: "Which GMGN tags predict wash trading behaviour?", sources: "1 source" },
  { done: false, title: "How deep is the slippage tail on 30m-late entries?", sources: "partial · 0 sources yet" },
  { done: false, title: "What share of LP pulls are announced vs silent?", sources: "needs-source" },
  { done: false, title: "Are co-buy graphs stable across weeks?", sources: "needs-source" },
];