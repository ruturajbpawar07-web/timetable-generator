"""FastAPI app.  Run:  uvicorn backend.main:app --reload  (from the project root)."""
from contextlib import asynccontextmanager
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, delete

from . import db, services as svc, importer, assistant, export
from scheduler import validator


@asynccontextmanager
async def lifespan(app):
    db.init()
    with db.Session() as s:
        if not s.scalar(select(db.College)):
            importer.load(Path(__file__).parent.parent / "data" / "dummy")
        if not s.scalar(select(db.Timetable)):
            r = svc.generate(s)
            if r.get("timetable_id"):
                svc.accept(s, r["timetable_id"])
    yield


app = FastAPI(title="Timetable Generator API", lifespan=lifespan)


def session():
    with db.Session() as s:
        yield s


@app.exception_handler(svc.Rejected)
def rejected(_: Request, e: svc.Rejected):
    return JSONResponse(status_code=409, content={"detail": str(e), "conflicts": e.conflicts})


def tid_or_active(s, tid: Optional[int]) -> int:
    if tid:
        return tid
    tt = svc.active_timetable(s)
    if not tt:
        raise HTTPException(404, "No timetable yet — generate one first")
    return tt.id


def working_date(s, d: Optional[Date]) -> Date:
    """Requested date, or today; weekends roll forward to the next working day."""
    d = d or Date.today()
    names = {w.name for w in s.scalars(select(db.WorkingDay))}
    for _ in range(7):
        if d.strftime("%A") in names:
            return d
        d += timedelta(days=1)
    return d


# ---------------- reference data ----------------
@app.get("/meta")
def meta(s=Depends(session)):
    cfg = svc.config(s)
    return {
        "college": cfg.get("college_name"), "academic_year": cfg.get("academic_year"),
        "days": [{"id": d.id, "name": d.name} for d in s.scalars(select(db.WorkingDay).order_by(db.WorkingDay.order))],
        "slots": [{"id": t.id, "index": t.index, "start": t.start, "end": t.end, "is_break": t.is_break, "label": t.label}
                  for t in s.scalars(select(db.TimeSlot).order_by(db.TimeSlot.index))],
        "departments": [{"id": d.id, "code": d.code, "name": d.name} for d in s.scalars(select(db.Department))],
        "programs": [{"id": p.id, "code": p.code, "name": p.name, "department_id": p.department_id}
                     for p in s.scalars(select(db.Program))],
        "semesters": sorted({x.number for x in s.scalars(select(db.Semester))}),
        "classes": classes(s),
        "faculty": [{"id": f.id, "code": f.code, "name": f.name, "department_id": f.department_id}
                    for f in s.scalars(select(db.Faculty))],
        "subjects": [{"id": x.id, "code": x.code, "name": x.name} for x in s.scalars(select(db.Subject))],
        "rooms": rooms(s),
        "today": working_date(s, None).isoformat(),
    }


@app.get("/classes")
def classes(s=Depends(session)):
    return [{"id": d.id, "code": d.code, "name": d.name, "year_level": d.year_level, "strength": d.strength,
             "semester": d.semester.number, "department_id": d.program.department_id, "program_id": d.program_id,
             "home_room_id": d.home_room_id, "batches": [{"id": b.id, "name": b.name, "strength": b.strength} for b in d.batches]}
            for d in s.scalars(select(db.Division).order_by(db.Division.code))]


@app.get("/rooms")
def rooms(s=Depends(session)):
    return [{"id": r.id, "code": r.code, "name": r.name, "kind": r.kind, "capacity": r.capacity, "lab_type": r.lab_type,
             "department_id": r.department_id} for r in s.scalars(select(db.Room).order_by(db.Room.kind, db.Room.code))]


@app.get("/subjects")
def subjects(s=Depends(session)):
    depts = {d.id: d.code for d in s.scalars(select(db.Department))}
    qualified = {}
    for f in s.scalars(select(db.Faculty)):
        for x in f.subjects:
            qualified.setdefault(x.id, []).append(f.name)
    return [{"id": x.id, "code": x.code, "name": x.name, "department": depts[x.department_id], "semester": x.semester_no,
             "credits": x.credits, "lecture_sessions_per_week": x.lecture_sessions_per_week,
             "tutorial_sessions_per_week": x.tutorial_sessions_per_week,
             "practical_sessions_per_week": x.practical_sessions_per_week,
             "practical_duration_periods": x.practical_duration_periods, "lab_type": x.lab_type, "is_core": x.is_core,
             "morning_preferred": x.morning_preferred, "qualified_faculty": qualified.get(x.id, [])}
            for x in s.scalars(select(db.Subject).order_by(db.Subject.code))]


