"""Application services: the only place that talks to both the DB and the scheduler.

DB rows -> scheduler.model.Problem/Entry (adapter), then every mutation is
validated by scheduler.validator / scheduler.substitution before it is saved,
and written to the audit log.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date as Date, timedelta
from typing import Optional

from sqlalchemy import select

from . import db
from scheduler import model as M, solver, validator, substitution as sub


class Rejected(Exception):
    """A change that would violate a hard constraint."""
    def __init__(self, message: str, conflicts: list | None = None):
        super().__init__(message)
        self.conflicts = conflicts or []


# ---------------- adapter ----------------
def config(s) -> dict:
    return {c.key: c.value for c in s.scalars(select(db.ConstraintConfiguration))}


def weights(s) -> dict:
    out = {}
    for k, v in config(s).items():
        try:
            out[k] = float(v)
        except ValueError:
            pass
    return out


def build_problem(s, locked: list[M.Entry] | None = None, extra_unavailable: dict | None = None) -> M.Problem:
    avail = defaultdict(lambda: {"UNAVAILABLE": [], "PREFERRED": []})
    for a in s.scalars(select(db.FacultyAvailability)):
        avail[a.faculty_id][a.kind].append((a.day_id, a.slot_id))
    for fid, pairs in (extra_unavailable or {}).items():
        avail[fid]["UNAVAILABLE"] += pairs
    divisions = s.scalars(select(db.Division)).all()
    reqs = s.scalars(select(db.SubjectRequirement)).all()
    locked = locked or []
    # a requirement with no teacher but already-locked sessions keeps that teacher
    locked_fac = {e.demand_id: e.faculty_id for e in locked}
    return M.Problem(
        days=[M.Day(d.id, d.name) for d in s.scalars(select(db.WorkingDay).order_by(db.WorkingDay.order))],
        slots=[M.Slot(t.id, t.index, t.start, t.end, t.is_break) for t in s.scalars(select(db.TimeSlot))],
        faculty=[M.Faculty(f.id, f.name, f.department_id, [x.id for x in f.subjects], f.max_per_day, f.max_per_week,
                           f.min_per_week, f.max_consecutive, avail[f.id]["UNAVAILABLE"], avail[f.id]["PREFERRED"])
                 for f in s.scalars(select(db.Faculty).where(db.Faculty.active))],
        subjects=[M.Subject(x.id, x.code, x.name, x.department_id, x.is_core, x.morning_preferred, x.lab_type)
                  for x in s.scalars(select(db.Subject))],
        classes=[M.ClassGroup(d.id, d.code, d.program.department_id, d.year_level, d.strength,
                              [M.Batch(b.id, b.name, b.strength) for b in d.batches], d.home_room_id) for d in divisions],
        rooms=[M.Room(r.id, r.code, r.kind, r.capacity, r.lab_type) for r in s.scalars(select(db.Room))],
        demands=[M.Demand(r.id, r.division_id, r.subject_id, r.component, r.sessions_per_week, r.duration_periods,
                          r.batch_id, (r.assignment.faculty_id if r.assignment else None) or locked_fac.get(r.id))
                 for r in reqs],
        locked=locked,
        weights=weights(s),
    )


def to_entry(e: db.TimetableEntry) -> M.Entry:
    return M.Entry(id=e.id, demand_id=e.requirement_id, class_id=e.division_id, batch_id=e.batch_id,
                   subject_id=e.subject_id, component=e.component, faculty_id=e.faculty_id, room_id=e.room_id,
                   day_id=e.day_id, slot_id=e.slot_id, duration=e.duration, locked=e.locked,
                   explanation=e.explanation or [])


def rows(s, tid: int) -> list[db.TimetableEntry]:
    return s.scalars(select(db.TimetableEntry).where(db.TimetableEntry.timetable_id == tid)).all()


def entries(s, tid: int) -> list[M.Entry]:
    return [to_entry(e) for e in rows(s, tid)]


def problem_and_entries(s, tid: int):
    es = entries(s, tid)
    p = build_problem(s, locked=[e for e in es if e.locked])
    # demands must carry the teacher actually scheduled (covers auto-assigned ones)
    by_dem = {e.demand_id: e.faculty_id for e in es}
    for d in p.demands:
        d.faculty_id = d.faculty_id or by_dem.get(d.id)
    return p, es


def active_timetable(s) -> Optional[db.Timetable]:
    return (s.scalar(select(db.Timetable).where(db.Timetable.status == "ACTIVE"))
            or s.scalar(select(db.Timetable).order_by(db.Timetable.id.desc())))


def audit(s, action: str, previous=None, new=None, reason: str | None = None):
    s.add(db.AuditLog(action=action, previous=previous, new=new, reason=reason))


def describe(p: M.Problem, e: M.Entry) -> dict:
    return {"subject": p.S[e.subject_id].name, "class": validator.cls_name(p, e), "faculty": p.F[e.faculty_id].name,
            "room": p.R[e.room_id].code, "when": validator.when(p, e.day_id, e.slot_id, e.duration)}


# ---------------- generation ----------------
def in_scope(s, scope: dict) -> set[int]:
    """Division ids matching the admin's Department/Program/Year/Semester filter."""
    q = select(db.Division).join(db.Program).join(db.Semester)
    if scope.get("department_id"):
        q = q.where(db.Program.department_id == scope["department_id"])
    if scope.get("program_id"):
        q = q.where(db.Division.program_id == scope["program_id"])
    if scope.get("year_level"):
        q = q.where(db.Division.year_level == scope["year_level"])
    if scope.get("semester"):
        q = q.where(db.Semester.number == int(scope["semester"]))
    return {d.id for d in s.scalars(q)}


