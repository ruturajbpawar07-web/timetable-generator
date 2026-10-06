"use client";
import { useMemo, useRef, useState } from "react";
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, DragEndEvent, DragOverEvent } from "@dnd-kit/core";
import { Lock, Unlock } from "lucide-react";
import { api, Any } from "@/lib/api";
import { Badge, Button, Modal, Reason, cx, toast } from "./ui";

// soft subject colours (literal class names so Tailwind keeps them)
const COLORS = [
  "bg-blue-50 border-blue-200 border-l-blue-500 text-blue-950 dark:bg-blue-950/60 dark:border-blue-900 dark:text-blue-100",
  "bg-emerald-50 border-emerald-200 border-l-emerald-500 text-emerald-950 dark:bg-emerald-950/60 dark:border-emerald-900 dark:text-emerald-100",
  "bg-amber-50 border-amber-200 border-l-amber-500 text-amber-950 dark:bg-amber-950/60 dark:border-amber-900 dark:text-amber-100",
  "bg-violet-50 border-violet-200 border-l-violet-500 text-violet-950 dark:bg-violet-950/60 dark:border-violet-900 dark:text-violet-100",
  "bg-rose-50 border-rose-200 border-l-rose-500 text-rose-950 dark:bg-rose-950/60 dark:border-rose-900 dark:text-rose-100",
  "bg-cyan-50 border-cyan-200 border-l-cyan-500 text-cyan-950 dark:bg-cyan-950/60 dark:border-cyan-900 dark:text-cyan-100",
  "bg-lime-50 border-lime-200 border-l-lime-500 text-lime-950 dark:bg-lime-950/60 dark:border-lime-900 dark:text-lime-100",
  "bg-fuchsia-50 border-fuchsia-200 border-l-fuchsia-500 text-fuchsia-950 dark:bg-fuchsia-950/60 dark:border-fuchsia-900 dark:text-fuchsia-100",
];
const COMP: Record<string, string> = { L: "Lecture", T: "Tutorial", P: "Practical" };

export type View = "class" | "faculty" | "room" | "lab";

type Props = {
  data: { id: number; days: Any[]; slots: Any[] };
  entries: Any[];
  view: View;
  editable?: boolean;
  onChanged?: () => void;
};

export default function TimetableGrid({ data, entries, view, editable, onChanged }: Props) {
  const [selected, setSelected] = useState<Any | null>(null);
  const [hover, setHover] = useState<{ key: string; ok: boolean | null; message?: string } | null>(null);
  const [rejected, setRejected] = useState<{ message: string; conflicts: Any[] } | null>(null);
  const reqId = useRef(0);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const groups = useMemo(() => {
    const m = new Map<string, Any[]>();
    for (const e of entries) {
      const k = `${e.day_id}:${e.slot_index}`;
      m.set(k, [...(m.get(k) ?? []), e]);
    }
    return [...m.entries()];
  }, [entries]);

  const byId = useMemo(() => new Map(entries.map((e) => [String(e.id), e])), [entries]);
  const target = (overId: string) => {
    const [day, slot] = overId.split(":").map(Number);
    return { day_id: day, slot_id: slot };
  };

  const onDragOver = async (ev: DragOverEvent) => {
    if (!ev.over) return setHover(null);
    const key = String(ev.over.id);
    const id = ++reqId.current;
    setHover({ key, ok: null });
    const r = await api("/timetable/validate", { body: { timetable_id: data.id, entry_id: Number(ev.active.id), ...target(key) } }).catch(() => null);
    if (id === reqId.current && r) setHover({ key, ok: r.ok, message: r.message });
  };

  const onDragEnd = async (ev: DragEndEvent) => {
    reqId.current++; // drop any in-flight hover validation
    setHover(null);
    const e = byId.get(String(ev.active.id));
    if (!ev.over || !e) return;
    const t = target(String(ev.over.id));
    if (t.day_id === e.day_id && t.slot_id === e.slot_id) return;
    try {
      await api("/timetable/move", { body: { timetable_id: data.id, entry_id: e.id, ...t } });
      toast(`${e.subject} moved — validated, no conflicts`);
      onChanged?.();
    } catch (err: Any) {
      setRejected({ message: err.message, conflicts: err.conflicts ?? [] });
    }
  };

  const cols = `5.5rem repeat(${data.days.length}, minmax(9.5rem, 1fr))`;
  const rows = `2.25rem ${data.slots.map((s: Any) => (s.is_break ? "1.75rem" : "minmax(5.25rem, auto)")).join(" ")}`;

  return (
    <DndContext sensors={sensors} onDragOver={onDragOver} onDragEnd={onDragEnd} onDragCancel={() => setHover(null)}>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="grid min-w-[52rem] gap-px bg-slate-100 dark:bg-zinc-800" style={{ gridTemplateColumns: cols, gridTemplateRows: rows }}>
          <div className="bg-white dark:bg-zinc-900" style={{ gridColumn: 1, gridRow: 1 }} />
          {data.days.map((d: Any, j: number) => (
            <div key={d.id} className="flex items-center justify-center bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:bg-zinc-900 dark:text-zinc-400" style={{ gridColumn: j + 2, gridRow: 1 }}>{d.name}</div>
          ))}
          {data.slots.map((s: Any, i: number) => (
            <div key={s.id} className={cx("flex flex-col justify-center px-2 text-[11px] text-slate-500 dark:text-zinc-400", s.is_break ? "bg-slate-50 dark:bg-zinc-950" : "bg-white dark:bg-zinc-900")} style={{ gridColumn: 1, gridRow: i + 2 }}>
              {s.is_break ? <span className="font-medium">Lunch</span> : <><span className="font-semibold text-slate-700 dark:text-zinc-200">{s.start}</span><span>{s.end}</span></>}
            </div>
          ))}
          {data.slots.map((s: Any, i: number) => data.days.map((d: Any, j: number) =>
            s.is_break
              ? <div key={`${d.id}:${s.id}`} className="bg-slate-50 dark:bg-zinc-950" style={{ gridColumn: j + 2, gridRow: i + 2 }} />
              : <Cell key={`${d.id}:${s.id}`} id={`${d.id}:${s.id}`} col={j + 2} row={i + 2} hover={hover} />
          ))}
          {groups.map(([k, es]) => {
            const [day, idx] = k.split(":").map(Number);
            const col = data.days.findIndex((d: Any) => d.id === day) + 2;
            const span = Math.max(...es.map((e) => e.duration));
            return (
              <div key={k} className="pointer-events-none z-10 flex gap-1 p-1" style={{ gridColumn: col, gridRow: `${idx + 2} / span ${span}` }}>
                {es.map((e) => <EntryCard key={e.id} e={e} view={view} editable={!!editable} onClick={() => setSelected(e)} />)}
              </div>
            );
          })}
        </div>
      </div>
      {hover?.ok === false && <div className="no-print mt-2 text-sm text-red-600">✗ {hover.message}</div>}
      <EntryModal e={selected} timetableId={data.id} onClose={() => setSelected(null)} onChanged={onChanged} />
      <Modal open={!!rejected} onClose={() => setRejected(null)} title="Move rejected">
        <p className="mb-3 text-sm">{rejected?.message}</p>
        <ul className="space-y-1">{rejected?.conflicts.map((c, i) => <Reason key={i} ok={false} text={`${c.type.replaceAll("_", " ")}: ${c.message}`} />)}</ul>
        <p className="mt-3 text-xs text-slate-500">Nothing was changed. Hard constraints are validated before any edit is saved.</p>
      </Modal>
    </DndContext>
  );
}

