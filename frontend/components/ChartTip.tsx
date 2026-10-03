"use client";
import { Any } from "@/lib/api";

/** Recharts tooltip with app styling; `render` receives the hovered row. */
export default function Tip({ active, payload, render }: Any) {
  if (!active || !payload?.length) return null;
  return <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md dark:border-zinc-700 dark:bg-zinc-900">{render(payload[0].payload)}</div>;
}
