import { SEED_QUESTIONS } from "@/lib/data";

export function KnowledgeGraph() {
  return (
    <>
      <div className="grid-panels" style={{ marginBottom: 16 }}>
        <div className="col-4 panel" data-od-id="kg-module-coverage">
          <div className="panel-head">
            <h3>Coverage across modules</h3>
            <span className="grow" />
            <span className="hint">knowledge_index · 12 notes</span>
          </div>
          <div className="panel-body">
            <div className="modcov">
              <div className="m"><span className="mn">Markets</span><div className="mtrack"><i style={{ width: "80%" }} /></div><span className="mv">4 / 5</span></div>
              <div className="m"><span className="mn">On-chain mechanics</span><div className="mtrack"><i style={{ width: "66%" }} /></div><span className="mv">2 / 3</span></div>
              <div className="m"><span className="mn">Wallet behaviour</span><div className="mtrack"><i style={{ width: "75%" }} /></div><span className="mv">3 / 4</span></div>
              <div className="m"><span className="mn">Security / threats</span><div className="mtrack"><i style={{ width: "100%" }} /></div><span className="mv">2 / 2</span></div>
              <div className="m"><span className="mn">Ops &amp; data</span><div className="mtrack"><i style={{ width: "50%" }} /></div><span className="mv">1 / 2</span></div>
            </div>
            <div className="prov" style={{ marginTop: 14 }}>
              <span className="src dc dc-calc">= our compute · knowledge_index</span>
              <span className="ts">counts are notes with status ≠ draft</span>
              <span className="ts">05:40 · 22m ago</span>
            </div>
          </div>
        </div>

        <div className="col-8 panel" data-od-id="kg-seed-questions">
          <div className="panel-head">
            <h3>10 seed questions — Phase 1 exit criteria</h3>
            <span className="grow" />
            <span className="hint">4 answered · 3 partial · 3 unanswered</span>
          </div>
          <div className="panel-body">
            <div className="progress">
              <div className="track"><div className="fill" style={{ width: "40%" }} /></div>
              <span className="pct">4 / 10 fully sourced</span>
            </div>
            <div className="exitc" style={{ marginTop: 10 }}>
              {SEED_QUESTIONS.map((sq, i) => (
                <div key={i} className="row">
                  <span className={`chk ${sq.done ? "on" : "off"}`}>✓</span>
                  <div className="c"><span className="t">{sq.title}</span><span className="sources">{sq.sources}</span></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid-panels">
        <div className="col-12 panel" data-od-id="kg-graph">
          <div className="panel-head">
            <h3>Knowledge graph — notes and how they link</h3>
            <span className="grow" />
            <span className="hint">node shape = status · edge style = link type · dotted edge = machine-discovered</span>
          </div>
          <div className="panel-body kg">
            <svg viewBox="0 0 980 470" role="img" aria-label="Knowledge graph of notes with typed edges">
              <g className="edges">
                <line className="edge rel auto" x1="180" y1="150" x2="350" y2="95" />
                <line className="edge pre" x1="350" y1="95" x2="470" y2="60" />
                <line className="edge pre" x1="470" y1="60" x2="620" y2="105" />
                <line className="edge rel auto" x1="350" y1="95" x2="355" y2="250" />
                <line className="edge con auto" x1="470" y1="60" x2="640" y2="230" />
                <line className="edge rel" x1="180" y1="150" x2="180" y2="330" />
                <line className="edge ext auto" x1="180" y1="330" x2="355" y2="250" />
                <line className="edge rel auto" x1="355" y1="250" x2="620" y2="105" />
                <line className="edge rel auto" x1="355" y1="250" x2="640" y2="230" />
                <line className="edge pre" x1="640" y1="230" x2="830" y2="180" />
                <line className="edge rel auto" x1="180" y1="150" x2="830" y2="180" />
                <line className="edge pre auto" x1="620" y1="105" x2="830" y2="330" />
                <line className="edge rel" x1="640" y1="230" x2="640" y2="400" />
                <line className="edge pre auto" x1="620" y1="105" x2="640" y2="230" />
                <line className="edge con auto" x1="350" y1="95" x2="640" y2="400" />
              </g>
              <g className="node v" transform="translate(180,150)">
                <rect className="ring" x="-58" y="-20" width="116" height="40" rx="9" />
                <text className="glyph" x="-42" y="5">✓</text>
                <text className="nlabel" y="5">GMGN PnL schema</text>
              </g>
              <g className="node v" transform="translate(350,95)">
                <rect className="ring" x="-66" y="-20" width="132" height="40" rx="9" />
                <text className="glyph" x="-50" y="5">✓</text>
                <text className="nlabel" y="5">Signal latency budget</text>
              </g>
              <g className="node v" transform="translate(470,60)">
                <rect className="ring" x="-62" y="-20" width="124" height="40" rx="9" />
                <text className="glyph" x="-46" y="5">✓</text>
                <text className="nlabel" y="5">FIFO PnL reconstruction</text>
              </g>
              <g className="node d" transform="translate(620,105)">
                <rect className="ring" x="-62" y="-20" width="124" height="40" rx="9" />
                <text className="glyph" x="-46" y="5">✎</text>
                <text className="nlabel" y="5">30m-late entry slippage</text>
              </g>
              <g className="node q" transform="translate(355,250)">
                <circle className="ring" r="30" />
                <text className="glyph" y="5" textAnchor="middle">?</text>
                <text className="nlabel" y="52">pump.fun fee dynamics</text>
              </g>
              <g className="node v" transform="translate(180,330)">
                <rect className="ring" x="-58" y="-20" width="116" height="40" rx="9" />
                <text className="glyph" x="-42" y="5">✓</text>
                <text className="nlabel" y="5">wash_trader tags</text>
              </g>
              <g className="node s" transform="translate(640,230)">
                <rect className="ring" x="-58" y="-20" width="116" height="40" rx="9" />
                <text className="glyph" x="-42" y="5">◆</text>
                <text className="nlabel" y="5">Honeypot mechanics</text>
              </g>
              <g className="node d" transform="translate(830,180)">
                <rect className="ring" x="-66" y="-20" width="132" height="40" rx="9" />
                <text className="glyph" x="-50" y="5">✎</text>
                <text className="nlabel" y="5">Cross-wallet co-buys</text>
              </g>
              <g className="node v" transform="translate(640,400)">
                <rect className="ring" x="-66" y="-20" width="132" height="40" rx="9" />
                <text className="glyph" x="-50" y="5">✓</text>
                <text className="nlabel" y="5">Cloudflare scrape tiers</text>
              </g>
              <g className="auto-badge">
                <text x="258" y="118">auto</text>
                <text x="508" y="152" style={{ textAnchor: "middle" }}>auto</text>
                <text x="268" y="248">auto</text>
                <text x="540" y="172">auto</text>
                <text x="490" y="230" style={{ textAnchor: "end" }}>auto</text>
                <text x="720" y="150">auto</text>
              </g>
              <g className="edge-label">
                <text x="352" y="80">prerequisite</text>
                <text x="520" y="88">prerequisite</text>
                <text x="340" y="112">relates</text>
                <text x="130" y="250">relates</text>
                <text x="250" y="296" style={{ textAnchor: "middle" }}>extends</text>
                <text x="740" y="300">prerequisite</text>
                <text x="640" y="152">contrasts</text>
              </g>
            </svg>
            <div className="kg-legend">
              <span className="li"><span className="sw" />verified</span>
              <span className="li"><span className="sw dashed" />draft</span>
              <span className="li"><span className="sw" style={{ borderRadius: "50%" }} />needs-why</span>
              <span className="li"><span className="sw" style={{ borderRadius: 4, borderWidth: 2 }} />needs-source</span>
              <span className="li"><span className="sw dot" />auto-discovered</span>
              <span className="li"><span className="sw" style={{ borderWidth: 2 }} />prerequisite</span>
              <span className="li"><span className="sw contrast" style={{ borderStyle: "dashed" }} />contrasts</span>
            </div>
            <div className="prov" style={{ marginTop: 12 }}>
              <span className="src dc dc-calc">= our compute · knowledge_links</span>
              <span className="ts">edges: related · prerequisite · extends · contrasts · confidence 0..1</span>
              <span className="ts">auto-discovery pass: weekly · last 05:00 Sun</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}