// EL ↔ EN toggle. Shows the OTHER language as the click-to-switch label,
// matching the pattern used on the landing page so the two surfaces feel
// like one product.

import { useT } from "../i18n/useT";

export default function LangSwitch({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useT();
  const other = lang === "en" ? "el" : "en";
  return (
    <button
      type="button"
      onClick={() => setLang(other)}
      title={t("topbar.langTitle")}
      className={
        "rounded border border-panel-border px-2 py-1 font-mono text-[10px] tracking-widest text-panel-muted " +
        "transition-colors hover:border-threat-amber/60 hover:text-threat-amber " +
        className
      }
    >
      {other.toUpperCase()}
    </button>
  );
}
