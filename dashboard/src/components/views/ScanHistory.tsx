"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useDashboard } from "@/lib/dashboard-context";
import type {
  ScanLedgerState,
  ScanRange,
  WalletScanRow,
  WalletScansPayload,
} from "@/lib/types";

/* ---------------------------- shared helpers ---------------------------- */

const DIST_LABELS: [string, string][] = [
  [">5x", "bucket-pos"], ["2–5x", "bucket-pos2"], ["<2x", "bucket-mid"], ["-0.5–0x", "bucket-neg2"], ["<-0.5x", "bucket-neg"],
];
const SENS_THRESHOLDS = [0.55, 0.6, 0.65, 0.7];

// gate_reason dari pipeline → kategori reject yang dipakai reject bars & tooltip.
const REASON_BUCKET_KEYS: Record<string, string> = {
  bad_tag: "scanReasonWashBot",
  wr7: "scanReasonWin7",
  wr30: "scanReasonWin30",
  txs7: "scanReasonTrades",
  hold: "scanReasonHolding",
  other: "scanReasonOther",
};

const STAGE_BUCKETS: { key: string; bucket: string; label: string }[] = [
  { key: "scanned", bucket: "", label: "scanStageScanned" },
  { key: "tagclean", bucket: "tagclean", label: "scanStageTag" },
  { key: "win7", bucket: "win7", label: "scanStageWin7" },
  { key: "win30", bucket: "win30", label: "scanStageWin30" },
  { key: "trades", bucket: "trades", label: "scanStageTrades" },
  { key: "holding", bucket: "holding", label: "scanStageHolding" },
  { key: "passed", bucket: "pass", label: "scanStagePassed" },
];

/* 6-stage funnel dari gate pipeline (stage-1 bad_tag diwakili tag-clean):
   tag-clean → wr7 ≥ 0.60 → wr30 ≥ 0.50 → txs ≥ 150 → hold < 48h → passed.
   Setiap baris memakai gate_reason yang SUDAH dicatat pipeline (bukan hitung ulang):
   hanya row fail di bucket stage-nya yang di-drop. */
function computeFunnel(rows: WalletScanRow[]): number[] {
  const n = rows.length;
  const tagClean = rows.filter((r) => r.reasonBucket !== "bad_tag").length;
  const win7 = rows.filter((r) => !["bad_tag", "wr7"].includes(r.reasonBucket)).length;
  const win30 = rows.filter((r) => !["bad_tag", "wr7", "wr30"].includes(r.reasonBucket)).length;
  const trades = rows.filter((r) => !["bad_tag", "wr7", "wr30", "txs7"].includes(r.reasonBucket)).length;
  const holding = rows.filter((r) => !["bad_tag", "wr7", "wr30", "txs7", "hold"].includes(r.reasonBucket)).length;
  const passed = rows.filter((r) => r.gate === "pass").length;
  return [n, tagClean, win7, win30, trades, holding, passed];
}

function shortAddr(a: string): string {
  return a.length > 8 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a;
}

function fmtTs(nowMs: number, ts: number, tr: (k: string, fb: string) => string): string {
  if (!ts) return "—";
  const diffH = Math.round((nowMs / 1000 - ts) / 3600);
  if (diffH < 1) return tr("scanJustNow", "just now");
  if (diffH < 24) return `${diffH}h ${tr("scanAgo", "ago")}`;
  return `${Math.round(diffH / 24)}d ${tr("scanAgo", "ago")}`;
}

function histogram(values: number[], bins: number, min: number, max: number, fmt: (v: number) => string) {
  const w = 260, h = 100, padB = 16;
  const counts = new Array(bins).fill(0);
  values.forEach((v) => {
    const idx = Math.min(bins - 1, Math.max(0, Math.floor(((v - min) / (max - min)) * bins)));
    counts[idx]++;
  });
  const maxC = Math.max(...counts) || 1;
  const barW = w / bins;
  const bars = counts
    .map((c, i) => {
      const bh = (c / maxC) * (h - padB);
      const x = i * barW + 1, y = h - padB - bh;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, barW - 2).toFixed(1)}" height="${bh.toFixed(1)}" rx="2" fill="var(--accent)" opacity="0.6"/>`;
    })
    .join("");
  const axis =
    `<line x1="0" y1="${h - padB}" x2="${w}" y2="${h - padB}" stroke="var(--border)"/>` +
    `<text x="0" y="${h}" font-family="monospace" font-size="8" fill="var(--muted)">${fmt(min)}</text>` +
    `<text x="${w}" y="${h}" text-anchor="end" font-family="monospace" font-size="8" fill="var(--muted)">${fmt(max)}</text>`;
  return `<svg viewBox="0 0 ${w} ${h}">${bars}${axis}</svg>`;
}

