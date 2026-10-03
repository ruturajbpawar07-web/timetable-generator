"use client";
import Link from "next/link";
import { Download } from "lucide-react";
import { useApi, Any } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge, Table } from "@/components/ui";

export default function SubstitutionsPage() {
  const pending = useApi<Any[]>("/substitutions/pending");
  const hist = useApi<Any[]>("/substitutions");
  if (hist.error) return <ErrorBox error={hist.error} />;
  if (!hist.data || !pending.data) return <Loading />;
  const open = pending.data.filter((p) => p.status === "PENDING");
  return (
    <>
      <PageHeader title="Substitutions" subtitle="Date-specific cover, cancellations and rescheduled lectures. The weekly timetable itself is never altered."
        actions={<a href="/api/export?kind=substitutions&format=xlsx"><Button><Download className="size-4" />Substitution report</Button></a>} />
      <Card title={`Pending (${open.length})`} action={<Link href="/absences" className="text-xs text-indigo-600">Resolve on Absences →</Link>}>
        {open.length ? (
          <Table head={["Date", "Lecture", "Absent", "Top candidate"]}>
            {open.map((p) => {
              const best = p.candidates.find((c: Any) => c.eligible);
              return (
                <tr key={`${p.date}${p.entry_id}`}>
                  <td>{p.date}</td><td>{p.when} · {p.subject} · {p.class}</td><td>{p.absent_faculty}</td>
                  <td>{best ? <Badge tone="green">{best.name} ({best.score})</Badge> : <Badge tone="red">none — reschedule</Badge>}</td>
                </tr>
              );
            })}
          </Table>
        ) : <Empty title="Nothing pending" hint="Every lecture affected by an absence in the next 7 days has been handled." />}
      </Card>
      <Card title="History" className="mt-6">
        {hist.data.length ? (
          <Table head={["Date", "Status", "Lecture", "Original", "Covered by / new slot", "Why"]}>
            {hist.data.map((x) => (
              <tr key={x.id}>
                <td className="whitespace-nowrap">{x.date}</td><td><StatusBadge s={x.status} /></td>
                <td>{x.subject} · {x.class}<div className="text-xs text-slate-500">{x.when} · {x.room}</div></td>
                <td>{x.original}</td><td>{x.substitute ?? x.new_when ?? "—"}</td>
                <td className="max-w-md text-xs text-slate-500">{x.reasons.join(" · ") || x.reason}</td>
              </tr>
            ))}
          </Table>
        ) : <Empty title="No substitutions yet" />}
      </Card>
    </>
  );
}
