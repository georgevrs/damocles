// Top bar: free-text input + 4 quick-launch chips fed by /api/watches/templates.
// The chips are NOT a forced choice — selecting one populates the input
// but the analyst can edit freely (per the plan: "the analyst is not
// limited to presets").

import { useState } from "react";
import {
  Anchor, ArrowLeft, MapPin, Plane, Play, Radio, Search, Send, Loader2,
  ShieldCheck, ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createWatch, fetchHealth, fetchWatchTemplates, switchLlmProvider, verifyAuditChain } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import LangSwitch from "./LangSwitch";
import StandingCoverageBadge from "./StandingCoverageBadge";
import type { WatchTemplate } from "../types";

// Where the landing page lives. Served by the FastAPI backend at /landing/
// (mounted in backend/main.py) and proxied through Vite so the same path
// works in dev and prod. Override at deploy time via window.DAMOCLES_LANDING_URL.
const LANDING_URL =
  (typeof window !== "undefined" && (window as { DAMOCLES_LANDING_URL?: string }).DAMOCLES_LANDING_URL) ||
  "/landing/";

const ICONS: Record<string, LucideIcon> = {
  anchor:  Anchor,
  "map-pin": MapPin,
  plane:   Plane,
  radio:   Radio,
  search:  Search,
};

export default function WatchInput() {
  const { t } = useT();
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const setActiveWatch = useDamocles((s) => s.setActiveWatch);
  const resetProgress  = useDamocles((s) => s.resetProgress);
  const setActiveBrief = useDamocles((s) => s.setActiveBrief);
  const queryClient    = useQueryClient();

  const { data: templates } = useQuery<WatchTemplate[]>({
    queryKey: ["watch-templates"],
    queryFn:  fetchWatchTemplates,
    staleTime: Infinity,
  });

  const submit = async () => {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setErr(null);
    try {
      const w = await createWatch(text.trim());
      setActiveWatch(w);
      setActiveBrief(null);
      resetProgress();
      // Invalidate any cached lists so the new watch shows up
      queryClient.invalidateQueries({ queryKey: ["watches"] });
    } catch (e) {
      const msg = (e as Error).message ?? String(e);
      setErr(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-b border-panel-border bg-panel-bg px-4 py-2">
      <div className="mx-auto flex max-w-7xl flex-col gap-2">
        {/* Row 1 — brand · standing-coverage · system pill ↔ controls */}
        <div className="flex items-center gap-3">
          <a
            href={LANDING_URL}
            title={t("topbar.backTitle")}
            className="flex items-center gap-2 select-none rounded px-1 py-0.5 transition-colors hover:bg-panel-surface/50"
          >
            <ArrowLeft size={11} className="text-panel-muted" />
            <div className="h-3 w-3 rotate-45 rounded-sm bg-threat-amber" />
            <span className="font-mono text-sm tracking-wider text-panel-text">DAMOCLES</span>
            <span className="font-mono text-[9px] tracking-widest text-panel-muted">{t("topbar.back")}</span>
          </a>

          <StandingCoverageBadge />

          <div className="ml-auto flex items-center gap-2">
            <ScanCinemaButton />
            <SystemPill />
            <LangSwitch />
          </div>
        </div>

        {/* Row 2 — chips ↔ free-text input + Run */}
        <div className="flex items-center gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {templates?.map((tpl) => {
              const Icon = ICONS[tpl.icon] ?? Search;
              const active = text === tpl.query;
              return (
                <button
                  key={tpl.id}
                  type="button"
                  onClick={() => setText(tpl.query)}
                  className={
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors " +
                    (active
                      ? "border-threat-amber/50 bg-threat-amber/10 text-threat-amber"
                      : "border-panel-border text-panel-muted hover:border-panel-text/30 hover:text-panel-text")
                  }
                >
                  <Icon size={13} />
                  {tpl.label}
                </button>
              );
            })}
          </div>

          <div className="ml-auto flex flex-1 max-w-2xl items-center gap-2">
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
              placeholder={t("topbar.input.placeholder")}
              className="flex-1 rounded-md border border-panel-border bg-panel-surface px-3 py-2 text-sm
                         text-panel-text placeholder-panel-muted/60 outline-none
                         focus:border-threat-amber/40"
              disabled={submitting}
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={submitting || !text.trim()}
              className="flex items-center gap-1.5 rounded-md bg-threat-amber/90 px-3 py-2 text-xs font-medium
                         text-black hover:bg-threat-amber disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {submitting ? t("topbar.btn.running") : t("topbar.btn.run")}
            </button>
          </div>
        </div>
      </div>
      {err && (
        <div className="mx-auto mt-2 max-w-7xl text-xs text-threat-red">Error: {err}</div>
      )}
    </div>
  );
}

