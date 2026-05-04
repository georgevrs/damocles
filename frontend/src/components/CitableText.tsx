// CitableText — a clickable section text with confidence-tinted underline.
//
// THIS IS THE GOLD-MEDAL DEMO MOMENT. When a judge clicks a sentence,
// the click fires fetchCitationChain → setActiveCitation in the store.
// The MapPanel (already subscribed to activeCitation) flies to the
// source's coordinates; on Day 18 the GraphPanel highlights the cited
// node; on Day 19 an EvidenceModal opens with the raw SAR tile / news
// article / Telegram message.
//
// Confidence color coding (per the plan §9):
//   > 0.80  green-300  (strong, multi-source corroboration)
//   0.60-0.80  amber-300 (single trusted source)
//   < 0.60  red-300    (weak signal, speculative)

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchCitationChain } from "../api";
import { useDamocles } from "../store/damocles";
import type { CitationChain } from "../types";

function confidenceColor(c: number): string {
  if (c >= 0.8) return "decoration-emerald-400/70 hover:decoration-emerald-300";
  if (c >= 0.6) return "decoration-amber-400/70 hover:decoration-amber-300";
  return "decoration-rose-400/70 hover:decoration-rose-300";
}

function confidenceText(c: number): string {
  if (c >= 0.8) return "text-emerald-200";
  if (c >= 0.6) return "text-amber-200";
  return "text-rose-200";
}

interface Props {
  briefId: string;
  sectionId: string;
  text: string;
  confidence: number;
  citationCount: number;
}

export default function CitableText({ briefId, sectionId, text, confidence, citationCount }: Props) {
  const [busy, setBusy] = useState(false);
  const setActiveCitation = useDamocles((s) => s.setActiveCitation);
  const activeSectionId   = useDamocles((s) => s.activeSectionId);
  const isActive = activeSectionId === sectionId;

  const handleClick = async () => {
    if (busy || citationCount === 0) return;
    setBusy(true);
    try {
      const chain: CitationChain = await fetchCitationChain(briefId, sectionId);
      setActiveCitation(chain, sectionId);
    } catch (e) {
      console.error("citation chain fetch failed", e);
    } finally {
      setBusy(false);
    }
  };

  // No-citation safety: render plain text (still styled but not clickable).
  if (citationCount === 0) {
    return <p className="text-sm leading-relaxed text-panel-text/80">{text}</p>;
  }

  const tone = confidenceText(confidence);
  const dec  = confidenceColor(confidence);
  const ring = isActive ? "ring-1 ring-amber-400/40 bg-amber-400/5" : "hover:bg-panel-text/5";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      title={`Confidence ${(confidence * 100).toFixed(0)}% · ${citationCount} citation${citationCount === 1 ? "" : "s"} · click to trace sources`}
      className={
        "group block w-full cursor-pointer rounded-md px-2 py-1.5 text-left transition-all duration-150 " +
        ring + " disabled:cursor-progress"
      }
    >
      <span
        className={
          "underline decoration-dotted underline-offset-2 transition-colors text-sm leading-relaxed " +
          tone + " " + dec
        }
      >
        {text}
      </span>
      {busy && (
        <span className="ml-2 inline-flex items-center text-xs text-panel-muted">
          <Loader2 size={11} className="mr-1 animate-spin" />
          tracing…
        </span>
      )}
    </button>
  );
}
