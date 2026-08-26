"use client";

import { useEffect } from "react";
import { DashboardProvider, useDashboard } from "@/lib/dashboard-context";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { LanguageLayer } from "@/components/LanguageLayer";
import { Footer } from "@/components/Footer";
import { CommandCenter } from "@/components/views/CommandCenter";
import { DailyPipeline } from "@/components/views/DailyPipeline";
import { SmartWallets } from "@/components/views/SmartWallets";
import { ScreeningVeto } from "@/components/views/ScreeningVeto";
import { EdgeLab } from "@/components/views/EdgeLab";
import { PaperPositions } from "@/components/views/PaperPositions";
import { KnowledgeGraph } from "@/components/views/KnowledgeGraph";
import { OpsHarness } from "@/components/views/OpsHarness";
import { AuthLogin } from "@/components/views/AuthLogin";
import { AuthSignup } from "@/components/views/AuthSignup";
import { AuthAccount } from "@/components/views/AuthAccount";

const AUTH_VIEWS = ["auth-login", "auth-signup"];

function App() {
  const ctx = useDashboard();
  const isAuthView = AUTH_VIEWS.includes(ctx.activeView);

  useEffect(() => {
    if (!ctx.isLoggedIn && !AUTH_VIEWS.includes(ctx.activeView)) {
      ctx.setPendingView(ctx.activeView);
      ctx.setActiveView("auth-login");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      {!isAuthView && (
        <Sidebar
          activeView={ctx.activeView}
          collapsed={ctx.sidebarCollapsed}
          open={ctx.sidebarOpen}
          onChangeView={ctx.setActiveView}
          onToggle={() => ctx.setSidebarCollapsed(!ctx.sidebarCollapsed)}
          onClose={() => ctx.setSidebarOpen(false)}
        />
      )}
      <div className="sb-backdrop" hidden={!ctx.sidebarOpen} onClick={() => ctx.setSidebarOpen(false)} />
      <div className="app">
        {!isAuthView && (
          <Topbar
            activeView={ctx.activeView}
            onChangeView={ctx.setActiveView}
            onOpenSidebar={() => ctx.setSidebarOpen(true)}
          />
        )}
        <main id="views">
          <section id="view-v0" className={`view ${ctx.activeView === "v0" ? "active" : ""}`}>
            <CommandCenter />
          </section>
          <section id="view-v1" className={`view ${ctx.activeView === "v1" ? "active" : ""}`}>
            <DailyPipeline />
          </section>
          <section id="view-v2" className={`view ${ctx.activeView === "v2" ? "active" : ""}`}>
            <SmartWallets />
          </section>
          <section id="view-v3" className={`view ${ctx.activeView === "v3" ? "active" : ""}`}>
            <ScreeningVeto />
          </section>
          <section id="view-v4" className={`view ${ctx.activeView === "v4" ? "active" : ""}`}>
            <EdgeLab />
          </section>
          <section id="view-v5" className={`view ${ctx.activeView === "v5" ? "active" : ""}`}>
            <PaperPositions />
          </section>
          <section id="view-v6" className={`view ${ctx.activeView === "v6" ? "active" : ""}`}>
            <KnowledgeGraph />
          </section>
          <section id="view-v7" className={`view ${ctx.activeView === "v7" ? "active" : ""}`}>
            <OpsHarness />
          </section>
          <section id="view-auth-login" className={`view ${ctx.activeView === "auth-login" ? "active" : ""}`}>
            <AuthLogin />
          </section>
          <section id="view-auth-signup" className={`view ${ctx.activeView === "auth-signup" ? "active" : ""}`}>
            <AuthSignup />
          </section>
          <section id="view-auth-account" className={`view ${ctx.activeView === "auth-account" ? "active" : ""}`}>
            <AuthAccount />
          </section>
        </main>
        {!isAuthView && <Footer />}
      </div>
      <LanguageLayer
        open={ctx.langLayerOpen}
        lang={ctx.lang}
        onChangeLang={ctx.setLang}
        onClose={() => ctx.setLangLayerOpen(false)}
      />
    </>
  );
}

export function AppShell() {
  return (
    <DashboardProvider>
      <App />
    </DashboardProvider>
  );
}