function sparkline(values: number[]) {
  const w = 160, h = 28;
  const min = Math.min(...values), max = Math.max(...values);
  const hi = max === min ? min + 1 : max;
  const pts = values.map((v, i) => {
    const x = values.length === 1 ? 0 : (i / (values.length - 1)) * w;
    const y = h - ((v - min) / (hi - min)) * (h - 4) - 2;
    return `${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  const d = "M" + pts.join(" L");
  const last = pts[pts.length - 1].split(" ");
  return `<svg viewBox="0 0 ${w} ${h}"><path d="${d}" fill="none" stroke="var(--accent)" stroke-width="1.6"/><circle cx="${last[0]}" cy="${last[1]}" r="2.2" fill="var(--accent)"/></svg>`;
}

function deltaHtml(a: number, b: number, fmt: (v: number) => string, higherIsBetter?: boolean) {
  const d = b - a;
  const cls = d === 0 ? "" : (d > 0) === (higherIsBetter !== false) ? "pnl-pos" : "pnl-neg";
  const arrow = d === 0 ? "·" : d > 0 ? "▲" : "▼";
  return `<span class="d ${cls}">${arrow} ${fmt(Math.abs(d))}</span>`;
}

function distHtml(dist: [number, number, number, number, number]) {
  const raw = [...dist];
  const max = Math.max(...raw) || 1;
  return raw
    .map((v, i) => {
      const pct = Math.max(4, Math.round((v / max) * 100));
      return `<div class="drow"><span class="dbucket">${DIST_LABELS[i][0]}</span><div class="dtrack"><i class="${DIST_LABELS[i][1]}" style="width:${pct}%"></i></div><span class="dval">${v}</span></div>`;
    })
    .join("");
}

function holdingH(r: WalletScanRow): number | null {
  return r.holdingSec != null ? r.holdingSec / 3600 : null;
}

function ScanLoading({ t }: { t: (k: string) => string }) {
  return (
    <div className="scan-loading">
      <div className="spinner" />
      <span>{t("scanLoading")}</span>
    </div>
  );
}

function walletLabel(r: WalletScanRow): string {
  return r.nickname || r.twitter || "";
}

/* ---------------------------- component ---------------------------- */

export function ScanHistory() {
  const { t } = useDashboard();
  const tr = (key: string, fb: string) => t(key) || fb;
  // nowMs: angka tetap per mount; disegarkan saat data dimuat ulang.
  const [now, setNow] = useState<number>(() => Date.now());

  const [data, setData] = useState<WalletScansPayload | null>(null);
  const [status, setStatus] = useState<"loading" | "live" | "na">("loading"); // loading = fetch, live = data asli, na = n/a
  const [range, setRange] = useState<ScanRange>("7d");
  const [ledger, setLedger] = useState<ScanLedgerState>({ sort: "scanTs", dir: "desc", gate: "all", q: "", page: 1, pageSize: 20 });
  const [drawer, setDrawer] = useState<{ addr: string; hist: WalletScanRow[] } | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const drawerTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartTipRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setStatus((s) => (s === "live" ? s : "loading"));
      try {
        // Minta data sesuai range aktif; refresh interval menyesuaikan.
        const days = range === "24h" ? 1 : range === "7d" ? 7 : range === "30d" ? 30 : null;
        const q = days ? `?days=${days}` : "";
        const res = await fetch(`/api/wallet-scans${q}`, { cache: "no-store" });
        const payload = (await res.json()) as WalletScansPayload;
        if (cancelled) return;
        setData(payload);
        setStatus(payload.ok && payload.rows.length > 0 ? "live" : "na");
        setNow(Date.now());
      } catch {
        if (cancelled) return;
        setStatus("na");
      }
    }
    load();
    const interval = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [range]);

  const live = status === "live";

  /* Unified view over live rows (n/a fallback = empty) */
  const rows: WalletScanRow[] = useMemo(
    () => (live && data ? data.rows : []),
    [live, data],
  );
  const runs = useMemo(() => (live && data ? data.runs : []), [live, data]);

  // scanTs/ts dari API dalam DETIK; now (Date.now()) dalam milidetik.
  const nowS = Math.floor(now / 1000);
  const cutoff = range === "24h" ? nowS - 24 * 3600 : range === "7d" ? nowS - 7 * 86400 : range === "30d" ? nowS - 30 * 86400 : 0;
  const rowsInRange = rows.filter((r) => r.scanTs >= cutoff);
  const runsInRange = runs.filter((r) => r.ts >= cutoff);

  const closeDrawer = () => {
    setDrawerVisible(false);
    if (drawerTimer.current) clearTimeout(drawerTimer.current);
    drawerTimer.current = setTimeout(() => setDrawer(null), 220);
  };

  useEffect(() => {
    if (!drawer) return;
    const raf = requestAnimationFrame(() => setDrawerVisible(true));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDrawer();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
    };
  }, [drawer]);

  /* summary */
  const summary = useMemo(() => {
    const noRuns = tr("scanNoRuns", "no scans in this range");
    if (!live) return { scans: "—", wallets: "—", latest: "—", latestNote: "n/a", tracked: "—", flagged: "—", noRunsNote: "n/a" };
    const runList = runsInRange;
    const uniqueWallets: Record<string, boolean> = {};
    rowsInRange.forEach((r) => { uniqueWallets[r.addr] = true; });
    const latestRun = runList.length ? runList.reduce((a, b) => (a.i < b.i ? a : b)) : null;
    const latestRows = latestRun ? rows.filter((r) => r.scanTs >= latestRun.ts && r.scanTs < latestRun.ts + 3600000) : [];
    const latestPassed = latestRows.filter((r) => r.gate === "pass").length;
    const byWallet: Record<string, WalletScanRow> = {};
    rowsInRange.forEach((r) => {
      if (!byWallet[r.addr] || r.scanTs < byWallet[r.addr].scanTs) byWallet[r.addr] = r;
    });
    let tracked = 0;
    Object.keys(byWallet).forEach((a) => { if (byWallet[a].gate === "pass") tracked++; });
    const flagged: Record<string, boolean> = {};
    rowsInRange.forEach((r) => {
      if (r.tags.indexOf("wash_trader") > -1 || r.tags.indexOf("bot") > -1) flagged[r.addr] = true;
    });
    return {
      scans: runList.length,
      wallets: Object.keys(uniqueWallets).length,
      latest: latestRun ? `${latestRows.length} / ${latestPassed}` : "—",
      latestNote: latestRun ? fmtTs(now, latestRun.ts, tr) : noRuns,
      tracked,
      flagged: Object.keys(flagged).length,
      noRunsNote: rowsInRange.length ? "" : noRuns,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, range, rows, runs]);

  /* run chart — live runs have scanned/passed already */
  const chart = useMemo(() => {
    const series = runsInRange.slice().sort((a, b) => b.i - a.i);

    const W = 960, H = 220, padL = 30, padR = 8, padT = 14, padB = 8;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const maxY = Math.max(5, Math.ceil((Math.max(1, ...series.map((s) => s.scanned)) * 1.15) / 5) * 5);
    const xPos = (i: number) => (series.length === 1 ? padL + plotW / 2 : padL + (i / (series.length - 1)) * plotW);
    const yPos = (v: number) => padT + plotH - (v / maxY) * plotH;

    const buildSegs = (field: "scanned" | "passed") => {
      const segs: { x: number; y: number; i: number }[][] = [];
      let cur: { x: number; y: number; i: number }[] = [];
      series.forEach((s, i) => {
        if (s.gap) {
          if (cur.length) { segs.push(cur); cur = []; }
          return;
        }
        cur.push({ x: xPos(i), y: yPos(s[field]), i });
      });
      if (cur.length) segs.push(cur);
      return segs;
    };
    const pathD = (pts: { x: number; y: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

    const scannedSegs = buildSegs("scanned");
    const passedSegs = buildSegs("passed");
    const parts: string[] = [];
    for (let gy = 0; gy <= 4; gy++) {
      const yy = padT + (plotH * gy) / 4;
      parts.push(`<line x1="${padL}" y1="${yy.toFixed(1)}" x2="${W - padR}" y2="${yy.toFixed(1)}" stroke="var(--border)" stroke-width="1" opacity="0.5"/>`);
      parts.push(`<text x="${padL - 6}" y="${(yy + 3).toFixed(1)}" text-anchor="end" font-family="monospace" font-size="9" fill="var(--muted)">${Math.round((maxY * (4 - gy)) / 4)}</text>`);
    }
    passedSegs.forEach((seg) => {
      if (seg.length < 2) return;
      const base = yPos(0);
      const d = pathD(seg) + ` L${seg[seg.length - 1].x.toFixed(1)} ${base.toFixed(1)} L${seg[0].x.toFixed(1)} ${base.toFixed(1)} Z`;
      parts.push(`<path d="${d}" fill="var(--accent)" opacity="0.12" stroke="none"/>`);
    });
    scannedSegs.forEach((seg) => parts.push(`<path d="${pathD(seg)}" fill="none" stroke="var(--fg-mut)" stroke-width="2"/>`));
    passedSegs.forEach((seg) => parts.push(`<path d="${pathD(seg)}" fill="none" stroke="var(--accent)" stroke-width="2"/>`));
    series.forEach((s, i) => {
      if (s.gap) parts.push(`<line x1="${xPos(i).toFixed(1)}" y1="${padT}" x2="${xPos(i).toFixed(1)}" y2="${(padT + plotH)}" stroke="var(--border)" stroke-width="1.5" stroke-dasharray="3 3"/>`);
    });
    const hitW = Math.max(4, plotW / series.length);
    series.forEach((s, i) => parts.push(`<rect data-i="${i}" x="${(xPos(i) - hitW / 2).toFixed(1)}" y="${padT}" width="${hitW.toFixed(1)}" height="${plotH}" fill="transparent"/>`));

    return { series, svg: parts.join("") };
  }, [runsInRange]);

  /* funnel — n/a → semua 0 */
  const funnel = useMemo(
    () => (live ? computeFunnel(rowsInRange) : [0, 0, 0, 0, 0, 0, 0]),
    [live, rowsInRange],
  );

  /* reject reasons */
  const rejectReasons = useMemo(() => {
    if (!live) return [];
    const rows2 = rowsInRange.filter((r) => r.gate === "fail");
    const counts: Record<string, number> = {};
    rows2.forEach((r) => {
      const b = r.reasonBucket || "other";
      counts[b] = (counts[b] || 0) + 1;
    });
    return Object.keys(counts)
      .map((k) => ({ key: k, label: t(REASON_BUCKET_KEYS[k]) || k, n: counts[k] }))
      .sort((a, b) => b.n - a.n);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, rowsInRange]);

  /* ledger */
  const ledgerRows = useMemo(() => {
    if (!live) return [];
    let out = rowsInRange;
    if (ledger.gate !== "all") out = out.filter((r) => r.gate === ledger.gate);
    if (ledger.q) {
      const q = ledger.q.toLowerCase();
      out = out.filter(
        (r) =>
          r.addr.toLowerCase().indexOf(q) > -1 ||
          (r.nickname || "").toLowerCase().indexOf(q) > -1 ||
          (r.twitter || "").toLowerCase().indexOf(q) > -1,
      );
    }
    const dir = ledger.dir === "asc" ? 1 : -1;
    const key = ledger.sort;
    return out.slice().sort((a, b) => {
      const av = key === "wallet" ? a.addr : String(a[key as keyof WalletScanRow] ?? "");
      const bv = key === "wallet" ? b.addr : String(b[key as keyof WalletScanRow] ?? "");
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [live, rowsInRange, ledger]);

  const totalPages = Math.max(1, Math.ceil(ledgerRows.length / ledger.pageSize));
  const safePage = Math.min(ledger.page, totalPages);
  const pageRows = ledgerRows.slice((safePage - 1) * ledger.pageSize, safePage * ledger.pageSize);

  /* sensitivity */
  const sensitivity = useMemo(() => {
    if (!live) return SENS_THRESHOLDS.map((th) => ({ th, n: null as number | null }));
    const basePool = rowsInRange.filter(
      (r) => !["bad_tag", "wr7", "wr30", "txs7", "hold"].includes(r.reasonBucket) && r.reasonBucket !== "other",
    );
    return SENS_THRESHOLDS.map((th) => ({
      th,
      n: basePool.filter((r) => r.win7 >= th).length,
    }));
  }, [live, rowsInRange]);

  /* histograms */
  const histograms = useMemo(() => {
    if (!live || !rowsInRange.length) return null;
    const win = rowsInRange.map((r) => r.win7);
    const trades = rowsInRange.map((r) => r.trades);
    const holding = rowsInRange
      .map(holdingH)
      .filter((v): v is number => v != null);
    return [
      { key: "win", label: t("scanHistWin"), html: histogram(win, 10, 0, 1, (v) => `${Math.round(v * 100)}%`) },
      { key: "trades", label: t("scanHistTrades"), html: histogram(trades, 10, 0, 400, (v) => `${Math.round(v)}`) },
      { key: "holding", label: t("scanHistHolding"), html: histogram(holding, 10, 0, 120, (v) => `${Math.round(v)}h`) },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, rowsInRange]);

  const sortLedger = (key: string) => {
    setLedger((prev) => {
      if (prev.sort === key) return { ...prev, dir: prev.dir === "asc" ? "desc" : "asc" };
      return { ...prev, sort: key, dir: key === "wallet" ? "asc" : "desc" };
    });
  };

  const openDrawer = (addr: string) => {
    const hist = rows.filter((r) => r.addr === addr).sort((a, b) => b.scanTs - a.scanTs).reverse();
    if (!hist.length) return;
    setDrawerVisible(false);
    if (drawerTimer.current) clearTimeout(drawerTimer.current);
    setDrawer({ addr, hist });
  };

  const copyAddr = async (e: React.MouseEvent, addr: string) => {
    e.stopPropagation();
    const btn = e.currentTarget as HTMLElement;
    try {
      await navigator.clipboard.writeText(addr);
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 900);
    } catch { /* clipboard unavailable */ }
  };

  const showTip = (i: number, svg: SVGSVGElement | null) => {
    const tip = chartTipRef.current;
    const s = chart.series[i];
    if (!tip || !svg) return;
    const svgRect = svg.getBoundingClientRect();
    const scale = svgRect.width / 960;
    const x = chart.series.length === 1 ? 30 + (960 - 38) / 2 : 30 + (i / (chart.series.length - 1)) * (960 - 38);
    tip.style.left = `${x * scale}px`;
    tip.style.top = "4px";
    if (s.gap) {
      tip.innerHTML = `<div class="stt">${fmtTs(now, s.ts, tr)}</div><div>${tr("scanNoRunTip", "no scan this hour")}</div>`;
    } else {
      const reasons = (s.rejects || [])
        .filter((r) => r.bucket !== "other" && r.n > 0)
        .map((r) => ({ label: t(REASON_BUCKET_KEYS[r.bucket]) || r.bucket, n: r.n }))
        .slice(0, 2);
      tip.innerHTML =
        `<div class="stt">${fmtTs(now, s.ts, tr)}</div>` +
        `<div><b>${s.scanned}</b> ${tr("scanLegendScanned", "scanned")} · <b>${s.passed}</b> ${tr("scanLegendPassed", "passed")} · <span class="str">${s.scanned - s.passed} ${tr("scanFail", "fail")}</span></div>` +
        (reasons.length ? `<div class="stt" style="margin-top:4px;">${reasons.map((r) => `${r.label} (${r.n})`).join(" · ")}</div>` : "");
    }
    tip.hidden = false;
  };

  const hideTip = () => {
    if (chartTipRef.current) chartTipRef.current.hidden = true;
  };

  const maxFunnel = funnel[0] || 1;
  const funnelPct = (n: number) => (maxFunnel ? Math.round((n / maxFunnel) * 100) : 0);
  const maxReject = rejectReasons[0] ? rejectReasons[0].n : 1;
  const funnelNodes = STAGE_BUCKETS.map((st, i) => {
    const n = funnel[i];
    const isLast = i === STAGE_BUCKETS.length - 1;
    return (
      <div key={st.key} className="pipe-node" data-stage={st.key}>
        <div className="pipe-card" tabIndex={0}>
          <div className="pipe-card-top">
            <div className="pipe-title-wrap">
              <div className="pipe-label">{t(st.label)}</div>
              <div className="pipe-meta">{live ? `${funnelPct(n)}%` : "—"}</div>
            </div>
          </div>
          <div className="pipe-card-bottom">
            <span className="pipe-count num" style={isLast && live ? { color: "var(--st-ok)" } : undefined}>{live ? n : "—"}</span>
            <span className="pipe-port" />
          </div>
        </div>
      </div>
    );
  });
  const funnelConns = STAGE_BUCKETS.slice(0, -1).map((_, i) => {
    const drop = funnel[i] - funnel[i + 1];
    return (
      <div key={i} className="pipe-connector-wrap">
        <div className="pipe-connector"><span className="dot" /></div>
        <span className="pipe-edge-label">{live ? (drop > 0 ? `−${drop}` : "0") : "—"}</span>
      </div>
    );
  });
  const buildRow = (nodes: React.ReactNode[], conns: React.ReactNode[]) => (
    <div className="pipe-row">
      {nodes.map((n, k) => (
        <React.Fragment key={k}>{n}{k < conns.length ? conns[k] : null}</React.Fragment>
      ))}
    </div>
  );
  const betweenDrop = funnel[3] - funnel[4];
  const drawerLatest = drawer ? drawer.hist[drawer.hist.length - 1] : null;
  const drawerFirst = drawer ? drawer.hist[0] : null;

  return (
    <div>
      {/* 0/1. HEADER + SUMMARY */}
      <div className="col-12 panel" data-od-id="scan-header">
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 10 }}>
          <h3>{t("hScanTitle")}</h3>
          <span className="pill sample">{status === "loading" ? "…" : live ? "live · wallet_scan_history" : "n/a"}</span>
          <span className="pill accent">{t("posPaperOnly")}</span>
          <span className="grow" />
          <span className="hint">{t("hScanSubtitle")}</span>
          <div className="scope-toggle" role="tablist" aria-label={t("hScanSubtitle")}>
            {(["24h", "7d", "30d", "all"] as ScanRange[]).map((r) => (
              <button
                key={r}
                type="button"
                className={`scope-opt ${range === r ? "active" : ""}`}
                role="tab"
                aria-selected={range === r}
                onClick={() => { setRange(r); setLedger((p) => ({ ...p, page: 1 })); }}
              >
                {t(`scanRange${r.charAt(0).toUpperCase() + r.slice(1)}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="panel-body">
          {status === "loading" ? (
            <ScanLoading t={t} />
          ) : (
            <div className="pos-stat-grid">
              <div className="pos-stat"><div className="pos-stat-label">{t("scanStatScansL")}</div><div className="pos-stat-value num">{summary.scans}</div><div className="pos-stat-note">{summary.noRunsNote}</div></div>
              <div className="pos-stat"><div className="pos-stat-label">{t("scanStatWalletsL")}</div><div className="pos-stat-value num">{summary.wallets}</div><div className="pos-stat-note">{summary.noRunsNote}</div></div>
              <div className="pos-stat"><div className="pos-stat-label">{t("scanStatLatestL")}</div><div className="pos-stat-value num">{summary.latest}</div><div className="pos-stat-note">{summary.latestNote}</div></div>
              <div className="pos-stat"><div className="pos-stat-label">{t("scanStatTrackedL")}</div><div className="pos-stat-value num">{summary.tracked}</div><div className="pos-stat-note" /></div>
              <div className="pos-stat"><div className="pos-stat-label">{t("scanStatFlaggedL")}</div><div className="pos-stat-value num">{summary.flagged}</div><div className="pos-stat-note" /></div>
            </div>
          )}
        </div>
      </div>

      {/* 2. RUN-OVER-TIME CHART */}
      <div className="col-12 panel" data-od-id="scan-run-chart" style={{ marginTop: 16 }}>
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 10 }}>
          <h3>{t("hScanRunChart")}</h3>
          <span className="grow" />
          <span className="hint">{t("scanRunChartHint")}</span>
        </div>
        <div className="panel-body">
          <div className="scan-chart-legend">
            <span className="li"><span className="sw scanned" />{t("scanLegendScanned")}</span>
            <span className="li"><span className="sw passed" />{t("scanLegendPassed")}</span>
          </div>
          <div className="scan-chart-wrap">
            {status === "loading" ? (
              <ScanLoading t={t} />
            ) : live ? (
              <svg
                viewBox="0 0 960 220"
                preserveAspectRatio="none"
                role="img"
                aria-label={t("scanAriaRunChart")}
                onMouseLeave={hideTip}
                ref={(el) => {
                  if (!el) return;
                  el.querySelectorAll("rect[data-i]").forEach((rect) => {
                    const el2 = rect as SVGRectElement;
                    el2.onmouseenter = () => showTip(Number(el2.getAttribute("data-i")), el);
                    el2.onmouseleave = hideTip;
                  });
                }}
                dangerouslySetInnerHTML={{ __html: chart.svg }}
              />
            ) : (
              <div className="small muted" style={{ padding: "60px 0", textAlign: "center" }}>
                {tr("scanNoRuns", "no scans in this range")} · n/a
              </div>
            )}
            <div className="scan-tooltip" ref={chartTipRef} hidden />
          </div>
        </div>
      </div>

      {/* 3. FUNNEL + REJECT REASONS */}
      <div className="grid-panels" style={{ marginTop: 16 }}>
        <div className="col-8 panel" data-od-id="scan-funnel">
          <div className="panel-head" style={{ flexWrap: "wrap", gap: 10 }}>
            <h3>{t("hScanFunnel")}</h3>
            <span className="grow" />
            <span className="hint">{t("scanFunnelHint")}</span>
          </div>
          <div className="panel-body">
            {status === "loading" ? (
              <ScanLoading t={t} />
            ) : (
              <div className="pipe-canvas" style={{ padding: "20px 16px" }}>
                <div className="pipe-flow" id="scanFunnelFlow" style={{ maxWidth: "none" }}>
                  {buildRow(funnelNodes.slice(0, 4), funnelConns.slice(0, 3))}
                  <div className="pipe-row-connector"><div className="pipe-connector"><span className="dot" /></div><span className="pipe-edge-label">{live ? (betweenDrop > 0 ? `−${betweenDrop}` : "0") : "—"}</span></div>
                  {buildRow(funnelNodes.slice(4), funnelConns.slice(4))}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="col-4 panel" data-od-id="scan-reject-reasons">
          <div className="panel-head">
            <h3>{t("hScanRejects")}</h3>
          </div>
          <div className="panel-body">
            {status === "loading" ? (
              <ScanLoading t={t} />
            ) : rejectReasons.length ? (
              <div className="dbar" style={{ marginTop: 0 }}>
                {rejectReasons.map((rr) => {
                  const pct = maxReject ? Math.max(2, Math.round((rr.n / maxReject) * 100)) : 0;
                  return (
                    <div key={rr.key} className="dbrow">
                      <span className="dbl">{rr.label}</span>
                      <div className="dbtr"><i style={{ width: `${pct}%` }} /></div>
                      <span className="dbn">{rr.n}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="small muted">n/a</div>
            )}
          </div>
        </div>
      </div>

      {/* 4. WALLET SCAN LEDGER */}
      <div className="col-12 panel" data-od-id="scan-ledger" style={{ marginTop: 16 }}>
        <div className="panel-head" style={{ flexWrap: "wrap", gap: 10 }}>
          <h3>{t("hScanLedger")}</h3>
          <span className="hint">{t("scanLedgerHint")}</span>
          <span className="grow" />
          <input
            className="input"
            type="search"
            placeholder="Filter alias or address…"
            value={ledger.q}
            onChange={(e) => setLedger((p) => ({ ...p, q: e.target.value, page: 1 }))}
            style={{ width: 200, padding: "7px 12px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--fg)" }}
          />
          <div className="pos-filter" role="group" aria-label={t("thGate")}>
            {(["all", "pass", "fail"] as const).map((g) => (
              <button
                key={g}
                type="button"
                className={`pos-filter-opt ${ledger.gate === g ? "active" : ""}`}
                aria-pressed={ledger.gate === g}
                onClick={() => setLedger((p) => ({ ...p, gate: g, page: 1 }))}
              >
                {t(`scanFilter${g.charAt(0).toUpperCase() + g.slice(1)}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap" style={{ maxHeight: 520 }}>
          <table className="dtable" id="scanTable">
            <thead>
              <tr>
                <th className="pos-token-th th-tip-left" data-sort="wallet" tabIndex={0} onClick={() => sortLedger("wallet")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("wallet"); } }}>
                  <span>{t("thWallet")}</span><span className="sort-arrow">{ledger.sort === "wallet" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="scanTs" tabIndex={0} onClick={() => sortLedger("scanTs")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("scanTs"); } }}>
                  <span>{t("thScanTs")}</span><span className="sort-arrow">{ledger.sort === "scanTs" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="win7" tabIndex={0} onClick={() => sortLedger("win7")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("win7"); } }}>
                  <span>{t("thWin7")}</span><span className="sort-arrow">{ledger.sort === "win7" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="win30" tabIndex={0} onClick={() => sortLedger("win30")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("win30"); } }}>
                  <span>{t("thWin30")}</span><span className="sort-arrow">{ledger.sort === "win30" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="trades" tabIndex={0} onClick={() => sortLedger("trades")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("trades"); } }}>
                  <span>{t("thTradesBS")}</span><span className="sort-arrow">{ledger.sort === "trades" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="holding" tabIndex={0} onClick={() => sortLedger("holding")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("holding"); } }}>
                  <span>{t("thHolding")}</span><span className="sort-arrow">{ledger.sort === "holding" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="vol7" tabIndex={0} onClick={() => sortLedger("vol7")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("vol7"); } }}>
                  <span>{t("thVol7")}</span><span className="sort-arrow">{ledger.sort === "vol7" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th className="num" data-sort="pnl7" tabIndex={0} onClick={() => sortLedger("pnl7")} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortLedger("pnl7"); } }}>
                  <span>{t("thPnl7")}</span><span className="sort-arrow">{ledger.sort === "pnl7" ? (ledger.dir === "asc" ? "▲" : "▼") : "▲"}</span>
                </th>
                <th>{t("thTags")}</th>
                <th className="th-info" tabIndex={0}><span>{t("thGate")}</span><span className="th-tip">{t("ttGate")}</span></th>
                <th>{t("thRejectReason")}</th>
              </tr>
            </thead>
            <tbody>
              {status === "loading" ? (
                <tr>
                  <td colSpan={11} style={{ padding: 0 }}>
                    <ScanLoading t={t} />
                  </td>
                </tr>
              ) : !live ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", color: "var(--muted)", padding: "30px 10px" }}>
                    <div style={{ fontFamily: "monospace", fontSize: 11 }}>n/a</div>
                    <div className="small" style={{ marginTop: 6 }}>{t("scanLedgerEmptyW")}</div>
                  </td>
                </tr>
              ) : pageRows.length === 0 ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", color: "var(--muted)", padding: "30px 10px" }}>
                    <div style={{ fontFamily: "monospace", fontSize: 11 }}>{t("scanLedgerEmptyT")}</div>
                    <div className="small" style={{ marginTop: 6 }}>{t("scanLedgerEmptyW")}</div>
                  </td>
                </tr>
              ) : (
                pageRows.map((r) => {
                  const label = walletLabel(r);
                  const idLine = label ? <b>{label}</b> : <span className="addr mono small">{shortAddr(r.addr)}</span>;
                  const subLine = label ? <span className="addr mono small muted">{shortAddr(r.addr)}</span> : null;
                  const hold = holdingH(r);
                  return (
                    <tr key={`${r.addr}-${r.scanTs}`} className="row-click" onClick={() => openDrawer(r.addr)}>
                      <td className="pos-token-td">
                        <span className="pos-token-cell">
                          <span className="wm-chip">{r.addr.slice(0, 2)}</span>
                          <span className="pos-token-meta">{idLine}{subLine}</span>
                          <button type="button" className="btn-icon copy-btn" data-copy={r.addr} title={t("tCopyAddr")} onClick={(e) => copyAddr(e, r.addr)}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
                          </button>
                        </span>
                      </td>
                      <td className="num">{fmtTs(now, r.scanTs, tr)}</td>
                      <td className="num">{(r.win7 * 100).toFixed(0)}%</td>
                      <td className="num">{(r.win30 * 100).toFixed(0)}%</td>
                      <td className="num">{r.buys}/{r.sells}</td>
                      <td className="num">{hold != null ? hold.toFixed(1) : "—"}</td>
                      <td className="num">{r.vol7.toFixed(1)} SOL</td>
                      <td className={`num ${r.pnl7 >= 0 ? "pnl-pos" : "pnl-neg"}`}>{r.pnl7 >= 0 ? "+" : ""}{r.pnl7.toFixed(1)}</td>
                      <td>
                        {r.tags.length ? r.tags.map((tg) => {
                          const struck = tg === "wash_trader" || tg === "bot";
                          return <span key={tg} className="pill locked" style={struck ? { textDecoration: "line-through" } : undefined}>{tg}</span>;
                        }) : <span className="small muted">—</span>}
                      </td>
                      <td><span className={`pill ${r.gate === "pass" ? "ok" : "fail"}`}>{r.gate}</span></td>
                      <td>{r.gate === "fail" ? <span className="small muted">{t(REASON_BUCKET_KEYS[r.reasonBucket]) || r.gateReason}</span> : "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="panel-body" style={{ padding: "10px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <span className="src dc dc-calc">{live ? "= live · wallet_scan_history" : "= n/a"}</span>
          <div className="pager">
            <button type="button" className="btn-icon" aria-label="Previous page" disabled={safePage <= 1} onClick={() => setLedger((p) => ({ ...p, page: p.page - 1 }))}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <span className="pager-label">{live ? `${safePage} / ${totalPages}` : "—"}</span>
            <button type="button" className="btn-icon" aria-label="Next page" disabled={!live || safePage >= totalPages} onClick={() => setLedger((p) => ({ ...p, page: p.page + 1 }))}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
            </button>
          </div>
        </div>
      </div>

      {/* 6. THRESHOLD SENSITIVITY */}
      <div className="grid-panels" style={{ marginTop: 16 }}>
        <div className="col-5 panel" data-od-id="scan-sensitivity">
          <div className="panel-head">
            <h3>{t("hScanSens")}</h3>
            <span className="grow" />
            <span className="pill sample">{status === "loading" ? "…" : live ? t("scanSensPill") : "n/a"}</span>
          </div>
          <div className="panel-body">
            {status === "loading" ? (
              <ScanLoading t={t} />
            ) : (
            <>
            <p className="small muted" style={{ marginBottom: 10 }}>{t("scanSensDesc")}</p>
            <div className="pos-filter" role="group" aria-label={t("scanSensLabel")}>
              {SENS_THRESHOLDS.map((th) => (
                <span key={th} className={`pos-filter-opt ${th === 0.6 ? "active" : ""}`} style={{ cursor: "default" }}>{th.toFixed(2)}</span>
              ))}
            </div>
            <div className="scan-sens-result">
              {sensitivity.map((s) => (
                <div key={s.th} className={`scan-sens-row ${s.th === 0.6 ? "current" : ""}`}>
                  <span>{t("scanSensLabel")} {s.th.toFixed(2)}{s.th === 0.6 ? ` · ${t("scanSensCurrent")}` : ""}</span>
                  <span className="n">{s.n != null ? `${s.n} ${t("scanSensWouldPass")}` : "n/a"}</span>
                </div>
              ))}
            </div>
            </>
            )}
          </div>
        </div>
        <div className="col-7 panel" data-od-id="scan-histograms">
          <div className="panel-head"><h3>{t("hScanHist")}</h3></div>
          <div className="panel-body">
            {status === "loading" ? (
              <ScanLoading t={t} />
            ) : histograms ? (
              <div className="scan-hist-grid">
                {histograms.map((h) => (
                  <div key={h.key} className="scan-hist">
                    <h4>{h.label}</h4>
                    <div dangerouslySetInnerHTML={{ __html: h.html }} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="small muted">n/a</div>
            )}
          </div>
        </div>
      </div>

      {/* WALLET SCAN DETAIL DRAWER */}
      <div className={`scan-drawer-scrim ${drawerVisible ? "open" : ""}`} hidden={!drawer} onClick={closeDrawer} />
      <div
        className={`scan-drawer ${drawerVisible ? "open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={t("tabWalletDetail")}
        hidden={!drawer}
      >
        {drawer && drawerLatest && drawerFirst && (
          <>
            <div className="scan-drawer-head">
              <div>
                <div className="scan-drawer-title">{walletLabel(drawerLatest) || shortAddr(drawer.addr)}</div>
                <span className="addr mono small muted">{shortAddr(drawer.addr)}</span>
              </div>
              <span className="grow" />
              <span className="pill sample">{status === "loading" ? "…" : live ? "live · wallet_scan_history" : "n/a"}</span>
              <button type="button" className="btn-icon" aria-label={t("scanAriaClose")} onClick={closeDrawer}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
            <div className="scan-drawer-body">
              <div>
                <h4>{t("scanDrawerSeries")}</h4>
                <div className="scan-spark-row"><span className="l">{t("thWin7")}</span><span dangerouslySetInnerHTML={{ __html: sparkline(drawer.hist.map((r) => r.win7)) }} /><span className="v">{(drawerLatest.win7 * 100).toFixed(0)}%</span></div>
                <div className="scan-spark-row"><span className="l">{t("thWin30")}</span><span dangerouslySetInnerHTML={{ __html: sparkline(drawer.hist.map((r) => r.win30)) }} /><span className="v">{(drawerLatest.win30 * 100).toFixed(0)}%</span></div>
                <div className="scan-spark-row"><span className="l">{t("thTradesBS")}</span><span dangerouslySetInnerHTML={{ __html: sparkline(drawer.hist.map((r) => r.trades)) }} /><span className="v">{drawerLatest.trades}</span></div>
                <div className="scan-spark-row"><span className="l">{t("thPnl7")}</span><span dangerouslySetInnerHTML={{ __html: sparkline(drawer.hist.map((r) => r.pnl7)) }} /><span className="v">{drawerLatest.pnl7 >= 0 ? "+" : ""}{drawerLatest.pnl7.toFixed(1)}</span></div>
              </div>
              <div>
                <h4>{t("scanDrawerDelta")}</h4>
                <div className="scan-delta-row"><span className="l">{t("thWin7")}</span><span dangerouslySetInnerHTML={{ __html: deltaHtml(drawerFirst.win7, drawerLatest.win7, (v) => `${(v * 100).toFixed(0)}pp`) }} /></div>
                <div className="scan-delta-row"><span className="l">{t("thTradesBS")}</span><span dangerouslySetInnerHTML={{ __html: deltaHtml(drawerFirst.trades, drawerLatest.trades, (v) => `${Math.round(v)}`) }} /></div>
                <div className="scan-delta-row"><span className="l">{t("thHolding")}</span><span dangerouslySetInnerHTML={{ __html: deltaHtml(drawerFirst.holdingSec ?? 0, drawerLatest.holdingSec ?? 0, (v) => `${(v / 3600).toFixed(1)}h`, false) }} /></div>
              </div>
              <div>
                <h4>{t("scanDrawerGateHist")}</h4>
                <div className="scan-gate-strip">
                  {drawer.hist.map((r, i) => (
                    <span key={i} className={`scan-gate-dot ${r.gate}`} title={`${fmtTs(now, r.scanTs, tr)} · ${r.gate}${r.gate === "fail" ? ` · ${r.gateReason}` : ""}`} />
                  ))}
                </div>
              </div>
              <div>
                <h4>{t("hPnlDist")}</h4>
                <div className="dist" dangerouslySetInnerHTML={{ __html: distHtml(drawerLatest.dist) }} />
              </div>
              <p className="small muted" style={{ marginTop: -6 }}>{live ? "wallet_scan_history · gate_reason from pipeline" : "n/a"}</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
