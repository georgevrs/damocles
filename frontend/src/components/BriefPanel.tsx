// BriefPanel — center column with citation-aware section rendering.
//
// Each section is wrapped in a CitableText that fires the citation chain
// on click. When the click resolves, CitationExpansion renders the
// resolved source nodes inline below the active section.
//
// Side effects of clicking a section:
//   - The MapPanel flies to the source coordinates (already wired via store)
//   - The GraphPanel will highlight the cited node (Day 18)
//   - An EvidenceModal will open with the raw source (Day 19)

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Loader2, ShieldAlert, Activity } from "lucide-react";
import { fetchBrief, listBriefsForWatch } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import type { BriefSection } from "../types";
import AoITabbed from "./AoITabbed";
import AoITriageList from "./AoITriageList";
import VesselDetail from "./VesselDetail";
import FlightDetail from "./FlightDetail";
import CitableText from "./CitableText";
import CitationExpansion from "./CitationExpansion";

function sectionAccent(t: string): string {
  switch (t) {
    case "BLUF":            return "border-amber-400/40 bg-amber-400/5";
    case "DEVILS_ADVOCATE": return "border-rose-400/30 bg-rose-400/5";
    case "RECOMMENDATION":  return "border-emerald-400/30 bg-emerald-400/5";
    default:                return "border-panel-border";
  }
}

function urgencyChip(urgency: string | undefined): string {
  switch (urgency) {
    case "IMMEDIATE": return "bg-rose-500/30 text-rose-100 border-rose-400/40";
    case "PRIORITY":  return "bg-amber-500/30 text-amber-100 border-amber-400/40";
    default:          return "bg-emerald-500/30 text-emerald-100 border-emerald-400/40";
  }
}

