export function PaperPositions() {
  return (
    <>
      <div className="lock-banner" data-od-id="v5-lock-banner">
        <div className="lock-ico">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
        </div>
        <div>
          <div className="lt">Phase 5 locked — paper trading is not enabled</div>
          <div className="lc">This is &quot;not yet&quot;, not &quot;broken&quot;. Paper only: every fill is simulated off live reserves, gas and fees — there are no signing keys anywhere on this box. Unlock criterion: the v3 GO/NO-GO gate passes (expectancy &gt; 0 AND profit_factor &gt; 1 on the walk-forward) → theia-paper cron switches on → fills begin simulating.</div>
        </div>
      </div>

      <div className="locked-panel">
        <div className="grid-panels">
          <div className="col-8 panel locked-overlay" data-od-id="v5-open-positions">
            <div className="panel-head">
              <h3>Open positions — paper_trades</h3>
              <span className="grow" />
              <span className="pill locked">Phase 5</span>
            </div>
            <div className="table-wrap" style={{ maxHeight: 420 }}>
              <table className="dtable">
                <thead>
                  <tr><th>Token</th><th className="num">Entry ts</th><th className="num">Entry price</th><th className="num">Size SOL</th><th className="num">Stop</th><th className="num">TP 1</th><th className="num">TP 2</th><th className="num">TP 3</th><th className="num">Dist to stop</th><th>State</th></tr>
                </thead>
                <tbody>
                  <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--muted)", padding: "34px 10px" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>0 open positions</div>
                    <div className="small" style={{ marginTop: 6 }}>Why: Phase 5 locked · When: after the v3 gate passes · Gates: GO/NO-GO → theia-paper cron</div>
                  </td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="col-4 panel locked-overlay" data-od-id="v5-fill-costs">
            <div className="panel-head">
              <h3>Cost is part of the result</h3>
              <span className="grow" />
              <span className="pill locked">Phase 5</span>
            </div>
            <div className="panel-body">
              <p className="small muted" style={{ lineHeight: 1.6 }}>Every simulated fill will carry a full snapshot — reserves, base_fee, priority_fee, gas_sol, slippage — so PnL is reconstructable to the SOL and gas + slippage are never a footnote.</p>
              <div className="empty" style={{ marginTop: 12, display: "block" }}>
                <div className="e-why"><b>No fills to show.</b></div>
                <div className="e-when">First fills appear the night Phase 5 unlocks.</div>
                <div className="e-gates">Costs visualized here: gas_sol · priority_fee · slippage per exit_reason.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="panel locked-overlay" data-od-id="v5-archives">
          <div className="panel-head">
            <h3>Archives — append-only ledger</h3>
            <span className="grow" />
            <span className="pill locked">Phase 5</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="dtable">
              <thead><tr><th className="num">hold_secs</th><th className="num">realized_pnl_sol</th><th className="num">roi</th><th>exit_reason</th><th className="num">ts</th></tr></thead>
              <tbody>
                <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: "26px 10px" }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>0 archived trades</div>
                  <div className="small" style={{ marginTop: 6 }}>exit_reason breakdown (stop / tp / trail / time_stop) lands here first.</div>
                </td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}