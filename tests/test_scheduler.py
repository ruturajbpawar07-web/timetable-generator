"""Scheduling-engine tests.  Pure scheduler package: no database, no API, no UI.

    backend/.venv/bin/python -m pytest tests -q
"""
from dataclasses import replace

import pytest

from scheduler.model import Problem, Day, Slot, Faculty, Subject, ClassGroup, Batch, Room, Demand, Entry
from scheduler import solver, validator, substitution as sub

MON, TUE = 1, 2
P1, P2, LUNCH, P3, P4 = 11, 12, 13, 14, 15
DBMS, OS, LAB, CG = 101, 102, 103, 104
SHARMA, PATIL, KULKARNI, VERMA = 1, 2, 3, 4
TE_A, TE_B = 201, 202
CR1, CR2, LAB1 = 301, 302, 303


def problem(**over) -> Problem:
    p = dict(
        days=[Day(MON, "Monday"), Day(TUE, "Tuesday")],
        slots=[Slot(P1, 1, "09:00", "10:00"), Slot(P2, 2, "10:00", "11:00"), Slot(LUNCH, 3, "11:00", "12:00", True),
               Slot(P3, 4, "12:00", "13:00"), Slot(P4, 5, "13:00", "14:00")],
        faculty=[Faculty(SHARMA, "Sharma", 1, [DBMS, OS], max_per_day=4, max_per_week=10),
                 Faculty(PATIL, "Patil", 1, [DBMS, LAB], max_per_day=4, max_per_week=10),
                 Faculty(KULKARNI, "Kulkarni", 1, [OS], max_per_day=4, max_per_week=10),
                 Faculty(VERMA, "Verma", 1, [CG], max_per_day=4, max_per_week=10)],
        subjects=[Subject(DBMS, "CE301", "DBMS", 1, is_core=True), Subject(OS, "CE302", "OS", 1),
                  Subject(LAB, "CE301L", "DBMS Lab", 1, lab_type="COMPUTER"), Subject(CG, "CE204", "Graphics", 1)],
        classes=[ClassGroup(TE_A, "TE-A", 1, "TE", 60, [Batch(1, "A1", 30), Batch(2, "A2", 30)], home_room_id=CR1),
                 ClassGroup(TE_B, "TE-B", 1, "TE", 60, home_room_id=CR2)],
        rooms=[Room(CR1, "CR1", "CLASSROOM", 60), Room(CR2, "CR2", "CLASSROOM", 60), Room(LAB1, "LAB1", "LAB", 30, "COMPUTER")],
        demands=[Demand(1, TE_A, DBMS, "L", 2, faculty_id=SHARMA), Demand(2, TE_B, DBMS, "L", 2, faculty_id=SHARMA),
                 Demand(3, TE_A, OS, "L", 2, faculty_id=KULKARNI), Demand(4, TE_B, OS, "L", 1, faculty_id=KULKARNI),
                 Demand(5, TE_A, LAB, "P", 1, duration=2, batch_id=1, faculty_id=PATIL),
                 Demand(6, TE_A, LAB, "P", 1, duration=2, batch_id=2, faculty_id=PATIL),
                 Demand(7, TE_B, CG, "L", 1, faculty_id=VERMA)],
        weights={"max_same_subject_per_day": 2, "same_subject_same_day_penalty": 8, "faculty_gap_penalty": 5},
    )
    p.update(over)
    return Problem(**p)


def solve(p):
    r = solver.solve(p, time_limit=5)
    assert r["status"] in ("OPTIMAL", "FEASIBLE"), r
    return r


def E(**kw):
    base = dict(demand_id=1, class_id=TE_A, subject_id=DBMS, component="L", faculty_id=SHARMA, room_id=CR1,
                day_id=MON, slot_id=P1)
    return Entry(**{**base, **kw})


def types(conflicts):
    return {c["type"] for c in conflicts}


# ---------------- solver: hard constraints hold ----------------
def test_generated_timetable_has_no_hard_conflicts_and_exact_sessions():
    r = solve(problem())
    assert r["hard_constraint_violations"] == 0
    assert r["metrics"]["unscheduled_sessions"] == 0
    got = {}
    for e in r["entries"]:
        got[e.demand_id] = got.get(e.demand_id, 0) + 1
    p = problem()
    assert got == {d.id: d.sessions for d in p.demands}          # credit requirement: exact count, no more