function SectionCard({ section, briefId }: { section: BriefSection; briefId: string }) {
  const { t } = useT();
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
        {section.section_type === "DEVILS_ADVOCATE" && (
          <ShieldAlert size={11} className="text-rose-300" />
        )}
        {section.section_type === "RECOMMENDATION" && (
          <Activity size={11} className="text-emerald-300" />
        )}
        <span>{label}</span>
        {section.agent_source && (
          <span className="rounded bg-panel-border/60 px-1 py-0.5 text-[9px] font-mono normal-case text-panel-muted">
            {section.agent_source}
          </span>
        )}
        {urgency && (
          <span className={"rounded border px-1.5 py-0.5 font-mono text-[9px] " + urgencyChip(urgency)}>
            {urgency}
          </span>
        )}
        {devilConf !== undefined && (
          <span className="ml-auto rounded border border-rose-400/30 px-1.5 py-0.5 font-mono text-[10px] text-rose-200">
            devil {(devilConf * 100).toFixed(0)}%
          </span>
        )}
        {devilConf === undefined && (
          <span className="ml-auto font-mono text-[10px]">
            {(section.confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <CitableText
        briefId={briefId}
        sectionId={section.id}
        text={section.text}
        confidence={section.confidence}
        citationCount={section.citation_node_ids.length}
      />

      {/* Tiny citation-id badges row */}
      {section.citation_node_ids.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1 px-2">
          {section.citation_node_ids.map((cid) => (
            <span
              key={cid}
              className="rounded bg-panel-border/60 px-1 py-0.5 font-mono text-[9px] text-panel-muted"
              title={cid}
            >
              {cid.slice(0, 8)}
            </span>
          ))}
        </div>
      )}

      {isActive && activeCitation && (
        <CitationExpansion chain={activeCitation} />
      )}
    </div>
  );
}

const SECTION_ORDER: Record<string, number> = {
  BLUF:             0,
  KEY_JUDGMENT:     1,
  SUPPORTING:       2,
  DEVILS_ADVOCATE:  3,
  RECOMMENDATION:   4,
};

export default function BriefPanel({ className }: { className?: string }) {
  const { t } = useT();
  const activeWatch    = useDamocles((s) => s.activeWatch);
  const activeBrief    = useDamocles((s) => s.activeBrief);
  const setActiveBrief = useDamocles((s) => s.setActiveBrief);
  const activeAoI      = useDamocles((s) => s.activeAoI);
  const activeVessel   = useDamocles((s) => s.activeVessel);
  const activeFlight   = useDamocles((s) => s.activeFlight);

  const { data: briefSummaries } = useQuery({
    queryKey: ["briefs", activeWatch?.id],
    queryFn:  () => activeWatch ? listBriefsForWatch(activeWatch.id) : Promise.resolve([]),
    enabled:  !!activeWatch,
    refetchInterval: activeBrief ? false : 3000,
  });

  const latestId = briefSummaries?.[0]?.id;
  const { data: brief } = useQuery({
    queryKey: ["brief", latestId],
    queryFn:  () => latestId ? fetchBrief(latestId) : Promise.resolve(null),
    enabled:  !!latestId,
  });

  useEffect(() => { if (brief) setActiveBrief(brief); }, [brief, setActiveBrief]);

  const sections = (activeBrief?.sections ?? []).slice().sort(
    (a, b) => (SECTION_ORDER[a.section_type] ?? 99) - (SECTION_ORDER[b.section_type] ?? 99),
  );

  return (
    <div className={"flex flex-col overflow-hidden border-x border-panel-border bg-panel-bg " + (className ?? "")}>
      <div className="flex items-center gap-2 border-b border-panel-border px-3 py-2 text-xs text-panel-muted">
        <FileText size={14} />
        <span>{t("panel.brief")}</span>
        {activeWatch && (
          <span className="ml-auto truncate font-mono text-[10px]">
            watch {activeWatch.id.slice(0, 8)}
          </span>
        )}
        {activeBrief && (
          <span className="font-mono text-[10px]">· brief {activeBrief.id.slice(0, 8)}</span>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {/* Selection cards — pinned to the top whenever a vessel or AoI
            is active. Both can be active simultaneously (vessel inside AoI). */}
        {activeFlight && <FlightDetail flight={activeFlight} />}
        {activeVessel && <VesselDetail vessel={activeVessel} />}
        {activeAoI    && <AoITabbed    aoi={activeAoI} />}

        {!activeWatch && !activeAoI && !activeVessel && !activeFlight && (
          <AoITriageList />
        )}
        {activeWatch && !activeBrief && <BriefSkeleton />}
        {activeBrief && (
          <>
            <div className="rounded-md border border-panel-border bg-panel-surface/40 p-2 text-[11px] text-panel-muted">
              {t("brief.cite.click")}
            </div>
            {sections.map((s) => (
              <SectionCard key={s.id} section={s} briefId={activeBrief.id} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// Shimmer placeholders that match the eventual section layout — analyst sees
// SOMETHING the moment they hit "Run watch", not a 60-second blank state.
function BriefSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-panel-muted">
        <Loader2 size={13} className="animate-spin" />
        <span>Pipeline running — sensors, fusion, four agents…</span>
      </div>
      {/* BLUF placeholder */}
      <div className="rounded-md border border-amber-400/30 bg-amber-400/5 p-3">
        <div className="mb-2 h-2 w-32 skeleton" />
        <div className="space-y-1.5">
          <div className="h-3 w-full skeleton" />
          <div className="h-3 w-[92%] skeleton" />
          <div className="h-3 w-[78%] skeleton" />
        </div>
      </div>
      {/* Key judgments */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-md border border-panel-border p-3">
          <div className="mb-2 h-2 w-24 skeleton" />
          <div className="space-y-1.5">
            <div className="h-3 w-[88%] skeleton" />
            <div className="h-3 w-[72%] skeleton" />
          </div>
        </div>
      ))}
      {/* Devil + Recommendation */}
      <div className="rounded-md border border-rose-400/30 p-3">
        <div className="mb-2 h-2 w-28 skeleton" />
        <div className="h-3 w-[80%] skeleton" />
      </div>
      <div className="rounded-md border border-emerald-400/30 p-3">
        <div className="mb-2 h-2 w-28 skeleton" />
        <div className="h-3 w-[60%] skeleton" />
      </div>
    </div>
  );
}
