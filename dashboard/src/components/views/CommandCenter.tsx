"use client";

import { useEffect, useState } from "react";
import { useDashboard } from "@/lib/dashboard-context";
import { PHASES, EXIT_CRITERIA, DIGEST_LINES } from "@/lib/data";
import type { OverviewPayload } from "@/lib/types";

const POLL_MS = 30_000;

function fmtExp(n: number): string {
  const v = n.toFixed(3);
  return n > 0 ? `+${v}` : v;
}

function fmtUsd(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(2)}k`;
  return `$${n.toFixed(2)}`;
}

export function CommandCenter() {
  const { t } = useDashboard();
  const [ov, setOv] = useState<OverviewPayload | null>(null);
  const [lastOk, setLastOk] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch("/api/overview", { cache: "no-store" });
        const data = (await r.json()) as OverviewPayload;
        if (cancelled) return;
        setOv(data);
        setLastOk(data.ok);
      } catch {
        if (cancelled) return;
        setLastOk(false);
      }
    }
    load();
    const iv = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, []);

  const exp = ov?.expectancy;
  const vit = ov?.vitals;
  const kn = ov?.knowledge;
  const live = lastOk && ov?.ok;

  const expReached = !!exp && exp.n > 0 && exp.expectancy > 0 && (exp.profitFactor ?? 0) > 1;
  const expStatus = exp && exp.n > 0
    ? `${exp.n} archives · E ${fmtExp(exp.expectancy)} · PF ${exp.profitFactor === null ? "∞" : exp.profitFactor.toFixed(2)}`
    : t("expStatus");
  const pfStatus = exp && exp.n > 0
    ? `win ${(exp.winRate * 100).toFixed(0)}% · ${exp.hardStop} hard_stop · ${exp.voided} voided`
    : t("pfStatus");

  const vitalsRows: Array<{ label: string; num: React.ReactNode; sub: string; accent?: boolean }> = [
    {
      label: t("vtCronsOn"),
      num: vit ? `${vit.cronsEnabled} / ${vit.cronsTotal}` : "—",
      sub: vit ? `enabled · ${vit.cronsTotal - vit.cronsEnabled} off` : t("vtSubOn"),
      accent: true,
    },
    {
      label: t("vtCronsOff"),
      num: vit ? `${vit.cronsTotal - vit.cronsEnabled}` : "—",
      sub: vit ? "phase-gated · wallet/health live" : t("vtSubOff"),
    },
    {
      label: t("vtQueue"),
      num: vit ? `${vit.queueDepth}` : "—",
      sub: vit
        ? `ready ${vit.queueBreakdown["ready"] ?? 0} · running ${vit.queueBreakdown["running"] ?? 0} · blocked ${vit.queueBreakdown["blocked"] ?? 0}`
        : t("vtSubQueue"),
    },
    {
      label: t("vtTools"),
      num: "28 / 29",
      sub: "1 unverified · dexdata",
    },
    {
      label: t("vtLlm"),
      num: vit && vit.llmSpendUsd !== null ? fmtUsd(vit.llmSpendUsd) : t("noData"),
      sub: vit && vit.llmShotsCount > 0
        ? `${vit.llmShotsCount} shots · llm_shots`
        : "llm_shots empty · budget_ledger empty",
    },
  ];

  const digestLines = ov?.digest
    ? [
        {
          time: "live",
          text: (
            <>
              <span className="tx">{ov.digest.note}</span>
              {ov.digest.signal24h > 0 || ov.digest.closed24h > 0 ? (
                <span className="s s-active" style={{ marginLeft: 8 }}>
                  {ov.digest.signal24h} sig · {ov.digest.closed24h} closed
                </span>
              ) : null}
            </>
          ),
        },
      ]
    : DIGEST_LINES;

  return (
    <>
      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-6 metric panel" data-od-id="hero-expectancy">
          <div className="mlabel">
            <span className="name">{t("mExp")}</span>
            <span className="grow" />
            {live ? <span className="dc dc-calc">= compute · archives</span> : <span className="dc dc-calc">= compute · expectancy.rs</span>}
          </div>
          <div className="value">
            {exp && exp.n > 0 ? fmtExp(exp.expectancy) : "—"}
            <span className="unit">{t("unitExp")}</span>
          </div>
          <div className="targetline">
            <span className="tk">{t("tk0")}</span>
            <span className="tk reached" style={{ display: expReached ? "" : "none" }}>{t("tkReached")}</span>
            <span className="muted">{live ? expStatus : t("expStatus")}</span>
          </div>
          <div className="pending-state">
            <div className="why">{t("whyExp")}</div>
            <div className="prov">
              <span className="src dc dc-calc">{live ? t("liveSrc") : t("srcOwn")}</span>
              <span className="ts">{live ? exp?.source : t("tsExp")}</span>
              <span className="ts">{live ? t("tsUpd") : ""}</span>
            </div>
          </div>
          <svg viewBox="0 0 420 74" role="img" aria-label={t("ariaExp")} style={{ marginTop: 12, width: "100%", height: "auto" }}>
            <line x1="0" y1="37" x2="420" y2="37" stroke="var(--accent)" strokeWidth="1.4" strokeDasharray="5 4" />
            <text x="414" y="32" textAnchor="end" fill="var(--accent)" fontSize="9" fontFamily="var(--font-mono)">target 0</text>
            <line x1="0" y1="58" x2="420" y2="58" stroke="var(--border)" strokeWidth="1" />
            <text x="414" y="72" textAnchor="end" fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">{t("svgGate")}</text>
            <rect x="0" y="37" width="420" height="21" fill="var(--bg)" opacity={0} />
            <text x="210" y="52" textAnchor="middle" fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">
              {exp && exp.n > 0
                ? `E ${fmtExp(exp.expectancy)} · PF ${exp.profitFactor === null ? "∞" : exp.profitFactor.toFixed(2)}`
                : t("svgAwait")}
            </text>
            <circle cx={exp && exp.n > 0 && exp.expectancy > 0 ? 336 : 210} cy="37" r="3" fill={exp && exp.n > 0 ? "var(--accent)" : "var(--muted)"} />
          </svg>
        </div>
        <div className="col-6 metric panel" data-od-id="hero-profit-factor">
          <div className="mlabel">
            <span className="name">{t("mPf")}</span>
            <span className="grow" />
            {live ? <span className="dc dc-calc">= compute · archives</span> : <span className="dc dc-calc">= compute · pnl.rs</span>}
          </div>
          <div className="value">
            {exp && exp.n > 0 ? (exp.profitFactor === null ? "∞" : exp.profitFactor.toFixed(2)) : "—"}
            <span className="unit">{t("unitPf")}</span>
          </div>
          <div className="targetline">
            <span className="tk">{t("tk1")}</span>
            <span className="tk reached" style={{ display: expReached ? "" : "none" }}>{t("tkReached")}</span>
            <span className="muted">{live ? pfStatus : t("pfStatus")}</span>
          </div>
          <div className="pending-state">
            <div className="why">{t("whyPf")}</div>
            <div className="prov">
              <span className="src dc dc-calc">{live ? t("liveSrc") : t("srcOwn")}</span>
              <span className="ts">{live ? exp?.source : t("tsPf")}</span>
              <span className="ts">{live ? `n=${exp?.n}` : ""}</span>
            </div>
          </div>
          <svg viewBox="0 0 420 74" role="img" aria-label={t("ariaPf")} style={{ marginTop: 12, width: "100%", height: "auto" }}>
            <line x1="0" y1="58" x2="420" y2="58" stroke="var(--accent)" strokeWidth="1.4" strokeDasharray="5 4" />
            <text x="414" y="53" textAnchor="end" fill="var(--accent)" fontSize="9" fontFamily="var(--font-mono)">target 1</text>
            <line x1="0" y1="20" x2="420" y2="20" stroke="var(--border)" strokeWidth="1" />
            <text x="414" y="15" textAnchor="end" fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">{t("svgGate")}</text>
            <text x="210" y="72" textAnchor="middle" fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">
              {exp && exp.n > 0 ? "from archives · net of fees+latency" : t("svgAwait")}
            </text>
            <circle cx={exp && exp.n > 0 && (exp.profitFactor ?? 0) > 1 ? 336 : 210} cy="58" r="3" fill={exp && exp.n > 0 ? "var(--accent)" : "var(--muted)"} />
          </svg>
        </div>
      </div>

      {/* phase rail */}
      <div className="panel" style={{ padding: "16px 16px 14px", marginBottom: 16 }} data-od-id="phase-rail">
        <div className="row-between" style={{ marginBottom: 12 }}>
          <div>
            <span className="eyebrow">{t("prEyebrow")}</span>
            <div className="h3" style={{ marginTop: 2 }}>{t("prTitle")}</div>
          </div>
          <div className="toolbar">
            <span className="s s-active">{t("prChip")}</span>
            <span className="s s-locked">{t("prLocked")}</span>
          </div>
        </div>
        <div className="phase-rail">
          {PHASES.map((p) => (
            <div key={p.phase} className={`phase-cell ${p.status}`} data-phase={p.phase}>
              <div className="pnum">PHASE {p.phase}</div>
              <div className="pname">{p.name}</div>
              <div className="pstatus">{p.statusLabel}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-7 panel" data-od-id="phase1-exit-criteria">
          <div className="panel-head">
            <h3>{t("hExitc")}</h3>
            <span className="grow" />
            <span className="hint">{live && kn ? `${kn.verified} / ${kn.total}` : "4 / 10"}</span>
          </div>
          <div className="panel-body">
            <div className="progress">
              <div className="track">
                <div className="fill" style={{ width: live && kn && kn.total > 0 ? `${Math.min(100, (kn.verified / kn.total) * 100)}%` : "40%" }} />
              </div>
              <span className="pct">{live && kn && kn.total > 0 ? `${Math.round((kn.verified / kn.total) * 100)}%` : "40%"}</span>
            </div>
            <div className="exitc" style={{ marginTop: 8 }}>
              {EXIT_CRITERIA.map((ec, i) => (
                <div key={i} className={`row ${ec.gate ? "gate" : ""}`}>
                  <span className={`chk ${ec.done ? "on" : "off"}`}>✓</span>
                  <div className="c"><span className="t">{ec.title}</span><span className="sources">{ec.sources}</span></div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="col-5 panel" data-od-id="agent-vitals">
          <div className="panel-head">
            <h3>{t("hVitals")}</h3>
            <span className="grow" />
            <span className="hint">{live ? t("liveSrc") : t("htHermes")}</span>
          </div>
          <div className="panel-body" style={{ padding: "10px 16px 14px" }}>
            <table className="dtable">
              <tbody>
                {vitalsRows.map((row, i) => (
                  <tr key={i}>
                    <td className="muted">{row.label}</td>
                    <td className="num">
                      {row.num}
                      <span className="sub" style={row.accent ? { color: "var(--accent)" } : undefined}>{row.sub}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid-panels">
        <div className="col-12 panel" data-od-id="last24h-digest">
          <div className="panel-head">
            <h3>{t("hDigest")}</h3>
            <span className="grow" />
            <span className="dc dc-llm">… prose · journal.md</span>
            <span className="hint" style={{ marginLeft: 8 }}>{t("htWindow")}</span>
          </div>
          <div className="panel-body">
            <div className="digest">
              {digestLines.map((dl, i) => (
                <div key={i} className="line">
                  <span className="tl">{dl.time}</span>
                  <span className="tx">{dl.text}</span>
                </div>
              ))}
            </div>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-calc">{live ? t("liveSrc") : "… prose · journal.md"}</span>
              <span className="ts">{live ? "reconstructed from theia.db · no journal table yet" : "written by theia-journal · grounded against store rows"}</span>
              <span className="ts">{live && ov ? `fetched ${new Date(ov.fetchedAt).toLocaleTimeString()}` : "06:00 UTC · fresh"}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
