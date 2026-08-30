import { SCREENED_TOKENS } from "@/lib/data";

export function ScreeningVeto() {
  return (
    <>
      <div className="grid-panels">
        <div className="col-5 panel" data-od-id="veto-summary">
          <div className="panel-head">
            <h3>Safety veto — a gate, not the edge</h3>
            <span className="grow" />
            <span className="hint">last 24h</span>
          </div>
          <div className="panel-body">
            <div className="row" style={{ gap: 24, alignItems: "flex-end" }}>
              <div>
                <div className="value num" style={{ fontSize: 34, fontWeight: 650 }}>78</div>
                <div className="small muted">passed the veto</div>
              </div>
              <div>
                <div className="value num" style={{ fontSize: 34, fontWeight: 650, color: "var(--st-fail)" }}>18</div>
                <div className="small muted">vetoed · blocked</div>
              </div>
              <div>
                <div className="value num" style={{ fontSize: 34, fontWeight: 650, color: "var(--muted)" }}>96</div>
                <div className="small muted">signals screened</div>
              </div>
            </div>
            <div className="progress" style={{ marginTop: 16 }}>
              <div className="track"><div className="fill" style={{ width: "81.3%", background: "var(--st-ok)" }} /></div>
              <span className="pct">81.3% pass rate</span>
            </div>
            <div className="drops" style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
              <span className="drop"><b>6</b> wash_trader tag</span>
              <span className="drop"><b>5</b> trade_count too low</span>
              <span className="drop"><b>4</b> liquidity gate</span>
              <span className="drop"><b>2</b> honeypot</span>
              <span className="drop"><b>1</b> rug_score &gt; threshold</span>
            </div>
            <div className="prov" style={{ marginTop: 14 }}>
              <span className="src dc dc-calc">= our compute · security.rs</span>
              <span className="ts">verdicts from on-chain fields + GoPlus checks</span>
              <span className="ts">06:00 UTC · fresh</span>
            </div>
          </div>
        </div>

        <div className="col-7 panel" data-od-id="screening-honesty">
          <div className="panel-head">
            <h3>Research finding — the score doesn&apos;t separate</h3>
            <span className="grow" />
            <span className="pill warn" style={{ borderStyle: "dashed" }}>honest negative result</span>
          </div>
          <div className="panel-body">
            <p className="small muted">Cumulative screen_score distribution for tokens that later graduated vs. tokens that died. The two curves overlap — consistent with the v2 thesis result: fresh pump.fun tokens are clean at t0, so a static score is a liquidity gate, not an edge.</p>
            <svg viewBox="0 0 640 200" style={{ width: "100%", height: "auto", marginTop: 12 }} role="img" aria-label="Cumulative screen score distribution overlapping for graduated and dead tokens">
              <g fontFamily="var(--font-mono)" fontSize="9" fill="var(--muted)">
                <line x1="40" y1="172" x2="624" y2="172" stroke="var(--border)" />
                <line x1="40" y1="20" x2="40" y2="172" stroke="var(--border)" />
                <text x="36" y="174" textAnchor="end">0</text>
                <text x="36" y="52" textAnchor="end">50%</text>
                <text x="36" y="22" textAnchor="end">100%</text>
                <text x="40" y="190">score →</text>
                <text x="624" y="190" textAnchor="end">screen_score</text>
              </g>
              <path d="M40 172 C 90 170, 140 166, 200 158 S 320 140, 420 118 S 560 78, 624 60" fill="none" stroke="var(--st-ok)" strokeWidth="2" />
              <path d="M40 172 C 80 171, 130 168, 190 162 S 300 148, 400 132 S 540 96, 624 78" fill="none" stroke="var(--st-fail)" strokeWidth="2" />
              <text x="180" y="140" fill="var(--st-ok)" fontFamily="var(--font-mono)" fontSize="10">graduated (n=214)</text>
              <text x="330" y="112" fill="var(--st-fail)" fontFamily="var(--font-mono)" fontSize="10">dead (n=1,022)</text>
              <rect x="150" y="150" width="360" height="18" rx="9" fill="var(--surface)" stroke="var(--border)" />
              <text x="330" y="163" textAnchor="middle" fill="var(--fg)" fontFamily="var(--font-mono)" fontSize="9.5">separation ≈ 0 — no decision boundary exists here</text>
            </svg>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-calc">= our compute · thesis_v2_eval.sql</span>
              <span className="ts">cumulative over 1,236 screened tokens · Jul 12 → Aug 21</span>
              <span className="ts">computed 05:00 · 1h ago</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid-panels" style={{ marginTop: 16 }}>
        <div className="col-12 panel" data-od-id="screen-results-table">
          <div className="panel-head">
            <h3>Screened tokens — today</h3>
            <span className="grow" />
            <span className="hint">per-token veto fields · security lib</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 420 }}>
            <table className="dtable">
              <thead>
                <tr>
                  <th>Token</th><th className="num">screen</th><th className="num">honeypot</th>
                  <th className="num">buy / sell tax</th><th className="num">mint / freeze auth</th>
                  <th className="num">LP locked</th><th className="num">top10</th>
                  <th className="num">wash</th><th className="num">rug</th>
                  <th>Verdict</th><th>Reject reason</th>
                </tr>
              </thead>
              <tbody>
                {SCREENED_TOKENS.map((st, i) => (
                  <tr key={i}>
                    <td><span className="addr">{st.addr}</span></td>
                    <td className="num">{st.screen}</td>
                    <td className="num" style={st.honeypotFail ? { color: "var(--st-fail)" } : undefined}>{st.honeypot}</td>
                    <td className="num" style={st.taxFail ? { color: "var(--st-fail)" } : undefined}>{st.tax}</td>
                    <td className="num">{st.mint}</td>
                    <td className="num" style={st.lpFail ? { color: "var(--st-fail)" } : undefined}>{st.lp}</td>
                    <td className="num" style={st.top10Fail ? { color: "var(--st-fail)" } : undefined}>{st.top10}</td>
                    <td className="num" style={st.washFail ? { color: "var(--st-fail)" } : undefined}>{st.wash}</td>
                    <td className="num" style={st.rugFail ? { color: "var(--st-fail)" } : undefined}>{st.rug}</td>
                    <td><span className={`s ${st.verdict === "pass" ? "s-ok" : "s-fail"}`}>{st.verdict}</span></td>
                    <td className="small muted">{st.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}