def test_lab_blocks_are_consecutive_and_never_span_lunch():
    r = solve(problem())
    p = problem()
    for e in r["entries"]:
        if e.component == "P":
            span = p.block(e.slot_id, e.duration)
            assert span is not None and len(span) == 2
            assert e.slot_id in (P1, P3)                            # P2 would run into lunch, P4 off the day
            assert p.R[e.room_id].kind == "LAB"


def test_parallel_batches_may_share_a_slot_but_whole_class_may_not():
    p = problem()
    a1 = E(demand_id=5, subject_id=LAB, component="P", batch_id=1, faculty_id=PATIL, room_id=LAB1, duration=2)
    a2 = E(demand_id=6, subject_id=LAB, component="P", batch_id=2, faculty_id=KULKARNI, room_id=CR1, duration=2)
    assert "CLASS_CONFLICT" not in types(validator.find_conflicts(p, [a1, a2]))
    lecture = E(slot_id=P2, room_id=CR2)                             # whole TE-A during A1's lab
    assert "CLASS_CONFLICT" in types(validator.find_conflicts(p, [a1, lecture]))


def test_faculty_unavailable_is_respected_by_solver_and_flagged_by_validator():
    p = problem()
    blocked = [(MON, s) for s in (P1, P2, P3, P4)]
    p.F[SHARMA].unavailable = blocked
    r = solve(p)
    assert all(not (e.faculty_id == SHARMA and e.day_id == MON) for e in r["entries"])
    assert "AVAILABILITY_CONFLICT" in types(validator.find_conflicts(p, [E()]))


def test_absent_faculty_cannot_be_scheduled_in_regeneration():
    p = problem()
    p.F[KULKARNI].unavailable = [(TUE, s) for s in (P1, P2, P3, P4)]   # absence passed as unavailability
    r = solve(p)
    assert all(not (e.faculty_id == KULKARNI and e.day_id == TUE) for e in r["entries"])


def test_locked_entries_are_kept_and_counted():
    locked = E(slot_id=P4, day_id=TUE, locked=True)
    r = solve(problem(locked=[locked]))
    keep = [e for e in r["entries"] if e.locked]
    assert len(keep) == 1 and (keep[0].day_id, keep[0].slot_id, keep[0].room_id) == (TUE, P4, CR1)
    assert sum(e.demand_id == 1 for e in r["entries"]) == 2          # locked one counts towards the 2 required


def test_max_daily_workload_is_never_exceeded():
    p = problem()
    p.F[SHARMA].max_per_day = 2
    r = solve(p)
    day, _ = validator.faculty_loads(p, r["entries"])
    assert all(n <= 2 for (f, d), n in day.items() if f == SHARMA)


def test_weekly_overload_is_reported_before_solving():
    p = problem()
    p.F[SHARMA].max_per_week = 3                                       # assigned 4
    r = solver.solve(p, time_limit=2)
    assert r["status"] == "INVALID_INPUT" and any("above the limit" in i for i in r["issues"])


def test_workload_balancer_assigns_least_loaded_qualified_teacher():
    p = problem()
    p.demands[1] = replace(p.demands[1], faculty_id=None)              # TE-B DBMS: Sharma or Patil
    fac = solver.assign_faculty(p)
    assert fac[2] == SHARMA            # Sharma has 2 fixed periods vs Patil 4 -> lower max utilisation
    p.F[SHARMA].max_per_week = 4       # now Sharma would hit 100%, Patil only 60%
    assert solver.assign_faculty(p)[2] == PATIL


# ---------------- validator: conflict detection ----------------
def test_faculty_double_booking_detected():
    c = validator.find_conflicts(problem(), [E(), E(demand_id=2, class_id=TE_B, room_id=CR2)])
    assert "FACULTY_CONFLICT" in types(c)


def test_class_double_booking_detected():
    c = validator.find_conflicts(problem(), [E(), E(demand_id=3, subject_id=OS, faculty_id=KULKARNI, room_id=CR2)])
    assert "CLASS_CONFLICT" in types(c)


def test_room_double_booking_detected():
    c = validator.find_conflicts(problem(), [E(), E(demand_id=4, class_id=TE_B, subject_id=OS, faculty_id=KULKARNI)])
    assert "ROOM_CONFLICT" in types(c)


def test_credit_shortage_detected():
    assert "CREDIT_SHORTAGE" in types(validator.find_conflicts(problem(), [E()]))


