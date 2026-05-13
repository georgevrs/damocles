// Global keyboard handler — Esc clears the active selection (AoI / vessel /
// citation chain) in priority order. Single source of truth so panels don't
// fight over the key. Mounted once in App.tsx.
//
// Also keeps the URL ?aoi= query parameter in sync with activeAoI so the
// analyst can copy/paste a permalink to a colleague.

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAoI } from "../api";
import { useDamocles } from "../store/damocles";

export default function EscToDeselect() {
  const setActiveAoI     = useDamocles((s) => s.setActiveAoI);
  const setActiveVessel  = useDamocles((s) => s.setActiveVessel);
  const setActiveFlight  = useDamocles((s) => s.setActiveFlight);
  const clearCitation    = useDamocles((s) => s.clearCitation);
  const activeAoIId      = useDamocles((s) => s.activeAoI?.id ?? null);
  const activeVessel     = useDamocles((s) => s.activeVessel);
  const activeFlight     = useDamocles((s) => s.activeFlight);
  const activeCitation   = useDamocles((s) => s.activeCitation);

  // Keep ?aoi= in sync with activeAoI (write side)
  useEffect(() => {
    const url = new URL(window.location.href);
    const current = url.searchParams.get("aoi");
    if (activeAoIId && current !== activeAoIId) {
      url.searchParams.set("aoi", activeAoIId);
      window.history.replaceState({}, "", url.toString());
    } else if (!activeAoIId && current) {
      url.searchParams.delete("aoi");
      window.history.replaceState({}, "", url.toString());
    }
  }, [activeAoIId]);

  // Read side — on mount, if ?aoi=… is present, open that AoI once data loads
  const { data: aois } = useQuery({
    queryKey: ["aoi"],
    queryFn:  () => fetchAoI("all"),
    staleTime: 15_000,
  });
  useEffect(() => {
    if (activeAoIId) return;   // already selected
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("aoi");
    if (!wanted || !aois) return;
    const match = aois.features.find((f) => f.id === wanted);
    if (match) setActiveAoI(match);
  }, [aois, activeAoIId, setActiveAoI]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Don't hijack Esc while typing in an input.
      const tag = (e.target as HTMLElement | null)?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      // Priority: dismiss the smallest selection first so Esc walks the analyst
      // "back" through their drill-down, the way a back button would.
      if (activeCitation) { clearCitation(); return; }
      if (activeFlight)   { setActiveFlight(null); return; }
      if (activeVessel)   { setActiveVessel(null); return; }
      if (activeAoIId)    { setActiveAoI(null); return; }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeAoIId, activeVessel, activeFlight, activeCitation,
      setActiveAoI, setActiveVessel, setActiveFlight, clearCitation]);

  return null;
}
