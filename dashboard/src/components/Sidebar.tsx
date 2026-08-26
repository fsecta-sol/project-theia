"use client";

import { useDashboard } from "@/lib/dashboard-context";
import type { ViewId } from "@/lib/types";
import { IconChevronLeft, IconChart, IconFunnel, IconMonitor, IconShield, IconFlask, IconLedger, IconGraph, IconPulse, IconInfo, IconDocs, IconLock } from "./icons";

export function Sidebar({ activeView, collapsed, open, onChangeView, onToggle, onClose }: {
  activeView: ViewId;
  collapsed: boolean;
  open: boolean;
  onChangeView: (id: ViewId) => void;
  onToggle: () => void;
  onClose: () => void;
}) {
  const { t } = useDashboard();
  const railClasses = ["rail", collapsed ? "collapsed" : "", open ? "open" : ""].filter(Boolean).join(" ");

  const handleAbout = () => window.alert(t("aboutText"));
  const handleDocs = () => window.alert(t("docsText"));

  const renderBtn = (v: ViewId, label: string, icon: React.ReactNode, opts?: { locked?: boolean; badge?: string; badgeLive?: boolean; lockTip?: string }) => (
    <button
      key={v}
      className={`sb-btn ${activeView === v ? "active" : ""} ${opts?.locked ? "locked" : ""}`}
      data-view={v}
      onClick={() => { if (!opts?.locked) { onChangeView(v); onClose(); } }}
    >
      {icon}
      <span className="sb-label">{label}</span>
      {opts?.badge && <span className={`sb-badge ${opts?.badgeLive ? "live" : ""}`}>{opts.badge}</span>}
      {opts?.locked && <span className="sb-lock" aria-hidden="true"><IconLock /></span>}
      <span className="tip" role="tooltip">
        <span>{label}</span>
        {opts?.lockTip && <span className="lock">{opts.lockTip}</span>}
      </span>
    </button>
  );

  return (
    <nav className={railClasses} data-od-id="nav-sidebar" aria-label="Primary">
      <div className="sb-head">
        <div className="sb-brand">
          <span className="mark" aria-hidden="true">T</span>
          <span className="sb-btext">
            <span className="sb-name">{t("brand")}</span>
            <span className="sb-phase">{t("brandPhase")}</span>
          </span>
        </div>
        <button className="sb-toggle" onClick={onToggle} aria-expanded={!collapsed} aria-label={collapsed ? t("tExpand") : t("tCollapse")} title={(collapsed ? t("tExpand") : t("tCollapse")) + "  ["}>
          <IconChevronLeft />
        </button>
      </div>
      <div className="sb-nav">
        <div className="sb-group">
          <div className="sb-group-title">{t("grpOperate")}</div>
          {renderBtn("v0", t("navOverview"), <IconChart />)}
          {renderBtn("v1", t("navPipeline"), <IconFunnel />)}
        </div>
        <div className="sb-group">
          <div className="sb-group-title">{t("grpResearch")}</div>
          {renderBtn("v2", t("navWallets"), <IconMonitor />)}
          {renderBtn("v3", t("navScreening"), <IconShield />)}
          {renderBtn("v4", t("navEdgeLab"), <IconFlask />)}
        </div>
        <div className="sb-group">
          <div className="sb-group-title">{t("grpRecord")}</div>
          {renderBtn("v5", t("navPositions"), <IconLedger />, { locked: true, badge: t("badgePhase5"), lockTip: t("tipLockP5") })}
          {renderBtn("v6", t("navKnowledge"), <IconGraph />, { badge: t("badgeLiveP1"), badgeLive: true, lockTip: t("tipLiveP1") })}
        </div>
        <div className="sb-group">
          <div className="sb-group-title">{t("grpSystem")}</div>
          {renderBtn("v7", t("navOps"), <IconPulse />)}
        </div>
      </div>
      <div className="sb-foot">
        <button className="sb-btn" id="navAbout" onClick={handleAbout}>
          <IconInfo />
          <span className="sb-label">{t("footAbout")}</span>
          <span className="tip" role="tooltip"><span>{t("footAbout")}</span></span>
        </button>
        <button className="sb-btn" id="navDocs" onClick={handleDocs}>
          <IconDocs />
          <span className="sb-label">{t("footDocs")}</span>
          <span className="tip" role="tooltip"><span>{t("footDocs")}</span></span>
        </button>
      </div>
    </nav>
  );
}