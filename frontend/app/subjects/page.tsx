"use client";
import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useApi, useMeta, Any } from "@/lib/api";
import { Badge, Card, ErrorBox, Loading, PageHeader, Select, Table } from "@/components/ui";

const COMP: Record<string, string> = { L: "Lecture", T: "Tutorial", P: "Practical" };

export default function SubjectsPage() {
  const meta = useMeta();
  const subjects = useApi<Any[]>("/subjects");
  const w = useApi("/analytics/workload");
  const [cls, setCls] = useState("");
  if (subjects.error) return <ErrorBox error={subjects.error} />;
  if (!subjects.data || !w.data || !meta) return <Loading />;
  const credits = w.data.credits.filter((c: Any) => !cls || c.class_id === Number(cls));
  const short = w.data.credits.filter((c: Any) => c.remaining > 0);
  return (
    <>
      <PageHeader title="Subjects" subtitle="Credits and weekly session requirements are configured separately — 1 credit ≠ 1 lecture." />
      <Card title="Subject catalogue">
        <Table head={["Code", "Subject", "Dept", "Sem", "Credits", "Lectures/wk", "Tutorials/wk", "Practicals/wk", "Block", "Flags", "Qualified faculty"]}>
          {subjects.data.map((s) => (
            <tr key={s.id}>
              <td className="font-mono text-xs">{s.code}</td><td className="font-medium">{s.name}</td><td>{s.department}</td><td>{s.semester}</td>
              <td className="tabular-nums">{s.credits}</td><td className="tabular-nums">{s.lecture_sessions_per_week}</td>
              <td className="tabular-nums">{s.tutorial_sessions_per_week}</td><td className="tabular-nums">{s.practical_sessions_per_week}</td>
              <td className="text-xs">{s.practical_sessions_per_week ? `${s.practical_duration_periods} periods · ${s.lab_type}` : "—"}</td>
              <td className="space-x-1">{s.is_core && <Badge tone="violet">core</Badge>}{s.morning_preferred && <Badge tone="amber">morning</Badge>}</td>
              <td className="text-xs text-slate-500">{s.qualified_faculty.join(", ")}{s.qualified_faculty.length === 1 && <Badge tone="red">single</Badge>}</td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card className="mt-6" title={<span className="flex items-center gap-2">Subject credit tracker
        {short.length ? <Badge tone="red"><AlertTriangle className="size-3" />{short.length} requirements short</Badge>
          : <Badge tone="green"><CheckCircle2 className="size-3" />every requirement fulfilled</Badge>}</span>}
        action={<Select value={cls} onChange={setCls} placeholder="All classes" options={meta.classes.map((c: Any) => ({ value: c.id, label: c.code }))} />}>
        <Table head={["Class", "Subject", "Type", "Batch", "Required", "Scheduled", "Remaining"]}>
          {credits.map((c: Any) => (
            <tr key={c.demand_id} className={c.remaining ? "bg-red-50 dark:bg-red-950/40" : ""}>
              <td>{c.class}</td><td>{c.subject}</td><td>{COMP[c.component]}</td><td>{c.batch ?? "—"}</td>
              <td className="tabular-nums">{c.required}</td><td className="tabular-nums">{c.scheduled}</td>
              <td className="tabular-nums">{c.remaining ? <span className="font-semibold text-red-600">{c.remaining}</span> : 0}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