// Combined LLM + audit pill. Single bordered chip with three sub-segments:
//   ● <model>   │   ✓ audit OK · 41   │
// Both segments share one border so the row reads as one unit instead of
// two free-floating badges.
function SystemPill() {
  const { t } = useT();
  const qc = useQueryClient();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
  const { data: verdict } = useQuery({
    queryKey: ["audit-verify"],
    queryFn: verifyAuditChain,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  // W3-T2: click the model segment to swap provider Gemini ↔ Ollama.
  // The button only fires when health is loaded so we know which way to flip.
  const swap = useMutation({
    mutationFn: (target: "gemini" | "ollama") => switchLlmProvider(target),
    onSettled: () => qc.invalidateQueries({ queryKey: ["health"] }),
  });
  const demoMode = health?.demo_mode === true;
  const currentProvider = health?.llm?.provider as "gemini" | "ollama" | undefined;
  const swapTarget: "gemini" | "ollama" =
    currentProvider === "ollama" ? "gemini" : "ollama";

  const llmOk    = health?.llm?.ok === true;
  const llmModel = (health?.llm?.model ?? "").replace("gemini-", "") || "—";

  const auditOk    = verdict?.verified === true;
  const auditTotal = verdict?.chain_total ?? 0;
  const auditEmpty = !verdict || auditTotal === 0;
  const auditLabel = auditEmpty ? t("topbar.audit.empty")
                   : auditOk     ? `${t("topbar.audit.ok")} · ${auditTotal}`
                                 : `${t("topbar.audit.tamper")} ${verdict?.first_bad_index}`;
  const auditTone  = auditEmpty ? "text-amber-300"
                   : auditOk     ? "text-emerald-300"
                                 : "text-rose-300";
  const AuditIcon  = auditOk ? ShieldCheck : ShieldAlert;

  return (
    <div
      className="flex items-center divide-x divide-panel-border/60 rounded border border-panel-border font-mono text-[10px]"
      title={verdict?.verdict ?? "system status"}
    >
      {health?.llm && (
        demoMode ? (
          <button
            type="button"
            onClick={() => swap.mutate(swapTarget)}
            disabled={swap.isPending || !currentProvider}
            className="flex items-center gap-1.5 px-2 py-0.5 hover:bg-panel-border/40 disabled:opacity-60"
            title={`click to swap to ${swapTarget}`}
          >
            <span className={"h-1.5 w-1.5 rounded-full " + (llmOk ? "bg-emerald-400" : "bg-rose-400")} />
            <span className="text-panel-text">{swap.isPending ? "swapping…" : llmModel}</span>
          </button>
        ) : (
          <div className="flex items-center gap-1.5 px-2 py-0.5">
            <span className={"h-1.5 w-1.5 rounded-full " + (llmOk ? "bg-emerald-400" : "bg-rose-400")} />
            <span className="text-panel-text">{llmModel}</span>
          </div>
        )
      )}
      <div className={"flex items-center gap-1.5 px-2 py-0.5 " + auditTone}>
        <AuditIcon size={11} />
        <span>{auditLabel}</span>
      </div>
    </div>
  );
}

// W3-T4 scan cinema button. Opens a WebSocket to /ws/scan-cinema and
// drips the snapshot AoIs into the damocles store one feature at a time.
// The MapPanel renders ``cinemaFeatures`` whenever ``cinemaActive`` is on,
// so the polygons pop in as frames arrive. GREEN→AMBER→RED ordering on
// the backend means the demo's six RED AoIs land last for the punchline.
function ScanCinemaButton() {
  const cinemaActive   = useDamocles((s) => s.cinemaActive);
  const cinemaTotal    = useDamocles((s) => s.cinemaTotal);
  const cinemaCount    = useDamocles((s) => s.cinemaFeatures.length);
  const cinemaStart    = useDamocles((s) => s.cinemaStart);
  const cinemaAdd      = useDamocles((s) => s.cinemaAddFeature);
  const cinemaStop     = useDamocles((s) => s.cinemaStop);

  function onClick() {
    if (cinemaActive) {
      cinemaStop();
      return;
    }
    // Vite dev-server proxies /ws to the FastAPI backend (see vite.config.ts).
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/scan-cinema?delay_ms=160`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "start") {
          cinemaStart(msg.total ?? 0);
        } else if (msg.type === "aoi" && msg.feature) {
          cinemaAdd(msg.feature);
        } else if (msg.type === "complete") {
          ws.close();
          // Hold the final frame for 1.2s so the audience reads RED,
          // then let the cached aoi query take back over seamlessly
          // (same features, no visual diff).
          window.setTimeout(() => cinemaStop(), 1200);
        }
      } catch { /* malformed frame — ignore */ }
    };
    ws.onerror = () => cinemaStop();
    ws.onclose = (e) => { if (!e.wasClean) cinemaStop(); };
  }

  const label = cinemaActive
    ? `${cinemaCount}/${cinemaTotal || "…"}`
    : "Play scan";

  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10px] " +
        (cinemaActive
          ? "border-threat-amber/60 text-threat-amber"
          : "border-panel-border text-panel-text hover:bg-panel-border/40")
      }
      title="DEMO — replay the standing-scan AoI surface"
    >
      <Play size={11} />
      <span>{label}</span>
    </button>
  );
}
