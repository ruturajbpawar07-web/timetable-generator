"use client";
import { useEffect, useState } from "react";
import { api, useApi, Any } from "@/lib/api";
import { Button, Card, ErrorBox, Loading, PageHeader, Table, inputCls, toast } from "@/components/ui";

const GROUPS: [string, (k: string) => boolean][] = [
  ["General", (k) => ["college_name", "academic_year"].includes(k)],
  ["Hard limits & solver", (k) => k.startsWith("max_") || k.startsWith("solver") || k.startsWith("student_max")],
  ["Substitute ranking", (k) => k.startsWith("sub")],
  ["Soft constraint weights", () => true],
];

export default function SettingsPage() {
  const { data, error, reload } = useApi<Any[]>("/settings");
  const [vals, setVals] = useState<Record<string, string>>({});
  useEffect(() => { if (data) setVals(Object.fromEntries(data.map((c) => [c.key, c.value]))); }, [data]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const save = async () => { await api("/settings", { method: "PUT", body: vals }); toast("Settings saved — used by the next generation"); reload(); };
  const seen = new Set<string>();
  return (
    <>
      <PageHeader title="Settings" subtitle="Constraint weights live in the ConstraintConfiguration table — nothing is hard-coded in the solver."
        actions={<Button variant="primary" onClick={save}>Save changes</Button>} />
      <div className="space-y-6">
        {GROUPS.map(([name, match]) => {
          const rows = data.filter((c) => !seen.has(c.key) && match(c.key));
          rows.forEach((c) => seen.add(c.key));
          return (
            <Card key={name} title={name}>
              <Table head={["Key", "Value", "Description"]}>
                {rows.map((c) => (
                  <tr key={c.key}>
                    <td className="font-mono text-xs">{c.key}</td>
                    <td><input className={`${inputCls} w-56`} value={vals[c.key] ?? ""} onChange={(e) => setVals({ ...vals, [c.key]: e.target.value })} /></td>
                    <td className="text-xs text-slate-500">{c.description}</td>
                  </tr>
                ))}
              </Table>
            </Card>
          );
        })}
        <Card title="Data import">
          <p className="text-sm text-slate-600 dark:text-zinc-300">The dataset is loaded from a folder of CSV/XLSX files (faculty, subjects, rooms, classes, assignments, availability, …).
            To load real college data, put the files in <code className="rounded bg-slate-100 px-1 dark:bg-zinc-800">data/college/</code> and run
            <code className="ml-1 rounded bg-slate-100 px-1 dark:bg-zinc-800">backend/.venv/bin/python -m backend.importer data/college</code>. See docs/DATA_IMPORT.md.</p>
        </Card>
      </div>
    </>
  );
}
