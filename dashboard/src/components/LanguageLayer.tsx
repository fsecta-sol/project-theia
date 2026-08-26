import { useDashboard } from "@/lib/dashboard-context";
import type { Lang } from "@/lib/types";
import { IconClose, IconCheck } from "./icons";

const LANGUAGES: { code: Lang; key: string; descKey: string }[] = [
  { code: "en", key: "langEn", descKey: "" },
  { code: "id", key: "langId", descKey: "" },
  { code: "ja", key: "langJa", descKey: "" },
];

const CODE_MAP: Record<Lang, string> = { en: "EN", id: "ID", ja: "JP" };
const DESC_MAP: Record<Lang, string> = {
  en: "English (United States)",
  id: "Indonesia",
  ja: "Japan",
};

export function LanguageLayer({ open, lang, onChangeLang, onClose }: {
  open: boolean;
  lang: Lang;
  onChangeLang: (l: Lang) => void;
  onClose: () => void;
}) {
  const { t } = useDashboard();

  return (
    <div className="lang-layer" role="dialog" aria-modal="true" hidden={!open}>
      <div className="lang-card">
        <div className="lc-head">
          <h3>{t("langPick")}</h3>
          <span className="lc-sub">{t("langPickSub")}</span>
          <button className="lc-close" onClick={onClose} aria-label={t("langClose")}>
            <IconClose />
          </button>
        </div>
        {LANGUAGES.map((l) => (
          <div
            key={l.code}
            className="lang-opt"
            role="radio"
            tabIndex={0}
            data-lang={l.code}
            aria-checked={lang === l.code}
            onClick={() => { onChangeLang(l.code); onClose(); }}
            onKeyDown={(e) => { if (e.key === "Enter") { onChangeLang(l.code); onClose(); } }}
          >
            <span className="lo-code">{CODE_MAP[l.code]}</span>
            <span>
              <span className="lo-name">{t(l.key)}</span>
              <div className="lo-desc">{DESC_MAP[l.code]}</div>
            </span>
            <span className="lo-check"><IconCheck /></span>
          </div>
        ))}
      </div>
    </div>
  );
}