def generate(s, scope: dict | None = None, base_id: int | None = None, seed: int = 0) -> dict:
    """Solve and store the result as a new DRAFT timetable.

    Entries of `base_id` that are locked, or that belong to divisions outside the
    scope, are passed to the solver as fixed.  Everything else is re-optimised.
    """
    scope = scope or {}
    divs = in_scope(s, scope)
    base = entries(s, base_id) if base_id else []
    fixed = [e for e in base if e.locked or e.class_id not in divs]
    p = build_problem(s, locked=fixed)
    result = solver.solve(p, seed=seed)

    run = db.GenerationRun(status=result["status"], seed=seed, scope=scope, generation_time=result["generation_time"],
                           metrics=result.get("metrics"), issues=result.get("issues"))
    s.add(run)
    s.flush()
    out = {k: v for k, v in result.items() if k != "entries"}
    out["run_id"] = run.id
    if not result["entries"]:
        audit(s, "GENERATION_FAILED", new={"run": run.id, "status": result["status"]}, reason="; ".join(result.get("issues", [])))
        s.commit()
        return out
    tt = db.Timetable(name=f"Draft #{run.id}", status="DRAFT", generation_run_id=run.id)
    s.add(tt)
    s.flush()
    for e in result["entries"]:
        expl = list(e.explanation)
        if e.demand_id in result.get("auto_assigned", {}):
            expl.append(f"⚙ {p.F[e.faculty_id].name} chosen by the workload balancer (lowest utilisation among qualified faculty)")
        s.add(db.TimetableEntry(timetable_id=tt.id, requirement_id=e.demand_id, division_id=e.class_id,
                                batch_id=e.batch_id, subject_id=e.subject_id, faculty_id=e.faculty_id,
                                room_id=e.room_id, day_id=e.day_id, slot_id=e.slot_id, duration=e.duration,
                                component=e.component, locked=e.locked, explanation=expl))
    audit(s, "TIMETABLE_GENERATED", new={"timetable_id": tt.id, "status": result["status"], "score": result.get("soft_score")},
          reason=f"Scope {scope or 'all'}; {len(fixed)} fixed entries kept")
    s.commit()
    out["timetable_id"] = tt.id
    return out


def accept(s, tid: int):
    for t in s.scalars(select(db.Timetable).where(db.Timetable.status == "ACTIVE")):
        t.status = "ARCHIVED"
    tt = s.get(db.Timetable, tid)
    tt.status = "ACTIVE"
    tt.name = tt.name.replace("Draft", "Timetable")
    audit(s, "TIMETABLE_ACCEPTED", new={"timetable_id": tid})
    s.commit()