function Cell({ id, col, row, hover }: { id: string; col: number; row: number; hover: { key: string; ok: boolean | null } | null }) {
  const { setNodeRef } = useDroppable({ id });
  const h = hover?.key === id;
  return <div ref={setNodeRef} style={{ gridColumn: col, gridRow: row }}
    className={cx("bg-white dark:bg-zinc-900", h && hover?.ok === true && "bg-emerald-50 ring-2 ring-inset ring-emerald-400 dark:bg-emerald-950",
      h && hover?.ok === false && "bg-red-50 ring-2 ring-inset ring-red-400 dark:bg-red-950", h && hover?.ok === null && "bg-slate-50 dark:bg-zinc-800")} />;
}

function EntryCard({ e, view, editable, onClick }: { e: Any; view: View; editable: boolean; onClick: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: e.id, disabled: !editable || e.locked });
  const who = `${e.class}${e.batch ? ` · ${e.batch}` : ""}`;
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 } : undefined;
  return (
    <button ref={setNodeRef} style={style} {...listeners} {...attributes} onClick={onClick}
      className={cx("pointer-events-auto flex min-w-0 flex-1 flex-col rounded-lg border border-l-4 px-2 py-1.5 text-left text-[11px] leading-tight shadow-xs transition hover:shadow-md",
        COLORS[e.subject_id % COLORS.length], editable && !e.locked && "cursor-grab active:cursor-grabbing", isDragging && "opacity-80 shadow-lg ring-2 ring-indigo-400")}
      title={`${e.subject} · ${e.faculty} · ${e.room} · ${e.class}${e.batch ? ` (${e.batch})` : ""}`}>
      <div className="flex items-center gap-1">
        <span className="truncate text-xs font-semibold">{e.subject_code}</span>
        {e.component !== "L" && <span className="rounded bg-black/5 px-1 text-[10px] dark:bg-white/10">{e.component === "P" ? "Lab" : "Tut"}</span>}
        {e.locked && <Lock className="ml-auto size-3 shrink-0 opacity-70" />}
      </div>
      <div className="truncate opacity-90">{e.subject}</div>
      <div className="truncate opacity-75">{view === "class" ? e.faculty : who}</div>
      <div className="mt-auto truncate pt-0.5 opacity-75">
        {view === "class" ? `${e.room}${e.batch ? ` · ${e.batch}` : ""}` : view === "faculty" ? e.room : e.faculty}
      </div>
    </button>
  );
}

function EntryModal({ e, timetableId, onClose, onChanged }: { e: Any | null; timetableId: number; onClose: () => void; onChanged?: () => void }) {
  const [busy, setBusy] = useState(false);
  if (!e) return null;
  const toggleLock = async () => {
    setBusy(true);
    try {
      await api("/timetable/lock", { body: { timetable_id: timetableId, locked: !e.locked, entry_ids: [e.id] } });
      toast(e.locked ? "Unlocked" : "Locked — will stay fixed during regeneration");
      onChanged?.();
      onClose();
    } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={<span>{e.subject} <span className="font-normal text-slate-500">· {e.class}{e.batch ? ` (${e.batch})` : ""}</span></span>}>
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="blue">{COMP[e.component]}{e.duration > 1 ? ` · ${e.duration} periods` : ""}</Badge>
        <Badge>{e.faculty}</Badge><Badge>{e.room}</Badge>
        {e.locked && <Badge tone="violet"><Lock className="size-3" /> Locked</Badge>}
      </div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Why was this slot selected?</h4>
      <ul className="space-y-1.5">{(e.explanation ?? []).map((t: string, i: number) => <Reason key={i} text={t} />)}</ul>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={toggleLock} loading={busy}>{e.locked ? <><Unlock className="size-4" />Unlock</> : <><Lock className="size-4" />Lock period</>}</Button>
        <Button variant="primary" onClick={onClose}>Done</Button>
      </div>
    </Modal>
  );
}
