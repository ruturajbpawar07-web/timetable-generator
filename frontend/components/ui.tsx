"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// Accent palette: literal class strings so Tailwind keeps them. Picked per label so each tile/card gets a
// stable colour; semantic tones (good/warn/bad) override it.
const ACCENTS = {
  indigo: { chip: "bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300", bar: "from-indigo-500 to-violet-500", dot: "bg-indigo-500" },
  sky: { chip: "bg-sky-100 text-sky-600 dark:bg-sky-950 dark:text-sky-300", bar: "from-sky-400 to-blue-500", dot: "bg-sky-500" },
  violet: { chip: "bg-violet-100 text-violet-600 dark:bg-violet-950 dark:text-violet-300", bar: "from-violet-500 to-fuchsia-500", dot: "bg-violet-500" },
  teal: { chip: "bg-teal-100 text-teal-600 dark:bg-teal-950 dark:text-teal-300", bar: "from-teal-400 to-cyan-500", dot: "bg-teal-500" },
  orange: { chip: "bg-orange-100 text-orange-600 dark:bg-orange-950 dark:text-orange-300", bar: "from-orange-400 to-pink-500", dot: "bg-orange-500" },
  pink: { chip: "bg-pink-100 text-pink-600 dark:bg-pink-950 dark:text-pink-300", bar: "from-pink-500 to-rose-500", dot: "bg-pink-500" },
  emerald: { chip: "bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300", bar: "from-emerald-400 to-teal-500", dot: "bg-emerald-500" },
  amber: { chip: "bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-300", bar: "from-amber-400 to-orange-500", dot: "bg-amber-500" },
  rose: { chip: "bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-300", bar: "from-rose-500 to-red-500", dot: "bg-rose-500" },
};
type Accent = keyof typeof ACCENTS;
const ROTATION: Accent[] = ["indigo", "sky", "violet", "teal", "orange", "pink"];
const pick = (key: string): Accent => ROTATION[[...key].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % ROTATION.length];

export function Card({ title, action, children, className, accent }: {
  title?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string; accent?: Accent;
}) {
  const a = ACCENTS[accent ?? pick(typeof title === "string" ? title : "card")];
  return (
    <section className={cx("rounded-xl border border-slate-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900", className)}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-zinc-800">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><span className={cx("h-4 w-1 shrink-0 rounded-full", a.dot)} />{title}</h2>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 bg-clip-text text-2xl font-bold tracking-tight text-transparent dark:from-indigo-300 dark:via-violet-300 dark:to-fuchsia-300">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">{subtitle}</p>}
      </div>
      {actions && <div className="no-print flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, icon, tone = "default", accent }: {
  label: string; value: React.ReactNode; hint?: string; icon?: React.ReactNode; tone?: "default" | "warn" | "bad" | "good"; accent?: Accent;
}) {
  const a = ACCENTS[({ good: "emerald", warn: "amber", bad: "rose" } as const)[tone as "good"] ?? accent ?? pick(label)];
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900">
      <div className={cx("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", a.bar)} />
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-slate-500 dark:text-zinc-400">{label}</span>
        <span className={cx("grid size-8 shrink-0 place-items-center rounded-lg", a.chip)}>{icon ?? <span className={cx("size-2 rounded-full", a.dot)} />}</span>
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500 dark:text-zinc-400">{hint}</div>}
    </div>
  );
}

const BADGE = {
  gray: "bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300",
  blue: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  amber: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  red: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  violet: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
};
export function Badge({ children, tone = "gray" }: { children: React.ReactNode; tone?: keyof typeof BADGE }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium", BADGE[tone])}>{children}</span>;
}

export function Button({ variant = "secondary", loading, className, children, ...p }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; loading?: boolean }) {
  const v = {
    primary: "bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-sm shadow-indigo-500/30 hover:from-indigo-500 hover:to-violet-500 border-transparent",
    secondary: "bg-white text-slate-700 hover:bg-slate-50 border-slate-200 dark:bg-zinc-900 dark:text-zinc-200 dark:border-zinc-700 dark:hover:bg-zinc-800",
    danger: "bg-white text-red-600 hover:bg-red-50 border-red-200 dark:bg-zinc-900 dark:border-red-900 dark:hover:bg-red-950",
    ghost: "border-transparent text-slate-600 hover:bg-slate-100 dark:text-zinc-300 dark:hover:bg-zinc-800",
  }[variant];
  return (
    <button {...p} disabled={p.disabled || loading}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:opacity-50", v, className)}>
      {loading && <Loader2 className="size-4 animate-spin" />}{children}
    </button>
  );
}

export const inputCls = "rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:ring-indigo-950";