@app.get("/faculty")
def faculty(s=Depends(session)):
    tid = tid_or_active(s, None)
    load = {r["faculty_id"]: r for r in svc.workload(s, tid)["faculty"]}
    depts = {d.id: d.code for d in s.scalars(select(db.Department))}
    return [{"id": f.id, "code": f.code, "name": f.name, "department": depts[f.department_id], "designation": f.designation,
             "subjects": [x.code for x in f.subjects], "max_per_day": f.max_per_day, "max_per_week": f.max_per_week,
             "min_per_week": f.min_per_week, "weekly": load.get(f.id, {}).get("weekly", 0),
             "status": load.get(f.id, {}).get("status")} for f in s.scalars(select(db.Faculty).order_by(db.Faculty.code))]


@app.get("/faculty/{fid}")
def faculty_profile(fid: int, date: Optional[Date] = None, s=Depends(session)):
    f = s.get(db.Faculty, fid)
    tid = tid_or_active(s, None)
    d = working_date(s, date)
    tt = timetable(tid, s)
    mine = [e for e in tt["entries"] if e["faculty_id"] == fid]
    day_id = next((x["id"] for x in tt["days"] if x["name"] == d.strftime("%A")), None)
    today = sorted((e for e in mine if e["day_id"] == day_id), key=lambda e: e["slot_index"])
    busy = {i for e in today for i in range(e["slot_index"], e["slot_index"] + e["duration"])}
    w = next(r for r in svc.workload(s, tid)["faculty"] if r["faculty_id"] == fid)
    subs = s.scalars(select(db.Substitution).where(db.Substitution.substitute_faculty_id == fid)).all()
    avail = [{"day_id": a.day_id, "slot_id": a.slot_id, "kind": a.kind}
             for a in s.scalars(select(db.FacultyAvailability).where(db.FacultyAvailability.faculty_id == fid))]
    absences = [{"date": a.date.isoformat(), "slot_id": a.slot_id, "reason": a.reason}
                for a in s.scalars(select(db.FacultyAbsence).where(db.FacultyAbsence.faculty_id == fid))]
    return {
        "id": f.id, "code": f.code, "name": f.name, "designation": f.designation,
        "department": s.get(db.Department, f.department_id).name,
        "subjects": [{"id": x.id, "code": x.code, "name": x.name} for x in f.subjects],
        "classes": sorted({e["class"] for e in mine}), "workload": w, "date": d.isoformat(),
        "today": today, "free_periods": [x for x in tt["slots"] if not x["is_break"] and x["index"] not in busy],
        "availability": avail, "absences": absences, "entries": mine,
        "substitutions": [{"date": x.date.isoformat(), "entry_id": x.entry_id, "status": x.status} for x in subs],
    }


class AvailIn(BaseModel):
    day_id: int
    slot_id: int
    kind: Optional[str] = None       # UNAVAILABLE | PREFERRED | None (clear)


@app.post("/faculty/{fid}/availability")
def set_availability(fid: int, body: AvailIn, s=Depends(session)):
    s.execute(delete(db.FacultyAvailability).where(db.FacultyAvailability.faculty_id == fid,
                                                   db.FacultyAvailability.day_id == body.day_id,
                                                   db.FacultyAvailability.slot_id == body.slot_id))
    if body.kind:
        s.add(db.FacultyAvailability(faculty_id=fid, day_id=body.day_id, slot_id=body.slot_id, kind=body.kind))
    svc.audit(s, "AVAILABILITY_CHANGED", new={"faculty_id": fid, **body.model_dump()})
    s.commit()
    return {"ok": True}


# ---------------- timetable ----------------
@app.get("/timetables")
def timetables(s=Depends(session)):
    out = []
    for t in s.scalars(select(db.Timetable).order_by(db.Timetable.id.desc())):
        run = s.get(db.GenerationRun, t.generation_run_id) if t.generation_run_id else None
        out.append({"id": t.id, "name": t.name, "status": t.status, "created_at": t.created_at.isoformat(timespec="minutes"),
                    "score": (run.metrics or {}).get("score") if run else None, "solver_status": run.status if run else None})
    return out


