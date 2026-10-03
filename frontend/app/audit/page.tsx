"use client";
import { useApi, Any } from "@/lib/api";
import { Card, ErrorBox, Loading, PageHeader, Table } from "@/components/ui";

const fmt = (v: Any) => (v == null ? "—" : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join(" · ") : String(v));

export default function AuditPage() {
  const { data, error } = useApi<Any[]>("/audit?limit=300");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader title="Audit Log" subtitle="Every timetable modification with previous and new values." />
      <Card>
        <Table head={["Time", "User", "Action", "Previous", "New", "Reason"]}>
          {data.map((a) => (
            <tr key={a.id} className="align-top">
              <td className="whitespace-nowrap tabular-nums">{a.ts.replace("T", " ")}</td><td>{a.user}</td>
              <td className="whitespace-nowrap font-medium">{a.action.replaceAll("_", " ")}</td>
              <td className="max-w-xs text-xs text-slate-500">{fmt(a.previous)}</td><td className="max-w-xs text-xs">{fmt(a.new)}</td>
              <td className="max-w-sm text-xs text-slate-500">{a.reason ?? ""}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
