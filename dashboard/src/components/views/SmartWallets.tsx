"use client";

import { useState, useMemo } from "react";
import { useDashboard } from "@/lib/dashboard-context";

interface Wallet {
  alias: string;
  addr: string;
  short: string;
  state: "watched" | "filtered" | "candidate" | "discarded";
  tags: string[];
  gmgnPnl: string;
  fifo: string;
  trades: number;
  win: string;
  winN: number;
  score: number;
  last: string;
  first: string;
  dist: [number, string][];
  signals: [string, string, string, string][];
  vetoNote: string;
}

const WALLETS: Wallet[] = [
  { alias: "grad_ape", addr: "7xKp9Qf2LmWz4TrVnJc8Hs5GdYu3EwRb1Ta6Nk0Pq", short: "7xKp…9Qa2", state: "watched", tags: [],
    gmgnPnl: "+41.2", fifo: "+38.9", trades: 214, win: "62.4%", winN: 214, score: 87, last: "12m ago", first: "Jun 03",
    dist: [[6, ">5x"], [14, "2–5x"], [82, "<2x"], [64, "-0.5–0x"], [48, "<-0.5x"]],
    signals: [["buy · 8m", "04:32", "pass", "watched"], ["buy · 12m", "03:11", "pass", "watched"], ["buy · 6m", "01:48", "veto", "wash"]],
    vetoNote: "3 of 5 signals cleared the safety veto today — both vetoes were wash_score > 0.8 on thin-fill pumps." },
  { alias: "whale_omega", addr: "9mDfZ2x8QwErT5yUiOpA7sDfGhJkLz1xCvBn4Nm", short: "9mDf…2Zx8", state: "watched", tags: [],
    gmgnPnl: "+23.7", fifo: "+21.9", trades: 98, win: "58.1%", winN: 98, score: 74, last: "1h ago", first: "Jun 21",
    dist: [[3, ">5x"], [9, "2–5x"], [34, "<2x"], [28, "-0.5–0x"], [24, "<-0.5x"]],
    signals: [["buy · 9m", "05:51", "pass", "watched"], ["buy · 7m", "02:20", "pass", "watched"]],
    vetoNote: "2 of 2 signals passed today. Account PnL is the denominator here — per-token PnL is deliberately not used." },
  { alias: "deep_plunge", addr: "2YaLRq5mWx8vBs7dFt4gHj3kLp0qWeRtYu6iOz", short: "2YaL…Rq5m", state: "filtered", tags: [],
    gmgnPnl: "+9.8", fifo: "—", trades: 76, win: "55.2%", winN: 76, score: 69, last: "4h ago", first: "Jul 08",
    dist: [[2, ">5x"], [5, "2–5x"], [25, "<2x"], [24, "-0.5–0x"], [20, "<-0.5x"]],
    signals: [["no signal yet", "—", "—", "queued"]],
    vetoNote: "Passed the filter; watch decision pending in queue. No signals are generated until it is watched." },
  { alias: "bot_blast", addr: "HbZcPn7wQr4Tk2mVx9Jd8SfGhYu0iKjLp1qWeRz", short: "HbZc…Pn7w", state: "discarded", tags: ["bot"],
    gmgnPnl: "+0.4", fifo: "—", trades: 890, win: "49.8%", winN: 890, score: 11, last: "2d ago", first: "Jun 30",
    dist: [[0, ">5x"], [2, "2–5x"], [118, "<2x"], [342, "-0.5–0x"], [428, "<-0.5x"]],
    signals: [["—", "—", "—", "discarded"]],
    vetoNote: "Discarded: flagged bot by GMGN + our wash detection. Kept visible with tags struck through — never silently hidden." },
  { alias: "wash_siren", addr: "B7xVZq90LmWr3tYfDg4hJk8pQwErTz2xCu6vN", short: "B7xV…Tq90", state: "discarded", tags: ["wash_trader"],
    gmgnPnl: "+1.1", fifo: "—", trades: 312, win: "49.8%", winN: 312, score: 22, last: "2d ago", first: "Jul 14",
    dist: [[0, ">5x"], [1, "2–5x"], [44, "<2x"], [121, "-0.5–0x"], [146, "<-0.5x"]],
    signals: [["—", "—", "—", "discarded"]],
    vetoNote: "Discarded: wash_trader tag + wash_score 0.86. This wallet would have passed a static score — exactly the v2 blind spot." },
  { alias: "sniper_sz", addr: "3JqRwLk1TnM8pVx2ZcY7dFgHbJk4qWeRt5uOi9", short: "3Jq…wLk1", state: "candidate", tags: [],
    gmgnPnl: "+6.2", fifo: "—", trades: 41, win: "51.3%", winN: 41, score: 62, last: "4h ago", first: "Aug 01",
    dist: [[1, ">5x"], [2, "2–5x"], [12, "<2x"], [12, "-0.5–0x"], [14, "<-0.5x"]],
    signals: [["—", "—", "—", "candidate"]],
    vetoNote: "Candidate: score above threshold, sample still thin (n=41). Confidence interval check pending before promotion." },
];

