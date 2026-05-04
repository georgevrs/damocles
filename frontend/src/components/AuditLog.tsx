// Bottom-right strip — recent audit entries + Verify chain button.

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Lock, ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";
import { fetchAuditPage, verifyAuditChain } from "../api";
import { useT } from "../i18n/useT";

export default function AuditLog({ className }: { className?: string }) {
  const { t } = useT();
  const [verdictText, setVerdictText] = useState<string | null>(null);
  const [verdictOk, setVerdictOk] = useState<boolean | null>(null);

  const { data, refetch, isFetching } = useQuery({
    queryKey: ["audit"],
    queryFn:  () => fetchAuditPage(24, 50),
    refetchInterval: 5000,
  });

  const verify = useMutation({
    mutationFn: verifyAuditChain,
    onSuccess: (v) => {
      setVerdictOk(v.verified);
      setVerdictText(v.verdict);
    },
  });

  const total = data?.chain_total ?? 0;
  const verified = data?.verified ?? false;

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
        <button
          onClick={() => verify.mutate()}
          disabled={verify.isPending}
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
          <p className="px-2 py-4 text-center text-panel-muted">{t("audit.empty")}</p>
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
