// Bottom-right strip — recent audit entries + Verify chain button.
//
// In DEMO_MODE the header also exposes two adjacent buttons — "Tamper byte"
// and "Restore" — which are the W3-T1 gold-medal moment. The first flips a
// hex char in a middle-of-chain entry's chain_hash on disk; the second
// replays the file from an in-memory snapshot. After each click we
// auto-fire Verify so the audience sees the verdict colour flip
// (green → red → green).

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Lock, ShieldCheck, ShieldAlert, RefreshCw, Zap, RotateCcw } from "lucide-react";
import {
  fetchAuditPage,
  fetchHealth,
  verifyAuditChain,
  tamperAuditChain,
  restoreAuditChain,
} from "../api";
import { useT } from "../i18n/useT";

export default function AuditLog({ className }: { className?: string }) {
  const { t } = useT();
  const qc = useQueryClient();
  const [verdictText, setVerdictText] = useState<string | null>(null);
  const [verdictOk, setVerdictOk] = useState<boolean | null>(null);

  // Widen the window to 30 days — the 24h default returned 0 entries even
  // when the chain had 92 (E2E §11). The chip in the topbar said audit OK,
  // but this panel said "empty" because everything was older than 24h.
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["audit"],
    queryFn:  () => fetchAuditPage(24 * 30, 100),
    refetchInterval: 5000,
  });

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn:  fetchHealth,
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
  const demoMode = health?.demo_mode === true;

  const verify = useMutation({
    mutationFn: verifyAuditChain,
    onSuccess: (v) => {
      setVerdictOk(v.verified);
      setVerdictText(v.verdict);
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const tamper = useMutation({
    mutationFn: tamperAuditChain,
    onSuccess: (v) => {
      setVerdictOk(false);
      setVerdictText(v.verdict);
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      setVerdictOk(false);
      setVerdictText(`tamper failed: ${msg}`);
    },
  });

  const restore = useMutation({
    mutationFn: restoreAuditChain,
    onSuccess: (v) => {
      setVerdictOk(v.verified);
      setVerdictText(v.verdict);
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      setVerdictOk(false);
      setVerdictText(`restore failed: ${msg}`);
    },
  });

  const total = data?.chain_total ?? 0;
  const verified = data?.verified ?? false;
  const anyBusy = verify.isPending || tamper.isPending || restore.isPending;

  return (
    <div className={"flex flex-col overflow-hidden bg-panel-bg " + (className ?? "")}>
      <div className="flex items-center gap-2 border-b border-panel-border px-3 py-1.5 text-xs text-panel-muted">
        <Lock size={13} />
        <span>{t("panel.audit")}</span>
        <span className="ml-2 font-mono text-[10px]">{total}</span>
        <button
          onClick={() => refetch()}
          className="ml-auto text-panel-muted hover:text-panel-text"
          title="refresh"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
        </button>
        {demoMode && (
          <>
            <button
              onClick={() => tamper.mutate()}
              disabled={anyBusy}
              className="flex items-center gap-1 rounded border border-threat-red/40 px-1.5 py-0.5 text-[10px] text-threat-red hover:border-threat-red disabled:opacity-60"
              title="DEMO_MODE — flip a byte in the on-disk chain_hash"
            >
              <Zap size={11} />
              {tamper.isPending ? t("audit.tamper.busy") : t("audit.tamper.btn")}
            </button>
            <button
              onClick={() => restore.mutate()}
              disabled={anyBusy}
              className="flex items-center gap-1 rounded border border-panel-border px-1.5 py-0.5 text-[10px] hover:border-panel-text/40 disabled:opacity-60"
              title="DEMO_MODE — replay the pre-tamper snapshot"
            >
              <RotateCcw size={11} />
              {restore.isPending ? t("audit.restore.busy") : t("audit.restore.btn")}
            </button>
          </>
        )}
        <button
          onClick={() => verify.mutate()}
          disabled={anyBusy}
          className="flex items-center gap-1 rounded border border-panel-border px-1.5 py-0.5 text-[10px] hover:border-panel-text/40 disabled:opacity-60"
        >
          {verified
            ? <ShieldCheck size={11} className="text-threat-green" />
            : <ShieldAlert size={11} className="text-threat-amber" />}
          {verify.isPending ? t("audit.verifying") : t("audit.verify")}
        </button>
      </div>

      {verdictText && (
        <div
          className={
            "border-b border-panel-border px-3 py-1 text-[11px] " +
            (verdictOk ? "text-threat-green" : "text-threat-red")
          }
        >
          {verdictText}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-snug">
        {(!data || data.entries.length === 0) && (
          <p className="px-2 py-4 text-center text-panel-muted">
            {data && data.chain_total > 0
              ? `${data.chain_total} ${t("audit.older_window")}`
              : t("audit.empty")}
          </p>
        )}
        {data?.entries.map((e) => (
          <div key={e.id} className="flex gap-2">
            <span className="w-20 truncate text-panel-muted">
              {new Date(e.timestamp).toLocaleTimeString()}
            </span>
            <span className="w-24 truncate text-threat-amber/80">{e.action_type}</span>
            <span className="w-28 truncate text-panel-text">{e.actor}</span>
            <span className="flex-1 truncate text-panel-muted">
              {e.chain_hash.slice(0, 12)}…
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
