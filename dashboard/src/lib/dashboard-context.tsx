"use client";

import { createContext, useContext, useState, useEffect, useCallback, useSyncExternalStore } from "react";
import type { ViewId, Lang } from "./types";
import { t } from "./i18n";

export type Theme = "dark" | "light";

export interface UserSession {
  user: string;
  email: string;
  joined: string;
  since: string;
}

const SESS_KEY = "theia-session";

interface DashboardContextType {
  theme: Theme;
  setTheme: (th: Theme) => void;
  toggleTheme: () => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  activeView: ViewId;
  setActiveView: (v: ViewId) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (c: boolean) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (o: boolean) => void;
  langLayerOpen: boolean;
  setLangLayerOpen: (o: boolean) => void;
  accMenuOpen: boolean;
  setAccMenuOpen: (o: boolean) => void;
  session: UserSession | null;
  login: (user: string, email?: string) => void;
  logout: () => void;
  isLoggedIn: boolean;
  pendingView: ViewId | null;
  setPendingView: (v: ViewId | null) => void;
  t: (key: string) => string;
  hydrated: boolean;
}

const DashboardContext = createContext<DashboardContextType>(null!);

export function useDashboard() {
  return useContext(DashboardContext);
}

function getStorage<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function setStorage<T>(key: string, value: T) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const saved = localStorage.getItem("theia-theme");
  return saved === "light" ? "light" : "dark";
}

function getLang(): Lang {
  if (typeof window === "undefined") return "en";
  const saved = localStorage.getItem("theia-lang");
  if (saved === "en" || saved === "id" || saved === "ja") return saved;
  return "en";
}

function getView(): ViewId {
  if (typeof window === "undefined") return "v0";
  return (localStorage.getItem("theia-view") as ViewId) || "v0";
}

// Only login/signup hide the app shell (sidebar, topbar, footer).
// The account view keeps the full shell, matching the source's showView().
const AUTH_VIEWS: ViewId[] = ["auth-login", "auth-signup"];

const emptySubscribe = () => () => {};
const getServerHydrated = () => false;
const getClientHydrated = () => true;

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  // Persisted preferences are read lazily once on first render. The tree only
  // mounts after ClientOnly has hydrated, so window/localStorage are safe here.
  const [theme, setThemeState] = useState<Theme>(() => getTheme());
  const [lang, setLangState] = useState<Lang>(() => getLang());
  const [activeView, setActiveViewState] = useState<ViewId>(() => getView());
  const [sidebarCollapsedState, setSidebarCollapsedState] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= 1100
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const sidebarCollapsed = sidebarCollapsedState;
  const [langLayerOpen, setLangLayerOpen] = useState(false);
  const [accMenuOpen, setAccMenuOpen] = useState(false);
  const [session, setSession] = useState<UserSession | null>(() =>
    getStorage<UserSession | null>(SESS_KEY, null)
  );
  const [pendingView, setPendingView] = useState<ViewId | null>(null);
  const hydrated = useSyncExternalStore(emptySubscribe, getClientHydrated, getServerHydrated);

  // Apply theme to body
  useEffect(() => {
    document.body.classList.toggle("light", theme === "light");
    if (hydrated) localStorage.setItem("theia-theme", theme);
  }, [theme, hydrated]);

  // Apply lang
  useEffect(() => {
    document.documentElement.lang = lang;
    document.body.setAttribute("data-lang", lang);
    if (hydrated) localStorage.setItem("theia-lang", lang);
  }, [lang, hydrated]);

  // Persist view
  useEffect(() => {
    if (hydrated) localStorage.setItem("theia-view", activeView);
  }, [activeView, hydrated]);

  // Drawer body class
  useEffect(() => {
    document.body.classList.toggle("drawer-open", sidebarOpen);
  }, [sidebarOpen]);

  // Auth-page body class
  const isAuthView = AUTH_VIEWS.includes(activeView);
  useEffect(() => {
    document.body.classList.toggle("auth-page", isAuthView);
  }, [isAuthView]);

  const setTheme = useCallback((th: Theme) => setThemeState(th), []);
  const toggleTheme = useCallback(() => setThemeState((th) => (th === "dark" ? "light" : "dark")), []);
  const setLang = useCallback((l: Lang) => setLangState(l), []);
  const setActiveView = useCallback((v: ViewId) => {
    setActiveViewState(v);
    setAccMenuOpen(false);
  }, []);

  const login = useCallback((user: string, email?: string) => {
    const joined = new Date().toISOString().slice(0, 10);
    const since = new Date().toLocaleString();
    const rec: UserSession = { user, email: email || "", joined, since };
    setSession(rec);
    setStorage(SESS_KEY, rec);
  }, []);

  const logout = useCallback(() => {
    setSession(null);
    setPendingView(null);
    localStorage.removeItem(SESS_KEY);
  }, []);

  const isLoggedIn = !!session;

  const setSidebarCollapsed = useCallback((c: boolean) => {
    setSidebarCollapsedState(c);
    if (typeof window !== "undefined") {
      try { localStorage.setItem("theia-rail", c ? "collapsed" : "expanded"); } catch {}
    }
  }, []);

  const translate = useCallback(
    (key: string) => t(lang, key),
    [lang]
  );

  return (
    <DashboardContext.Provider
      value={{
        theme,
        setTheme,
        toggleTheme,
        lang,
        setLang,
        activeView,
        setActiveView,
        sidebarCollapsed,
        setSidebarCollapsed,
        sidebarOpen,
        setSidebarOpen,
        langLayerOpen,
        setLangLayerOpen,
        accMenuOpen,
        setAccMenuOpen,
        session,
        login,
        logout,
        isLoggedIn,
        pendingView,
        setPendingView,
        t: translate,
        hydrated,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}