@app.get("/timetable")
def timetable(timetable_id: Optional[int] = None, s=Depends(session)):
    tid = tid_or_active(s, timetable_id)
    p, es = svc.problem_and_entries(s, tid)
    tt = s.get(db.Timetable, tid)
    run = s.get(db.GenerationRun, tt.generation_run_id) if tt.generation_run_id else None
    out = []
    for e in es:
        c = p.C[e.class_id]
        out.append({"id": e.id, "day_id": e.day_id, "slot_id": e.slot_id, "slot_index": p.pos[e.slot_id],
                    "duration": e.duration, "component": e.component, "locked": e.locked,
                    "start": p.slots[p.pos[e.slot_id]].start, "end": p.slots[p.pos[e.slot_id] + e.duration - 1].end,
                    "class_id": e.class_id, "class": c.name, "year_level": c.year_level, "department_id": c.department_id,
                    "batch_id": e.batch_id, "batch": next((b.name for b in c.batches if b.id == e.batch_id), None),
                    "subject_id": e.subject_id, "subject": p.S[e.subject_id].name, "subject_code": p.S[e.subject_id].code,
                    "faculty_id": e.faculty_id, "faculty": p.F[e.faculty_id].name,
                    "room_id": e.room_id, "room": p.R[e.room_id].code, "room_kind": p.R[e.room_id].kind,
                    "explanation": e.explanation or validator.explain(p, es, e)})
    return {"id": tid, "name": tt.name, "status": tt.status, "metrics": run.metrics if run else validator.metrics(p, es),
            "days": [{"id": d.id, "name": d.name} for d in p.days],
            "slots": [{"id": x.id, "index": i, "start": x.start, "end": x.end, "is_break": x.is_break}
                      for i, x in enumerate(p.slots)],
            "entries": out}


class GenerateIn(BaseModel):
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    year_level: Optional[str] = None
    semester: Optional[int] = None
    base_timetable_id: Optional[int] = None
    seed: int = 0


@app.post("/timetable/generate")
def generate(body: GenerateIn, s=Depends(session)):
    scope = body.model_dump(exclude={"base_timetable_id", "seed"}, exclude_none=True)
    base = body.base_timetable_id
    if base is None:      # keep locked entries (and out-of-scope divisions) of the active timetable
        tt = svc.active_timetable(s)
        base = tt.id if tt else None
    return svc.generate(s, scope, base, body.seed)


@app.post("/timetable/{tid}/accept")
def accept(tid: int, s=Depends(session)):
    svc.accept(s, tid)
    return {"ok": True}


class MoveIn(BaseModel):
    timetable_id: int
    entry_id: int
    day_id: int
    slot_id: int
    room_id: Optional[int] = None


@app.post("/timetable/validate")
def validate(body: MoveIn, s=Depends(session)):
    try:
        return svc.move(s, body.timetable_id, body.entry_id, body.day_id, body.slot_id, body.room_id, dry_run=True)
    except svc.Rejected as e:
        return {"ok": False, "message": str(e), "conflicts": e.conflicts}


@app.post("/timetable/move")
def move(body: MoveIn, s=Depends(session)):
    return svc.move(s, body.timetable_id, body.entry_id, body.day_id, body.slot_id, body.room_id)


class LockIn(BaseModel):
    timetable_id: int
    locked: bool = True
    entry_ids: Optional[list[int]] = None
    day_id: Optional[int] = None
    division_id: Optional[int] = None
    faculty_id: Optional[int] = None
    component: Optional[str] = None


@app.post("/timetable/lock")
def lock(body: LockIn, s=Depends(session)):
    return {"changed": svc.set_lock(s, **body.model_dump())}


@app.get("/conflicts")
def conflicts(timetable_id: Optional[int] = None, s=Depends(session)):
    return svc.conflicts(s, tid_or_active(s, timetable_id))


class TidIn(BaseModel):
    timetable_id: Optional[int] = None


@app.post("/conflicts/resolve")
def resolve(body: TidIn, s=Depends(session)):
    return svc.resolve(s, tid_or_active(s, body.timetable_id))


# ---------------- absences & substitutions ----------------
class AbsenceIn(BaseModel):
    faculty_id: int
    date: Date
    slot_ids: Optional[list[int]] = None      # None = full day
    reason: Optional[str] = None


