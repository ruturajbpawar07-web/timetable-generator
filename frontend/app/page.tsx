"use client";
import Link from "next/link";
import { AlertTriangle, CalendarDays, DoorOpen, UserCog, UserX, Users } from "lucide-react";
import { useApi, Any } from "@/lib/api";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";

export default function Dashboard() {
  const { data: d, error } = useApi("/dashboard");
  if (error) return <ErrorBox error={error} />;
  if (!d) return <Loading />;
  const c = d.cards;
  return (
    <>
      <PageHeader title="Dashboard" subtitle={`${d.day}, ${d.date} · ${d.timetable.name}`} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Active Faculty" value={c.active_faculty} icon={<Users className="size-4" />} />
        <Stat label="Classes Today" value={c.classes_today} hint="scheduled sessions" icon={<CalendarDays className="size-4" />} />
        <Stat label="Faculty Absent" value={c.faculty_absent} tone={c.faculty_absent ? "warn" : "default"} icon={<UserX className="size-4" />} />
        <Stat label="Substitutions Required" value={c.substitutions_required} tone={c.substitutions_required ? "bad" : "good"} icon={<UserCog className="size-4" />} />
        <Stat label="Open Conflicts" value={c.open_conflicts} tone={c.open_conflicts ? "bad" : "good"} icon={<AlertTriangle className="size-4" />} />
        <Stat label="Rooms In Use" value={`${c.rooms_in_use}/${c.rooms_total}`} icon={<DoorOpen className="size-4" />} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card title="Today's Schedule" className="xl:col-span-2" action={<Link href="/timetable" className="text-xs text-indigo-600">Full timetable →</Link>}>
          {d.schedule.length ? (
            <div className="max-h-[28rem] overflow-y-auto">
              <Table head={["Time", "Class", "Subject", "Faculty", "Room", "Status"]}>
                {d.schedule.map((e: Any) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap tabular-nums">{e.start}–{e.end}</td>
                    <td className="whitespace-nowrap">{e.class}{e.batch && <span className="text-slate-500"> · {e.batch}</span>}</td>
                    <td>{e.subject}{e.component === "P" && <Badge tone="blue">Lab</Badge>}</td>
                    <td className="whitespace-nowrap">{e.substitute ? <><s className="text-slate-400">{e.faculty}</s> {e.substitute}</> : e.faculty}</td>
                    <td>{e.room}</td>
                    <td><StatusBadge s={e.today_status} /></td>
                  </tr>
                ))}
              </Table>
            </div>
          ) : <Empty title="No classes on this day" />}
        </Card>

        <div className="space-y-6">
          <Card title="Pending Substitutions" action={<Link href="/absences" className="text-xs text-indigo-600">Manage →</Link>}>
            {d.pending.length ? (
              <ul className="space-y-3">
                {d.pending.map((p: Any) => (
                  <li key={p.entry_id} className="text-sm">
                    <div className="font-medium">{p.subject} · {p.class}</div>
                    <div className="text-xs text-slate-500">{p.when} · {p.absent_faculty} absent</div>
                    <div className="mt-1 text-xs">{p.candidates.find((x: Any) => x.eligible)
                      ? <>Suggested: <b>{p.candidates.find((x: Any) => x.eligible).name}</b></>
                      : <span className="text-red-600">No eligible substitute — reschedule</span>}</div>
                  </li>
                ))}
              </ul>
            ) : <Empty title="All covered" hint="No absences without a substitute today." />}
          </Card>
          <Card title="Warnings">
            {d.warnings.length ? (
              <ul className="space-y-2 text-sm">{d.warnings.map((w: string, i: number) => (
                <li key={i} className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />{w}</li>))}</ul>
            ) : <Empty title="No warnings" />}
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card title="Faculty Availability Today" className="xl:col-span-2">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {d.availability.map((f: Any) => (
              <Link key={f.faculty_id} href={`/faculty/${f.faculty_id}`} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm hover:bg-slate-50 dark:border-zinc-800 dark:hover:bg-zinc-800">
                <span className="truncate">{f.name}</span>
                {f.absent ? <Badge tone="red">Absent</Badge> : <Badge tone={f.lectures_today ? "blue" : "gray"}>{f.lectures_today} periods</Badge>}
              </Link>
            ))}
          </div>
        </Card>
        <Card title="Recent Changes" action={<Link href="/audit" className="text-xs text-indigo-600">Audit log →</Link>}>
          <ul className="space-y-3">
            {d.recent.map((a: Any) => (
              <li key={a.id} className="text-sm">
                <div className="flex justify-between gap-2"><span className="font-medium">{a.action.replaceAll("_", " ").toLowerCase()}</span>
                  <span className="shrink-0 text-xs text-slate-500">{a.ts.slice(5, 16).replace("T", " ")}</span></div>
                {a.reason && <div className="line-clamp-2 text-xs text-slate-500">{a.reason}</div>}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
