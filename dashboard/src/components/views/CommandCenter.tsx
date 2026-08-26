import { useDashboard } from "@/lib/dashboard-context";
import { PHASES, EXIT_CRITERIA, DIGEST_LINES } from "@/lib/data";

export function CommandCenter() {
  const { t } = useDashboard();

  return (
    <>
      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-6 metric panel" data-od-id="hero-expectancy">
          <div className="mlabel">
            <span className="name">{t("mExp")}</span>
            <span className="grow" />
            <span className="dc dc-calc">= compute · expectancy.rs</span>
          </div>
          <div className="value">—<span className="unit">{t("unitExp")}</span></div>
          <div className="targetline">
            <span className="tk">{t("tk0")}</span>
            <span className="tk reached" style={{ display: "none" }}>{t("tkReached")}</span>
            <span className="muted">{t("expStatus")}</span>
          </div>
          <div className="pending-state">
            <div className="why">{t("whyExp")}</div>
            <div className="prov">
              <span className="src dc dc-calc">{t("srcOwn")}</span>
              <span className="ts">{t("tsExp")}</span>
              <span className="ts">{t("tsUpd")}</span>
            </div>
          </div>
          <svg viewBox="0 0 420 74" role="img" aria-label={t("ariaExp")} style={{ marginTop: 12, width: "100%", height: "auto" }}>
            <line x1="0" y1="37" x2="420" y2="37" stroke="var(--accent)" strokeWidth="1.4" strokeDasharray="5 4" />
            <text x="414" y="32" textAnchor="end" fill="var(--accent)" fontSize="9" fontFamily="var(--font-mono)">target 0</text>
            <line x1="0" y1="58" x2="420" y2="58" stroke="var(--border)" strokeWidth="1" />
            <text x="414" y="72" textAnchor="end" fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">{t("svgGate")}</text>
            <rect x="0" y="37" width="420" height="21" fill="var(--bg)" opacity={0} />
            <text x="210" y="52" textAnchor="middle" fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">{t("svgAwait")}</text>
            <circle cx="210" cy="37" r="3" fill="var(--muted)" />
          </svg>
        </div>
        <div className="col-6 metric panel" data-od-id="hero-profit-factor">
          <div className="mlabel">
            <span className="name">{t("mPf")}</span>
            <span className="grow" />
            <span className="dc dc-calc">= compute · pnl.rs</span>
          </div>
          <div className="value">—<span className="unit">{t("unitPf")}</span></div>
          <div className="targetline">
            <span className="tk">{t("tk1")}</span>
            <span className="tk reached" style={{ display: "none" }}>{t("tkReached")}</span>
            <span className="muted">{t("pfStatus")}</span>
          </div>
          <div className="pending-state">
            <div className="why">{t("whyPf")}</div>
            <div className="prov">
              <span className="src dc dc-calc">{t("srcOwn")}</span>
              <span className="ts">{t("tsPf")}</span>
              <span className="ts">{t("tsUpd")}</span>
            </div>
          </div>
          <svg viewBox="0 0 420 74" role="img" aria-label={t("ariaPf")} style={{ marginTop: 12, width: "100%", height: "auto" }}>
            <line x1="0" y1="58" x2="420" y2="58" stroke="var(--accent)" strokeWidth="1.4" strokeDasharray="5 4" />
            <text x="414" y="53" textAnchor="end" fill="var(--accent)" fontSize="9" fontFamily="var(--font-mono)">target 1</text>
            <line x1="0" y1="20" x2="420" y2="20" stroke="var(--border)" strokeWidth="1" />
            <text x="414" y="15" textAnchor="end" fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">{t("svgGate")}</text>
            <text x="210" y="72" textAnchor="middle" fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">{t("svgAwait")}</text>
            <circle cx="210" cy="58" r="3" fill="var(--muted)" />
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
            <span className="hint">4 / 10</span>
          </div>
          <div className="panel-body">
            <div className="progress">
              <div className="track"><div className="fill" style={{ width: "40%" }} /></div>
              <span className="pct">40%</span>
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
            <span className="hint">{t("htHermes")}</span>
          </div>
          <div className="panel-body" style={{ padding: "10px 16px 14px" }}>
            <table className="dtable">
              <tbody>
                <tr><td className="muted">{t("vtCronsOn")}</td><td className="num">2 / 9<span className="sub" style={{ color: "var(--accent)" }}>{t("vtSubOn")}</span></td></tr>
                <tr><td className="muted">{t("vtCronsOff")}</td><td className="num">7<span className="sub">{t("vtSubOff")}</span></td></tr>
                <tr><td className="muted">{t("vtQueue")}</td><td className="num">14<span className="sub">{t("vtSubQueue")}</span></td></tr>
                <tr><td className="muted">{t("vtTools")}</td><td className="num">28 / 29<span className="sub" style={{ color: "var(--st-warn)" }}>{t("vtSubTools")}</span></td></tr>
                <tr><td className="muted">{t("vtLlm")}</td><td className="num">$1.84<span className="sub">{t("vtSubLlm")}</span></td></tr>
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
              {DIGEST_LINES.map((dl, i) => (
                <div key={i} className="line">
                  <span className="tl">{dl.time}</span>
                  <span className="tx">{dl.text}</span>
                </div>
              ))}
            </div>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-llm">… prose · journal.md</span>
              <span className="ts">written by theia-journal · grounded against store rows</span>
              <span className="ts">06:00 UTC · fresh</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}