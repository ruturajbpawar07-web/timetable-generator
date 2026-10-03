"use client";
import { use } from "react";
import { useApi, useMeta, api, Any } from "@/lib/api";
import TimetableGrid from "@/components/TimetableGrid";
import { Badge, Card, ErrorBox, LoadBar, Loading, PageHeader, Stat, StatusBadge, cx, toast } from "@/components/ui";

const NEXT: Record<string, string | null> = { "": "UNAVAILABLE", UNAVAILABLE: "PREFERRED", PREFERRED: null };

export default function FacultyProfile({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const meta = useMeta();
  const { data: f, error, reload } = useApi(`/faculty/${id}`);
  const tt = useApi("/timetable");
  if (error) return <ErrorBox error={error} />;
  if (!f || !meta || !tt.data) return <Loading />;
  const w = f.workload;
  const avail = new Map(f.availability.map((a: Any) => [`${a.day_id}:${a.slot_id}`, a.kind]));
  const teaching = new Set(f.entries.flatMap((e: Any) => Array.from({ length: e.duration }, (_, i) => `${e.day_id}:${tt.data.slots[e.slot_index + i].id}`)));

  const cycle = async (day_id: number, slot_id: number) => {
    const cur = (avail.get(`${day_id}:${slot_id}`) as string) ?? "";
    await api(`/faculty/${id}/availability`, { body: { day_id, slot_id, kind: NEXT[cur] } });
    if (NEXT[cur] === "UNAVAILABLE" && teaching.has(`${day_id}:${slot_id}`))
      toast("Marked unavailable during a scheduled lecture — see Conflicts to resolve it", "info");
    reload();
  };

  return (
    <>
      <PageHeader title={f.name} subtitle={`${f.code} · ${f.designation} · ${f.department}`} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Weekly workload" value={`${w.weekly}/${w.max_per_week}`} hint={`minimum ${w.min_per_week} · ${w.utilization}% utilised`} tone={w.status === "OK" ? "good" : "warn"} />
        <Stat label={`Lectures on ${f.date}`} value={f.today.length} />
        <Stat label="Free periods today" value={f.free_periods.length} />
        <Stat label="Substitutions taken" value={f.substitutions.length} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Subjects & classes">
          <div className="mb-2 text-xs font-medium text-slate-500">Authorized subjects</div>
          <div className="mb-4 flex flex-wrap gap-1">{f.subjects.map((s: Any) => <Badge key={s.id} tone="blue">{s.code} {s.name}</Badge>)}</div>
          <div className="mb-2 text-xs font-medium text-slate-500">Assigned classes</div>
          <div className="flex flex-wrap gap-1">{f.classes.map((c: string) => <Badge key={c}>{c}</Badge>)}</div>
        </Card>
        <Card title="Daily workload">
          <div className="space-y-2">
            {Object.entries(w.daily).map(([d, n]) => (
              <div key={d} className="grid grid-cols-[6rem_1fr_3rem] items-center gap-2 text-sm">
                <span>{d}</span><LoadBar value={n as number} max={w.max_per_day} /><span className="text-right tabular-nums">{n as number}/{w.max_per_day}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title={`Today (${f.date})`}>
          {f.today.length ? <ul className="space-y-2 text-sm">{f.today.map((e: Any) => (
            <li key={e.id} className="flex justify-between gap-2"><span>{e.start} · {e.subject_code} · {e.class}{e.batch ? ` (${e.batch})` : ""}</span><span className="text-slate-500">{e.room}</span></li>
          ))}</ul> : <p className="text-sm text-slate-500">No lectures.</p>}
          <div className="mt-3 text-xs text-slate-500">Free: {f.free_periods.map((s: Any) => s.start).join(", ") || "none"}</div>
        </Card>
      </div>

      <Card title="Weekly timetable" className="mt-6"><TimetableGrid data={tt.data} entries={f.entries} view="faculty" /></Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Availability (click a cell: unavailable → preferred → clear)" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead><tr><th />{meta.slots.filter((s) => !s.is_break).map((s) => <th key={s.id} className="px-1 py-1 font-medium text-slate-500">{s.start}</th>)}</tr></thead>
              <tbody>{meta.days.map((d) => (
                <tr key={d.id}><td className="pr-2 font-medium">{d.name.slice(0, 3)}</td>
                  {meta.slots.filter((s) => !s.is_break).map((s) => {
                    const k = avail.get(`${d.id}:${s.id}`);
                    return <td key={s.id} className="p-0.5"><button onClick={() => cycle(d.id, s.id)} title={String(k ?? "available")}
                      className={cx("h-7 w-14 rounded border text-[10px]", k === "UNAVAILABLE" ? "border-red-300 bg-red-100 text-red-700 dark:bg-red-950"
                        : k === "PREFERRED" ? "border-emerald-300 bg-emerald-100 text-emerald-700 dark:bg-emerald-950" : "border-slate-200 dark:border-zinc-700",
                        teaching.has(`${d.id}:${s.id}`) && "font-semibold")}>
                      {k === "UNAVAILABLE" ? "✗" : k === "PREFERRED" ? "★" : teaching.has(`${d.id}:${s.id}`) ? "class" : ""}</button></td>;
                  })}</tr>))}</tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-slate-500">Unavailable slots are hard constraints for the solver and substitution engine; preferred slots earn a configurable bonus.</p>
        </Card>
        <Card title="Absences & substitutions">
          <ul className="space-y-1 text-sm">
            {f.absences.map((a: Any, i: number) => <li key={i}><Badge tone="red">absent</Badge> {a.date} {a.slot_id ? "(partial)" : "(full day)"} {a.reason}</li>)}
            {f.substitutions.map((x: Any, i: number) => <li key={`s${i}`}><StatusBadge s={x.status} /> covering on {x.date}</li>)}
            {!f.absences.length && !f.substitutions.length && <li className="text-slate-500">None recorded.</li>}
          </ul>
        </Card>
      </div>
    </>
  );
}
