"use client";

import { useEffect, useRef, useState } from "react";
import { useDashboard } from "@/lib/dashboard-context";
import type { PipeScope, PipelineV4Payload, V4ScopeData } from "@/lib/types";

const POLL_MS = 30_000;

interface PipeNode {
  label: string;
  meta: string;
  count: string;
  icon: React.ReactNode;
  tipTitle: string;
  tipDescription: string;
  example?: React.ReactNode;
}

interface PipeEdge {
  label: string;
  className?: string;
}

const ICON_HARVEST = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v10M8 9l4 4 4-4" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></svg>;
const ICON_QUALIFY = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.2 2.2L16 9.5" /></svg>;
const ICON_WALLETS = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v1h1a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" /><path d="M16.5 13h.01" /></svg>;
const ICON_SIGNAL = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12h4l2-7 4 14 2-7h6" /></svg>;
const ICON_SCREEN = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" /><path d="M9 12l2 2 4-4" /></svg>;
const ICON_ENTRY = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M13 3h6v18h-6" /><path d="M3 12h12M11 8l4 4-4 4" /></svg>;
const ICON_MONITOR = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" /><circle cx="12" cy="12" r="3" /></svg>;
const ICON_EXIT = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="5" rx="1.2" /><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9" /><path d="M10 13h4" /></svg>;

function isNode(item: PipeNode | PipeEdge): item is PipeNode {
  return "meta" in item;
}

