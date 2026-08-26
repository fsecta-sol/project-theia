"use client";

import { useDashboard } from "@/lib/dashboard-context";

export function AuthAccount() {
  const ctx = useDashboard();

  if (!ctx.isLoggedIn) {
    return (
      <div className="acc-view">
        <div className="auth-eyebrow">{ctx.t("accEyebrow")}</div>
        <h2 className="auth-title">{ctx.t("accTitle")}</h2>
        <p className="auth-sub">{ctx.t("accSub")}</p>
        <div className="acc-signedout">
          <div className="panel">
            <div className="panel-body">
              <div className="h3">{ctx.t("accSignedOut")}</div>
              <p className="small muted">{ctx.t("accLoginFirst")}</p>
              <button className="auth-btn" style={{ minWidth: 180 }} onClick={() => ctx.setActiveView("auth-login")}>{ctx.t("accToLogin")}</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const initials = (ctx.session?.user || "?").trim().charAt(0).toUpperCase() || "?";

  return (
    <div className="acc-view">
      <div className="auth-eyebrow">{ctx.t("accEyebrow")}</div>
      <h2 className="auth-title">{ctx.t("accTitle")}</h2>
      <p className="auth-sub">{ctx.t("accSub")}</p>
      <div>
        <div className="grid-panels" style={{ marginTop: 24 }}>
          <div className="col-7 panel">
            <div className="panel-head"><h3>{ctx.t("accProfile")}</h3><span className="grow" /></div>
            <div className="panel-body">
              <div className="acc-head">
                <span className="acc-avatar">{initials}</span>
                <span>
                  <div className="h3">{ctx.session?.user || "Operator"}</div>
                  <div className="small muted">{ctx.session?.email || ""}</div>
                </span>
              </div>
              <div className="acc-kv" style={{ marginTop: 16 }}>
                <div className="kv"><span className="k">{ctx.t("accUsername")}</span><span className="v">{ctx.session?.user || "—"}</span></div>
                <div className="kv"><span className="k">{ctx.t("accEmail")}</span><span className="v">{ctx.session?.email || "—"}</span></div>
                <div className="kv"><span className="k">{ctx.t("accJoined")}</span><span className="v">{ctx.session?.joined || "—"}</span></div>
              </div>
            </div>
          </div>
          <div className="col-5 panel">
            <div className="panel-head"><h3>{ctx.t("accSession")}</h3><span className="grow" /></div>
            <div className="panel-body">
              <div className="acc-kv">
                <div className="kv"><span className="k">{ctx.t("accSignedInSince")}</span><span className="v">{ctx.session?.since || "—"}</span></div>
                <div className="kv"><span className="k">device</span><span className="v">Chrome · Windows</span></div>
                <div className="kv"><span className="k">IP</span><span className="v">127.0.0.1</span></div>
              </div>
            </div>
          </div>
        </div>
        <div className="note acc-local">{ctx.t("accLocal")}</div>
      </div>
    </div>
  );
}