"use client";

import { useState } from "react";
import { useDashboard } from "@/lib/dashboard-context";
import { MCP_SERVERS, LLM_SHOTS, CONTEXT_WINDOWS, COST_BARS } from "@/lib/data";
import type { CronJob } from "@/lib/types";

const INITIAL_CRON: CronJob[] = [
  { cron: "theia-learn", enabled: true, schedule: "*/20 min", lastRun: "06:00", nextRun: "06:20", lastStatus: "ok", phaseGate: "Phase 1" },
  { cron: "task-runner", enabled: true, schedule: "*/30 min", lastRun: "05:40", nextRun: "06:10", lastStatus: "ok", phaseGate: "Phase 1" },
  { cron: "gmgn-harvest", enabled: false, schedule: "*/60 min", lastRun: "05:00", nextRun: "—", lastStatus: "parked", phaseGate: "needs Phase 2" },
  { cron: "screener", enabled: false, schedule: "*/15 min", lastRun: "—", nextRun: "—", lastStatus: "locked", phaseGate: "needs Phase 2" },
  { cron: "backtest-wf", enabled: false, schedule: "06:00 daily", lastRun: "04:00", nextRun: "—", lastStatus: "manual", phaseGate: "run manually pre-Phase 3" },
  { cron: "theia-paper", enabled: false, schedule: "continuous", lastRun: "—", nextRun: "—", lastStatus: "locked", phaseGate: "needs Phase 5 · after GO gate" },
];

