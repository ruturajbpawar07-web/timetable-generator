"""Smart assistant: natural language -> intent -> deterministic query function.

Never writes to the database.  Changes come back as `actions` (endpoint +
payload) that the admin confirms in the UI, which then go through the normal
validated API.  ponytail: rule-based intent parsing; an LLM intent classifier
can replace `detect()` later without touching the query functions.
"""
from __future__ import annotations

import re
from datetime import date as Date, timedelta

from sqlalchemy import select

from . import db, services as svc
from scheduler import validator, substitution as sub

ALIASES = {"dbms": "Database Management Systems", "os": "Operating Systems", "oops": "Object Oriented Programming"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXAMPLES = ["Who can substitute Prof. Sharma tomorrow?", "Find free DBMS teachers at 11 AM.",
            "Why does Prof. Joshi have 13 lectures?", "Find timetable conflicts.",
            "Reschedule Tuesday's cancelled DBMS lecture.", "Which classroom is free Wednesday at 2 PM?",
            "Which faculty are free during Period 4?"]


def acronym(name: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in ("of", "and")).upper()


def find_faculty(p, q):
    ql = q.lower()
    for f in p.faculty:
        last = f.name.split()[-1].lower()
        if re.search(rf"\b{re.escape(last)}\b", ql):
            return f


def find_subject(p, q):
    ql = q.lower()
    for k, name in ALIASES.items():
        if re.search(rf"\b{k}\b", ql):
            return next((s for s in p.subjects if s.name == name), None)
    for s in p.subjects:
        if s.name.lower() in ql or re.search(rf"\b{s.code.lower()}\b", ql):
            return s
    tokens = set(re.findall(r"\b[A-Z]{2,4}\b", q))       # acronyms must be typed in capitals
    return next((s for s in p.subjects if acronym(s.name) in tokens), None)


def find_date(s, q) -> Date:
    ql, today = q.lower(), Date.today()
    if "tomorrow" in ql:
        return today + timedelta(days=1)
    for i, d in enumerate(DAYS):
        if d in ql:
            return today + timedelta(days=(i - today.weekday()) % 7)
    return today


def find_slot(p, q):
    ql = q.lower()
    m = re.search(r"\b(?:period|p)\s*(\d)\b", ql)
    teaching = [x for x in p.slots if not x.is_break]
    if m and 1 <= int(m.group(1)) <= len(teaching):
        return teaching[int(m.group(1)) - 1]
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", ql)
    if m and (m.group(3) or m.group(2)):
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0) if m.group(3) else int(m.group(1))
        return next((x for x in p.slots if int(x.start[:2]) == h and not x.is_break), None)


