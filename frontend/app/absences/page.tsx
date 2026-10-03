"use client";
import { useEffect, useState } from "react";
import { CalendarClock, FlaskConical, Trash2, UserCheck, Wand2, XCircle } from "lucide-react";
import { api, useApi, useMeta, Any } from "@/lib/api";
import { Badge, Button, Card, Empty, Loading, PageHeader, Reason, Select, Stat, StatusBadge, cx, inputCls, toast } from "@/components/ui";

export default function AbsencesPage() {
  const meta = useMeta();
  const list = useApi<Any[]>("/absences");
  const [form, setForm] = useState<Any>({ faculty_id: "", date: "", full: true, slots: [] as number[], reason: "" });
  const [res, setRes] = useState<Any | null>(null);
  const [mode, setMode] = useState<"real" | "sim">("real");
  const [busy, setBusy] = useState("");

  useEffect(() => { if (meta && !form.date) setForm((f: Any) => ({ ...f, date: meta.today })); }, [meta, form.date]);
  // deep link from the assistant: ?faculty=&date=  -> what-if analysis
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("faculty") && q.get("date")) {
      setForm((f: Any) => ({ ...f, faculty_id: q.get("faculty"), date: q.get("date") }));
      simulate(Number(q.get("faculty")), q.get("date")!);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const body = () => ({ faculty_id: Number(form.faculty_id), date: form.date, slot_ids: form.full ? null : form.slots, reason: form.reason || null });
  const load = async (faculty_id: number, date: string) => {
    setMode("real");
    setRes(await api(`/absence/analysis?faculty_id=${faculty_id}&date=${date}`));
  };
  const submit = async () => {
    setBusy("submit");
    try {
      const r = await api("/faculty/absence", { body: body() });
      setMode("real"); setRes(r); list.reload();
      toast(`${r.faculty} marked absent — ${r.affected.length} lecture(s) affected`);
    } catch (e: Any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  async function simulate(faculty_id?: number, date?: string) {
    setBusy("sim");
    try {
      setMode("sim");
      setRes(await api("/simulate/absence", { body: faculty_id ? { faculty_id, date } : body() }));
    } catch (e: Any) { toast(e.message, "error"); } finally { setBusy(""); }
  }
  const autoAll = async () => {
    setBusy("auto");
    try {
      const r = await api("/substitution/auto", { body: { faculty_id: res.faculty_id, date: res.date } });
      toast(`Assigned ${r.assigned.length} substitute(s)${r.unresolved.length ? `, ${r.unresolved.length} need rescheduling` : ""}`);
      await load(res.faculty_id, res.date);
    } finally { setBusy(""); }
  };
  const remove = async (a: Any) => {
    await api(`/faculty/absence?faculty_id=${a.faculty_id}&date=${a.date}`, { method: "DELETE" });
    toast("Absence removed"); list.reload(); setRes(null);
  };

  if (!meta) return <Loading />;
  const teaching = meta.slots.filter((s) => !s.is_break);
  const canSubmit = form.faculty_id && form.date && (form.full || form.slots.length);

  return (
    <>
      <PageHeader title="Absences" subtitle="Record an absence: affected lectures are found immediately and ranked substitutes are proposed. Nothing is assigned without your confirmation." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Mark faculty absent" className="lg:col-span-2">
          <div className="grid gap-3 sm:grid-cols-3">
            <Select label="Faculty" value={form.faculty_id} onChange={(v) => setForm({ ...form, faculty_id: v })} placeholder="Select faculty…"
              options={meta.faculty.map((f) => ({ value: f.id, label: f.name }))} />
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">Date
              <input type="date" className={inputCls} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">Reason (optional)
              <input className={inputCls} value={form.reason} placeholder="e.g. Medical leave" onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" checked={form.full} onChange={() => setForm({ ...form, full: true })} />Full day</label>
            <label className="mr-2 flex items-center gap-1.5"><input type="radio" checked={!form.full} onChange={() => setForm({ ...form, full: false })} />Specific periods</label>
            {!form.full && teaching.map((s) => (
              <button key={s.id} onClick={() => setForm({ ...form, slots: form.slots.includes(s.id) ? form.slots.filter((x: number) => x !== s.id) : [...form.slots, s.id] })}
                className={cx("rounded-md border px-2 py-1 text-xs", form.slots.includes(s.id) ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300" : "border-slate-200 dark:border-zinc-700")}>
                {s.label} {s.start}</button>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <Button variant="primary" disabled={!canSubmit} loading={busy === "submit"} onClick={submit}>Submit absence</Button>
            <Button disabled={!canSubmit} loading={busy === "sim"} onClick={() => simulate()}><FlaskConical className="size-4" />What-if simulation</Button>
          </div>
        </Card>
        <Card title="Recorded absences">
          {list.data?.length ? (
            <ul className="space-y-2">{list.data.map((a) => (
              <li key={`${a.faculty_id}${a.date}`} className="flex items-center justify-between gap-2 text-sm">
                <button className="text-left hover:text-indigo-600" onClick={() => { setForm({ ...form, faculty_id: String(a.faculty_id) }); load(a.faculty_id, a.date); }}>
                  <div className="font-medium">{a.faculty}</div>
                  <div className="text-xs text-slate-500">{a.date} · {a.full_day ? "full day" : `${a.slot_ids.length} period(s)`}{a.reason ? ` · ${a.reason}` : ""}</div>
                </button>
                <button onClick={() => remove(a)} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Remove absence"><Trash2 className="size-4" /></button>
              </li>))}</ul>
          ) : <Empty title="No absences recorded" hint="Try: Prof. Anil Sharma, full day, on a weekday." />}
        </Card>
      </div>

      {res && !res.working_day && <Card className="mt-6"><Empty title={`${res.date} is not a working day`} /></Card>}
      {res?.working_day && mode === "sim" && <Simulation res={res} onApply={submit} />}
      {res?.working_day && mode === "real" && (
        <Card className="mt-6" title={<span className="uppercase tracking-wide">{res.faculty} absent · {res.date}</span>}
          action={res.affected.some((x: Any) => x.status === "PENDING") && <Button variant="primary" loading={busy === "auto"} onClick={autoAll}><Wand2 className="size-4" />Auto assign all</Button>}>
          {res.affected.length ? <div className="space-y-4">
            {res.affected.map((x: Any) => <Affected key={x.entry_id} x={x} date={res.date} onDone={() => load(res.faculty_id, res.date)} />)}
          </div> : <Empty title="No lectures affected" hint="This faculty member teaches nothing in the selected periods." />}
        </Card>
      )}
    </>
  );
}

function Simulation({ res, onApply }: { res: Any; onApply: () => void }) {
  const s = res.summary;
  return (
    <Card className="mt-6" title={<span className="flex items-center gap-2"><FlaskConical className="size-4" />What happens if {res.faculty} is absent on {res.date}? <Badge tone="amber">simulation — nothing saved</Badge></span>}
      action={<Button variant="primary" onClick={onApply}>Record this absence</Button>}>
      <div className="mb-4 grid grid-cols-3 gap-3">
        <Stat label="Affected lectures" value={s.affected} />
        <Stat label="Automatic substitutions possible" value={s.auto_substitutable} tone="good" />
        <Stat label="Requires rescheduling" value={s.needs_reschedule} tone={s.needs_reschedule ? "bad" : "good"} />
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-zinc-800">
        {res.plan.map((p: Any) => (
          <li key={p.entry_id} className="py-2 text-sm">
            <div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{p.when} · {p.subject} · {p.class}</span>
              {p.substitute ? <Badge tone="green">→ {p.substitute}</Badge> : <Badge tone="red">no eligible substitute</Badge>}</div>
            {p.reasons.length > 0 && <div className="mt-1 text-xs text-slate-500">{p.reasons.filter((r: Any) => r.ok).map((r: Any) => r.text).join(" · ")}</div>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Affected({ x, date, onDone }: { x: Any; date: string; onDone: () => void }) {
  const [alt, setAlt] = useState(false);
  const [resched, setResched] = useState(false);
  const best = x.candidates.find((c: Any) => c.eligible);
  const act = async (fn: () => Promise<Any>, msg: string) => {
    try { await fn(); toast(msg); onDone(); } catch (e: Any) { toast(e.message, "error"); }
  };
  const assign = (c: Any) => act(() => api("/substitution/assign", { body: { entry_id: x.entry_id, date, faculty_id: c.faculty_id } }), `${c.name} assigned to ${x.subject} · ${x.class}`);

  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><div className="font-semibold">{x.start} — {x.subject} — {x.class}</div>
          <div className="text-xs text-slate-500">{x.when} · {x.room} · originally {x.faculty}</div></div>
        <div className="flex items-center gap-2"><StatusBadge s={x.status} />{x.substitute && <Badge tone="blue"><UserCheck className="size-3" />{x.substitute}</Badge>}</div>
      </div>

      {best ? (
        <div className="mt-3 rounded-lg bg-emerald-50/60 p-3 dark:bg-emerald-950/30">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Recommended: {best.name} <span className="font-normal normal-case">(score {best.score})</span></div>
          <ul className="grid gap-1 sm:grid-cols-2">{best.reasons.map((r: Any, i: number) => <Reason key={i} text={r.text} ok={r.ok} />)}</ul>
        </div>
      ) : (
        <div className="mt-3 rounded-lg bg-red-50/70 p-3 text-sm dark:bg-red-950/30">
          <div className="mb-1 flex items-center gap-1.5 font-semibold text-red-700 dark:text-red-300"><XCircle className="size-4" />No eligible substitute</div>
          <ul className="space-y-1">{x.candidates.map((c: Any) => (
            <li key={c.faculty_id}><b>{c.name}</b>: {c.reasons.filter((r: Any) => !r.ok).map((r: Any) => r.text).join("; ")}</li>))}
            {!x.candidates.length && <li>No other faculty member is authorized to teach {x.subject}.</li>}
          </ul>
          {x.unqualified_free > 0 && <p className="mt-1 text-xs text-slate-500">{x.unqualified_free} other faculty are free but not authorized for {x.subject}, so they are not eligible.</p>}
          <p className="mt-1 text-xs">Suggestion: reschedule this lecture or cancel it.</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {best && <Button variant="primary" onClick={() => assign(best)}>Assign {best.name.split(" ").slice(-1)}</Button>}
        <Button onClick={() => setAlt(!alt)}>View alternatives ({x.candidates.length})</Button>
        <Button variant="danger" onClick={() => act(() => api("/substitution/cancel", { body: { entry_id: x.entry_id, date, reason: "Faculty absent" } }), "Lecture cancelled")}>Cancel lecture</Button>
        <Button onClick={() => setResched(!resched)}><CalendarClock className="size-4" />Reschedule</Button>
      </div>

      {alt && (
        <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-100 dark:divide-zinc-800 dark:border-zinc-800">
          {x.candidates.map((c: Any) => (
            <li key={c.faculty_id} className="flex flex-wrap items-start justify-between gap-2 p-3 text-sm">
              <div className="min-w-0 flex-1"><div className="font-medium">{c.name} <Badge tone={c.eligible ? "green" : "red"}>{c.eligible ? `eligible · ${c.score}` : "not eligible"}</Badge></div>
                <div className="mt-1 text-xs text-slate-500">{c.reasons.map((r: Any) => `${r.ok ? "✓" : "✗"} ${r.text}`).join("  ")}</div></div>
              {c.eligible && <Button onClick={() => assign(c)}>Assign</Button>}
            </li>
          ))}
        </ul>
      )}
      {resched && (
        <div className="mt-3 flex flex-wrap gap-2">
          {(x.reschedule_options ?? []).map((o: Any) => (
            <Button key={o.label} variant="ghost" className="border-slate-200 dark:border-zinc-700"
              onClick={() => act(() => api("/substitution/reschedule", { body: { entry_id: x.entry_id, date, new_date: o.date, slot_id: o.slot_id, room_id: o.room_id } }), `Rescheduled to ${o.label}`)}>
              {o.label}</Button>
          ))}
          {!x.reschedule_options?.length && <span className="text-sm text-slate-500">No free slot in the next 7 days where teacher, class and a room are all free.</span>}
        </div>
      )}
    </div>
  );
}