function PipeRow({ items }: { items: (PipeNode | PipeEdge)[] }) {
  return (
    <div className="pipe-row">
      {items.map((item, index) => {
        if (!isNode(item)) {
          return (
            <div key={index} className={`pipe-connector-wrap ${item.className ?? ""}`}>
              <div className="pipe-connector"><span className="dot" /></div>
              <span className="pipe-edge-label">{item.label}</span>
            </div>
          );
        }
        return (
          <div key={index} className="pipe-node" data-stage={item.label}>
            <div className="pipe-card" tabIndex={0}>
              <div className="pipe-tip"><b>{item.tipTitle}</b><span>{item.tipDescription}</span></div>
              <div className="pipe-card-top">
                <div className="pipe-ico">{item.icon}</div>
                <div className="pipe-title-wrap"><div className="pipe-label">{item.label}</div><div className="pipe-meta">{item.meta}</div></div>
              </div>
              <div className="pipe-card-bottom"><span className="pipe-count num">{item.count}</span><span className="pipe-port" /></div>
              {item.example ? <div className="pipe-example">{item.example}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function countPct(part: number, total: number): string {
  if (!total) return "—";
  return `${((part / total) * 100).toFixed(1)}%`;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

function ago(ts: number | null, now: number): string {
  if (!ts) return "—";
  return `${Math.max(0, Math.floor((now - ts) / 86400))}d`;
}

function replaceToken(text: string, token: string, value: string): string {
  return text.replace(token, value);
}

export function DailyPipeline() {
  const { t } = useDashboard();
  const flowRef = useRef<HTMLDivElement>(null);
  const [pipeline, setPipeline] = useState<PipelineV4Payload | null>(null);
  const [scope, setScope] = useState<PipeScope>("all");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/pipeline", { cache: "no-store" });
        const data = (await response.json()) as PipelineV4Payload;
        if (!cancelled) setPipeline(data);
      } catch {
        if (!cancelled) setPipeline(null);
      }
    }
    load();
    const interval = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const flow = flowRef.current;
    if (!flow) return;
    const flowElement = flow;
    const rows = Array.from(flowElement.querySelectorAll(".pipe-row")) as HTMLElement[];
    let alive = true;
    const timers: ReturnType<typeof setTimeout>[] = [];

    function pulse(node: HTMLElement) {
      node.classList.add("pulse");
      timers.push(setTimeout(() => {
        if (alive) node.classList.remove("pulse");
      }, 700));
    }

    function animateRow(row: HTMLElement, startAt: number) {
      const nodes = Array.from(row.querySelectorAll(".pipe-node")) as HTMLElement[];
      const connectors = Array.from(row.querySelectorAll(".pipe-connector")) as HTMLElement[];
      nodes.forEach((node, index) => {
        const delay = startAt + index * 260;
        timers.push(setTimeout(() => {
          if (!alive) return;
          pulse(node);
        }, delay));
        if (index < connectors.length) {
          timers.push(setTimeout(() => {
            if (!alive) return;
            const connector = connectors[index];
            connector.classList.remove("run");
            void connector.offsetWidth;
            connector.classList.add("run");
          }, delay + 120));
        }
      });
      return startAt + nodes.length * 260;
    }

    function runPulse() {
      if (!alive) return;
      const next = animateRow(rows[0], 0);
      const vertical = flowElement.querySelector(".pipe-row-connector .pipe-connector") as HTMLElement | null;
      const secondRow = rows[1];
      if (vertical) {
        timers.push(setTimeout(() => {
          if (!alive) return;
          vertical.classList.remove("run");
          void vertical.offsetWidth;
          vertical.classList.add("run");
        }, next + 120));
      }
      animateRow(secondRow, next + 420);
    }

    runPulse();
    const interval = setInterval(runPulse, 6000);
    return () => {
      alive = false;
      clearInterval(interval);
      timers.forEach(clearTimeout);
    };
  }, []);

  const data: V4ScopeData | null = pipeline?.scopes?.[scope] ?? null;
  const counts = data?.counts;
  const now = pipeline ? Math.floor(pipeline.fetchedAt / 1000) : 0;
  const lastSignal = pipeline?.timing?.lastSignalTs ?? null;
  const isIdle = scope === "h24" && (counts?.buy ?? 0) === 0;
  const freshness = pipeline
    ? isIdle
      ? replaceToken(t("freshIdle"), "{d}", ago(lastSignal, now))
      : t("freshNow")
    : "—";

  const signalSkips = pipeline?.notes?.signalSkips ?? {};
  const exitReasons = pipeline?.notes?.exitReasons ?? {};
  const maxSkip = Math.max(1, ...Object.values(signalSkips));
  const maxExit = Math.max(1, ...Object.values(exitReasons));
  const passRate = counts ? countPct(counts.screenPass, counts.screenPass + counts.screenVeto) : "—";

  const discoveryRow: (PipeNode | PipeEdge)[] = counts ? [
    { label: t("stHarvestLbl"), meta: t("stHarvestMeta"), count: fmt(counts.harvest), icon: ICON_HARVEST, tipTitle: t("tipHarvestT"), tipDescription: t("tipHarvestD") },
    { label: "24s" },
    { label: t("stQualifyLbl"), meta: "tags · dup gate", count: fmt(counts.qualify), icon: ICON_QUALIFY, tipTitle: t("tipQualifyT"), tipDescription: t("tipQualifyD") },
    { label: t("edgeWatchlist"), className: "pipe-connector-watchlist" },
    { label: t("stWalletsLbl"), meta: t("stWalletsMeta"), count: fmt(counts.wallets), icon: ICON_WALLETS, tipTitle: t("tipWalletsT"), tipDescription: t("tipWalletsD") },
    { label: "6m 10s", className: "pipe-connector-wide" },
    { label: t("stBuyLbl"), meta: t("stBuyMeta"), count: fmt(counts.buy), icon: ICON_SIGNAL, tipTitle: t("tipBuyT"), tipDescription: t("tipBuyD") },
  ] : [];

  const screenExample = data && counts ? (
    <span className={`pill ${counts.screenVeto > 0 ? "fail" : "flat"}`}>{data.screenExText || "all checks pass"}</span>
  ) : null;
  const monitorExample = data ? (
    <><span className={`pill ${data.monitorPnlCls}`}>{data.monitorPnlText}</span><span className="small muted">{data.monitorGuardText}</span></>
  ) : null;
  const exitExample = data ? (
    <><span className={`pill ${data.exitPnlCls}`}>{data.exitPnlText}</span><span className="small muted">{data.exitNoteText}</span></>
  ) : null;

  const lifecycleRow: (PipeNode | PipeEdge)[] = counts ? [
    {
      label: t("stScreenLbl"), meta: t("stScreenMeta"), count: `${fmt(counts.screenPass)} / ${fmt(counts.screenVeto)}`,
      icon: ICON_SCREEN, tipTitle: t("tipScreenT"), tipDescription: t("tipScreenD"), example: screenExample,
    },
    { label: "4s" },
    { label: t("stEntryLbl"), meta: t("stEntryMeta"), count: fmt(counts.entry), icon: ICON_ENTRY, tipTitle: t("tipEntryT"), tipDescription: t("tipEntryD") },
    { label: t("edgeLive"), className: "pipe-connector-wide" },
    { label: t("stMonitorLbl"), meta: t("stMonitorMeta"), count: fmt(counts.monitor), icon: ICON_MONITOR, tipTitle: t("tipMonitorT"), tipDescription: t("tipMonitorD"), example: monitorExample },
    { label: t("edgeHold"), className: "pipe-connector-wide" },
    { label: t("stExitLbl"), meta: t("stExitMeta"), count: fmt(counts.exit), icon: ICON_EXIT, tipTitle: t("tipExitT"), tipDescription: t("tipExitD"), example: exitExample },
  ] : [];

  const fallbackRow: (PipeNode | PipeEdge)[] = [
    { label: "—", meta: "—", count: "—", icon: ICON_HARVEST, tipTitle: "", tipDescription: "" },
  ];

  return (
    <div className="grid-panels">
      <div className="col-12 panel" data-od-id="pipeline-funnel">
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 10 }}>
          <h3>{t("hFunnel")}</h3>
          <span className="grow" />
          <span className="hint flow-live"><span className="flow-live-dot" /><span>{t("hintPipeLive")}</span></span>
          <div className="scope-toggle" role="tablist" aria-label="Pipeline scope">
            <button type="button" className={`scope-opt ${scope === "all" ? "active" : ""}`} onClick={() => setScope("all")} role="tab" aria-selected={scope === "all"}>{t("scopeAll")}</button>
            <button type="button" className={`scope-opt ${scope === "h24" ? "active" : ""}`} onClick={() => setScope("h24")} role="tab" aria-selected={scope === "h24"}>{t("scope24h")}</button>
          </div>
        </div>
        <div className="panel-body">
          <div className="pipe-canvas">
            <div className="pipe-flow" ref={flowRef}>
              <div className="pipe-row-label">{t("rowDetect")}</div>
              <PipeRow items={discoveryRow.length ? discoveryRow : fallbackRow} />
              <div className="pipe-row-connector"><div className="pipe-connector"><span className="dot" /></div><span className="pipe-edge-label">12s</span></div>
              <div className="pipe-row-label">{t("rowExec")}</div>
              <PipeRow items={lifecycleRow.length ? lifecycleRow : fallbackRow} />
            </div>
          </div>
          <div className="prov" style={{ marginTop: 14, flexWrap: "wrap" }}>
            <span className="src dc dc-calc">{t("srcOwn")}</span>
            <span className="ts">{t("provApi")}</span>
            <span className={`ts ${isIdle ? "stale-text" : ""}`}>{freshness}</span>
          </div>
        </div>
      </div>

      <div className="col-12 panel" data-od-id="pipeline-notes">
        <div className="panel-head"><h3>{t("hVolDies")}</h3><span className="grow" /><span className="hint">{t("htRead")}</span></div>
        <div className="panel-body">
          <div className="collapse">
            <div className="cstep"><span className="cval">{counts ? fmt(counts.harvest) : "—"}<small>{t("cHarvested")}</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">{counts ? fmt(counts.qualify) : "—"}<small>{t("cQualified")}</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">{counts ? fmt(counts.buy) : "—"}<small>{t("cSignals")}</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">{counts ? fmt(counts.screenPass) : "—"}<small>{t("cScreened")}</small></span></div>
            <div className="cstep" style={{ marginLeft: "auto" }}><span className="pill accent"><span>{passRate}</span> <span>{t("stScreenRate")}</span></span></div>
          </div>
          <div className="notes-grid" style={{ marginTop: 14 }}>
            <div className="notes-col">
              <div className="nt"><span className="nval">{counts ? countPct(counts.qualify, counts.harvest) : "—"}</span> {t("noteQualifyT")}</div>
              <p className="np muted">{t("noteQualifyP")}</p>
              <div className="dbar">
                <div className="dbrow"><span className="dbl">{t("rDupAddr")}</span><span className="dbtr"><i style={{ width: "0%" }} /></span><span className="dbn">{t("sNa")}</span></div>
                <div className="dbrow"><span className="dbl">{t("rNoTag")}</span><span className="dbtr"><i style={{ width: "0%" }} /></span><span className="dbn">{t("sNa")}</span></div>
              </div>
            </div>
            <div className="notes-col">
              <div className="nt"><span className="nval">{pipeline?.notes?.signalSkips ? Object.values(signalSkips).reduce((sum, n) => sum + n, 0) : "—"}</span> {t("noteScreenT")}</div>
              <p className="np muted">{t("noteScreenP")}</p>
              <div className="dbar">
                {Object.entries(signalSkips).map(([action, n]) => (
                  <div className="dbrow" key={action}><span className="dbl">{action}</span><span className="dbtr"><i style={{ width: `${(n / maxSkip) * 100}%` }} /></span><span className="dbn">{n}</span></div>
                ))}
                {!Object.keys(signalSkips).length ? <div className="dbrow"><span className="dbl">no signal data</span><span className="dbtr"><i style={{ width: "0%" }} /></span><span className="dbn">{t("sNa")}</span></div> : null}
              </div>
            </div>
            <div className="notes-col">
              <div className="nt"><span className="nval">{Object.values(exitReasons).reduce((sum, n) => sum + n, 0) || "—"}</span> {t("noteExitT")}</div>
              <p className="np muted">{t("noteExitP")}</p>
              <div className="dbar">
                {Object.entries(exitReasons).map(([reason, n]) => (
                  <div className="dbrow" key={reason}><span className="dbl">{reason}</span><span className="dbtr"><i style={{ width: `${(n / maxExit) * 100}%` }} /></span><span className="dbn">{n}</span></div>
                ))}
                {!Object.keys(exitReasons).length ? <div className="dbrow"><span className="dbl">no exit data</span><span className="dbtr"><i style={{ width: "0%" }} /></span><span className="dbn">{t("sNa")}</span></div> : null}
              </div>
            </div>
          </div>
          <div className="empty" style={{ marginTop: 14 }}>
            <div><div className="e-why" dangerouslySetInnerHTML={{ __html: t("whyFunnel") }} /><div className="e-when">{t("whenFunnel")}</div><div className="e-gates">{t("gatesFunnel")}</div></div>
          </div>
        </div>
      </div>

      <div className="col-12 panel" data-od-id="legacy-discovery-path">
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 6 }}><h3>{t("hLegacy")}</h3><span className="grow" /><span className="pill locked">{t("stDemoted")}</span></div>
        <div className="panel-body">
          <div className="legacy-flow lf-h">
            <div className="lf-step"><span className="lf-chip"><span>new_pools</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">GeckoTerminal · v2 path, deprecated</span></div><div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>tokens</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">Dexscreener · v2 path, deprecated</span></div><div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>screens</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">static screen · v2 path, deprecated</span></div><div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>token_corpus</span><span className="lf-stat">{t("stZero7d")}</span></span><span className="lf-src">our store · static_screen held</span></div>
          </div>
          <div className="note" style={{ marginTop: 10 }}>{t("lfNote")}</div>
        </div>
      </div>
    </div>
  );
}
