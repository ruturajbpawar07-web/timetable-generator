"use client";
import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Wand2 } from "lucide-react";
import { api, useApi, Any } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, toast } from "@/components/ui";

export default function ConflictsPage() {
  const { data, error, reload } = useApi<Any[]>("/conflicts");
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading label="Checking every hard constraint…" />;
  const resolve = async () => {
    setBusy(true);
    try {
      const r = await api("/conflicts/resolve", { body: {} });
      toast(r.status === "NO_CONFLICTS" ? "Nothing to resolve" : `Re-optimised ${r.changed} conflicting entries; everything else stayed fixed`);
      reload();
    } catch (e: Any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const groups: Record<string, Any[]> = {};
  for (const c of data) (groups[c.type] ??= []).push(c);
  return (
    <>
      <PageHeader title="Conflicts" subtitle="Faculty, class, room, lab, workload, credit, availability, practical-block and substitute checks on the active timetable."
        actions={data.length > 0 && <Button variant="primary" loading={busy} onClick={resolve}><Wand2 className="size-4" />Resolve automatically</Button>} />
      {data.length === 0 ? (
        <Card><Empty icon={<CheckCircle2 className="size-8 text-emerald-500" />} title="No conflicts — every hard constraint is satisfied"
          hint="To see detection in action: open a faculty profile and mark a slot they teach as unavailable, then come back here and use “Resolve automatically”." /></Card>
      ) : (
        <div className="space-y-4">
          {Object.entries(groups).map(([type, cs]) => (
            <Card key={type} title={<span className="flex items-center gap-2"><AlertTriangle className="size-4 text-red-500" />{type.replaceAll("_", " ")} <Badge tone="red">{cs.length}</Badge></span>}>
              <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
                {cs.map((c, i) => (
                  <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <span>{c.message}</span>
                    <span className="flex gap-2"><Badge tone={c.severity === "hard" ? "red" : "amber"}>{c.severity}</Badge>
                      <Link href="/timetable?edit=1" className="text-xs text-indigo-600">Edit →</Link></span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
