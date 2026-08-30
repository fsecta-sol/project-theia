"use client";

import { useState } from "react";
import Image from "next/image";
import { useDashboard } from "@/lib/dashboard-context";
import { IconMoon, IconSun, IconEye, IconEyeOff } from "@/components/icons";

export function AuthSignup() {
  const ctx = useDashboard();
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSignup = () => {
    const userEl = document.getElementById("signupUser") as HTMLInputElement;
    const emailEl = document.getElementById("signupEmail") as HTMLInputElement;
    const passEl = document.getElementById("signupPass") as HTMLInputElement;
    const u = userEl?.value?.trim() || "";
    const em = emailEl?.value?.trim() || "";
    const p = passEl?.value || "";
    if (!u || !em || !p) { setError(ctx.t("authErrFill")); return; }
    if (u.length < 3) { setError(ctx.t("authErrUser")); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { setError(ctx.t("authErrEmail")); return; }
    if (p.length < 8) { setError(ctx.t("authErrPass")); return; }

    setError("");
    setLoading(true);

    // Simulate brief delay
    setTimeout(() => {
      // Store in localStorage
      try {
        const users = JSON.parse(localStorage.getItem("theia-users") || "{}");
        if (users[u.toLowerCase()]) {
          setError(ctx.t("authErrUserTaken"));
          setLoading(false);
          return;
        }
        const joined = new Date().toISOString().slice(0, 10);
        users[u.toLowerCase()] = { user: u, email: em, pass: p, joined };
        localStorage.setItem("theia-users", JSON.stringify(users));
      } catch {}

      ctx.login(u, em);
      setLoading(false);
      // Reset form
      (document.getElementById("signupForm") as HTMLFormElement)?.reset();
      const target = ctx.pendingView || "v0";
      ctx.setPendingView(null);
      ctx.setActiveView(target);
    }, 450);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSignup();
  };

  return (
    <div className="auth-split">
      <div className="auth-form-col">
        <div className="auth-topbar-row">
          <span className="auth-eyebrow">{ctx.t("authSignupEyebrow")}</span>
          <button className="theme-btn auth-theme-toggle" title={ctx.t("thTitle")} aria-label={ctx.t("thTheme")} onClick={ctx.toggleTheme}>
            <span style={{ display: ctx.theme === "dark" ? "block" : "none" }}><IconMoon /></span>
            <span style={{ display: ctx.theme === "light" ? "block" : "none" }}><IconSun /></span>
          </button>
        </div>
        <div className="auth-view">
          <h2 className="auth-title">{ctx.t("authSignupTitle")}</h2>
          <p className="auth-sub">{ctx.t("authSignupSub")}</p>
          <form className="auth-card" id="signupForm" onSubmit={(e) => e.preventDefault()} noValidate>
            <div className={`auth-error ${error ? "show" : ""}`} role="alert">{error}</div>
            <div className="auth-field">
              <label htmlFor="signupUser">{ctx.t("authSignupUser")}</label>
              <input className="auth-input" id="signupUser" name="username" autoComplete="username" placeholder={ctx.t("authUserPlaceholder")} onKeyDown={handleKeyDown} />
            </div>
            <div className="auth-field">
              <label htmlFor="signupEmail">{ctx.t("authSignupEmail")}</label>
              <input className="auth-input" id="signupEmail" name="email" type="email" autoComplete="email" placeholder={ctx.t("authEmailPlaceholder")} onKeyDown={handleKeyDown} />
            </div>
            <div className="auth-field">
              <label htmlFor="signupPass">{ctx.t("authSignupPass")}</label>
              <div className="auth-pass-wrap">
                <input className="auth-input" id="signupPass" name="password" type={showPass ? "text" : "password"} autoComplete="new-password" placeholder={ctx.t("authSignupPassPlaceholder")} onKeyDown={handleKeyDown} />
                <button type="button" className="pass-toggle" data-revealed={showPass} onClick={() => setShowPass((p) => !p)} aria-label={showPass ? ctx.t("authHidePass") : ctx.t("authShowPass")} aria-pressed={showPass}>
                  <span className="icon-eye" style={{ display: showPass ? "none" : "block" }}><IconEye /></span>
                  <span className="icon-eye-off" style={{ display: showPass ? "block" : "none" }}><IconEyeOff /></span>
                </button>
              </div>
              <span className="auth-note">{ctx.t("authSignupPassNote")}</span>
            </div>
            <button className="auth-btn" type="submit" disabled={loading} onClick={handleSignup}>
              {loading ? ctx.t("authLoginLoading") : ctx.t("authSignupBtn")}
            </button>
          </form>
          <div className="auth-switch">
            <span>{ctx.t("authHaveAccount")}</span>{" "}
            <a onClick={() => ctx.setActiveView("auth-login")}>{ctx.t("authToLogin")}</a>
          </div>
          <div className="auth-demo">{ctx.t("authDemo")}</div>
        </div>
      </div>
      <div className="auth-art-col">
        <div className="auth-art" aria-hidden="true">
          <Image className="auth-art-photo" alt={ctx.t("authArtAlt")} src={ctx.theme === "dark" ? "/art/auth-art-dark.png" : "/art/auth-art-light.jpg"} fill unoptimized priority />
        </div>
        <div className="auth-quote">
          <span className="qmark" aria-hidden="true">{"“"}</span>
          <div className="qtext">
            <span>{ctx.t("authQuote")}</span>
            <span className="qwho">{ctx.t("authQuoteWho")}</span>
          </div>
        </div>
      </div>
    </div>
  );
}