export function OpsHarness() {
  const { t } = useDashboard();
  const [cronJobs, setCronJobs] = useState<CronJob[]>(INITIAL_CRON);

  const toggleCron = (name: string) => {
    setCronJobs((prev) =>
      prev.map((cj) => {
        if (cj.cron !== name) return cj;
        if (cj.lastStatus === "locked") return cj;
        return { ...cj, enabled: !cj.enabled };
      })
    );
  };

  return (
    <>
      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-8 panel" data-od-id="mcp-servers">
          <div className="panel-head">
            <h3>{t("hMcp")}</h3>
            <span className="grow" />
            <span className="hint">{t("htTools")}</span>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead><tr><th>{t("thServer")}</th><th>{t("thStatus")}</th><th className="num">{t("thTools")}</th><th className="num">{t("thRate")}</th><th className="num">{t("thCache")}</th><th>{t("thNotes")}</th></tr></thead>
              <tbody>
                {MCP_SERVERS.map((s, i) => (
                  <tr key={i}>
                    <td><span className="mono">{s.server}</span></td>
                    <td><span className={`s ${s.status === "ok" ? "s-ok" : "s-warn"}`}>{t(s.status === "ok" ? "stOk" : "stDegraded")}</span></td>
                    <td className="num">{s.tools}</td><td className="num">{s.rateLimit}</td><td className="num">{s.cacheHit}</td>
                    <td className="small muted">{s.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="col-4 panel" data-od-id="llm-cost">
          <div className="panel-head">
            <h3>{t("hCostLLM")}</h3>
            <span className="grow" />
            <span className="pill warn" style={{ borderStyle: "dashed" }}>{t("stWatchBurn")}</span>
          </div>
          <div className="panel-body">
            <div className="value num" style={{ fontSize: 30, fontWeight: 650 }}>$1.84</div>
            <div className="small muted">spent in last 24h · $0.11 / hr avg</div>
            <div className="costbars" style={{ marginTop: 14 }}>
              {COST_BARS.map((cb, i) => (
                <div key={i} className="cb">
                  <span className="cbname">{cb.name}</span>
                  <div className="cbtrack"><i style={{ width: cb.width }} /></div>
                  <span className="cbval">{cb.cost}<span className="sub">{cb.tokens}</span></span>
                </div>
              ))}
            </div>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-llm">… llm_shots · shots ledger</span>
              <span className="ts">policy decisions logged per shot</span>
              <span className="ts">06:00 · fresh</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-8 panel" data-od-id="llm-shots-table">
          <div className="panel-head">
            <h3>{t("hShots")}</h3>
            <span className="grow" />
            <span className="hint">{t("htShots")}</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 380 }}>
            <table className="dtable">
              <thead><tr><th>{t("thSkill")}</th><th className="num">{t("thShots")}</th><th className="num">{t("thTokIn")}</th><th className="num">{t("thTokOut")}</th><th className="num">{t("thCost")}</th><th>{t("thPolicy")}</th><th>{t("thGrounding")}</th></tr></thead>
              <tbody>
                {LLM_SHOTS.map((ls, i) => {
                  const policyClass = ls.policy === "allow" ? "ok" : ls.policy === "escalate" ? "accent" : "fail";
                  return (
                    <tr key={i}>
                      <td><span className="mono">{ls.skill}</span></td>
                      <td className="num">{ls.shots}</td><td className="num">{ls.tokIn}</td><td className="num">{ls.tokOut}</td><td className="num">{ls.cost}</td>
                      <td><span className={`pill ${policyClass}`}>{t(`st${ls.policy.charAt(0).toUpperCase() + ls.policy.slice(1)}`)}</span></td>
                      <td><span className={`s ${ls.groundingStatus === "ok" ? "s-ok" : "s-warn"}`}>{t(ls.groundingStatus === "ok" ? "stCited" : "stUncited")}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="panel-body" style={{ paddingTop: 10 }}>
            <div className="note" dangerouslySetInnerHTML={{ __html: t("noteDeny") }} />
          </div>
        </div>
        <div className="col-4 panel" data-od-id="context-windows">
          <div className="panel-head">
            <h3>{t("hCtx")}</h3>
            <span className="grow" />
            <span className="hint">{t("htSess")}</span>
          </div>
          <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {CONTEXT_WINDOWS.map((cw, i) => (
              <div key={i}>
                <div className="row-between"><span className="small">{cw.name} · {cw.session}</span><span className="num small">{cw.pct}%</span></div>
                <div className="progress" style={{ margin: "6px 0 0" }}><div className="track"><div className="fill" style={{ width: `${cw.pct}%`, background: cw.warn ? "var(--st-warn)" : "var(--accent)" }} /></div></div>
                <div className="tiny muted" style={{ marginTop: 4 }}>{cw.tokens}</div>
              </div>
            ))}
            <div className="note" style={{ marginTop: 2 }}>{t("noteCtx")}</div>
          </div>
        </div>
      </div>

      <div className="grid-panels">
        <div className="col-12 panel" data-od-id="cron-schedule">
          <div className="panel-head">
            <h3>{t("hCron")}</h3>
            <span className="grow" />
            <span className="hint">{t("htPhase1")}</span>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead><tr><th>{t("thCron")}</th><th>{t("thEnabled")}</th><th>{t("thSchedule")}</th><th>{t("thLastRun")}</th><th>{t("thNextRun")}</th><th>{t("thLastStatus")}</th><th>{t("thPhaseGate")}</th></tr></thead>
              <tbody>
                {cronJobs.map((cj, i) => {
                  const statusClass = cj.lastStatus === "ok" ? "s-ok" : cj.lastStatus === "manual" ? "s-warn" : "s-locked";
                  const statusKey = cj.lastStatus === "ok" ? "stOk" : cj.lastStatus === "parked" ? "stParked" : cj.lastStatus === "manual" ? "stManual" : "stLocked";
                  return (
                    <tr key={i}>
                      <td><span className="mono">{cj.cron}</span></td>
                      <td><span className={`switch ${cj.enabled ? "on" : ""}`} data-cron={cj.cron} onClick={() => toggleCron(cj.cron)} /></td>
                      <td className="num">{cj.schedule}</td>
                      <td className="num">{cj.lastRun}</td>
                      <td className="num">{cj.nextRun}</td>
                      <td><span className={`s ${statusClass}`}>{t(statusKey)}</span></td>
                      <td className="small muted">{cj.phaseGate}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}