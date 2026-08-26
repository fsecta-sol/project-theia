import { useDashboard } from "@/lib/dashboard-context";
import { FUNNEL_STAGES } from "@/lib/data";

export function DailyPipeline() {
  const { t } = useDashboard();

  return (
    <div className="grid-panels">
      <div className="col-12 panel" data-od-id="pipeline-funnel">
        <div className="panel-head">
          <h3>{t("hFunnel")}</h3>
          <span className="grow" />
          <span className="hint">{t("htWindowVs")}</span>
        </div>
        <div className="panel-body">
          <div className="small muted" style={{ marginBottom: 10 }}>Bar width is on a compressed scale (∝ volume<sup>0.3</sup>) so the tail stages stay readable — the numbers, not the bars, are the source of truth. Baseline: 12,847 harvested.</div>
          <div className="funnel">
            {FUNNEL_STAGES.map((fs, i) => (
              <div key={i} className="fstage">
                <div className="sleft">
                  <div className="sname"><span className="seq">{fs.seq}</span> {fs.name}</div>
                  <div className="slat">{fs.latency}</div>
                </div>
                <div className="sright">
                  <div className={`bar ${fs.locked ? "locked-stage" : ""}`}>
                    <span className="fill" style={{ width: fs.barWidth }} />
                    <span className="ct num">{fs.ct}</span><span className="csub">{fs.csub}</span>
                    {fs.vd && (<><span className="grow" /><span className={`vd ${fs.vdClass || ""}`}>{fs.vd}</span></>)}
                    {fs.locknote && (<><span className="grow" /><span className="locknote">{fs.locknote}</span></>)}
                  </div>
                  <div className="drops">
                    {fs.drops.map((d, j) => (
                      <span key={j} className={`drop ${d.gate ? "gate" : ""}`}>
                        {d.bold && <b>{d.bold}</b>}{d.label}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="prov" style={{ marginTop: 14 }}>
            <span className="src dc dc-calc">= our compute</span>
            <span className="ts">pipeline_metrics · aggregated per stage from store rows</span>
            <span className="ts">06:00 UTC · fresh</span>
          </div>
        </div>
      </div>

      <div className="col-12 panel" data-od-id="pipeline-notes">
        <div className="panel-head">
          <h3>{t("hVolDies")}</h3>
          <span className="grow" />
          <span className="hint">{t("htRead")}</span>
        </div>
        <div className="panel-body">
          <div className="collapse">
            <div className="cstep"><span className="cval">12,847<small>harvested</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">473<small>filtered</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">96<small>signals</small></span><span className="carrow">→</span></div>
            <div className="cstep"><span className="cval">78<small>survive veto</small></span></div>
            <div className="cstep" style={{ marginLeft: "auto" }}><span className="pill accent"><span>−99.4%</span> <span>{t("stHarvest")}</span></span></div>
          </div>
          <div className="notes-grid" style={{ marginTop: 14 }}>
            <div className="notes-col">
              <div className="nt"><span className="nval">96.3%</span> 1 · Filter is the biggest wall</div>
              <p className="np muted">Most of the harvest has no real trade history. The filter is doing its job; the harvest tier is the bottleneck to watch.</p>
              <div className="dbar">
                <div className="dbrow"><span className="dbl">no trade history</span><span className="dbtr"><i style={{ width: "97%" }} /></span><span className="dbn">9,842</span></div>
                <div className="dbrow"><span className="dbl">below PnL floor</span><span className="dbtr"><i style={{ width: "20%" }} /></span><span className="dbn">2,051</span></div>
                <div className="dbrow"><span className="dbl">activity too old</span><span className="dbtr"><i style={{ width: "5%" }} /></span><span className="dbn">481</span></div>
              </div>
            </div>
            <div className="notes-col">
              <div className="nt"><span className="nval">53%</span> 2 · Latency is eating signals</div>
              <p className="np muted">More than half the signals were already stale at the ≤30 min budget. The v3 thesis explicitly tolerates this — but it is the largest measured leak today.</p>
              <div className="dbar">
                <div className="dbrow"><span className="dbl">stale &gt;30m</span><span className="dbtr"><i style={{ width: "100%" }} /></span><span className="dbn">251</span></div>
                <div className="dbrow"><span className="dbl">no buy match</span><span className="dbtr"><i style={{ width: "33%" }} /></span><span className="dbn">82</span></div>
                <div className="dbrow"><span className="dbl">duplicate</span><span className="dbtr"><i style={{ width: "18%" }} /></span><span className="dbn">44</span></div>
              </div>
            </div>
            <div className="notes-col">
              <div className="nt"><span className="nval">19%</span> 3 · The veto stays silent</div>
              <p className="np muted">Screening is now a safety net, not the edge — consistent with the v2 thesis result. 78 of 96 clear the veto.</p>
              <div className="dbar">
                <div className="dbrow"><span className="dbl">wash_trader</span><span className="dbtr"><i style={{ width: "100%" }} /></span><span className="dbn">6</span></div>
                <div className="dbrow"><span className="dbl">trade_count low</span><span className="dbtr"><i style={{ width: "83%" }} /></span><span className="dbn">5</span></div>
                <div className="dbrow"><span className="dbl">liquidity gate</span><span className="dbtr"><i style={{ width: "67%" }} /></span><span className="dbn">4</span></div>
                <div className="dbrow"><span className="dbl">honeypot</span><span className="dbtr"><i style={{ width: "33%" }} /></span><span className="dbn">2</span></div>
                <div className="dbrow"><span className="dbl">rug_score</span><span className="dbtr"><i style={{ width: "17%" }} /></span><span className="dbn">1</span></div>
              </div>
            </div>
          </div>
          <div className="empty" style={{ marginTop: 14 }}>
            <div>
              <div className="e-why" dangerouslySetInnerHTML={{ __html: t("whyFunnel") }} />
              <div className="e-when">{t("whenFunnel")}</div>
              <div className="e-gates">{t("gatesFunnel")}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="col-12 panel" data-od-id="legacy-discovery-path">
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 6 }}>
          <h3>{t("hLegacy")}</h3>
          <span className="grow" />
          <span className="pill locked">{t("stDemoted")}</span>
        </div>
        <div className="panel-body">
          <div className="legacy-flow lf-h">
            <div className="lf-step"><span className="lf-chip"><span>new_pools</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">GeckoTerminal · v2 path, deprecated</span></div>
            <div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>tokens</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">Dexscreener · v2 path, deprecated</span></div>
            <div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>screens</span><span className="lf-stat">{t("stOnHold")}</span></span><span className="lf-src">static screen · v2 path, deprecated</span></div>
            <div className="lf-arrow">→</div>
            <div className="lf-step"><span className="lf-chip"><span>token_corpus</span><span className="lf-stat">{t("stZero7d")}</span></span><span className="lf-src">our store · static_screen held</span></div>
          </div>
          <div className="note" style={{ marginTop: 10 }}>{t("lfNote")}</div>
        </div>
      </div>
    </div>
  );
}