# ---------------- manual edit / locks / conflicts ----------------
def move(s, tid: int, entry_id: int, day_id: int, slot_id: int, room_id: int | None = None,
         dry_run: bool = False) -> dict:
    p, es = problem_and_entries(s, tid)
    idx = next(i for i, e in enumerate(es) if e.id == entry_id)
    if es[idx].locked:
        raise Rejected("This entry is locked. Unlock it before moving.")
    moved, conflicts = validator.validate_move(p, es, idx, day_id, slot_id, room_id)
    if conflicts:
        raise Rejected("Cannot move lecture. " + conflicts[0]["message"] + ".", conflicts)
    if dry_run:
        return {"ok": True}
    row = s.get(db.TimetableEntry, entry_id)
    before = describe(p, es[idx])
    row.day_id, row.slot_id, row.room_id = moved.day_id, moved.slot_id, moved.room_id
    es[idx] = moved
    row.explanation = validator.explain(p, es, moved) + ["✎ Moved manually by admin"]
    audit(s, "LECTURE_MOVED", before, describe(p, moved))
    s.commit()
    return {"ok": True}


def set_lock(s, timetable_id: int, locked: bool, entry_ids=None, day_id=None, division_id=None, faculty_id=None,
             component=None) -> int:
    q = select(db.TimetableEntry).where(db.TimetableEntry.timetable_id == timetable_id)
    if entry_ids:
        q = q.where(db.TimetableEntry.id.in_(entry_ids))
    if day_id:
        q = q.where(db.TimetableEntry.day_id == day_id)
    if division_id:
        q = q.where(db.TimetableEntry.division_id == division_id)
    if faculty_id:
        q = q.where(db.TimetableEntry.faculty_id == faculty_id)
    if component:
        q = q.where(db.TimetableEntry.component == component)
    n = 0
    for e in s.scalars(q):
        e.locked = locked
        n += 1
    audit(s, "LOCK" if locked else "UNLOCK", new={"timetable_id": timetable_id, "entries": n, "entry_ids": entry_ids,
                                                  "day_id": day_id, "division_id": division_id, "faculty_id": faculty_id})
    s.commit()
    return n


def conflicts(s, tid: int) -> list[dict]:
    p, es = problem_and_entries(s, tid)
    out = validator.find_conflicts(p, es)
    # substitutions that became invalid (e.g. substitute later marked absent/unavailable)
    for x in s.scalars(select(db.Substitution).where(db.Substitution.status == "SUBSTITUTED",
                                                     db.Substitution.date >= Date.today())):
        e = next((e for e in es if e.id == x.entry_id), None)
        if not e:
            continue
        ctx = context(s, p, es, x.date, exclude_sub=x.id)
        c = next((c for c in sub.candidates(p, es, e, ctx, x.workload_override) if c["faculty_id"] == x.substitute_faculty_id), None)
        if c and not c["eligible"]:
            out.append(dict(type="INVALID_SUBSTITUTE", severity="hard", entry_ids=[e.id], substitution_id=x.id,
                            message=f"{c['name']} can no longer cover {p.S[e.subject_id].name} for {validator.cls_name(p, e)} "
                                    f"on {x.date}: " + "; ".join(r["text"] for r in c["reasons"] if not r["ok"])))
    return out


def resolve(s, tid: int) -> dict:
    """Re-solve only the entries involved in conflicts; everything else stays fixed."""
    p, es = problem_and_entries(s, tid)
    bad = {i for c in validator.find_conflicts(p, es) if c["severity"] == "hard" for i in c.get("entry_ids", [])}
    if not bad:
        return {"status": "NO_CONFLICTS", "changed": 0}
    keep = [e for e in es if e.id not in bad]
    p = build_problem(s, locked=keep)
    for d in p.demands:
        d.faculty_id = d.faculty_id or next((e.faculty_id for e in es if e.demand_id == d.id), None)
    result = solver.solve(p)
    if not result["entries"]:
        raise Rejected("Automatic resolution failed: " + "; ".join(result.get("issues", [])))
    # update the freed rows in place so entry ids (and substitutions pointing at them) survive
    free = defaultdict(list)
    for row in rows(s, tid):
        if row.id in bad:
            free[row.requirement_id].append(row)
    for e in result["entries"]:
        if e.id is None:
            row = free[e.demand_id].pop()
            row.faculty_id, row.room_id, row.day_id, row.slot_id = e.faculty_id, e.room_id, e.day_id, e.slot_id
            row.explanation = e.explanation + ["⚙ Moved by automatic conflict resolution"]
    audit(s, "CONFLICTS_RESOLVED", new={"timetable_id": tid, "rescheduled_entries": len(bad)})
    s.commit()
    return {"status": result["status"], "changed": len(bad)}


