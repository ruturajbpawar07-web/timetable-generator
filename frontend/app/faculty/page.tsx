"use client";
import Link from "next/link";
import { useState } from "react";
import { Search } from "lucide-react";
import { useApi, Any } from "@/lib/api";
import { Badge, Card, ErrorBox, LoadBar, Loading, PageHeader, Table, inputCls } from "@/components/ui";

export default function FacultyPage() {
  const { data, error } = useApi<Any[]>("/faculty");
  const [q, setQ] = useState("");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const rows = data.filter((f) => `${f.name} ${f.code} ${f.department} ${f.subjects.join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageHeader title="Faculty" subtitle={`${data.length} faculty members · workload from the active timetable`} />
      <Card title={
        <div className="relative"><Search className="absolute left-2.5 top-2 size-4 text-slate-400" />
          <input className={`${inputCls} w-72 pl-8`} placeholder="Search name, department, subject…" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
        <Table head={["Faculty", "Department", "Authorized subjects", "Limits / day · week", "Weekly workload", "Status"]}>
          {rows.map((f) => (
            <tr key={f.id} className="hover:bg-slate-50 dark:hover:bg-zinc-800/50">
              <td><Link href={`/faculty/${f.id}`} className="font-medium text-indigo-600 hover:underline">{f.name}</Link>
                <div className="text-xs text-slate-500">{f.code} · {f.designation}</div></td>
              <td>{f.department}</td>
              <td><div className="flex max-w-xs flex-wrap gap-1">{f.subjects.map((s: string) => <Badge key={s}>{s}</Badge>)}</div></td>
              <td className="tabular-nums">{f.max_per_day} · {f.min_per_week}–{f.max_per_week}</td>
              <td className="w-48"><div className="mb-1 text-xs tabular-nums">{f.weekly} periods</div><LoadBar value={f.weekly} max={f.max_per_week} min={f.min_per_week} /></td>
              <td><Badge tone={f.status === "OK" ? "green" : f.status === "OVERLOADED" ? "red" : "amber"}>{f.status?.toLowerCase()}</Badge></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
