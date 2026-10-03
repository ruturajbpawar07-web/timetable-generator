"use client";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi, Any } from "@/lib/api";
import { Card, ErrorBox, Loading, PageHeader, Stat } from "@/components/ui";
import Tip from "@/components/ChartTip";

const axis = { stroke: "var(--axis)", fontSize: 11, tickLine: false };

function UtilChart({ rows, height = 240 }: { rows: Any[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 10 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="code" {...axis} interval={0} angle={-30} textAnchor="end" height={50} />
        <YAxis {...axis} axisLine={false} width={34} unit="%" domain={[0, 100]} />
        <Tooltip cursor={{ fill: "var(--grid)", opacity: 0.4 }} content={<Tip render={(r: Any) => <>{r.code}: {r.utilization}% ({r.used} periods)</>} />} />
        <Bar isAnimationActive={false} dataKey="utilization" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function AnalyticsPage() {
  const { data, error } = useApi("/analytics/workload");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const m = data.metrics;
  const byClass: Record<string, { req: number; got: number }> = {};
  for (const c of data.credits) {
    byClass[c.class] ??= { req: 0, got: 0 };
    byClass[c.class].req += c.required;
    byClass[c.class].got += Math.min(c.scheduled, c.required);
  }
  const completion = Object.entries(byClass).map(([code, v]) => ({ code, utilization: Math.round((100 * v.got) / v.req), used: v.got }));
  return (
    <>
      <PageHeader title="Analytics" subtitle="Scheduling quality metrics for the active timetable — no invented accuracy numbers." />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Optimisation score" value={m.score} />
        <Stat label="Hard violations" value={m.hard_constraint_violations} tone={m.hard_constraint_violations ? "bad" : "good"} />
        <Stat label="Unscheduled sessions" value={m.unscheduled_sessions} tone={m.unscheduled_sessions ? "bad" : "good"} />
        <Stat label="Student gaps" value={m.student_gaps} hint="idle periods between classes" />
        <Stat label="Faculty gaps" value={m.faculty_gaps} />
        <Stat label="Preferences met" value={`${m.preference_satisfaction_pct}%`} />
      </div>
      <Card title="Score components" className="mt-6">
        <div className="grid gap-4 sm:grid-cols-5">
          {Object.entries(m.components).map(([k, v]) => (
            <div key={k}><div className="text-xs text-slate-500">{k.replaceAll("_", " ")}</div><div className="text-lg font-semibold tabular-nums">{v as number}%</div></div>
          ))}
        </div>
        <p className="mt-3 font-mono text-xs text-slate-500">{m.score_formula}</p>
      </Card>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card title={`Classroom utilisation (avg ${m.room_utilization_pct}%)`}><UtilChart rows={data.rooms.filter((r: Any) => r.kind === "CLASSROOM")} /></Card>
        <Card title={`Lab utilisation (avg ${m.lab_utilization_pct}%)`}><UtilChart rows={data.rooms.filter((r: Any) => r.kind === "LAB")} /></Card>
      </div>
      <Card title="Subject completion — required sessions scheduled per class" className="mt-6"><UtilChart rows={completion} height={220} /></Card>
    </>
  );
}
