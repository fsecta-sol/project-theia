"use client";

import { useState } from "react";
import { useDashboard } from "@/lib/dashboard-context";
import { IconMoon, IconSun, IconEye, IconEyeOff } from "@/components/icons";

export function AuthLogin() {
  const ctx = useDashboard();
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = () => {
    const usernameEl = document.getElementById("loginUser") as HTMLInputElement;
    const passEl = document.getElementById("loginPass") as HTMLInputElement;
    const u = usernameEl?.value?.trim() || "";
    const p = passEl?.value || "";
    if (!u || !p) { setError(ctx.t("authErrFill")); return; }
    if (u.length < 3) { setError(ctx.t("authErrUser")); return; }
    setError("");
    setLoading(true);

    // Simulate brief delay, then "login"
    setTimeout(() => {
      ctx.login(u, "");
      setLoading(false);
      const target = ctx.pendingView || "v0";
      ctx.setPendingView(null);
      ctx.setActiveView(target);
    }, 200);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleLogin();
  };

  return (
    <div className="auth-split">
      <div className="auth-form-col">
        <div className="auth-topbar-row">
          <span className="auth-eyebrow">{ctx.t("authLoginEyebrow")}</span>
          <button className="theme-btn auth-theme-toggle" title={ctx.t("thTitle")} aria-label={ctx.t("thTheme")} onClick={ctx.toggleTheme}>
            <span style={{ display: ctx.theme === "dark" ? "block" : "none" }}><IconMoon /></span>
            <span style={{ display: ctx.theme === "light" ? "block" : "none" }}><IconSun /></span>
          </button>
        </div>
        <div className="auth-view">
          <h2 className="auth-title">{ctx.t("authLoginTitle")}</h2>
          <p className="auth-sub">{ctx.t("authLoginSub")}</p>
          <form className="auth-card" onSubmit={(e) => e.preventDefault()} noValidate>
            <div className={`auth-error ${error ? "show" : ""}`} role="alert">{error}</div>
            <div className="auth-field">
              <label htmlFor="loginUser">{ctx.t("authLoginUser")}</label>
              <input className="auth-input" id="loginUser" name="username" autoComplete="username" placeholder={ctx.t("authUserPlaceholder")} onKeyDown={handleKeyDown} />
            </div>
            <div className="auth-field">
              <label htmlFor="loginPass">{ctx.t("authLoginPass")}</label>
              <div className="auth-pass-wrap">
                <input className="auth-input" id="loginPass" name="password" type={showPass ? "text" : "password"} autoComplete="current-password" placeholder={ctx.t("authPassPlaceholder")} onKeyDown={handleKeyDown} />
                <button type="button" className="pass-toggle" data-revealed={showPass} onClick={() => setShowPass((p) => !p)} aria-label={showPass ? ctx.t("authHidePass") : ctx.t("authShowPass")} aria-pressed={showPass}>
                  <span className="icon-eye" style={{ display: showPass ? "none" : "block" }}><IconEye /></span>
                  <span className="icon-eye-off" style={{ display: showPass ? "block" : "none" }}><IconEyeOff /></span>
                </button>
              </div>
            </div>
            <button className="auth-btn" type="button" disabled={loading} onClick={handleLogin}>
              {loading ? ctx.t("authLoginLoading") : ctx.t("authLoginBtn")}
            </button>
          </form>
          <div className="auth-switch">
            <span>{ctx.t("authNoAccount")}</span>{" "}
            <a onClick={() => ctx.setActiveView("auth-signup")}>{ctx.t("authToSignup")}</a>
          </div>
          <div className="auth-demo">{ctx.t("authDemo")}</div>
        </div>
      </div>
      <div className="auth-art-col" data-od-id="auth-art">
        <div className="auth-art" aria-hidden="true">
          <img className="auth-art-photo" alt={ctx.t("authArtAlt")} src={ctx.theme === "dark" ? "/image-3.png" : "/image-4.png"} />
        </div>
        <div className="auth-quote">
          <span className="qmark" aria-hidden="true">"</span>
          <div className="qtext">
            <span>{ctx.t("authQuote")}</span>
            <span className="qwho">{ctx.t("authQuoteWho")}</span>
          </div>
        </div>
      </div>
    </div>
  );
}