"""CP-SAT timetable solver.

Two phases:

1. Faculty assignment (only for demands with no teacher): pick a qualified
   teacher per demand so that weekly utilisation (load / max_per_week) is as
   even as possible.  This is where "avoid unfair workload concentration"
   is decided.

2. Timetabling: one boolean x[d, day, start, room] per *feasible* placement of
   a demand.  Placements that already collide with locked entries, faculty
   unavailability or breaks are never created, so those hard constraints are
   enforced by construction.  The remaining hard constraints (no overlaps for
   faculty / student units / rooms, session counts, daily & weekly load) are
   linear constraints.  Soft constraints become penalty terms whose weights
   come from `problem.weights` (ConstraintConfiguration table).
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import replace

from ortools.sat.python import cp_model

from .model import Problem, Entry, Demand
from . import validator

STATUS = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
          cp_model.INFEASIBLE: "INFEASIBLE", cp_model.MODEL_INVALID: "MODEL_INVALID",
          cp_model.UNKNOWN: "UNKNOWN"}


def demand_key(class_id, batch_id, subject_id, component):
    return (class_id, batch_id, subject_id, component)


def assign_faculty(p: Problem) -> dict[int, int]:
    """Phase 1: returns {demand_id: faculty_id} for every demand (fixed + chosen)."""
    fixed = {d.id: d.faculty_id for d in p.demands if d.faculty_id is not None}
    open_ = [d for d in p.demands if d.faculty_id is None]
    if not open_:
        return fixed

    load = defaultdict(int)
    for d in p.demands:
        if d.faculty_id is not None:
            load[d.faculty_id] += d.sessions * d.duration

    m = cp_model.CpModel()
    pick = {}
    for d in open_:
        cands = [f for f in p.faculty if d.subject_id in f.subject_ids]
        if not cands:
            raise ValueError(f"No qualified faculty for {p.S[d.subject_id].name} ({p.C[d.class_id].name})")
        for f in cands:
            pick[d.id, f.id] = m.NewBoolVar("")
        m.AddExactlyOne(pick[d.id, f.id] for f in cands)

    max_util = m.NewIntVar(0, 1000, "max_util")
    familiarity = []
    for f in p.faculty:
        terms = [pick[k] * (p.D[k[0]].sessions * p.D[k[0]].duration) for k in pick if k[1] == f.id]
        total = sum(terms) + load[f.id]
        if terms:
            m.Add(total <= f.max_per_week)
        # utilisation in per-mille so integer arithmetic is fine
        m.Add(total * 1000 <= max_util * max(f.max_per_week, 1))
        # tie-break: prefer a teacher who already teaches that class
        teaches = {d.class_id for d in p.demands if d.faculty_id == f.id}
        familiarity += [pick[k] for k in pick if k[1] == f.id and p.D[k[0]].class_id in teaches]
    m.Minimize(max_util * 10 - sum(familiarity))

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = 5
    if s.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError("Cannot assign faculty without exceeding weekly workload limits")
    return {**fixed, **{k[0]: k[1] for k, v in pick.items() if s.Value(v)}}


def solve(p: Problem, time_limit: float | None = None, seed: int = 0) -> dict:
    t0 = time.time()
    issues = validator.precheck(p)
    if issues:
        return {"status": "INVALID_INPUT", "issues": issues, "entries": [],
                "generation_time": round(time.time() - t0, 2)}
    try:
        fac = assign_faculty(p)
    except ValueError as e:
        return {"status": "INFEASIBLE", "issues": [str(e)], "entries": [],
                "generation_time": round(time.time() - t0, 2)}

    demands = [replace(d, faculty_id=fac[d.id]) for d in p.demands]
    P = len(p.slots)
    teaching = [i for i, s in enumerate(p.slots) if not s.is_break]

    # ---- occupancy already taken by locked/fixed entries ----
    busy_f, busy_u, busy_r = set(), set(), set()
    locked_load_day = defaultdict(int)
    locked_count = defaultdict(int)
    for e in p.locked:
        span = p.block(e.slot_id, e.duration) or []
        for i in span:
            busy_f.add((e.faculty_id, e.day_id, i))
            busy_r.add((e.room_id, e.day_id, i))
            for u in p.units(e.class_id, e.batch_id):
                busy_u.add((u, e.day_id, i))
        locked_load_day[e.faculty_id, e.day_id] += e.duration
        locked_count[demand_key(e.class_id, e.batch_id, e.subject_id, e.component)] += 1

    unavailable = {(f.id, d, p.pos[s]) for f in p.faculty for d, s in f.unavailable if s in p.pos}
    preferred = {(f.id, d, p.pos[s]) for f in p.faculty for d, s in f.preferred if s in p.pos}
    first_break = next((i for i, s in enumerate(p.slots) if s.is_break), P)

    m = cp_model.CpModel()
    x = {}                                    # (demand, day, start_pos, room) -> BoolVar
    cover_f = defaultdict(list)               # (fac, day, pos) -> vars
    cover_u = defaultdict(list)               # (unit, day, pos)
    cover_r = defaultdict(list)               # (room, day, pos)
    by_dd = defaultdict(list)                 # (demand, day) -> vars
    load_fd = defaultdict(list)               # (fac, day) -> weighted vars
    bonus = []                                # linear terms to subtract from objective
    remaining = {}

    for d in demands:
        need = d.sessions - locked_count[demand_key(d.class_id, d.batch_id, d.subject_id, d.component)]
        remaining[d.id] = max(need, 0)
        if need <= 0:
            continue
        subj, cls = p.S[d.subject_id], p.C[d.class_id]
        units = p.units(d.class_id, d.batch_id)
        rooms = p.eligible_rooms(d)
        placed = []
        for day in p.days:
            for start in teaching:
                span = p.block(p.slots[start].id, d.duration)
                if not span:
                    continue
                if any((d.faculty_id, day.id, i) in busy_f or (d.faculty_id, day.id, i) in unavailable
                       or any((u, day.id, i) in busy_u for u in units) for i in span):
                    continue
                for r in rooms:
                    if any((r.id, day.id, i) in busy_r for i in span):
                        continue
                    v = m.NewBoolVar("")
                    x[d.id, day.id, start, r.id] = v
                    placed.append(v)
                    by_dd[d.id, day.id].append(v)
                    load_fd[d.faculty_id, day.id].append(v * d.duration)
                    for i in span:
                        cover_f[d.faculty_id, day.id, i].append(v)
                        cover_r[r.id, day.id, i].append(v)
                        for u in units:
                            cover_u[u, day.id, i].append(v)
                    # per-placement soft terms (pure coefficients, no extra vars)
                    gain = 0
                    gain += p.w("faculty_preference_bonus") * sum((d.faculty_id, day.id, i) in preferred for i in span)
                    if subj.morning_preferred and start + d.duration <= first_break:
                        gain += p.w("morning_preference_bonus")
                    if cls.home_room_id == r.id:
                        gain += p.w("home_room_bonus")
                    gain -= p.w("room_capacity_waste_penalty") * ((r.capacity - p.strength(d.class_id, d.batch_id)) // 10)
                    if gain:
                        bonus.append(int(round(gain)) * v)
        if len(placed) < need:
            return {"status": "INFEASIBLE", "entries": [], "generation_time": round(time.time() - t0, 2),
                    "issues": [f"{subj.name} for {cls.name}: only {len(placed)} feasible placements for {need} sessions "
                               f"(faculty {p.F[d.faculty_id].name} unavailable/locked, or no free room)"]}
        m.Add(sum(placed) == need)                                         # HARD: required sessions

    # HARD: nobody (faculty / student unit / room) in two places at once
    for cover in (cover_f, cover_u, cover_r):
        for vs in cover.values():
            if len(vs) > 1:
                m.AddAtMostOne(vs)

    # HARD: subject-per-day cap, faculty daily/weekly limits
    max_same = int(p.w("max_same_subject_per_day", 2))
    for (did, day), vs in by_dd.items():
        m.Add(sum(vs) <= max_same)
    for f in p.faculty:
        week = []
        for day in p.days:
            day_terms = load_fd.get((f.id, day.id), [])
            week += day_terms
            if day_terms:
                m.Add(sum(day_terms) + locked_load_day[f.id, day.id] <= f.max_per_day)
        if week:
            m.Add(sum(week) + sum(locked_load_day[f.id, dd.id] for dd in p.days) <= f.max_per_week)

    penalties = []

    def busy_expr(cover, key_prefix, fixed, day, i):
        """0/1 expression: is this person/unit busy at (day, i)?"""
        if (key_prefix, day, i) in fixed:
            return 1
        return sum(cover.get((key_prefix, day, i), []))

    def runs(cover, fixed, who, max_consec, gap_w, consec_w, balance_w):
        """Gap, consecutive-run and daily-balance penalties for one person/unit."""
        peak = m.NewIntVar(0, P, "")
        for day in p.days:
            b = {i: busy_expr(cover, who, fixed, day.id, i) for i in teaching}
            m.Add(sum(b.values()) <= peak)
            # Gaps: count busy blocks in the day (breaks skipped, so P4 -> P5 is adjacent);
            # every block beyond the first means a hole of any length.
            if gap_w:
                starts = [b[teaching[0]]]
                for prev, i in zip(teaching, teaching[1:]):
                    t = m.NewBoolVar("")
                    m.Add(t >= b[i] - b[prev])
                    starts.append(t)
                g = m.NewIntVar(0, len(teaching), "")
                m.Add(g >= sum(starts) - 1)
                penalties.append(gap_w * g)
            for i in teaching:
                window = list(range(i, i + max_consec + 1))
                if consec_w and all(j in b for j in window):
                    c = m.NewIntVar(0, 1, "")
                    m.Add(c >= sum(b[j] for j in window) - max_consec)
                    penalties.append(consec_w * c)
        if balance_w:
            penalties.append(balance_w * peak)

    for f in p.faculty:
        if any(k[0] == f.id for k in cover_f):
            runs(cover_f, busy_f, f.id, f.max_consecutive, int(p.w("faculty_gap_penalty")),
                 int(p.w("faculty_consecutive_penalty")), int(p.w("faculty_daily_balance_penalty")))
    student_consec = int(p.w("student_max_consecutive", 4))
    for c in p.classes:
        for u in p.units(c.id, None):
            if any(k[0] == u for k in cover_u):
                runs(cover_u, busy_u, u, student_consec, int(p.w("student_gap_penalty")),
                     int(p.w("student_consecutive_penalty")), int(p.w("student_daily_balance_penalty")))

    # SOFT: same subject more than once a day
    w_same = int(p.w("same_subject_same_day_penalty"))
    if w_same:
        for vs in by_dd.values():
            if len(vs) > 1:
                e = m.NewIntVar(0, max_same, "")
                m.Add(e >= sum(vs) - 1)
                penalties.append(w_same * e)

    # SOFT: two core (difficult) theory subjects back to back for a class
    w_core = int(p.w("core_consecutive_penalty"))
    if w_core:
        core = defaultdict(list)
        for (did, day, start, rid), v in x.items():
            d = p.D[did]
            if p.S[d.subject_id].is_core and d.component == "L":
                for i in range(start, start + d.duration):
                    core[d.class_id, day, i].append(v)
        for (cid, day, i), vs in core.items():
            nxt = core.get((cid, day, i + 1))
            if nxt:
                b = m.NewBoolVar("")
                m.Add(b >= sum(vs) + sum(nxt) - 1)
                penalties.append(w_core * b)

    # SOFT: fair share of first/last periods across faculty (minimise the worst case)
    w_fl = int(p.w("first_last_period_fairness_penalty"))
    if w_fl and teaching:
        for edge in (teaching[0], teaching[-1]):
            worst = m.NewIntVar(0, len(p.days), "")
            for f in p.faculty:
                vs = [v for day in p.days for v in cover_f.get((f.id, day.id, edge), [])]
                if vs:
                    m.Add(sum(vs) <= worst)
            penalties.append(w_fl * worst)

    m.Minimize(sum(penalties) - sum(bonus))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit or p.w("solver_time_limit_seconds", 20)
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = seed
    st = solver.Solve(m)
    status = STATUS.get(st, "UNKNOWN")
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status, "entries": [], "generation_time": round(time.time() - t0, 2),
                "issues": ["Solver found no timetable that satisfies every hard constraint. "
                           "Check workload limits, unavailability and locked periods."]}

    entries = [replace(e) for e in p.locked]          # fixed entries keep their own locked flag
    for (did, day, start, rid), v in x.items():
        if solver.Value(v):
            d = p.D[did]
            entries.append(Entry(demand_id=did, class_id=d.class_id, batch_id=d.batch_id, subject_id=d.subject_id,
                                 component=d.component, faculty_id=fac[did], room_id=rid, day_id=day,
                                 slot_id=p.slots[start].id, duration=d.duration))
    # demands carry the chosen faculty so validation/metrics see phase-1 results
    p2 = replace(p, demands=demands)
    for e in entries:
        e.explanation = validator.explain(p2, entries, e)
    conflicts = validator.find_conflicts(p2, entries)
    metrics = validator.metrics(p2, entries)
    return {
        "status": status,
        "generation_time": round(time.time() - t0, 2),
        "objective": solver.ObjectiveValue(),
        "hard_constraint_violations": len([c for c in conflicts if c["severity"] == "hard"]),
        "soft_score": metrics["score"],
        "metrics": metrics,
        "conflicts": conflicts,
        "auto_assigned": {did: f for did, f in fac.items() if p.D[did].faculty_id is None},
        "entries": entries,
    }
