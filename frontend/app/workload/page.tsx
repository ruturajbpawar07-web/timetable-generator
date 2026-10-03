"use client";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi, Any } from "@/lib/api";
import Tip from "@/components/ChartTip";
import { Badge, Card, ErrorBox, LoadBar, Loading, PageHeader, Stat, Table } from "@/components/ui";

const STATUS_FILL: Record<string, string> = { OK: "var(--series-1)", UNDERLOADED: "var(--status-warn)", OVERLOADED: "var(--status-bad)" };
const axis = { stroke: "var(--axis)", fontSize: 11, tickLine: false };

export default function WorkloadPage() {
  const { data, error } = useApi("/analytics/workload");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const fac = [...data.faculty].sort((a: Any, b: Any) => b.weekly - a.weekly);
  const days = Object.keys(fac[0]?.daily ?? {});
  const maxDaily = Math.max(1, ...fac.flatMap((f: Any) => Object.values(f.daily) as number[]));
  const count = (s: string) => fac.filter((f: Any) => f.status === s).length;
  return (
    <>
      <PageHeader title="Workload" subtitle="Status uses each faculty member's configured min/max weekly limits — not a global threshold." />
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Within limits" value={count("OK")} tone="good" />
        <Stat label="Underloaded (< min)" value={count("UNDERLOADED")} tone={count("UNDERLOADED") ? "warn" : "default"} />
        <Stat label="Overloaded (> max)" value={count("OVERLOADED")} tone={count("OVERLOADED") ? "bad" : "default"} />
        <Stat label="Workload spread (σ)" value={data.metrics.faculty_workload_std} hint={`utilisation σ ${data.metrics.faculty_utilization_std_pct}%`} />
      </div>
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Lectures per faculty (periods / week)" className="xl:col-span-2"
          action={<div className="flex gap-2 text-xs">{Object.entries(STATUS_FILL).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1"><span className="size-2.5 rounded-sm" style={{ background: c }} />{k.toLowerCase()}</span>))}</div>}>
          <ResponsiveContainer width="100%" height={fac.length * 26 + 30}>
            <BarChart data={fac} layout="vertical" margin={{ left: 10, right: 20 }} barCategoryGap={4}>
              <CartesianGrid horizontal={false} stroke="var(--grid)" />
              <XAxis type="number" {...axis} />
              <YAxis type="category" dataKey="name" width={150} {...axis} axisLine={false} />
              <Tooltip cursor={{ fill: "var(--grid)", opacity: 0.4 }} content={<Tip render={(f: Any) => <>
                <div className="font-semibold">{f.name}</div><div>{f.weekly} periods · limits {f.min_per_week}–{f.max_per_week}</div><div>{f.status.toLowerCase()}</div></>} />} />
              <Bar isAnimationActive={false} dataKey="weekly" radius={[0, 4, 4, 0]} maxBarSize={18}>
                {fac.map((f: Any) => <Cell key={f.faculty_id} fill={STATUS_FILL[f.status]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Department workload (periods / week)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.departments} margin={{ top: 10 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="department" {...axis} /><YAxis {...axis} axisLine={false} width={30} />
              <Tooltip cursor={{ fill: "var(--grid)", opacity: 0.4 }} content={<Tip render={(d: Any) => <>{d.department}: {d.periods} periods</>} />} />
              <Bar isAnimationActive={false} dataKey="periods" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <Card title="Daily workload (periods per day; darker = busier)" className="mt-6">
        <Table head={["Faculty", ...days, "Week", "Limits", "Status"]}>
          {fac.map((f: Any) => (
            <tr key={f.faculty_id}>
              <td className="whitespace-nowrap font-medium">{f.name}</td>
              {days.map((d) => {
                const n = f.daily[d];
                return <td key={d} className="text-center tabular-nums" title={`${n}/${f.max_per_day} max per day`}
                  style={{ background: n ? `color-mix(in srgb, var(--series-1) ${Math.round((n / maxDaily) * 55)}%, transparent)` : undefined }}>{n}</td>;
              })}
              <td className="w-40"><div className="text-xs tabular-nums">{f.weekly}</div><LoadBar value={f.weekly} max={f.max_per_week} min={f.min_per_week} /></td>
              <td className="whitespace-nowrap text-xs text-slate-500">{f.min_per_week}–{f.max_per_week}/wk · {f.max_per_day}/day</td>
              <td><Badge tone={f.status === "OK" ? "green" : f.status === "OVERLOADED" ? "red" : "amber"}>{f.status.toLowerCase()}</Badge></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
