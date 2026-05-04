// Tiny zero-dep i18n hook for the operational frontend.
// Persists language choice in localStorage; defaults to English.

import { create } from "zustand";
import { STRINGS, type Lang } from "./strings";

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const initial: Lang = (() => {
  try {
    const v = localStorage.getItem("damocles.lang");
    if (v === "el" || v === "en") return v;
  } catch { /* localStorage may be blocked */ }
  return "en";
})();

export const useLang = create<LangState>((set) => ({
  lang: initial,
  setLang: (lang) => {
    try { localStorage.setItem("damocles.lang", lang); } catch { /* ignore */ }
    document.documentElement.lang = lang;
    set({ lang });
  },
}));

// Sync html[lang] on initial load.
if (typeof document !== "undefined") {
  document.documentElement.lang = initial;
}

/** Returns a `t(key)` function bound to the current language. Falls back to
 *  English if the key is missing in the active language; falls back to the
 *  raw key (so missing strings are obvious in dev) if not in either. */
export function useT() {
  const lang = useLang((s) => s.lang);
  const t = (key: string): string => {
    const dict = STRINGS[lang];
    if (key in dict) return dict[key];
    if (key in STRINGS.en) return STRINGS.en[key];
    return key;
  };
  return { lang, t, setLang: useLang.getState().setLang };
}
