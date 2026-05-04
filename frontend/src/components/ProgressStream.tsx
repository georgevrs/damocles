// Bottom-left strip — live WebSocket pipeline progress.

import { useEffect } from "react";
import { Activity } from "lucide-react";
import { openWatchProgressSocket } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import type { ProgressEvent } from "../types";

export default function ProgressStream({ className }: { className?: string }) {
  const { t } = useT();
  const activeWatch    = useDamocles((s) => s.activeWatch);
  const events         = useDamocles((s) => s.progressEvents);
  const appendProgress = useDamocles((s) => s.appendProgress);
  const markProgressDone = useDamocles((s) => s.markProgressDone);

  // Open + tear down the WebSocket lifecycle when activeWatch changes.
  useEffect(() => {
    if (!activeWatch) return;
    const ws = openWatchProgressSocket(
      activeWatch.id,
      (e) => {
        const ev = e as unknown as ProgressEvent;
        appendProgress(ev);
        if (ev.stage === "complete") markProgressDone();
      },
      () => { /* socket closed */ },
    );
    return () => ws.close();
  }, [activeWatch, appendProgress, markProgressDone]);

  const last = events.at(-1);

  return (
    <div className={"flex flex-col overflow-hidden bg-panel-bg " + (className ?? "")}>
      <div className="flex items-center gap-2 border-b border-panel-border px-3 py-1.5 text-xs text-panel-muted">
        <Activity size={13} />
        <span>{t("panel.progress")}</span>
        {last && (
          <span className="ml-auto font-mono text-[10px]">
            {last.progress_pct}% · {last.stage}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-snug">
        {events.length === 0 && (
          <p className="px-2 py-4 text-center text-panel-muted">
            {t("progress.empty")}
          </p>
        )}
        {events.map((e, i) => {
          const color =
            e.status === "complete" ? "text-threat-green" :
            e.status === "failed"   ? "text-threat-red"   :
            e.status === "skipped"  ? "text-threat-amber" :
                                      "text-panel-muted";
          return (
            <div key={i} className="flex gap-2">
              <span className="w-10 text-right text-panel-muted">{String(e.progress_pct).padStart(3)}%</span>
              <span className={"w-24 truncate " + color}>{e.stage}</span>
              <span className="w-16 text-panel-muted">{e.status}</span>
              <span className="flex-1 truncate text-panel-text">{e.detail}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
