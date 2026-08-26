"use client";

import { useDashboard } from "@/lib/dashboard-context";
import type { ViewId } from "@/lib/types";
import { IconMenu, IconGlobe, IconMoon, IconSun, IconUser, IconSignOut, IconLogIn, IconPlus } from "./icons";

const VIEW_KEYS: Record<string, string> = {
  v0: "view0", v1: "view1", v2: "view2", v3: "view3",
  v4: "view4", v5: "view5", v6: "view6", v7: "view7",
};

export function Topbar({ activeView, onChangeView, onOpenSidebar }: {
  activeView: ViewId;
  onChangeView: (id: ViewId) => void;
  onOpenSidebar: () => void;
}) {
  const ctx = useDashboard();

  const handleSignOut = () => {
    ctx.logout();
    ctx.setActiveView("auth-login");
  };

  return (
    <header className="topbar" data-od-id="topbar">
      <button className="nav-burger" onClick={onOpenSidebar} aria-label={ctx.t("tOpenNav")}>
        <IconMenu />
      </button>
      <h1>{ctx.t(VIEW_KEYS[activeView] || "view0")}</h1>
      <span className="grow" />
      <button className="ls-btn" onClick={() => ctx.setLangLayerOpen(true)} aria-label="Select language" aria-haspopup="dialog" aria-controls="langLayer">
        <IconGlobe />
        <span>{(ctx.lang === "en" ? "EN" : ctx.lang === "id" ? "ID" : "JP")}</span>
      </button>
      <button className="theme-btn" onClick={ctx.toggleTheme} title={ctx.t("thTitle")} aria-label={ctx.t("thTheme")}>
        <span style={{ display: ctx.theme === "dark" ? "block" : "none" }}><IconMoon /></span>
        <span style={{ display: ctx.theme === "light" ? "block" : "none" }}><IconSun /></span>
      </button>
      <div className="acc-wrap">
        <button className="acc-btn" onClick={() => ctx.setAccMenuOpen(!ctx.accMenuOpen)} aria-label={ctx.t("authAccLabel")} aria-haspopup="true" aria-expanded={ctx.accMenuOpen} title={ctx.t("authAccLabel")}>
          <IconUser />
          <span className="acc-dot" hidden={!ctx.isLoggedIn} />
        </button>
        <div className={`acc-menu ${ctx.accMenuOpen ? "open" : ""}`} role="menu" aria-label={ctx.t("authAccLabel")}>
          <div className="acc-mhead">
            <span className="acc-avatar">{ctx.session?.user?.charAt(0).toUpperCase() || "T"}</span>
            <span>
              <span className="acc-mname">{ctx.session?.user || "Operator"}</span><br />
              <span className="acc-mmail">{ctx.session?.email || "—"}</span>
            </span>
          </div>
          {ctx.isLoggedIn ? (
            <div className="acc-msigned">
              <button className="acc-mitem" role="menuitem" onClick={() => onChangeView("auth-account")}>
                <IconUser />
                <span>{ctx.t("authViewAccount")}</span>
              </button>
              <button className="acc-mitem signout" role="menuitem" onClick={handleSignOut}>
                <IconSignOut />
                <span>{ctx.t("authLogOut")}</span>
              </button>
            </div>
          ) : (
            <div className="acc-msigned">
              <div className="acc-guest">{ctx.t("authGuest")}</div>
              <button className="acc-mitem" role="menuitem" onClick={() => { onChangeView("auth-login"); ctx.setAccMenuOpen(false); }}>
                <IconLogIn />
                <span>{ctx.t("authSignIn")}</span>
              </button>
              <button className="acc-mitem" role="menuitem" onClick={() => { onChangeView("auth-signup"); ctx.setAccMenuOpen(false); }}>
                <IconPlus />
                <span>{ctx.t("authSignUp")}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}