def answer(s, q: str) -> dict:
    tt = svc.active_timetable(s)
    p, es = svc.problem_and_entries(s, tt.id)
    ql = q.lower()
    f, subj, slot = find_faculty(p, q), find_subject(p, q), find_slot(p, q)
    d = find_date(s, q)
    if svc.day_of(p, d) is None and not any(x in ql for x in DAYS):
        d = d + timedelta(days=(7 - d.weekday()) % 7 or 1)      # weekend -> next Monday
    day_id = svc.day_of(p, d)
    when_txt = f"{d.strftime('%A')} {d.isoformat()}"

    def free_at(fid, ctx, sl):
        pos = p.pos[sl.id]
        return (not ctx.is_absent(p, fid, [pos]) and
                (day_id, sl.id) not in {tuple(x) for x in p.F[fid].unavailable} and
                not any(x.faculty_id == fid and pos in (validator.span(p, x) or []) for x in sub.today_entries(es, ctx)))

    # 1. conflicts
    if "conflict" in ql:
        cs = svc.conflicts(s, tt.id)
        return {"intent": "find_conflicts", "text": f"Found {len(cs)} conflict(s) in {tt.name}." if cs
                else f"No conflicts — {tt.name} satisfies every hard constraint.",
                "rows": [{"type": c["type"], "message": c["message"]} for c in cs]}

    # 2. substitutes for an absent teacher
    if f and any(w in ql for w in ("substitut", "cover", "replace", "absent")):
        if day_id is None:
            return {"intent": "substitute", "text": f"{d} is not a working day."}
        res = svc.analyse_absence(s, f.id, d, simulate=True)
        rows = [{"lecture": f"{x['when']} · {x['subject']} · {x['class']}",
                 "best substitute": x["substitute"] or "— none eligible (reschedule)",
                 "why": "; ".join(r["text"] for r in x["reasons"] if r["ok"])} for x in res["plan"]]
        sm = res["summary"]
        return {"intent": "substitute", "text": f"If {f.name} is absent on {when_txt}: {sm['affected']} lecture(s) affected, "
                f"{sm['auto_substitutable']} can be covered, {sm['needs_reschedule']} need rescheduling.",
                "rows": rows, "link": f"/absences?faculty={f.id}&date={d.isoformat()}"}

    # 3. workload explanation
    if f and ("why" in ql or "workload" in ql or "lectures" in ql):
        mine = [e for e in es if e.faculty_id == f.id]
        total = sum(e.duration for e in mine)
        parts = {}
        for e in mine:
            k = f"{p.S[e.subject_id].name} — {p.C[e.class_id].name} ({validator.COMPONENT[e.component]})"
            parts[k] = parts.get(k, 0) + e.duration
        return {"intent": "explain_workload",
                "text": f"{f.name} teaches {total} periods/week (limit {f.min_per_week}–{f.max_per_week}). "
                        f"It comes from {len(parts)} assigned requirement(s); practicals count every period of the block.",
                "rows": [{"assignment": k, "periods": v} for k, v in sorted(parts.items(), key=lambda kv: -kv[1])]}

    # 4. reschedule a cancelled lecture
    if "reschedul" in ql:
        cands = s.scalars(select(db.Substitution).where(db.Substitution.status == "CANCELLED")).all()
        by_id = {e.id: e for e in es}
        match = [x for x in cands if x.entry_id in by_id
                 and (not subj or by_id[x.entry_id].subject_id == subj.id)
                 and (not any(dn in ql for dn in DAYS) or by_id[x.entry_id].day_id == day_id)]
        if not match:
            return {"intent": "reschedule", "text": "No cancelled lecture matches. Cancel it first on the Absences page "
                    "(or name the subject and day, e.g. \"Reschedule Tuesday's cancelled DBMS lecture\")."}
        x = match[0]
        e = by_id[x.entry_id]
        opts = sub.reschedule_options(p, es, e, svc.contexts_after(s, p, es, x.date + timedelta(days=1)))
        return {"intent": "reschedule", "text": f"Free slots for {p.S[e.subject_id].name} · {validator.cls_name(p, e)} "
                f"(cancelled {x.date}) where {p.F[e.faculty_id].name}, the class and a room are all free:",
                "rows": [{"option": o["label"]} for o in opts],
                "actions": [{"label": f"Reschedule to {o['label']}", "endpoint": "/substitution/reschedule",
                             "payload": {"entry_id": e.id, "date": x.date.isoformat(), "new_date": o["date"],
                                         "slot_id": o["slot_id"], "room_id": o["room_id"]}} for o in opts[:4]]}

    if day_id is None:
        return {"intent": "unknown", "text": f"{d} is not a working day. Try one of:", "rows": [{"example": x} for x in EXAMPLES]}
    ctx = svc.context(s, p, es, d)

    # 5. free rooms
    if slot and any(w in ql for w in ("room", "classroom", "lab")) and "free" in ql:
        kind = "LAB" if "lab" in ql else "CLASSROOM"
        pos = p.pos[slot.id]
        used = {x.room_id for x in sub.today_entries(es, ctx) if pos in (validator.span(p, x) or [])}
        free = [r for r in p.rooms if r.kind == kind and r.id not in used]
        return {"intent": "free_rooms", "text": f"{len(free)} {kind.lower()}(s) free on {when_txt} at {slot.start}.",
                "rows": [{"room": r.code, "capacity": r.capacity, "type": r.lab_type or kind.title()} for r in free]}

    # 6/7. free teachers (optionally for a subject)
    if slot and "free" in ql:
        pool = [x for x in p.faculty if not subj or subj.id in x.subject_ids]
        free = [x for x in pool if free_at(x.id, ctx, slot)]
        what = f"{subj.name} teachers" if subj else "faculty"
        return {"intent": "free_faculty", "text": f"{len(free)} of {len(pool)} {what} free on {when_txt} at {slot.start}.",
                "rows": [{"faculty": x.name, "periods today": sum(e.duration for e in sub.today_entries(es, ctx)
                                                                if e.faculty_id == x.id)} for x in free]}

    return {"intent": "unknown", "text": "I can answer scheduling questions like:",
            "rows": [{"example": x} for x in EXAMPLES]}
