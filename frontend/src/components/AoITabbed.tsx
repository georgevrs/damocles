// AoITabbed — wraps Brief / DNA / Detail into a 3-tab inner pane that lives
// inside the BriefPanel when an AoI is active.
//
// Tab order is deliberate — Brief first because that is the gold-medal
// demo moment. Brief auto-fires the agent pipeline the first time the
// analyst lands on the tab; subsequent visits show the rendered sections.
//
// Switching to a different AoI clears the previous brief from the store
// so we never show AoI A's BLUF after the analyst has moved to AoI B.

import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, FileText, Layers, Sparkles, AlertTriangle, Activity, ShieldAlert } from "lucide-react";
import AoIDetail from "./AoIDetail";
import InformationDNA from "./InformationDNA";
import CitableText from "./CitableText";
import CitationExpansion from "./CitationExpansion";
import { generateAoIBrief, type AoIFeature } from "../api";
import type { Brief, BriefSection } from "../types";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

type Tab = "brief" | "dna" | "detail";

const SECTION_ORDER: Record<string, number> = {
  BLUF: 0, KEY_JUDGMENT: 1, SUPPORTING: 2, DEVILS_ADVOCATE: 3, RECOMMENDATION: 4,
};

function sectionAccent(t: string): string {
  switch (t) {
    case "BLUF":            return "border-amber-400/40 bg-amber-400/5";
    case "DEVILS_ADVOCATE": return "border-rose-400/30 bg-rose-400/5";
    case "RECOMMENDATION":  return "border-emerald-400/30 bg-emerald-400/5";
    default:                return "border-panel-border";
  }
}

export default function AoITabbed({ aoi }: { aoi: AoIFeature }) {
  const { t } = useT();
  const [tab, setTab] = useState<Tab>("brief");
  const setActiveBrief = useDamocles((s) => s.setActiveBrief);
  const activeBrief    = useDamocles((s) => s.activeBrief);

  const mutation = useMutation({
    mutationFn: () => generateAoIBrief(aoi.id),
    onSuccess: (b: Brief) => setActiveBrief(b),
  });

  // Clear previous AoI's brief when switching AoIs (avoids stale BLUF flash)
  useEffect(() => {
    setActiveBrief(null);
    mutation.reset();
    setTab("brief");
    // Eagerly auto-fire brief generation when the analyst lands on a new
    // AoI — saves the extra click that the demo script glosses over.
    if (aoi.properties.threat_grade === "RED" || aoi.properties.threat_grade === "AMBER") {
      mutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aoi.id]);

  // Whether the current activeBrief is for THIS aoi (synthetic watch_id pattern).
  const briefIsForThisAoI = !!activeBrief && activeBrief.watch_id === `aoi-watch-${aoi.id}`;

  return (
    <div className="space-y-2">
      <TabBar tab={tab} setTab={setTab} t={t} hasBrief={briefIsForThisAoI} pending={mutation.isPending} />

      {tab === "brief" && (
        <BriefTab
          briefIsForThisAoI={briefIsForThisAoI}
          isPending={mutation.isPending}
          isError={mutation.isError}
          mutate={() => mutation.mutate()}
          t={t}
        />
      )}

      {tab === "dna" && (
        <div className="h-[440px] overflow-hidden rounded-md border border-panel-border bg-panel-surface/30">
          <InformationDNA />
        </div>
      )}

      {tab === "detail" && <AoIDetail aoi={aoi} />}
    </div>
  );
}

function BriefTab({
  briefIsForThisAoI, isPending, isError, mutate, t,
}: {
  briefIsForThisAoI: boolean;
  isPending: boolean;
  isError: boolean;
  mutate: () => void;
  t: (k: string) => string;
}) {
  const activeBrief = useDamocles((s) => s.activeBrief);
  const sections = (activeBrief?.sections ?? []).slice().sort(
    (a, b) => (SECTION_ORDER[a.section_type] ?? 99) - (SECTION_ORDER[b.section_type] ?? 99),
  );

  if (isPending) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-panel-border bg-panel-surface/40 px-3 py-3 text-[11px] text-panel-muted">
        <Loader2 size={13} className="animate-spin" />
        <span>{t("aoi.brief.generating")}</span>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 rounded-md border border-rose-400/40 bg-rose-400/5 px-3 py-2 text-[11px] text-rose-200">
          <AlertTriangle size={13} />
          <span>{t("aoi.brief.error")}</span>
        </div>
        <button
          type="button"
          onClick={mutate}
          className="w-full rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-[12px] font-mono text-amber-200 hover:bg-amber-400/15"
        >
          {t("aoi.brief.cta")}
        </button>
      </div>
    );
  }
  if (!briefIsForThisAoI || !activeBrief) {
    return (
      <button
        type="button"
        onClick={mutate}
        className="w-full rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-[12px] font-mono text-amber-200 hover:bg-amber-400/15"
      >
        {t("aoi.brief.cta")}
      </button>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-md border border-panel-border bg-panel-surface/40 px-2 py-1.5 text-[10px] text-panel-muted">
        <span className="font-mono">brief {activeBrief.id.slice(0, 8)}</span>
        <span className="ml-auto">{t("brief.cite.click")}</span>
      </div>
      {sections.map((s) => (
        <SectionCard key={s.id} section={s} briefId={activeBrief.id} t={t} />
      ))}
    </div>
  );
}

