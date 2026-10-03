"use client";
import { useEffect, useMemo, useState } from "react";
import { Download, Lock, Move, Printer, Unlock } from "lucide-react";
import { api, useApi, useMeta, Any } from "@/lib/api";
import TimetableGrid, { View } from "@/components/TimetableGrid";
import { Badge, Button, ErrorBox, Loading, PageHeader, Select, cx, toast } from "@/components/ui";

const VIEWS: { id: View; label: string }[] = [
  { id: "class", label: "Class view" }, { id: "faculty", label: "Faculty view" },
  { id: "room", label: "Room view" }, { id: "lab", label: "Lab view" },
];

export default function TimetablePage() {
  const meta = useMeta();
  const [tid, setTid] = useState<number | null>(null);
  const [view, setView] = useState<View>("class");
  const [dept, setDept] = useState("");
  const [year, setYear] = useState("");
  const [id, setId] = useState<number | null>(null);
  const [edit, setEdit] = useState(false);
  const [lockDay, setLockDay] = useState("");

  // initial selection from the URL (?tid=&view=&id=&edit=1)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("tid")) setTid(Number(q.get("tid")));
    if (q.get("view")) setView(q.get("view") as View);
    if (q.get("id")) setId(Number(q.get("id")));
    if (q.get("edit")) setEdit(true);
  }, []);

  const list = useApi<Any[]>("/timetables");
  const tt = useApi(`/timetable${tid ? `?timetable_id=${tid}` : ""}`);
  const data = tt.data;

  const options = useMemo(() => {
    if (!meta) return [];
    if (view === "class") return meta.classes
      .filter((c: Any) => (!dept || c.department_id === Number(dept)) && (!year || c.year_level === year))
      .map((c: Any) => ({ value: c.id, label: c.code }));
    if (view === "faculty") return meta.faculty.filter((f) => !dept || f.department_id === Number(dept)).map((f) => ({ value: f.id, label: f.name }));
    return meta.rooms.filter((r: Any) => r.kind === (view === "lab" ? "LAB" : "CLASSROOM")).map((r: Any) => ({ value: r.id, label: `${r.code} · ${r.name}` }));
  }, [meta, view, dept, year]);

  // keep a valid selection when the view or filters change
  useEffect(() => {
    if (options.length && !options.some((o) => o.value === id)) setId(Number(options[0].value));
  }, [options, id]);

  const key = { class: "class_id", faculty: "faculty_id", room: "room_id", lab: "room_id" }[view];
  const entries = data?.entries.filter((e: Any) => e[key] === id) ?? [];
  const lockParam = { class: "division_id", faculty: "faculty_id", room: null, lab: null }[view];

  const lock = async (locked: boolean, extra: Any) => {
    const r = await api("/timetable/lock", { body: { timetable_id: data.id, locked, ...extra } });
    toast(`${locked ? "Locked" : "Unlocked"} ${r.changed} entries`);
    tt.reload();
  };
  const exportUrl = (fmt: string) => `/api/export?kind=${view === "lab" ? "room" : view}&id=${id}&format=${fmt}&timetable_id=${data?.id}`;

  if (tt.error) return <ErrorBox error={tt.error} />;
  if (!data || !meta) return <Loading />;
  const m = data.metrics ?? {};
  const label = options.find((o) => o.value === id)?.label;

  return (
    <>
      <PageHeader title="Timetable" subtitle={`${data.name} · ${data.status.toLowerCase()} · ${data.entries.length} sessions`}
        actions={<>
          <Select value={data.id} onChange={(v) => setTid(Number(v))}
            options={(list.data ?? []).map((t) => ({ value: t.id, label: `${t.name} (${t.status.toLowerCase()}${t.score != null ? `, score ${t.score}` : ""})` }))} />
          <a href={exportUrl("xlsx")}><Button><Download className="size-4" />Excel</Button></a>
          <a href={exportUrl("csv")}><Button><Download className="size-4" />CSV</Button></a>
          <Button onClick={() => window.print()}><Printer className="size-4" />PDF</Button>
        </>} />

      <div className="no-print mb-4 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 dark:border-zinc-700 dark:bg-zinc-900">
          {VIEWS.map((v) => (
            <button key={v.id} onClick={() => setView(v.id)}
              className={cx("rounded-md px-3 py-1 text-sm", view === v.id ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-50 dark:text-zinc-300 dark:hover:bg-zinc-800")}>{v.label}</button>
          ))}
        </div>
        {(view === "class" || view === "faculty") && (
          <Select value={dept} onChange={setDept} placeholder="All departments" options={meta.departments.map((d) => ({ value: d.id, label: d.code }))} />
        )}
        {view === "class" && <Select value={year} onChange={setYear} placeholder="All years" options={["SE", "TE", "BE"].map((y) => ({ value: y, label: y }))} />}
        <Select value={id ?? ""} onChange={(v) => setId(Number(v))} options={options} className="min-w-52" />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant={edit ? "primary" : "secondary"} onClick={() => setEdit(!edit)}><Move className="size-4" />{edit ? "Editing (drag cards)" : "Edit manually"}</Button>
          {lockParam && <>
            <Button onClick={() => lock(true, { [lockParam]: id })}><Lock className="size-4" />Lock {view}</Button>
            <Button variant="ghost" onClick={() => lock(false, { [lockParam]: id })}><Unlock className="size-4" />Unlock</Button>
          </>}
          <Select value={lockDay} onChange={(v) => { setLockDay(""); if (v) lock(true, { day_id: Number(v), ...(lockParam ? { [lockParam]: id } : {}) }); }}
            placeholder="Lock a day…" options={data.days.map((d: Any) => ({ value: d.id, label: `Lock ${d.name}` }))} />
          <Button variant="ghost" onClick={() => lock(true, { component: "P", ...(lockParam ? { [lockParam]: id } : {}) })}><Lock className="size-4" />Lock practicals</Button>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-sm font-semibold">{label}</span>
        <Badge>{entries.reduce((a: number, e: Any) => a + e.duration, 0)} periods/week</Badge>
        {entries.some((e: Any) => e.locked) && <Badge tone="violet"><Lock className="size-3" />{entries.filter((e: Any) => e.locked).length} locked</Badge>}
        <span className="no-print ml-auto text-slate-500">
          Score {m.score ?? "–"} · {m.hard_constraint_violations ?? 0} hard violations · {m.unscheduled_sessions ?? 0} unscheduled · click a card for “why this slot?”
        </span>
      </div>
      {edit && <p className="no-print mb-3 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">
        Drag a card to another period. Target cells turn green/red as the move is validated against every hard constraint before it is saved.</p>}
      <TimetableGrid data={data} entries={entries} view={view} editable={edit} onChanged={tt.reload} />
    </>
  );
}
