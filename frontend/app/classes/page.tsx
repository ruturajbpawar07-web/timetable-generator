"use client";
import Link from "next/link";
import { useApi, useMeta, Any } from "@/lib/api";
import { Badge, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";

export default function ClassesPage() {
  const meta = useMeta();
  const { data: w, error } = useApi("/analytics/workload");
  if (error) return <ErrorBox error={error} />;
  if (!meta || !w) return <Loading />;
  const rooms = new Map(meta.rooms.map((r: Any) => [r.id, r.code]));
  const depts = new Map(meta.departments.map((d) => [d.id, d.code]));
  return (
    <>
      <PageHeader title="Classes" subtitle={`${meta.classes.length} divisions · practical batches run in parallel labs`} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {meta.classes.map((c: Any) => {
          const reqs = w.credits.filter((x: Any) => x.class_id === c.id);
          const short = reqs.filter((x: Any) => x.remaining > 0).length;
          return (
            <Card key={c.id} title={<span>{c.code} <span className="font-normal text-slate-500">· {depts.get(c.department_id)} · Sem {c.semester}</span></span>}
              action={<Link className="text-xs text-indigo-600" href={`/timetable?view=class&id=${c.id}`}>Timetable →</Link>}>
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                <Badge>{c.strength} students</Badge><Badge>Home {rooms.get(c.home_room_id) ?? "—"}</Badge>
                {c.batches.map((b: Any) => <Badge key={b.id} tone="blue">{b.name}: {b.strength}</Badge>)}
                <Badge tone={short ? "red" : "green"}>{short ? `${short} short` : "all sessions scheduled"}</Badge>
              </div>
              <ul className="space-y-1 text-sm">
                {reqs.map((r: Any) => (
                  <li key={r.demand_id} className="flex justify-between gap-2">
                    <span className="truncate">{r.subject} <span className="text-xs text-slate-500">{r.component}{r.batch ? ` · ${r.batch}` : ""}</span></span>
                    <span className={r.remaining ? "text-red-600" : "text-slate-500"}>{r.scheduled}/{r.required}</span>
                  </li>
                ))}
              </ul>
            </Card>
          );
        })}
      </div>
    </>
  );
}
