"use client";
import Link from "next/link";
import { useApi, Any } from "@/lib/api";
import { Badge, Card, ErrorBox, LoadBar, Loading, PageHeader, Table } from "@/components/ui";

export default function RoomsPage() {
  const rooms = useApi<Any[]>("/rooms");
  const w = useApi("/analytics/workload");
  if (rooms.error) return <ErrorBox error={rooms.error} />;
  if (!rooms.data || !w.data) return <Loading />;
  const use = new Map(w.data.rooms.map((r: Any) => [r.room_id, r]));
  return (
    <>
      <PageHeader title="Rooms & Labs" subtitle="Theory sessions need a classroom ≥ class strength; practicals need a lab of the subject's lab type ≥ batch strength." />
      <Card>
        <Table head={["Room", "Type", "Capacity", "Lab type", "Periods used / week", "Utilisation", ""]}>
          {rooms.data.map((r) => {
            const u: Any = use.get(r.id) ?? { used: 0, utilization: 0 };
            return (
              <tr key={r.id}>
                <td><div className="font-medium">{r.code}</div><div className="text-xs text-slate-500">{r.name}</div></td>
                <td><Badge tone={r.kind === "LAB" ? "violet" : "gray"}>{r.kind.toLowerCase()}</Badge></td>
                <td className="tabular-nums">{r.capacity}</td><td>{r.lab_type ?? "—"}</td>
                <td className="tabular-nums">{u.used}</td>
                <td className="w-56"><div className="mb-1 text-xs">{u.utilization}%</div><LoadBar value={u.utilization} max={100} /></td>
                <td><Link className="text-xs text-indigo-600" href={`/timetable?view=${r.kind === "LAB" ? "lab" : "room"}&id=${r.id}`}>Schedule →</Link></td>
              </tr>
            );
          })}
        </Table>
      </Card>
    </>
  );
}