# ---------------- absences & substitutions ----------------
def day_of(p: M.Problem, d: Date) -> Optional[int]:
    name = d.strftime("%A")
    return next((x.id for x in p.days if x.name == name), None)


def context(s, p: M.Problem, es: list[M.Entry], d: Date, exclude_sub: int | None = None,
            extra_absence: dict | None = None) -> sub.DateContext:
    ctx = sub.DateContext(day_id=day_of(p, d), date=d.isoformat())
    for a in s.scalars(select(db.FacultyAbsence).where(db.FacultyAbsence.date == d)):
        if a.slot_id is None:
            ctx.absent[a.faculty_id] = None
        elif ctx.absent.get(a.faculty_id, set()) is not None:
            ctx.absent.setdefault(a.faculty_id, set()).add(a.slot_id)
    for fid, slots in (extra_absence or {}).items():
        ctx.absent[fid] = None if slots is None else set(slots) | (ctx.absent.get(fid) or set())
    by_id = {e.id: e for e in es}
    monday = d - timedelta(days=d.weekday())
    week = s.scalars(select(db.Substitution).where(db.Substitution.date >= monday,
                                                   db.Substitution.date < monday + timedelta(days=7))).all()
    for x in week:
        e = by_id.get(x.entry_id)
        if not e or x.id == exclude_sub:
            continue
        if x.status == "SUBSTITUTED":
            ctx.week_extra[x.substitute_faculty_id] = ctx.week_extra.get(x.substitute_faculty_id, 0) + e.duration
        if x.date == d:
            ctx.removed.add(e.id)
            if x.status == "SUBSTITUTED":
                ctx.extra.append(sub.as_substitute(e, x.substitute_faculty_id))
    for x in s.scalars(select(db.Substitution).where(db.Substitution.status == "RESCHEDULED", db.Substitution.new_date == d)):
        e = by_id.get(x.entry_id)
        if e:
            ctx.extra.append(M.Entry(**{**asdict(e), "id": None, "day_id": ctx.day_id, "slot_id": x.new_slot_id,
                                        "room_id": x.new_room_id}))
    return ctx


def _sub_row(s, entry_id: int, d: Date):
    return s.scalar(select(db.Substitution).where(db.Substitution.entry_id == entry_id, db.Substitution.date == d))


def analyse_absence(s, faculty_id: int, d: Date, slot_ids: list[int] | None = None, simulate: bool = False) -> dict:
    """Affected lectures + ranked candidates.  simulate=True treats the absence as
    hypothetical and plans greedy auto-substitution without touching the DB."""
    tt = active_timetable(s)
    p, es = problem_and_entries(s, tt.id)
    if day_of(p, d) is None:
        return {"date": d.isoformat(), "working_day": False, "affected": []}
    extra = {faculty_id: slot_ids} if simulate else None
    ctx = context(s, p, es, d, extra_absence=extra)
    if faculty_id not in ctx.absent:          # analysing without a recorded absence = assume full day
        ctx.absent[faculty_id] = set(slot_ids) if slot_ids else None
    hit = sub.affected(p, es, faculty_id, ctx)
    out = []
    for e in hit:
        existing = None if simulate else _sub_row(s, e.id, d)
        cands = sub.candidates(p, es, e, ctx)
        item = {"entry_id": e.id, **describe(p, e), "start": p.slots[p.pos[e.slot_id]].start,
                "status": existing.status if existing else "PENDING",
                "substitute": p.F[existing.substitute_faculty_id].name if existing and existing.substitute_faculty_id else None,
                "candidates": [c for c in cands if c["qualified"]][:8],
                "unqualified_free": sum(1 for c in cands if not c["qualified"] and
                                        all(r["ok"] for r in c["reasons"][1:3]))}
        if not simulate:
            item["reschedule_options"] = sub.reschedule_options(p, es, e, contexts_after(s, p, es, d + timedelta(days=1)))
        out.append(item)
    res = {"date": d.isoformat(), "working_day": True, "faculty_id": faculty_id, "faculty": p.F[faculty_id].name, "affected": out}
    if simulate:
        plan = sub.auto_plan(p, es, hit, ctx)
        res["summary"] = {"affected": len(hit), "auto_substitutable": sum(1 for x in plan if x["best"]),
                          "needs_reschedule": sum(1 for x in plan if not x["best"])}
        res["plan"] = [{"entry_id": x["entry"].id, **describe(p, x["entry"]),
                        "substitute": x["best"]["name"] if x["best"] else None,
                        "reasons": x["best"]["reasons"] if x["best"] else []} for x in plan]
    return res


