import { BACKTEST_WINDOWS, HYPOTHESES } from "@/lib/data";
import { IconFile } from "@/components/icons";

export function EdgeLab() {
  return (
    <>
      {/* GO/NO-GO gate */}
      <div className="panel gate-card" style={{ marginBottom: 16 }} data-od-id="v3-go-no-go-gate">
        <div className="ghead">
          <div className="gtitle">
            <div className="row" style={{ gap: 10 }}>
              <span className="mono small" style={{ fontWeight: 700 }}>H-0003</span>
              <h2 style={{ fontSize: 15, fontWeight: 650 }}>Follow verified-profitable wallets, ≤ 30 min late</h2>
            </div>
            <div className="sub">validation gate for the v3 thesis — one number decides the build</div>
          </div>
          <span className="pill accent">backtesting · 4 / 5 windows</span>
          <span className="pill warn" style={{ borderStyle: "dashed" }}>decision pending</span>
        </div>
        <div className="gbody">
          <div>
            <div className="h3" style={{ fontSize: 13 }}>What the gate says</div>
            <p className="small muted" style={{ marginTop: 8, lineHeight: 1.65 }}>
              Backtest <b>follow 30-min-late</b> against smart wallets&apos; <i>past</i> buys. Replay the wallet&apos;s buy, wait up to 30 minutes, enter at the same queue position — net of gas, priority fees and slippage. The result is <b>+EV → build the live loop</b>; <b>≤ 0 → thesis dead, stop here</b>. Not a softer &quot;keep iterating&quot; — a hard fork.
            </p>
            <div className="grule">Rule: <code>expectancy &gt; 0</code> <b>and</b> <code>profit_factor &gt; 1</code>, net of fees + latency</div>
            <div className="prov" style={{ borderTop: 0, paddingTop: 6, marginTop: 14 }}>
              <span className="src dc dc-calc">= our compute · backtest_wf.rs</span>
              <span className="ts">walk-forward · expanding train window</span>
              <span className="ts">last window closed 04:00</span>
            </div>
          </div>
          <div className="gate-meter">
            <div className="gm-row">
              <span className="gml">Expectancy</span>
              <div className="gm-track">
                <div className="gm-fill" style={{ width: "62%" }} />
                <span className="gm-rule" style={{ left: "50%" }} title="gate: > 0" />
                <span className="gm-rule gate-line" style={{ left: "88%" }} title="current +0.31" />
              </div>
              <span className="gm-val pnl-pos num">+0.31<span style={{ fontSize: 9, fontWeight: 400, color: "var(--muted)" }}> SOL</span></span>
            </div>
            <div className="ci" style={{ marginLeft: 110 }}>
              <span className="n" style={{ marginLeft: 0 }}>95% CI <b>±0.14</b> · n=<b>412</b> trades</span>
            </div>
            <div className="gm-row">
              <span className="gml">Profit factor</span>
              <div className="gm-track">
                <div className="gm-fill" style={{ width: "62%" }} />
                <span className="gm-rule" style={{ left: "50%" }} title="gate: > 1" />
                <span className="gm-rule gate-line" style={{ left: "80%" }} title="current 1.24" />
              </div>
              <span className="gm-val pnl-pos num">1.24</span>
            </div>
            <div className="ci" style={{ marginLeft: 110 }}>
              <span className="n" style={{ marginLeft: 0 }}>95% CI <b>±0.19</b> · n=<b>412</b></span>
            </div>
            <div className="note" style={{ marginTop: 6 }}>Final OOS window closes in ~3h 12m. Nothing before then is the answer.</div>
          </div>
        </div>
      </div>

      <div className="grid-panels" style={{ marginBottom: 16 }}>
        {/* walk-forward */}
        <div className="col-7 panel" data-od-id="backtest-walkforward">
          <div className="panel-head">
            <h3>Walk-forward — H-0003</h3>
            <span className="grow" />
            <span className="hint">in-sample / out-of-sample strictly separated</span>
          </div>
          <div className="panel-body">
            <div className="wf-wrap">
              <div className="wf-band"><span className="wf-label">train region · expanding IS</span></div>
              <div className="wf-axes">
                <div className="wf-ys"><span>+0.8</span><span>+0.4</span><span>0</span><span>−0.4</span></div>
                <div className="wf-plot">
                  <div className="wf-line" style={{ top: "12.5%" }} />
                  <div className="wf-line" style={{ top: "50%" }} />
                  <div className="wf-line" style={{ top: "87.5%" }} />
                  <div className="wf-bars">
                    <div className="wf-bar is">
                      <span className="wv num">+0.42</span>
                      <span className="b" style={{ height: "73%", background: "var(--st-ok)" }} />
                      <span className="w" style={{ height: 8 }} />
                      <span className="wl">W1</span>
                    </div>
                    <div className="wf-bar is">
                      <span className="wv num">+0.51</span>
                      <span className="b" style={{ height: "82%", background: "var(--st-ok)" }} />
                      <span className="w" style={{ height: 8 }} />
                      <span className="wl">W2</span>
                    </div>
                    <div className="wf-bar is">
                      <span className="wv num">+0.27</span>
                      <span className="b" style={{ height: "59%", background: "var(--st-ok)" }} />
                      <span className="w" style={{ height: 8 }} />
                      <span className="wl">W3</span>
                    </div>
                    <div className="wf-bar is">
                      <span className="wv num">+0.38</span>
                      <span className="b" style={{ height: "68%", background: "var(--st-ok)" }} />
                      <span className="w" style={{ height: 8 }} />
                      <span className="wl">W4</span>
                    </div>
                    <div className="wf-bar oos">
                      <span className="wv num">+0.19</span>
                      <span className="b" style={{ height: "52%", border: "1px solid color-mix(in oklch,var(--st-ok) 60%,transparent)", background: "color-mix(in oklch,var(--st-ok) 45%,var(--raised))" }} />
                      <span className="w" style={{ height: 8 }} />
                      <span className="wl">W5 · OOS</span>
                    </div>
                    <div className="wf-bar pending">
                      <span className="b" style={{ height: 2 }} />
                      <span className="wl">W6 · open</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="wf-legend">
              <span className="li"><i style={{ background: "var(--st-ok)" }} />in-sample test window</span>
              <span className="li"><i style={{ background: "color-mix(in oklch,var(--st-ok) 45%,var(--raised))", border: "1px solid var(--st-ok)" }} />out-of-sample</span>
              <span className="li"><i style={{ background: "var(--raised)", border: "1px dashed var(--border)" }} />pending</span>
              <span className="li"><i style={{ background: "var(--raised)" }} />95% CI whisker</span>
            </div>
            <div className="prov">
              <span className="src dc dc-calc">= our compute · backtest_wf.rs</span>
              <span className="ts">per-window expectancy, CI via Wilson · n per window 61–108</span>
              <span className="ts">recomputed 04:00 · 2h ago</span>
            </div>
          </div>
        </div>

        {/* backtest table */}
        <div className="col-5 panel" data-od-id="backtest-table">
          <div className="panel-head">
            <h3>Window detail</h3>
            <span className="grow" />
            <span className="hint">expectancy in SOL / trade</span>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead><tr><th>Window</th><th className="num">n</th><th className="num">Exp</th><th className="num">PF</th><th className="num">Win</th><th className="num">MaxDD</th></tr></thead>
              <tbody>
                {BACKTEST_WINDOWS.map((bw, i) => (
                  <tr key={i}>
                    <td><span className="mono">{bw.label}</span></td>
                    <td className="num">{bw.n}</td>
                    <td className="num pnl-pos">{bw.exp}</td>
                    <td className="num">{bw.pf}</td>
                    <td className="num">{bw.win}</td>
                    <td className="num">{bw.maxdd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel-body" style={{ paddingTop: 12 }}>
            <div className="h3" style={{ fontSize: "12.5px", marginBottom: 8 }}>Sample size matters</div>
            <div className="ci" style={{ marginBottom: 8 }}>
              <span className="bar"><i style={{ left: "20%", width: "60%" }} /><b style={{ left: "50%" }} /></span>
              <span className="n">12 trades · CI <b>±0.61</b> — reads like noise</span>
            </div>
            <div className="ci weak">
              <span className="bar"><i style={{ left: "38%", width: "24%" }} /><b style={{ left: "50%" }} /></span>
              <span className="n">412 trades · CI <b>±0.14</b> — usable signal</span>
            </div>
          </div>
        </div>
      </div>

      {/* hypotheses */}
      <div className="grid-panels">
        <div className="col-7 panel" data-od-id="hypotheses-list">
          <div className="panel-head">
            <h3>Hypotheses</h3>
            <span className="grow" />
            <span className="hint">the vault rationale is one click from every row</span>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr><th>ID</th><th>Title</th><th>Status</th><th className="num">Best exp</th><th className="num">Best PF</th><th className="num">Best win</th><th /></tr>
              </thead>
              <tbody>
                {HYPOTHESES.map((h) => {
                  const statusClass = h.status === "backtesting" ? "accent" : h.status === "promoted" ? "ok" : "locked";
                  return (
                    <tr key={h.id}>
                      <td><span className="mono">{h.id}</span></td>
                      <td>{h.title}</td>
                      <td><span className={`pill ${statusClass}`}>{h.statusLabel}</span></td>
                      <td className={`num ${h.bestExp === "—" ? "" : "pnl-pos"}`}>{h.bestExp}</td>
                      <td className="num">{h.bestPf}</td>
                      <td className="num">{h.bestWin}</td>
                      <td><a href="#" className="btn-icon" title="rationale note" aria-label="Open rationale note"><IconFile /></a></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* graveyard */}
        <div className="col-5 panel" data-od-id="hypothesis-graveyard">
          <div className="panel-head">
            <h3>Hypothesis graveyard</h3>
            <span className="grow" />
            <span className="hint">failed research is inventory</span>
          </div>
          <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="empty" style={{ display: "block" }}>
              <div className="row" style={{ gap: 10, marginBottom: 6 }}>
                <span className="mono small" style={{ fontWeight: 700 }}>H-0001</span>
                <span className="pill locked">rejected</span>
              </div>
              <div className="e-why"><b>Static screen at t0 predicts the rug.</b></div>
              <div className="e-when" style={{ marginTop: 4 }}>Cause of death: v2 thesis test — fresh pump.fun tokens are clean at t0 (mint/freeze revoked by default), so screen_score is a liquidity gate. The rug is a forward event (LP pull / dump), not a launch-time flag.</div>
            </div>
            <div className="empty" style={{ display: "block" }}>
              <div className="row" style={{ gap: 10, marginBottom: 6 }}>
                <span className="mono small" style={{ fontWeight: 700 }}>H-0002</span>
                <span className="pill locked">rejected</span>
              </div>
              <div className="e-why"><b>Instant copy-trade of smart wallets.</b></div>
              <div className="e-when" style={{ marginTop: 4 }}>Cause of death: signal latency after tx confirmation exceeds the alpha window — by the time the copy fills, the move is done. Distinct from H-0003&apos;s 30-minute tolerance.</div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}