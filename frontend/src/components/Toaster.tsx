// Minimal toast system — zustand store + Toaster sink.
//
// Used to surface React Query failures that would otherwise vanish into
// console.error. The original audit flagged "silent failures kill analyst
// trust." Toasts auto-dismiss after 6s; analyst can click to dismiss.

import { useEffect } from "react";
import { create } from "zustand";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

export type ToastKind = "error" | "warn" | "info" | "success";

interface ToastItem {
  id:      number;
  kind:    ToastKind;
  text:    string;
  detail?: string;
  ttlMs:   number;
}

interface ToastState {
  items: ToastItem[];
  push:  (t: Omit<ToastItem, "id" | "ttlMs"> & { ttlMs?: number }) => number;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToasts = create<ToastState>((set) => ({
  items: [],
  push: (t) => {
    const id = nextId++;
    set((s) => ({ items: [...s.items, { ttlMs: 6000, id, ...t }] }));
    return id;
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

// Public helpers — short imports for component code.
export const toastError = (text: string, detail?: string) =>
  useToasts.getState().push({ kind: "error", text, detail });
export const toastWarn  = (text: string, detail?: string) =>
  useToasts.getState().push({ kind: "warn",  text, detail });
export const toastInfo  = (text: string, detail?: string) =>
  useToasts.getState().push({ kind: "info",  text, detail });
export const toastOk    = (text: string, detail?: string) =>
  useToasts.getState().push({ kind: "success", text, detail });

const KIND_ACCENT: Record<ToastKind, string> = {
  error:   "border-rose-400/50 bg-rose-400/10 text-rose-100",
  warn:    "border-amber-400/50 bg-amber-400/10 text-amber-100",
  info:    "border-cyan-400/40 bg-cyan-400/10 text-cyan-100",
  success: "border-emerald-400/50 bg-emerald-400/10 text-emerald-100",
};

const KIND_ICON = {
  error:   AlertTriangle,
  warn:    AlertTriangle,
  info:    Info,
  success: CheckCircle2,
};

export default function Toaster() {
  const items = useToasts((s) => s.items);
  const dismiss = useToasts((s) => s.dismiss);

  // Schedule auto-dismiss for any new item.
  useEffect(() => {
    const timers = items.map((t) => window.setTimeout(() => dismiss(t.id), t.ttlMs));
    return () => { timers.forEach(window.clearTimeout); };
  }, [items, dismiss]);

  if (items.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {items.map((t) => {
        const Icon = KIND_ICON[t.kind];
        return (
          <div
            key={t.id}
            className={
              "pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 " +
              "shadow-lg backdrop-blur-sm " + KIND_ACCENT[t.kind]
            }
          >
            <Icon size={14} className="mt-0.5 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] leading-tight">{t.text}</div>
              {t.detail && (
                <div className="mt-0.5 truncate font-mono text-[10px] opacity-70">{t.detail}</div>
              )}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="flex-shrink-0 rounded text-current/70 hover:text-current"
              title="dismiss"
            >
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
