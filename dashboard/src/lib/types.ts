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

export interface FunnelStage {
  seq: string;
  name: string;
  latency: string;
  barWidth: string;
  ct: string;
  csub: string;
  vd?: string;
  vdClass?: string;
  locked?: boolean;
  locknote?: string;
  drops: { label: string; bold?: string; gate?: boolean }[];
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