const WATCH_PILL: Record<string, [string, string]> = {
  watched: ["pill ok", "watched"],
  filtered: ["pill accent", "filtered"],
  candidate: ["pill", "candidate"],
  discarded: ["pill locked", "discarded"],
};

const DIST_LABELS: [string, string][] = [
  [">5x", "bucket-pos"], ["2–5x", "bucket-pos2"], ["<2x", "bucket-mid"], ["-0.5–0x", "bucket-neg2"], ["<-0.5x", "bucket-neg"],
];

function pnlColor(v: string) {
  if (v === "—" || !v) return "";
  return v.charAt(0) === "-" ? "pnl-neg" : v.charAt(0) === "+" ? "pnl-pos" : parseFloat(v) < 0 ? "pnl-neg" : "pnl-pos";
}
function winColor(n: number) {
  return n >= 55 ? "pnl-pos" : n >= 50 ? "delta-flat" : "pnl-neg";
}

export function SmartWallets() {
  const { t } = useDashboard();
  const [tab, setTab] = useState<"roster" | "detail">("roster");
  const [filter, setFilter] = useState("");
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [wallets, setWallets] = useState<Wallet[]>(WALLETS);

  const filteredWallets = useMemo(() => {
    const q = filter.toLowerCase();
    if (!q) return wallets;
    return wallets.filter((w) => (w.alias + w.addr + w.short + w.state).toLowerCase().includes(q));
  }, [wallets, filter]);

  const toggleWatch = (addr: string) => {
    setWallets((prev) =>
      prev.map((w) => {
        if (w.addr !== addr) return w;
        const nextState = w.state === "watched" ? "filtered" : w.state === "filtered" ? "watched" : w.state;
        return { ...w, state: nextState as Wallet["state"] };
      })
    );
  };

  const openWallet = (addr: string) => {
    const w = wallets.find((x) => x.addr === addr);
    if (!w) return;
    setSelectedWallet(w);
    setTab("detail");
  };

  const copyAddr = async (addr: string) => {
    try { await navigator.clipboard.writeText(addr); } catch {}
  };

  return (
    <div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <div className="tabs" role="tablist">
          <button className={tab === "roster" ? "active" : ""} onClick={() => setTab("roster")}>Roster</button>
          <button className={tab === "detail" ? "active" : ""} onClick={() => setTab("detail")}>Wallet detail</button>
        </div>
        <span style={{ flex: 1 }} />
        <input
          className="input"
          type="search"
          placeholder="Filter alias or address…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 240, padding: "7px 12px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--fg)" }}
        />
        <span className="hint mono small muted">{t("htProv")}</span>
      </div>

      {/* ROSTER */}
      <div style={{ display: tab === "roster" ? "block" : "none" }}>
        <div className="panel">
          <div className="panel-head">
            <h3>{t("hWallets")}</h3>
            <span className="grow" />
            <span className="hint">{t("htPnlDenom")}</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 600 }}>
            <table className="dtable">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>{t("thWatch")}</th>
                  <th>{t("thWallet")}</th>
                  <th>{t("thState")}</th>
                  <th>{t("thTags")}</th>
                  <th className="num"><span>{t("thPnl")}</span> <span className="dc dc-prov">◆</span></th>
                  <th className="num"><span>{t("thFifo")}</span> <span className="dc dc-calc">=</span></th>
                  <th className="num">{t("thTrades")}</th>
                  <th className="num"><span>{t("thWin")}</span> <span className="dc dc-calc">=</span></th>
                  <th className="num">{t("thScore")}</th>
                  <th>{t("thLast")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredWallets.map((w) => {
                  const [pillClass, stateLabel] = WATCH_PILL[w.state];
                  const gPnlCls = pnlColor(w.gmgnPnl);
                  const fPnlCls = pnlColor(w.fifo);
                  const winCls = w.win !== "—" ? winColor(parseFloat(w.win)) : "";
                  return (
                    <tr key={w.addr} className="row-click" onClick={() => openWallet(w.addr)}>
                      <td>
                        <span
                          className={`switch ${w.state === "watched" ? "on" : ""}`}
                          title={t("tToggleWatch")}
                          aria-label={t("tToggleWatch")}
                          onClick={(e) => { e.stopPropagation(); toggleWatch(w.addr); }}
                        />
                      </td>
                      <td><span className="addr">{w.short}</span><span className="sub muted">{w.alias}</span></td>
                      <td><span className={`pill ${pillClass}`}>{t(`st${w.state.charAt(0).toUpperCase() + w.state.slice(1)}`)}</span></td>
                      <td>{w.tags.length ? w.tags.map((tg) => <span key={tg} className="pill locked" style={{ textDecoration: "line-through" }}>{tg}</span>) : <span className="small muted">—</span>}</td>
                      <td className={`num ${gPnlCls}`}><span className="dc dc-prov" style={{ marginRight: 6 }}>◆</span><b>{w.gmgnPnl}</b></td>
                      <td className={`num ${fPnlCls}`}><span className="dc dc-calc" style={{ marginRight: 6 }}>=</span>{w.fifo}</td>
                      <td className="num">{w.trades}</td>
                      <td className={`num ${winCls}`}>{w.win}<span className="sub muted">n={w.winN}</span></td>
                      <td className="num">{w.score}</td>
                      <td className="num">{w.last}</td>
                      <td>
                        <button className="btn-icon copy-btn" title={t("tCopyAddr")} aria-label={t("tCopyAddr")} onClick={(e) => { e.stopPropagation(); copyAddr(w.addr); }}>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="panel-body" style={{ padding: "10px 16px" }}>
            <div className="prov" style={{ marginTop: 0, borderTop: 0, paddingTop: 0 }}>
              <span className="src dc dc-prov">◆ provider · GMGN scrape</span>
              <span className="src dc dc-calc">= our compute · fifo_pnl.rs</span>
              <span className="ts">harvested 04:40 · last refresh 06:00</span>
            </div>
          </div>
        </div>

        <div className="grid-panels" style={{ marginTop: 16 }}>
          <div className="col-4 panel">
            <div className="panel-head"><h3>{t("hThree")}</h3></div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <span className="pill" style={{ borderStyle: "dashed", color: "var(--st-warn)", borderColor: "color-mix(in oklch,var(--st-warn) 45%,transparent)", background: "color-mix(in oklch,var(--st-warn) 10%,transparent)" }}>{t("stCandidate")}</span>
                <div className="small muted">Score above threshold, not yet in the follow set. Dashed amber.</div>
              </div>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <span className="pill accent">{t("stFiltered")}</span>
                <div className="small muted">Passed the filter; a decision to watch or discard is pending. Solid teal.</div>
              </div>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <span className="pill ok">{t("stWatched")}</span>
                <div className="small muted">Live in the follow set — signals flow to the pipeline. Filled green-blue.</div>
              </div>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <span className="pill locked">{t("stDiscarded")}</span>
                <div className="small muted">Tagged wash_trader / bot — shown, not hidden, with tags struck through.</div>
              </div>
            </div>
          </div>
          <div className="col-4 panel">
            <div className="panel-head"><h3>{t("hTrust")}</h3></div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <span className="dc dc-prov">◆ provider</span>
                <p className="small muted" style={{ marginTop: 6 }}>GMGN account PnL. Scraped, not reconstructable by us — displayed with a diamond marker and its own provenance.</p>
              </div>
              <div>
                <span className="dc dc-calc">= compute</span>
                <p className="small muted" style={{ marginTop: 6 }}>Our FIFO reconstruction off on-chain fills. Deterministic, reproducible to the SOL — displayed with a dashed teal marker.</p>
              </div>
            </div>
          </div>
          <div className="col-4 panel">
            <div className="panel-head"><h3>{t("hQueue")}</h3><span className="grow" /><span className="hint">{t("htSlots")}</span></div>
            <div className="panel-body" style={{ padding: "10px 16px 12px" }}>
              <div className="progress" style={{ margin: "2px 0 10px" }}><div className="track"><div className="fill" style={{ width: "33%" }} /></div><span className="pct">2 / 6</span></div>
              <table className="dtable">
                <tbody>
                  <tr><td><span className="addr">9mDf…2Zx8</span></td><td className="num" style={{ color: "var(--st-ok)" }}>queued</td></tr>
                  <tr><td><span className="addr">2YaL…Rq5m</span></td><td className="num" style={{ color: "var(--st-ok)" }}>queued</td></tr>
                </tbody>
              </table>
              <div className="note" style={{ marginTop: 8 }}>{t("noteQueue")}</div>
            </div>
          </div>
        </div>
      </div>

      {/* WALLET DETAIL */}
      <div style={{ display: tab === "detail" ? "block" : "none" }}>
        {selectedWallet ? (
          <WalletDetail wallet={selectedWallet} />
        ) : (
          <div className="panel">
            <div className="panel-body" style={{ textAlign: "center", color: "var(--muted)", padding: "40px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>Select a wallet from the roster to view details.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function WalletDetail({ wallet: w }: { wallet: Wallet }) {
  const { t } = useDashboard();
  const [pillClass, stateLabel] = WATCH_PILL[w.state];
  const maxDist = Math.max(...w.dist.map((d) => d[0]));

  return (
    <div className="panel" data-od-id="wallet-detail">
      <div className="panel-head">
        <div className="h3" style={{ fontSize: 14 }}>{w.alias}</div>
        <span className="addr mono small muted" style={{ marginLeft: 8 }}>{w.short}</span>
        <span className="grow" />
        <span className={`pill ${pillClass}`}>{t(`st${w.state.charAt(0).toUpperCase() + w.state.slice(1)}`)}</span>
      </div>
      <div className="panel-body">
        <div className="grid-panels">
          <div className="col-7">
            <div className="h3" style={{ fontSize: "12.5px", marginBottom: 10 }}>PnL distribution — 5x buckets, native shape</div>
            <div className="dist">
              {w.dist.map((d, i) => {
                const pct = Math.max(4, Math.round(d[0] / maxDist * 100));
                return (
                  <div key={i} className="drow">
                    <span className="dbucket">{DIST_LABELS[i][0]}</span>
                    <div className="dtrack"><i className={DIST_LABELS[i][1]} style={{ width: `${pct}%` }} /></div>
                    <span className="dval">{d[0]}</span>
                  </div>
                );
              })}
            </div>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-prov">◆ provider · GMGN distribution</span>
              <span className="ts">bucket counts as scraped · not redistributed</span>
              <span className="ts">scraped 04:40 · last refresh 06:00</span>
            </div>
          </div>
          <div className="col-5">
            <div className="h3" style={{ fontSize: "12.5px", marginBottom: 10 }}>Signal history → veto outcome</div>
            <div className="table-wrap" style={{ maxHeight: 260 }}>
              <table className="dtable">
                <thead><tr><th>{t("thSignal")}</th><th className="num">{t("thTs")}</th><th>{t("thVeto")}</th><th>{t("thResult")}</th></tr></thead>
                <tbody>
                  {w.signals.map((s, i) => {
                    const v = s[2] === "pass" ? <span className="s s-ok">{t("sPass")}</span> : s[2] === "veto" ? <span className="s s-fail">{t("sVeto")}</span> : <span className="s s-locked">{s[2]}</span>;
                    return (
                      <tr key={i}>
                        <td className="small">{s[0]}</td>
                        <td className="num small">{s[1]}</td>
                        <td>{v}</td>
                        <td className="small muted">{s[3]}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="note" style={{ marginTop: 10 }}>{w.vetoNote}</div>
          </div>
        </div>
        <div className="grid-panels" style={{ marginTop: 16 }}>
          <div className="col-12" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <dl className="kv">
              <dt>Smart score</dt><dd className="num">{w.score}</dd>
              <dt>Filter pass</dt><dd className="num">{w.state === "discarded" ? t("sNo") : t("sYes")}</dd>
              <dt>Wash check</dt><dd className="num">{w.tags.includes("wash_trader") ? t("sFlagged") : t("sClean")}</dd>
            </dl>
            <dl className="kv">
              <dt>Account PnL ◆</dt><dd className={`num ${pnlColor(w.gmgnPnl)}`}>{w.gmgnPnl} SOL</dd>
              <dt>FIFO PnL =</dt><dd className={`num ${w.fifo === "—" ? "" : pnlColor(w.fifo)}`}>{w.fifo === "—" ? t("sNa") : w.fifo + " SOL"}</dd>
              <dt>Win rate =</dt><dd className="num">{w.win} (n={w.winN})</dd>
            </dl>
            <dl className="kv">
              <dt>First seen</dt><dd className="num">{w.first}</dd>
              <dt>Last active</dt><dd className="num">{w.last}</dd>
              <dt>GMGN tags</dt><dd>{w.tags.length ? w.tags.map((tg) => <span key={tg} className="pill locked" style={{ textDecoration: "line-through" }}>{tg}</span>) : <span className="small muted">—</span>}</dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}