function SectionCard({ section, briefId, t }: { section: BriefSection; briefId: string; t: (k: string) => string }) {
  const activeSectionId = useDamocles((s) => s.activeSectionId);
  const activeCitation  = useDamocles((s) => s.activeCitation);
  const isActive = activeSectionId === section.id;
  const accent = sectionAccent(section.section_type);
  const label  = t(`brief.section.${section.section_type}`);
  const devilConf = section.section_type === "DEVILS_ADVOCATE"
    ? (section.extra?.devil_confidence as number | undefined)
    : undefined;
  const urgency = section.section_type === "RECOMMENDATION"
    ? (section.extra?.urgency as string | undefined)
    : undefined;

  return (
    <div className={"rounded-md border p-3 transition-colors " + accent}>
      <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider text-panel-muted">
        {section.section_type === "DEVILS_ADVOCATE" && (<ShieldAlert size={11} className="text-rose-300" />)}
        {section.section_type === "RECOMMENDATION" && (<Activity size={11} className="text-emerald-300" />)}
        <span>{label}</span>
        {urgency && (
          <span className="rounded border border-amber-400/40 bg-amber-500/30 px-1.5 py-0.5 font-mono text-[9px] text-amber-100">
            {urgency}
          </span>
        )}
        {devilConf !== undefined ? (
          <span className="ml-auto rounded border border-rose-400/30 px-1.5 py-0.5 font-mono text-[10px] text-rose-200">
            devil {(devilConf * 100).toFixed(0)}%
          </span>
        ) : (
          <span className="ml-auto font-mono text-[10px]">{(section.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      <CitableText
        briefId={briefId}
        sectionId={section.id}
        text={section.text}
        confidence={section.confidence}
        citationCount={section.citation_node_ids.length}
      />
      {section.citation_node_ids.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1 px-2">
          {section.citation_node_ids.map((cid) => (
            <span
              key={cid}
              className={
                "rounded px-1 py-0.5 font-mono text-[9px] " +
                (cid.startsWith("aoi-")
                  ? "bg-amber-400/20 text-amber-200 border border-amber-400/40"
                  : "bg-panel-border/60 text-panel-muted")
              }
              title={cid}
            >
              {cid.startsWith("aoi-") ? "aoi://" + cid.slice(4, 12) : cid.slice(0, 8)}
            </span>
          ))}
        </div>
      )}
      {isActive && activeCitation && <CitationExpansion chain={activeCitation} />}
    </div>
  );
}

function TabBar({
  tab, setTab, t, hasBrief, pending,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  t: (k: string) => string;
  hasBrief: boolean;
  pending: boolean;
}) {
  const tabs: { id: Tab; label: string; Icon: typeof Layers; badge?: string }[] = [
    {
      id: "brief",
      label: t("dna.tab.brief"),
      Icon: FileText,
      badge: pending ? "…" : (hasBrief ? "•" : undefined),
    },
    { id: "dna",    label: t("dna.tab.dna"),    Icon: Sparkles },
    { id: "detail", label: t("dna.tab.detail"), Icon: Layers },
  ];
  return (
    <div className="flex gap-1 rounded-md border border-panel-border bg-panel-surface/30 p-1 text-[11px]">
      {tabs.map(({ id, label, Icon, badge }) => {
        const active = id === tab;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={
              "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1 transition-colors " +
              (active
                ? "bg-amber-400/15 text-amber-200"
                : "text-panel-muted hover:text-panel-text")
            }
          >
            <Icon size={11} />
            <span className="font-mono uppercase tracking-wider">{label}</span>
            {badge && <span className="font-mono text-amber-300">{badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
