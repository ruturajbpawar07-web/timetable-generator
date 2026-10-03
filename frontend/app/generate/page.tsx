"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Download, Loader2, Lock, Pencil, RefreshCw, Sparkles, XCircle } from "lucide-react";
import { api, useApi, useMeta, Any } from "@/lib/api";
import { Badge, Button, Card, PageHeader, Select, Stat, Table, toast } from "@/components/ui";

const STEPS = ["Validating input data", "Constructing constraints", "Running CP-SAT optimisation", "Validating result", "Calculating quality metrics"];

export default function GeneratePage() {
  const meta = useMeta();
  const runs = useApi<Any[]>("/runs");
  const [scope, setScope] = useState<Any>({});
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [res, setRes] = useState<Any | null>(null);
  const [seed, setSeed] = useState(0);

  // the solver is one request; the step list just mirrors its pipeline while we wait
  useEffect(() => {
    if (!busy) return;
    setStep(0);
    const t = setInterval(() => setStep((s) => Math.min(s + 1, 2)), 900);
    return () => clearInterval(t);
  }, [busy]);

  const run = async (base?: number, nextSeed = seed) => {
    setBusy(true);
    setRes(null);
    try {
      const body = { ...scope, seed: nextSeed, ...(base ? { base_timetable_id: base } : {}) };
      Object.keys(body).forEach((k) => body[k] === "" && delete body[k]);
      const r = await api("/timetable/generate", { body });
      setStep(5);
      setRes(r);
      if (r.timetable_id) toast(`Generated ${r.status.toLowerCase()} timetable in ${r.generation_time}s`);
      else toast(`Generation failed: ${r.status}`, "error");
      runs.reload();
    } catch (e: Any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const accept = async () => {
    await api(`/timetable/${res.timetable_id}/accept`, { method: "POST" });
    toast("Timetable accepted and now active");
    setRes({ ...res, accepted: true });
  };
  const m = res?.metrics;

  return (
    <>
      <PageHeader title="Generate Timetable" subtitle="Constraint satisfaction + optimisation with Google OR-Tools CP-SAT. Locked periods are never moved." />
      <Card title="Scope">
        <div className="flex flex-wrap items-end gap-3">
          <Select label="Department" value={scope.department_id} onChange={(v) => setScope({ ...scope, department_id: v })} placeholder="All departments"
            options={(meta?.departments ?? []).map((d) => ({ value: d.id, label: d.name }))} />
          <Select label="Program" value={scope.program_id} onChange={(v) => setScope({ ...scope, program_id: v })} placeholder="All programs"
            options={(meta?.programs ?? []).filter((p) => !scope.department_id || p.department_id === Number(scope.department_id)).map((p) => ({ value: p.id, label: p.name }))} />
          <Select label="Academic year" value={meta?.academic_year} onChange={() => {}} options={meta ? [{ value: meta.academic_year, label: meta.academic_year }] : []} />
          <Select label="Year" value={scope.year_level} onChange={(v) => setScope({ ...scope, year_level: v })} placeholder="All years"
            options={["SE", "TE", "BE"].map((y) => ({ value: y, label: y }))} />
          <Select label="Semester" value={scope.semester} onChange={(v) => setScope({ ...scope, semester: v })} placeholder="All semesters"
            options={(meta?.semesters ?? []).map((s) => ({ value: s, label: `Semester ${s}` }))} />
          <Button variant="primary" onClick={() => run()} loading={busy} className="ml-auto px-5 py-2"><Sparkles className="size-4" />Generate Timetable</Button>
        </div>
        <p className="mt-3 text-xs text-slate-500">Divisions outside the selected scope keep their sessions from the active timetable (treated as fixed), so shared faculty and rooms never clash.</p>
      </Card>

      {(busy || res) && (
        <Card title={busy ? "Generating optimized timetable…" : "Result"} className="mt-6">
          <ol className="mb-4 grid gap-2 sm:grid-cols-5">
            {STEPS.map((s, i) => (
              <li key={s} className="flex items-center gap-2 text-sm">
                {step > i || (!busy && res?.timetable_id) ? <CheckCircle2 className="size-4 text-emerald-600" />
                  : busy && step === i ? <Loader2 className="size-4 animate-spin text-indigo-600" />
                  : !busy && res && !res.timetable_id ? <XCircle className="size-4 text-red-500" /> : <Circle className="size-4 text-slate-300" />}
                <span className={step >= i || res ? "" : "text-slate-400"}>{s}</span>
              </li>
            ))}
          </ol>
          {res && !res.timetable_id && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
              <b>{res.status}</b>
              <ul className="mt-1 list-disc pl-5">{(res.issues ?? []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          {m && (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
                <Stat label="Solver status" value={res.status} hint={`${res.generation_time}s`} />
                <Stat label="Hard violations" value={res.hard_constraint_violations} tone={res.hard_constraint_violations ? "bad" : "good"} />
                <Stat label="Unscheduled sessions" value={m.unscheduled_sessions} tone={m.unscheduled_sessions ? "bad" : "good"} />
                <Stat label="Optimisation score" value={m.score} hint="see formula below" />
                <Stat label="Student gaps" value={m.student_gaps} hint={`faculty gaps ${m.faculty_gaps}`} />
                <Stat label="Preferences met" value={`${m.preference_satisfaction_pct}%`} hint={`subject spread ${m.subject_spread_pct}%`} />
              </div>
              <div className="mt-3 grid gap-3 text-xs text-slate-500 md:grid-cols-2">
                <div>Workload σ {m.faculty_workload_std} periods · utilisation σ {m.faculty_utilization_std_pct}% · rooms {m.room_utilization_pct}% · labs {m.lab_utilization_pct}%</div>
                <div className="font-mono">{m.score_formula}</div>
              </div>
              {Object.keys(res.auto_assigned ?? {}).length > 0 && (
                <p className="mt-2 text-xs text-slate-500">{Object.keys(res.auto_assigned).length} requirement(s) had no teacher; the workload balancer assigned the least-utilised qualified faculty.</p>
              )}
              <div className="mt-5 flex flex-wrap gap-2">
                <Button variant="primary" onClick={accept} disabled={res.accepted}><CheckCircle2 className="size-4" />{res.accepted ? "Accepted" : "Accept Timetable"}</Button>
                <Button onClick={() => { setSeed(seed + 1); run(res.timetable_id, seed + 1); }} loading={busy}><RefreshCw className="size-4" />Regenerate (keep locks)</Button>
                <Link href={`/timetable?tid=${res.timetable_id}&edit=1`}><Button><Pencil className="size-4" />Edit Manually</Button></Link>
                <Link href={`/timetable?tid=${res.timetable_id}`}><Button><Lock className="size-4" />Lock Periods</Button></Link>
                <a href={`/api/export?kind=master&format=xlsx&timetable_id=${res.timetable_id}`}><Button><Download className="size-4" />Export</Button></a>
              </div>
            </>
          )}
        </Card>
      )}

      <Card title="Generation history" className="mt-6">
        <Table head={["Run", "Started", "Status", "Scope", "Seed", "Time", "Score", "Issues"]}>
          {(runs.data ?? []).map((r) => (
            <tr key={r.id}>
              <td>#{r.id}</td><td className="whitespace-nowrap">{r.started_at.replace("T", " ")}</td>
              <td><Badge tone={r.status === "OPTIMAL" || r.status === "FEASIBLE" ? "green" : "red"}>{r.status}</Badge></td>
              <td className="text-xs">{Object.keys(r.scope ?? {}).length ? JSON.stringify(r.scope) : "all"}</td>
              <td>{r.seed}</td><td>{r.generation_time}s</td><td>{r.score ?? "–"}</td>
              <td className="max-w-md text-xs text-slate-500">{(r.issues ?? []).join("; ")}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
