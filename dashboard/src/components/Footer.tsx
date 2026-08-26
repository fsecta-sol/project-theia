import { useDashboard } from "@/lib/dashboard-context";

export function Footer() {
  const { t } = useDashboard();
  return (
    <footer className="pagefoot" data-od-id="footer" style={{ padding: "14px 24px", borderTop: "1px solid var(--border)", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--muted)", display: "flex", gap: "20px", flexWrap: "wrap", alignItems: "center" }}>
      <span>{t("foot1")}</span>
      <span>{t("foot2")}</span>
      <span className="grow" style={{ flex: 1 }} />
      <span>{t("foot3")}</span>
    </footer>
  );
}