@app.post("/faculty/absence")
def absence(body: AbsenceIn, s=Depends(session)):
    return svc.record_absence(s, body.faculty_id, body.date, body.slot_ids, body.reason)


@app.delete("/faculty/absence")
def remove_absence(faculty_id: int, date: Date, s=Depends(session)):
    s.execute(delete(db.FacultyAbsence).where(db.FacultyAbsence.faculty_id == faculty_id, db.FacultyAbsence.date == date))
    svc.audit(s, "ABSENCE_REMOVED", new={"faculty_id": faculty_id, "date": date.isoformat()})
    s.commit()
    return {"ok": True}


@app.get("/absences")
def absences(start: Optional[Date] = None, s=Depends(session)):
    start = start or Date.today() - timedelta(days=7)
    out = {}
    for a in s.scalars(select(db.FacultyAbsence).where(db.FacultyAbsence.date >= start).order_by(db.FacultyAbsence.date)):
        k = (a.faculty_id, a.date)
        item = out.setdefault(k, {"faculty_id": a.faculty_id, "faculty": s.get(db.Faculty, a.faculty_id).name,
                                  "date": a.date.isoformat(), "slot_ids": [], "full_day": False, "reason": a.reason})
        if a.slot_id is None:
            item["full_day"] = True
        else:
            item["slot_ids"].append(a.slot_id)
    return list(out.values())


@app.get("/absence/analysis")
def absence_analysis(faculty_id: int, date: Date, s=Depends(session)):
    return svc.analyse_absence(s, faculty_id, date)


@app.post("/simulate/absence")
def simulate(body: AbsenceIn, s=Depends(session)):
    return svc.analyse_absence(s, body.faculty_id, body.date, body.slot_ids, simulate=True)


@app.get("/substitutes")
def substitutes(entry_id: int, date: Date, s=Depends(session)):
    return svc.analyse_one(s, entry_id, date)


class AssignIn(BaseModel):
    entry_id: int
    date: Date
    faculty_id: int
    override_workload: bool = False


@app.post("/substitution/assign")
def assign(body: AssignIn, s=Depends(session)):
    return svc.assign_substitute(s, body.entry_id, body.date, body.faculty_id, body.override_workload)


class AutoIn(BaseModel):
    faculty_id: int
    date: Date


@app.post("/substitution/auto")
def auto(body: AutoIn, s=Depends(session)):
    return svc.auto_assign_all(s, body.faculty_id, body.date)


class CancelIn(BaseModel):
    entry_id: int
    date: Date
    reason: Optional[str] = None


@app.post("/substitution/cancel")
def cancel(body: CancelIn, s=Depends(session)):
    return svc.cancel_lecture(s, body.entry_id, body.date, body.reason)


class RescheduleIn(BaseModel):
    entry_id: int
    date: Date
    new_date: Date
    slot_id: int
    room_id: int


@app.post("/substitution/reschedule")
def reschedule(body: RescheduleIn, s=Depends(session)):
    return svc.reschedule(s, body.entry_id, body.date, body.new_date, body.slot_id, body.room_id)


@app.get("/substitutions")
def substitutions(s=Depends(session)):
    tid = tid_or_active(s, None)
    p, es = svc.problem_and_entries(s, tid)
    by_id = {e.id: e for e in es}
    out = []
    for x in s.scalars(select(db.Substitution).order_by(db.Substitution.date.desc(), db.Substitution.id.desc())):
        e = by_id.get(x.entry_id)
        if not e:
            continue
        out.append({"id": x.id, "date": x.date.isoformat(), "status": x.status, **svc.describe(p, e),
                    "original": p.F[x.original_faculty_id].name,
                    "substitute": p.F[x.substitute_faculty_id].name if x.substitute_faculty_id else None,
                    "new_when": f"{x.new_date} {validator.when(p, svc.day_of(p, x.new_date), x.new_slot_id, e.duration)} "
                                f"{p.R[x.new_room_id].code}" if x.status == "RESCHEDULED" else None,
                    "reasons": x.reasons or [], "reason": x.reason})
    return out


@app.get("/substitutions/pending")
def pending(s=Depends(session)):
    return svc.pending_substitutions(s, Date.today())


# ---------------- analytics / dashboard ----------------
@app.get("/analytics/workload")
def analytics(timetable_id: Optional[int] = None, s=Depends(session)):
    return svc.workload(s, tid_or_active(s, timetable_id))


