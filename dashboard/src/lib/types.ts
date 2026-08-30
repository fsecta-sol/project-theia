export type ViewId =
  | "v0" | "v1" | "v2" | "v3" | "v4" | "v5" | "v6" | "v7"
  | "auth-login" | "auth-signup" | "auth-account";

export type Lang = "en" | "id" | "ja";

export type Theme = "dark" | "light";

export interface NavItem {
  view: ViewId;
  label: string;
  icon: React.ReactNode;
  locked?: boolean;
  badge?: string;
  badgeLive?: boolean;
  lockTip?: string;
  phase?: string;
}

export interface PhaseCellData {
  phase: number;
  name: string;
  status: "done" | "active" | "locked";
  statusLabel: string;
}

export interface ExitCriterion {
  done: boolean;
  title: string;
  sources: string;
  gate?: boolean;
}

export interface DigestLine {
  time: string;
  text: React.ReactNode;
}

export interface ScreenedToken {
  addr: string;
  screen: number;
  honeypot: string;
  honeypotFail?: boolean;
  tax: string;
  taxFail?: boolean;
  mint: string;
  lp: string;
  lpFail?: boolean;
  top10: string;
  top10Fail?: boolean;
  wash: number;
  washFail?: boolean;
  rug: number;
  rugFail?: boolean;
  verdict: "pass" | "veto";
  reason: string;
}

export interface BacktestWindow {
  label: string;
  n: number;
  exp: string;
  pf: string;
  win: string;
  maxdd: string;
}

export interface Hypothesis {
  id: string;
  title: string;
  status: "backtesting" | "promoted" | "draft" | "rejected";
  statusLabel: string;
  bestExp: string;
  bestPf: string;
  bestWin: string;
}

export interface MCPServer {
  server: string;
  status: "ok" | "degraded";
  tools: string;
  rateLimit: string;
  cacheHit: string;
  notes: string;
}

export interface LLMShot {
  skill: string;
  shots: number;
  tokIn: string;
  tokOut: string;
  cost: string;
  policy: "allow" | "escalate" | "deny";
  grounding: string;
  groundingStatus: "ok" | "warn";
}

export interface CronJob {
  cron: string;
  enabled: boolean;
  schedule: string;
  lastRun: string;
  nextRun: string;
  lastStatus: "ok" | "locked" | "parked" | "manual" | "warn";
  phaseGate: string;
}

export interface ContextWindow {
  name: string;
  session: string;
  pct: number;
  tokens: string;
  shots: number;
  warn?: boolean;
}

export interface CostBar {
  name: string;
  width: string;
  cost: string;
  tokens: string;
}

// ---- live data from /api/overview (wired to ~/.hermes/theia/theia.db) ----

export interface ExpectancyStats {
  n: number;
  expectancy: number;
  profitFactor: number | null; // null when no losing trades (∞)
  winRate: number;
  totalPnl: number;
  hardStop: number;
  voided: number;
  updatedTs: number | null;
  source: string;
}

export interface KnowledgeStats {
  verified: number;
  total: number;
  needsSource: number;
  draft: number;
  updatedTs: number | null;
}

export interface VitalsStats {
  cronsEnabled: number;
  cronsTotal: number;
  queueDepth: number;
  queueBreakdown: Record<string, number>;
  llmSpendUsd: number | null;
  llmShotsCount: number;
  pipelineLastRunTs: number | null;
  pipelineNote: string;
}

export interface OverviewPayload {
  ok: boolean;
  error?: string;
  fetchedAt: number;
  expectancy: ExpectancyStats;
  knowledge: KnowledgeStats;
  vitals: VitalsStats;
  digest: { note: string; signal24h: number; closed24h: number };
}

// ---- live data from /api/pipeline (v4 scope shape) ----

export type PipeScope = "all" | "h24";

export interface V4ScopeData {
  counts: {
    harvest: number;
    qualify: number;
    wallets: number;
    buy: number;
    screenPass: number;
    screenVeto: number;
    entry: number;
    monitor: number;
    exit: number;
  };
  screenExText: string; // inline example under Screen node
  monitorPnlText: string; // unrealized pnl pill or "—"
  monitorPnlCls: "ok" | "fail" | "flat";
  monitorGuardText: string;
  exitPnlText: string;
  exitPnlCls: "ok" | "fail" | "flat";
  exitNoteText: string;
}

// ---- live data from /api/wallets ----

export interface LiveWallet {
  address: string;
  nickname: string;
  twitter: string;
  winrate7d: number;
  winrate30d: number;
  pnl7d: number;
  realizedProfit7d: number;
  txs7d: number;
  avgHoldingSec: number;
  volume7d: number;
  tags: string[];
  lastActiveTs: number | null;
  dist: [number, string][];
  isSmartMoney: boolean;
  source: string;
}

export interface WalletsPayload {
  ok: boolean;
  error?: string;
  fetchedAt: number;
  ts: number;
  wallets: LiveWallet[];
  smartCount: number;
  total: number;
}

export interface PipelineV4Payload {
  ok: boolean;
  error?: string;
  fetchedAt: number;
  scopes: Record<PipeScope, V4ScopeData>;
  timing: {
    signalLatencyAvgSecs: number | null;
    avgHoldSecs: number | null;
    lastSignalTs: number | null;
    pipelineLastRunTs: number | null;
  };
  notes: {
    exitReasons: Record<string, number>;
    signalSkips: Record<string, number>;
    smartTotal: number;
    harvestTotal: number;
  };
  digestNote: string;
}

// ---- Scan History (sample-data generator, mirrors the static source) ----

export type ScanRange = "24h" | "7d" | "30d" | "all";

export interface ScanWalletMeta {
  addr: string;
  handle: string | null;
  skill: number;
  idx: number;
  badActor: boolean;
  badKind: "bot" | "wash_trader";
}

export interface ScanRun {
  i: number;
  ts: number;
  gap: boolean;
}

export interface ScanRow {
  wallet: ScanWalletMeta;
  addr: string;
  runI: number;
  scanTs: number;
  win7: number;
  win30: number;
  trades: number;
  buys: number;
  sells: number;
  holding: number;
  vol7: number;
  pnl7: number;
  tags: string[];
  rejectReason: "wash_bot" | "win7" | "win30" | "trades" | "holding" | null;
  gate: "pass" | "fail";
}

export interface ScanLedgerState {
  sort: string;
  dir: "asc" | "desc";
  gate: "all" | "pass" | "fail";
  q: string;
  page: number;
  pageSize: number;
}

// ---- live data from /api/wallet-scans (wallet_scan_history) ----

export interface WalletScanRun {
  i: number;
  ts: number;
  gap: boolean;
  scanned: number;
  passed: number;
  rejects: { bucket: string; n: number }[];
}

export interface WalletScanRow {
  addr: string;
  scanTs: number;
  win7: number;
  win30: number;
  trades: number;
  buys: number;
  sells: number;
  holdingSec: number | null;
  vol7: number;
  pnl7: number;
  tags: string[];
  gate: "pass" | "fail";
  gateReason: string;
  reasonBucket: string;
  lastActiveTs: number | null;
  nickname: string;
  twitter: string;
  dist: [number, number, number, number, number];
}

export interface WalletScansPayload {
  ok: boolean;
  error?: string;
  fetchedAt: number;
  ts: number;
  runs: WalletScanRun[];
  rows: WalletScanRow[];
}



