"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bot, Send, ShieldCheck } from "lucide-react";
import { api, Any } from "@/lib/api";
import { Button, Card, PageHeader, Table, inputCls, toast } from "@/components/ui";

const EXAMPLES = [
  "Who can substitute Prof. Sharma tomorrow?", "Find free DBMS teachers at 11 AM.", "Why does Prof. Kapoor have 16 lectures?",
  "Find timetable conflicts.", "Reschedule Tuesday's cancelled DBMS lecture.", "Which classroom is free Wednesday at 2 PM?",
  "Which faculty are free during Period 4?",
];
type Msg = { role: "user" | "bot"; text: string; res?: Any };

export default function AssistantPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const ask = async (text: string) => {
    if (!text.trim()) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ("");
    setBusy(true);
    try {
      const res = await api("/assistant", { body: { query: text } });
      setMsgs((m) => [...m, { role: "bot", text: res.text, res }]);
    } catch (e: Any) {
      setMsgs((m) => [...m, { role: "bot", text: `Error: ${e.message}` }]);
    } finally { setBusy(false); }
  };
  const confirm = async (a: Any) => {
    try { await api(a.endpoint, { body: a.payload }); toast(`Done: ${a.label}`); }
    catch (e: Any) { toast(e.message, "error"); }
  };

  return (
    <>
      <PageHeader title="Smart Assistant" subtitle="Natural language → intent → deterministic scheduling function → constraint validation → your confirmation." />
      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <Card className="flex min-h-[32rem] flex-col">
          <div className="max-h-[60vh] min-h-[24rem] space-y-4 overflow-y-auto pr-1">
            {!msgs.length && <div className="flex h-72 flex-col items-center justify-center gap-2 text-center text-sm text-slate-500">
              <Bot className="size-8 text-indigo-400" />Ask about substitutes, free rooms, free teachers, workload or conflicts.</div>}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                <div className={m.role === "user" ? "max-w-[80%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white"
                  : "max-w-full rounded-2xl rounded-bl-sm border border-slate-200 bg-slate-50 px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-800/50"}>
                  <div>{m.text}</div>
                  {m.res?.intent && <div className="mt-1 text-[11px] text-slate-500">intent: {m.res.intent}</div>}
                  {m.res?.rows?.length > 0 && <div className="mt-3 rounded-lg bg-white dark:bg-zinc-900">
                    <Table head={Object.keys(m.res.rows[0])}>
                      {m.res.rows.map((r: Any, j: number) => <tr key={j}>{Object.values(r).map((v: Any, k) => <td key={k} className="align-top">{String(v)}</td>)}</tr>)}
                    </Table></div>}
                  {m.res?.actions?.length > 0 && <div className="mt-3 flex flex-wrap gap-2">
                    {m.res.actions.map((a: Any) => <Button key={a.label} onClick={() => confirm(a)}><ShieldCheck className="size-4" />Confirm: {a.label}</Button>)}</div>}
                  {m.res?.link && <Link className="mt-2 inline-block text-xs text-indigo-600" href={m.res.link}>Open in Absences →</Link>}
                </div>
              </div>
            ))}
            <div ref={end} />
          </div>
          <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <input className={`${inputCls} flex-1`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a scheduling question…" />
            <Button variant="primary" loading={busy} type="submit"><Send className="size-4" />Ask</Button>
          </form>
        </Card>
        <Card title="Try asking">
          <div className="flex flex-col gap-2">{EXAMPLES.map((x) => (
            <button key={x} onClick={() => ask(x)} className="rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:border-zinc-700 dark:hover:bg-zinc-800">{x}</button>))}</div>
          <p className="mt-4 text-xs text-slate-500">The assistant never edits data directly. Proposed changes appear as “Confirm” buttons and go through the same validated API as manual edits.</p>
        </Card>
      </div>
    </>
  );
}