def contexts_after(s, p, es, d: Date, days: int = 7):
    out = []
    for i in range(days):
        x = d + timedelta(days=i)
        if day_of(p, x) is not None:
            out.append(context(s, p, es, x))
    return out


def record_absence(s, faculty_id: int, d: Date, slot_ids: list[int] | None, reason: str | None) -> dict:
    for sid in (slot_ids or [None]):
        s.add(db.FacultyAbsence(faculty_id=faculty_id, date=d, slot_id=sid, reason=reason))
    f = s.get(db.Faculty, faculty_id)
    audit(s, "FACULTY_ABSENT", new={"faculty": f.name, "date": d.isoformat(), "slots": slot_ids or "full day"}, reason=reason)
    s.commit()
    return analyse_absence(s, faculty_id, d)


def assign_substitute(s, entry_id: int, d: Date, faculty_id: int, override_workload: bool = False) -> dict:
    tt = active_timetable(s)
    p, es = problem_and_entries(s, tt.id)
    e = next(e for e in es if e.id == entry_id)
    existing = _sub_row(s, entry_id, d)
    ctx = context(s, p, es, d, exclude_sub=existing.id if existing else None)
    ctx.removed.discard(entry_id)
    c = next((c for c in sub.candidates(p, es, e, ctx, override_workload) if c["faculty_id"] == faculty_id), None)
    if not c or not c["eligible"]:
        why = "; ".join(r["text"] for r in (c or {"reasons": []})["reasons"] if not r["ok"])
        raise Rejected(f"{p.F[faculty_id].name} cannot substitute: {why or 'not eligible'}")
    if existing:
        s.delete(existing)
    s.add(db.Substitution(entry_id=entry_id, date=d, original_faculty_id=e.faculty_id, substitute_faculty_id=faculty_id,
                          status="SUBSTITUTED", reasons=[r["text"] for r in c["reasons"] if r["ok"]],
                          workload_override=override_workload))
    audit(s, "SUBSTITUTE_ASSIGNED", {"faculty": p.F[e.faculty_id].name, **describe(p, e)},
          {"substitute": c["name"], "date": d.isoformat()}, reason="; ".join(r["text"] for r in c["reasons"] if r["ok"]))
    s.commit()
    return {"ok": True, "substitute": c["name"]}


def auto_assign_all(s, faculty_id: int, d: Date) -> dict:
    res = analyse_absence(s, faculty_id, d)
    done, failed = [], []
    for item in res["affected"]:
        if item["status"] != "PENDING":
            continue
        best = next((c for c in analyse_one(s, item["entry_id"], d) if c["eligible"]), None)
        if best:
            assign_substitute(s, item["entry_id"], d, best["faculty_id"])
            done.append({"entry_id": item["entry_id"], "substitute": best["name"]})
        else:
            failed.append(item["entry_id"])
    return {"assigned": done, "unresolved": failed}


def analyse_one(s, entry_id: int, d: Date) -> list[dict]:
    tt = active_timetable(s)
    p, es = problem_and_entries(s, tt.id)
    e = next(e for e in es if e.id == entry_id)
    return sub.candidates(p, es, e, context(s, p, es, d))