def test_manual_move_validation_names_the_clash():
    p = problem()
    es = [E(id=1), E(id=2, demand_id=2, class_id=TE_B, room_id=CR2, slot_id=P2)]
    _, bad = validator.validate_move(p, es, 0, MON, P2)
    assert bad and "Sharma already teaches TE-B (DBMS)" in bad[0]["message"]
    _, ok = validator.validate_move(p, es, 0, TUE, P3)
    assert ok == []


def test_move_into_break_rejected():
    _, bad = validator.validate_move(problem(), [E(id=1)], 0, MON, LUNCH)
    assert "BREAK_CONFLICT" in types(bad)


# ---------------- substitution engine ----------------
def week():
    """TE-A DBMS by Sharma Mon P1; Patil teaches DBMS lab to TE-A on Tue; Kulkarni busy Mon P1."""
    return [E(id=1),
            E(id=2, demand_id=5, subject_id=LAB, component="P", batch_id=1, faculty_id=PATIL, room_id=LAB1, day_id=TUE, duration=2),
            E(id=3, demand_id=4, class_id=TE_B, subject_id=OS, faculty_id=KULKARNI, room_id=CR2)]


def test_valid_substitute_is_qualified_free_and_ranked_first():
    p, es = problem(), week()
    ctx = sub.DateContext(day_id=MON, absent={SHARMA: None})
    assert [e.id for e in sub.affected(p, es, SHARMA, ctx)] == [1]
    best = sub.candidates(p, es, es[0], ctx)[0]
    assert best["faculty_id"] == PATIL and best["eligible"]
    assert any("Already teaches TE-A" in r["text"] for r in best["reasons"])


def test_free_but_unqualified_teacher_is_not_eligible():
    p, es = problem(), week()
    c = next(c for c in sub.candidates(p, es, es[0], sub.DateContext(day_id=MON, absent={SHARMA: None})) if c["faculty_id"] == VERMA)
    assert not c["eligible"] and not c["qualified"]


def test_busy_or_absent_teacher_is_not_eligible():
    p, es = problem(), week()
    es.append(E(id=9, demand_id=2, class_id=TE_B, faculty_id=PATIL, room_id=CR2))   # Patil now busy Mon P1
    ctx = sub.DateContext(day_id=MON, absent={SHARMA: None})
    assert not next(c for c in sub.candidates(p, es, es[0], ctx) if c["faculty_id"] == PATIL)["eligible"]
    ctx2 = sub.DateContext(day_id=MON, absent={SHARMA: None, PATIL: None})
    assert not next(c for c in sub.candidates(p, week(), week()[0], ctx2) if c["faculty_id"] == PATIL)["eligible"]


def test_no_substitute_available_offers_reschedule_options():
    p = problem()
    cg = E(id=7, demand_id=7, class_id=TE_B, subject_id=CG, faculty_id=VERMA, room_id=CR2)
    ctx = sub.DateContext(day_id=MON, absent={VERMA: None})
    assert not any(c["eligible"] for c in sub.candidates(p, [cg], cg, ctx))
    opts = sub.reschedule_options(p, [cg], cg, [sub.DateContext(day_id=TUE, date="2026-10-06")])
    assert opts and all(o["day_id"] == TUE for o in opts)


def test_auto_plan_never_gives_one_teacher_two_lectures_at_once():
    p = problem()
    es = [E(id=1), E(id=2, demand_id=2, class_id=TE_B, room_id=CR2, slot_id=P1, faculty_id=KULKARNI)]
    ctx = sub.DateContext(day_id=MON, absent={SHARMA: None, KULKARNI: None})
    plan = sub.auto_plan(p, es, es, ctx)
    picks = [x["best"]["faculty_id"] for x in plan if x["best"]]
    assert len(picks) == len(set(picks))


def test_daily_workload_limit_blocks_substitute_unless_overridden():
    p = problem()
    p.F[PATIL].max_per_day = 1
    es = week() + [E(id=8, demand_id=2, class_id=TE_B, faculty_id=PATIL, room_id=CR2, slot_id=P4)]
    ctx = sub.DateContext(day_id=MON, absent={SHARMA: None})
    patil = lambda o: next(c for c in sub.candidates(p, es, es[0], ctx, o) if c["faculty_id"] == PATIL)
    assert not patil(False)["eligible"] and patil(True)["eligible"]