export function Select({ label, value, onChange, options, placeholder, className }: {
  label?: string; value: string | number | undefined | null; onChange: (v: string) => void;
  options: { value: string | number; label: string }[]; placeholder?: string; className?: string;
}) {
  const el = (
    <select className={cx(inputCls, className)} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  return label ? <label className="flex flex-col gap-1 text-xs font-medium text-slate-500 dark:text-zinc-400">{label}{el}</label> : el;
}

export function Modal({ open, onClose, title, children, wide }: {
  open: boolean; onClose: () => void; title: React.ReactNode; children: React.ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-[8vh] backdrop-blur-[2px]" onClick={onClose}>
      <div role="dialog" aria-modal className={cx("w-full rounded-xl border border-slate-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900", wide ? "max-w-3xl" : "max-w-lg")}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3 dark:border-zinc-800">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-zinc-800"><X className="size-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="text-slate-300 dark:text-zinc-600">{icon ?? <Info className="size-8" />}</div>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-md text-xs text-slate-500 dark:text-zinc-400">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-10 text-sm text-slate-500"><Loader2 className="size-4 animate-spin" />{label}</div>;
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
      <XCircle className="mt-0.5 size-4 shrink-0" />
      <div>{error}<div className="text-xs opacity-80">Is the API running on :8000? (see README)</div></div>
    </div>
  );
}

/** Explanation line renderer: ✓ / ✗ / ⚠ / ★ prefixes become icons. */
export function Reason({ text, ok }: { text: string; ok?: boolean }) {
  const t = text.replace(/^[✓✗⚠★🔒⚙✎]\s*/u, "");
  const k = ok === false || text.startsWith("✗") ? "bad" : text.startsWith("⚠") ? "warn" : text.startsWith("★") || text.startsWith("⚙") || text.startsWith("🔒") || text.startsWith("✎") ? "info" : "ok";
  const icon = { ok: <CheckCircle2 className="size-4 text-emerald-600" />, bad: <XCircle className="size-4 text-red-500" />,
    warn: <AlertTriangle className="size-4 text-amber-500" />, info: <Info className="size-4 text-indigo-500" /> }[k];
  return <li className="flex items-start gap-2 text-sm"><span className="mt-0.5 shrink-0">{icon}</span><span>{text.startsWith("🔒") ? "🔒 " : ""}{t}</span></li>;
}

// ---- toasts: fire-and-forget via a window event, rendered by <Toaster/> in the shell ----
type T = { id: number; msg: string; tone: "success" | "error" | "info" };
export function toast(msg: string, tone: T["tone"] = "success") {
  window.dispatchEvent(new CustomEvent("toast", { detail: { msg, tone } }));
}
export function Toaster() {
  const [items, setItems] = useState<T[]>([]);
  useEffect(() => {
    const h = (e: Event) => {
      const id = Date.now() + Math.random();
      setItems((x) => [...x, { id, ...(e as CustomEvent).detail }]);
      setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 5000);
    };
    window.addEventListener("toast", h);
    return () => window.removeEventListener("toast", h);
  }, []);
  return (
    <div className="fixed bottom-4 right-4 z-[60] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={cx("flex items-start gap-2 rounded-lg border bg-white p-3 text-sm shadow-lg dark:bg-zinc-900",
          t.tone === "error" ? "border-red-200 dark:border-red-900" : "border-slate-200 dark:border-zinc-700")}>
          {t.tone === "error" ? <XCircle className="mt-0.5 size-4 shrink-0 text-red-500" /> : t.tone === "info" ? <Info className="mt-0.5 size-4 shrink-0 text-indigo-500" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
          <span>{t.msg}</span>
        </div>
      ))}
    </div>
  );
}

export function Table({ head, children }: { head: React.ReactNode[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-500 dark:border-zinc-800 dark:text-zinc-400">
          {head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2">{h}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-slate-100 dark:divide-zinc-800 [&_td]:px-3 [&_td]:py-2">{children}</tbody>
      </table>
    </div>
  );
}

/** Thin progress bar with configured limits (used for workload). */
export function LoadBar({ value, max, min = 0 }: { value: number; max: number; min?: number }) {
  const pct = Math.min(100, (value / Math.max(max, 1)) * 100);
  const color = value > max ? "bg-[var(--status-bad)]" : value < min ? "bg-[var(--status-warn)]" : "bg-[var(--series-1)]";
  return (
    <div className="relative h-2 w-full rounded-full bg-slate-100 dark:bg-zinc-800" title={`${value} periods (limits ${min}–${max})`}>
      <div className={cx("h-2 rounded-full", color)} style={{ width: `${pct}%` }} />
      {min > 0 && <div className="absolute top-[-2px] h-3 w-px bg-slate-400" style={{ left: `${(min / max) * 100}%` }} />}
    </div>
  );
}

export function StatusBadge({ s }: { s: string }) {
  const tone = ({ SCHEDULED: "green", SUBSTITUTED: "blue", CANCELLED: "red", RESCHEDULED: "amber", PENDING: "amber" } as const)[s as "SCHEDULED"] ?? "gray";
  return <Badge tone={tone}>{s.toLowerCase()}</Badge>;
}