def cancel_lecture(s, entry_id: int, d: Date, reason: str | None) -> dict:
    tt = active_timetable(s)
    p, es = problem_and_entries(s, tt.id)
    e = next(e for e in es if e.id == entry_id)
    if (x := _sub_row(s, entry_id, d)):
        s.delete(x)
    s.add(db.Substitution(entry_id=entry_id, date=d, original_faculty_id=e.faculty_id, status="CANCELLED", reason=reason))
    audit(s, "LECTURE_CANCELLED", describe(p, e), {"date": d.isoformat()}, reason)
    s.commit()
    return {"ok": True}


def reschedule(s, entry_id: int, d: Date, new_date: Date, slot_id: int, room_id: int) -> dict:
    tt = active_timetable(s)
    p, es = problem_and_entries(s, tt.id)
    e = next(e for e in es if e.id == entry_id)
    ctx = context(s, p, es, new_date)
    ok = any(o["slot_id"] == slot_id and o["room_id"] == room_id for o in sub.reschedule_options(p, es, e, [ctx], limit=999))
    if not ok:
        raise Rejected("That slot is not free for the teacher, the class and the room.")
    if (x := _sub_row(s, entry_id, d)):
        s.delete(x)
    s.add(db.Substitution(entry_id=entry_id, date=d, original_faculty_id=e.faculty_id, status="RESCHEDULED",
                          new_date=new_date, new_slot_id=slot_id, new_room_id=room_id))
    audit(s, "LECTURE_RESCHEDULED", describe(p, e),
          {"date": new_date.isoformat(), "when": validator.when(p, ctx.day_id, slot_id, e.duration), "room": p.R[room_id].code})
    s.commit()
    return {"ok": True}


def pending_substitutions(s, start: Date, days: int = 7) -> list[dict]:
    out = []
    seen = set()
    for a in s.scalars(select(db.FacultyAbsence).where(db.FacultyAbsence.date >= start,
                                                       db.FacultyAbsence.date < start + timedelta(days=days))):
        if (a.faculty_id, a.date) in seen:
            continue
        seen.add((a.faculty_id, a.date))
        res = analyse_absence(s, a.faculty_id, a.date)
        for item in res["affected"]:
            out.append({**item, "date": a.date.isoformat(), "absent_faculty_id": a.faculty_id,
                        "absent_faculty": res["faculty"], "candidates": item["candidates"][:3]})
    return out


# ---------------- analytics ----------------
def workload(s, tid: int) -> dict:
    p, es = problem_and_entries(s, tid)
    day, week = validator.faculty_loads(p, es)
    fac_dept = {f.id: f.department_id for f in s.scalars(select(db.Faculty))}
    depts = {d.id: d.code for d in s.scalars(select(db.Department))}
    rows_ = []
    for f in p.faculty:
        w = week.get(f.id, 0)
        status = "OVERLOADED" if w > f.max_per_week else "UNDERLOADED" if w < f.min_per_week else "OK"
        rows_.append({"faculty_id": f.id, "name": f.name, "department": depts[fac_dept[f.id]], "weekly": w,
                      "max_per_week": f.max_per_week, "min_per_week": f.min_per_week, "max_per_day": f.max_per_day,
                      "utilization": round(100 * w / f.max_per_week, 1) if f.max_per_week else 0,
                      "daily": {d.name: day.get((f.id, d.id), 0) for d in p.days}, "status": status})
    dept = defaultdict(int)
    for r in rows_:
        dept[r["department"]] += r["weekly"]
    teaching = sum(not x.is_break for x in p.slots) * len(p.days)
    room_use = defaultdict(int)
    for e in es:
        room_use[e.room_id] += e.duration
    rooms = [{"room_id": r.id, "code": r.code, "kind": r.kind, "used": room_use[r.id],
              "utilization": round(100 * room_use[r.id] / teaching, 1)} for r in p.rooms]
    credits = []
    for c in validator.credit_status(p, es):
        credits.append({**c, "class": p.C[c["class_id"]].name, "subject": p.S[c["subject_id"]].name,
                        "batch": next((b.name for b in p.C[c["class_id"]].batches if b.id == c["batch_id"]), None)})
    return {"faculty": rows_, "departments": [{"department": k, "periods": v} for k, v in dept.items()],
            "rooms": rooms, "credits": credits, "metrics": validator.metrics(p, es)}
