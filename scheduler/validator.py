"""Constraint/conflict engine: the single source of truth for "is this timetable valid?".

Used after every solve, before every manual move, for the conflicts page,
and to explain why an entry sits where it does.  Pure functions over
Problem + list[Entry].
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import mean, pstdev
from typing import Optional

from .model import Problem, Entry

COMPONENT = {"L": "lecture", "T": "tutorial", "P": "practical"}
SCORE_FORMULA = ("score = 0 if any hard violation or unscheduled session, else "
                 "100 × mean(subject_spread, student_compactness, faculty_compactness, "
                 "preference_satisfaction, daily_balance)")


# ---------- naming helpers ----------
def period_no(p: Problem) -> dict[int, int]:
    """slot id -> human period number (breaks not counted)."""
    out, n = {}, 0
    for s in p.slots:
        if not s.is_break:
            n += 1
            out[s.id] = n
    return out


def when(p: Problem, day_id: int, slot_id: int, duration: int = 1) -> str:
    pos = p.pos[slot_id]
    end = p.slots[min(pos + duration - 1, len(p.slots) - 1)].end
    return f"{p.DAY[day_id].name} P{period_no(p).get(slot_id, '?')} ({p.slots[pos].start}–{end})"


def cls_name(p: Problem, e) -> str:
    c = p.C[e.class_id]
    b = next((b.name for b in c.batches if b.id == e.batch_id), None)
    return f"{c.name} ({b})" if b else c.name


def span(p: Problem, e: Entry) -> Optional[list[int]]:
    return p.block(e.slot_id, e.duration)


def _ref(e: Entry, i: int):
    return e.id if e.id is not None else i


# ---------- input validation ----------
def precheck(p: Problem) -> list[str]:
    """Cheap feasibility checks run before the solver, with readable messages."""
    issues = []
    teaching = sum(not s.is_break for s in p.slots) * len(p.days)
    unit_load, fac_load = defaultdict(int), defaultdict(int)
    for d in p.demands:
        for u in p.units(d.class_id, d.batch_id):
            unit_load[u] += d.sessions * d.duration
        if d.faculty_id is not None:
            fac_load[d.faculty_id] += d.sessions * d.duration
            if d.subject_id not in p.F[d.faculty_id].subject_ids:
                issues.append(f"{p.F[d.faculty_id].name} is assigned {p.S[d.subject_id].name} but is not authorized for it")
        if not p.eligible_rooms(d):
            issues.append(f"No room/lab fits {p.S[d.subject_id].name} ({p.C[d.class_id].name}, "
                          f"{p.strength(d.class_id, d.batch_id)} students)")
        if not any(p.block(s.id, d.duration) for s in p.slots):
            issues.append(f"No {d.duration}-period block exists for {p.S[d.subject_id].name}")
    for (cid, bid), n in unit_load.items():
        if n > teaching:
            issues.append(f"{p.C[cid].name} needs {n} periods/week but only {teaching} exist")
    for fid, n in fac_load.items():
        if n > p.F[fid].max_per_week:
            issues.append(f"{p.F[fid].name} is assigned {n} periods/week, above the limit of {p.F[fid].max_per_week}")
    return issues


# ---------- conflict detection ----------
def _pair(p: Problem, e: Entry, o: Entry, move_view: bool) -> list[tuple[str, str]]:
    """Hard clashes between two entries."""
    if e.day_id != o.day_id:
        return []
    se, so = span(p, e) or [], span(p, o) or []
    shared = sorted(set(se) & set(so))
    if not shared:
        return []
    t = when(p, e.day_id, p.slots[shared[0]].id)
    out = []
    S, F, R = p.S, p.F, p.R
    if e.faculty_id == o.faculty_id:
        out.append(("FACULTY_CONFLICT",
                    f"{F[e.faculty_id].name} already teaches {cls_name(p, o)} ({S[o.subject_id].name}) during {t}"
                    if move_view else
                    f"{F[e.faculty_id].name} is assigned to {cls_name(p, e)} ({S[e.subject_id].name}) "
                    f"AND {cls_name(p, o)} ({S[o.subject_id].name}) on {t}"))
    if set(p.units(e.class_id, e.batch_id)) & set(p.units(o.class_id, o.batch_id)):
        out.append(("CLASS_CONFLICT",
                    f"{cls_name(p, o)} already has {S[o.subject_id].name} during {t}" if move_view else
                    f"{cls_name(p, e)} has {S[e.subject_id].name} and {S[o.subject_id].name} at the same time on {t}"))
    if e.room_id == o.room_id:
        kind = "LAB_CONFLICT" if R[e.room_id].kind == "LAB" else "ROOM_CONFLICT"
        out.append((kind, f"{R[e.room_id].code} is already used by {cls_name(p, o)} ({S[o.subject_id].name}) during {t}"
                    if move_view else
                    f"{R[e.room_id].code} hosts {cls_name(p, e)} and {cls_name(p, o)} on {t}"))
    return out


def _single(p: Problem, e: Entry) -> list[tuple[str, str]]:
    """Checks that concern one entry alone."""
    out = []
    f, s, r = p.F[e.faculty_id], p.S[e.subject_id], p.R[e.room_id]
    sp = span(p, e)
    d = p.D.get(e.demand_id)
    if sp is None:
        out.append(("PRACTICAL_BLOCK_CONFLICT" if e.duration > 1 else "BREAK_CONFLICT",
                    f"{s.name} ({e.duration} periods) cannot start at {when(p, e.day_id, e.slot_id)}: "
                    f"block runs into a break or past the end of the day"))
        sp = []
    if d and d.duration != e.duration:
        out.append(("PRACTICAL_BLOCK_CONFLICT", f"{s.name} needs a {d.duration}-period block, has {e.duration}"))
    blocked = {(dd, p.pos[ss]) for dd, ss in f.unavailable if ss in p.pos}
    if any((e.day_id, i) in blocked for i in sp):
        out.append(("AVAILABILITY_CONFLICT", f"{f.name} is unavailable on {when(p, e.day_id, e.slot_id, e.duration)}"))
    if e.subject_id not in f.subject_ids:
        out.append(("QUALIFICATION_CONFLICT", f"{f.name} is not authorized to teach {s.name}"))
    need = p.strength(e.class_id, e.batch_id)
    if r.capacity < need:
        out.append(("ROOM_CONFLICT", f"{r.code} holds {r.capacity}, {cls_name(p, e)} has {need} students"))
    if e.component == "P" and (r.kind != "LAB" or (s.lab_type and r.lab_type != s.lab_type)):
        out.append(("LAB_CONFLICT", f"{s.name} practical needs a {s.lab_type or 'lab'} lab, {r.code} is not one"))
    if e.component != "P" and r.kind == "LAB":
        out.append(("ROOM_CONFLICT", f"{s.name} lecture placed in lab {r.code}"))
    return out


def faculty_loads(p: Problem, entries: list[Entry]):
    day, week = defaultdict(int), defaultdict(int)
    for e in entries:
        day[e.faculty_id, e.day_id] += e.duration
        week[e.faculty_id] += e.duration
    return day, week


def _workload(p: Problem, entries: list[Entry], only: Optional[set] = None) -> list[dict]:
    day, week = faculty_loads(p, entries)
    out = []
    for (fid, did), n in day.items():
        if (only is None or (fid, did) in only) and n > p.F[fid].max_per_day:
            out.append(dict(type="WORKLOAD_CONFLICT", severity="hard", faculty_id=fid,
                            message=f"{p.F[fid].name} has {n} periods on {p.DAY[did].name} (max {p.F[fid].max_per_day})"))
    for fid, n in week.items():
        if (only is None or any(k[0] == fid for k in only)) and n > p.F[fid].max_per_week:
            out.append(dict(type="WORKLOAD_CONFLICT", severity="hard", faculty_id=fid,
                            message=f"{p.F[fid].name} has {n} periods this week (max {p.F[fid].max_per_week})"))
    return out


def credit_status(p: Problem, entries: list[Entry]) -> list[dict]:
    """Required vs scheduled sessions per demand (subject credit tracker)."""
    got = defaultdict(int)
    for e in entries:
        got[e.demand_id] += 1
    return [dict(demand_id=d.id, class_id=d.class_id, batch_id=d.batch_id, subject_id=d.subject_id,
                 component=d.component, required=d.sessions, scheduled=got[d.id],
                 remaining=max(d.sessions - got[d.id], 0)) for d in p.demands]


def find_conflicts(p: Problem, entries: list[Entry]) -> list[dict]:
    out = []
    for i, e in enumerate(entries):
        for kind, msg in _single(p, e):
            out.append(dict(type=kind, severity="hard", message=msg, entry_ids=[_ref(e, i)]))
        for j in range(i + 1, len(entries)):
            for kind, msg in _pair(p, e, entries[j], False):
                out.append(dict(type=kind, severity="hard", message=msg, entry_ids=[_ref(e, i), _ref(entries[j], j)]))
    out += [{**c, "entry_ids": [_ref(e, i) for i, e in enumerate(entries) if e.faculty_id == c["faculty_id"]]}
            for c in _workload(p, entries)]
    for c in credit_status(p, entries):
        if c["scheduled"] != c["required"]:
            short = c["scheduled"] < c["required"]
            out.append(dict(type="CREDIT_SHORTAGE" if short else "CREDIT_EXCESS", severity="hard" if short else "soft",
                            entry_ids=[], demand_id=c["demand_id"],
                            message=f"{p.C[c['class_id']].name} {p.S[c['subject_id']].name} {COMPONENT[c['component']]}: "
                                    f"{c['scheduled']}/{c['required']} sessions scheduled"))
    return out


def validate_move(p: Problem, entries: list[Entry], idx: int, day_id: int, slot_id: int,
                  room_id: Optional[int] = None, faculty_id: Optional[int] = None) -> tuple[Entry, list[dict]]:
    """Would moving entries[idx] create a hard conflict?  Returns (moved entry, conflicts)."""
    e = entries[idx]
    moved = replace(e, day_id=day_id, slot_id=slot_id, room_id=room_id or e.room_id,
                    faculty_id=faculty_id or e.faculty_id)
    others = entries[:idx] + entries[idx + 1:]
    out = [dict(type=k, severity="hard", message=m) for k, m in _single(p, moved)]
    for o in others:
        out += [dict(type=k, severity="hard", message=m, entry_ids=[o.id]) for k, m in _pair(p, moved, o, True)]
    out += _workload(p, others + [moved], only={(moved.faculty_id, day_id)})
    return moved, out


# ---------- explainability ----------
def explain(p: Problem, entries: list[Entry], e: Entry) -> list[str]:
    f, s, r = p.F[e.faculty_id], p.S[e.subject_id], p.R[e.room_id]
    kinds = {k for k, _ in _single(p, e)}
    for o in entries:
        if o is not e:
            kinds |= {k for k, _ in _pair(p, e, o, True)}
    t = when(p, e.day_id, e.slot_id, e.duration)
    ok = lambda good, yes, no: ("✓ " + yes) if good else ("✗ " + no)
    out = [
        ok("FACULTY_CONFLICT" not in kinds and "AVAILABILITY_CONFLICT" not in kinds,
           f"{f.name} available and free on {t}", f"{f.name} is not free on {t}"),
        ok("CLASS_CONFLICT" not in kinds, f"{cls_name(p, e)} has no other session at this time",
           f"{cls_name(p, e)} is double-booked"),
        ok(not kinds & {"ROOM_CONFLICT", "LAB_CONFLICT"},
           f"{r.code} free, capacity {r.capacity} ≥ {p.strength(e.class_id, e.batch_id)} students"
           + (" (home room)" if p.C[e.class_id].home_room_id == r.id else ""),
           f"{r.code} is not suitable or already in use"),
    ]
    d = p.D.get(e.demand_id)
    same = [o for o in entries if o.demand_id == e.demand_id]
    if d:
        out.append(f"✓ {s.name} requires {d.sessions} {COMPONENT[d.component]}(s)/week — {len(same)}/{d.sessions} scheduled")
    today = sum(o.day_id == e.day_id for o in same)
    out.append(f"✓ No other {s.name} {COMPONENT[e.component]} on {p.DAY[e.day_id].name}" if today == 1
               else f"⚠ {s.name} appears {today}× on {p.DAY[e.day_id].name} (needed to fit {len(same)} sessions)")
    day, week = faculty_loads(p, entries)
    out.append(ok(day[f.id, e.day_id] <= f.max_per_day and week[f.id] <= f.max_per_week,
                  f"{f.name} load {day[f.id, e.day_id]}/{f.max_per_day} today, {week[f.id]}/{f.max_per_week} this week",
                  f"{f.name} exceeds workload limit"))
    if (e.day_id, e.slot_id) in [tuple(x) for x in f.preferred]:
        out.append(f"★ Inside {f.name}'s preferred time")
    first_break = next((i for i, x in enumerate(p.slots) if x.is_break), len(p.slots))
    if s.morning_preferred and p.pos[e.slot_id] + e.duration <= first_break:
        out.append(f"★ {s.name} is morning-preferred and placed before the break")
    if e.locked:
        out.append("🔒 Locked by admin — kept fixed during regeneration")
    return out


# ---------- quality metrics ----------
def metrics(p: Problem, entries: list[Entry]) -> dict:
    breaks = {i for i, s in enumerate(p.slots) if s.is_break}
    teaching = len(p.slots) - len(breaks)
    fac_busy, unit_busy = defaultdict(set), defaultdict(set)
    room_periods = defaultdict(int)
    for e in entries:
        for i in span(p, e) or []:
            fac_busy[e.faculty_id, e.day_id].add(i)
            for u in p.units(e.class_id, e.batch_id):
                unit_busy[u, e.day_id].add(i)
            room_periods[p.R[e.room_id].kind] += 1

    def gaps(busy):
        g = t = 0
        for pos in busy.values():
            lo, hi = min(pos), max(pos)
            g += sum(1 for i in range(lo, hi + 1) if i not in pos and i not in breaks)
            t += len(pos)
        return g, t

    fg, ft = gaps(fac_busy)
    sg, st = gaps(unit_busy)
    conflicts = find_conflicts(p, entries)
    credits = credit_status(p, entries)
    unscheduled = sum(c["remaining"] for c in credits)
    hard = sum(c["severity"] == "hard" and c["type"] != "CREDIT_SHORTAGE" for c in conflicts)

    _, week = faculty_loads(p, entries)
    loads = [week.get(f.id, 0) for f in p.faculty]
    util = [week.get(f.id, 0) / f.max_per_week * 100 for f in p.faculty if f.max_per_week]

    # preference: faculty preferred slots + morning-preferred subjects
    first_break = min(breaks) if breaks else len(p.slots)
    pref_ok = pref_all = 0
    for e in entries:
        f, s = p.F[e.faculty_id], p.S[e.subject_id]
        if f.preferred:
            pref_all += 1
            pref_ok += (e.day_id, e.slot_id) in [tuple(x) for x in f.preferred]
        if s.morning_preferred:
            pref_all += 1
            pref_ok += p.pos[e.slot_id] + e.duration <= first_break
    per_dd = defaultdict(int)
    for e in entries:
        per_dd[e.demand_id, e.day_id] += 1
    spread = sum(v == 1 for v in per_dd.values()) / max(len(per_dd), 1)

    cvs = []
    for f in p.faculty:
        days = [len(fac_busy.get((f.id, d.id), ())) for d in p.days]
        if sum(days):
            cvs.append(pstdev(days) / mean(days))
    balance = 1 - min(1, mean(cvs)) if cvs else 1
    parts = dict(subject_spread=spread, student_compactness=1 - sg / max(st, 1),
                 faculty_compactness=1 - fg / max(ft, 1),
                 preference_satisfaction=pref_ok / pref_all if pref_all else 1, daily_balance=balance)
    score = 0 if hard or unscheduled else round(100 * mean(parts.values()), 1)
    n_class = sum(r.kind == "CLASSROOM" for r in p.rooms)
    n_lab = sum(r.kind == "LAB" for r in p.rooms)
    cap = teaching * len(p.days)
    return {
        "hard_constraint_violations": hard,
        "unscheduled_sessions": unscheduled,
        "faculty_workload_std": round(pstdev(loads), 2) if loads else 0,
        "faculty_utilization_std_pct": round(pstdev(util), 1) if util else 0,
        "student_gaps": sg, "faculty_gaps": fg,
        "room_utilization_pct": round(100 * room_periods["CLASSROOM"] / max(n_class * cap, 1), 1),
        "lab_utilization_pct": round(100 * room_periods["LAB"] / max(n_lab * cap, 1), 1),
        "preference_satisfaction_pct": round(100 * parts["preference_satisfaction"], 1),
        "subject_spread_pct": round(100 * spread, 1),
        "components": {k: round(v * 100, 1) for k, v in parts.items()},
        "score": score,
        "score_formula": SCORE_FORMULA,
    }