@app.get("/dashboard")
def dashboard(date: Optional[Date] = None, s=Depends(session)):
    d = working_date(s, date)
    tid = tid_or_active(s, None)
    tt = timetable(tid, s)
    day_id = next((x["id"] for x in tt["days"] if x["name"] == d.strftime("%A")), None)
    today = sorted((e for e in tt["entries"] if e["day_id"] == day_id), key=lambda e: (e["slot_index"], e["class"]))
    subs = {(x.entry_id): x for x in s.scalars(select(db.Substitution).where(db.Substitution.date == d))}
    names = {f.id: f.name for f in s.scalars(select(db.Faculty))}
    for e in today:
        x = subs.get(e["id"])
        e["today_status"] = x.status if x else "SCHEDULED"
        e["substitute"] = names.get(x.substitute_faculty_id) if x and x.substitute_faculty_id else None
    absent = {a.faculty_id for a in s.scalars(select(db.FacultyAbsence).where(db.FacultyAbsence.date == d))}
    pend = svc.pending_substitutions(s, d, days=1)
    pend = [x for x in pend if x["status"] == "PENDING"]
    w = svc.workload(s, tid)
    conf = svc.conflicts(s, tid)
    warnings = [f"{r['name']} is {r['status'].lower()} ({r['weekly']} periods; limits {r['min_per_week']}–{r['max_per_week']})"
                for r in w["faculty"] if r["status"] != "OK"]
    warnings += [f"{c['class']} {c['subject']}: {c['scheduled']}/{c['required']} sessions" for c in w["credits"] if c["remaining"]]
    load_today = {}
    for e in today:
        load_today[e["faculty_id"]] = load_today.get(e["faculty_id"], 0) + e["duration"]
    return {
        "date": d.isoformat(), "day": d.strftime("%A"), "timetable": {"id": tid, "name": tt["name"]},
        "cards": {"active_faculty": len(names), "classes_today": len(today), "faculty_absent": len(absent),
                  "substitutions_required": len(pend), "open_conflicts": len(conf),
                  "rooms_in_use": len({e["room_id"] for e in today}), "rooms_total": len(rooms(s))},
        "schedule": today, "pending": pend[:10],
        "availability": [{"faculty_id": fid, "name": n, "absent": fid in absent, "lectures_today": load_today.get(fid, 0)}
                         for fid, n in names.items()],
        "recent": audit(limit=8, s=s), "warnings": warnings, "metrics": w["metrics"],
    }


@app.get("/audit")
def audit(limit: int = 100, s=Depends(session)):
    return [{"id": a.id, "ts": a.ts.isoformat(timespec="seconds"), "user": a.user, "action": a.action,
             "previous": a.previous, "new": a.new, "reason": a.reason}
            for a in s.scalars(select(db.AuditLog).order_by(db.AuditLog.id.desc()).limit(limit))]


@app.get("/runs")
def runs(s=Depends(session)):
    return [{"id": r.id, "started_at": r.started_at.isoformat(timespec="seconds"), "status": r.status, "seed": r.seed,
             "scope": r.scope, "generation_time": r.generation_time, "score": (r.metrics or {}).get("score"), "issues": r.issues}
            for r in s.scalars(select(db.GenerationRun).order_by(db.GenerationRun.id.desc()))]


# ---------------- settings ----------------
@app.get("/settings")
def settings(s=Depends(session)):
    return [{"key": c.key, "value": c.value, "description": c.description}
            for c in s.scalars(select(db.ConstraintConfiguration).order_by(db.ConstraintConfiguration.key))]


@app.put("/settings")
def save_settings(body: dict[str, str], s=Depends(session)):
    for k, v in body.items():
        c = s.get(db.ConstraintConfiguration, k)
        if c and c.value != str(v):
            svc.audit(s, "SETTING_CHANGED", {k: c.value}, {k: str(v)})
            c.value = str(v)
    s.commit()
    return {"ok": True}


# ---------------- assistant / export ----------------
class AskIn(BaseModel):
    query: str


@app.post("/assistant")
def ask(body: AskIn, s=Depends(session)):
    return assistant.answer(s, body.query)


@app.get("/export")
def do_export(kind: str = "master", format: str = "xlsx", id: Optional[int] = None,
              timetable_id: Optional[int] = None, s=Depends(session)):
    data, mime, name = export.build(s, tid_or_active(s, timetable_id), kind, format, id)
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})
