"""Faculty absence / substitution engine.

A weekly timetable plus a `DateContext` (who is absent that date, which
one-off sessions already exist) answers: which lectures are affected, who can
legally cover each one, how they rank, and where a lecture could be
rescheduled if nobody can.

Eligibility is hard-filtered (authorized, free, present, available, within
limits); ranking is a weighted score whose weights live in the
ConstraintConfiguration table (keys `sub_*`).  A free teacher who is not
authorized for the subject is never eligible.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Optional

from .model import Problem, Entry
from .validator import span, cls_name, when


@dataclass
class DateContext:
    day_id: int
    date: str = ""
    absent: dict[int, Optional[set[int]]] = field(default_factory=dict)  # faculty -> slot ids (None = full day)
    extra: list[Entry] = field(default_factory=list)      # one-off sessions on this date (subs, rescheduled)
    removed: set[int] = field(default_factory=set)        # regular entry ids not held as usual (subbed/cancelled/moved)
    week_extra: dict[int, int] = field(default_factory=dict)  # extra periods per faculty this week

    def is_absent(self, p: Problem, fid: int, positions: list[int]) -> bool:
        if fid not in self.absent:
            return False
        slots = self.absent[fid]
        return slots is None or any(p.slots[i].id in slots for i in positions)


def today_entries(entries: list[Entry], ctx: DateContext) -> list[Entry]:
    """What actually happens on this date: regular entries minus removed, plus one-offs."""
    return [e for e in entries if e.day_id == ctx.day_id and e.id not in ctx.removed] + ctx.extra


def affected(p: Problem, entries: list[Entry], faculty_id: int, ctx: DateContext) -> list[Entry]:
    return sorted((e for e in entries if e.day_id == ctx.day_id and e.faculty_id == faculty_id
                   and ctx.is_absent(p, faculty_id, span(p, e) or [])), key=lambda e: p.pos[e.slot_id])


def _busy(p: Problem, day: list[Entry], fid: int) -> dict[int, Entry]:
    return {i: e for e in day if e.faculty_id == fid for i in span(p, e) or []}


def candidates(p: Problem, entries: list[Entry], e: Entry, ctx: DateContext,
               override_workload: bool = False) -> list[dict]:
    """Every faculty member evaluated for covering `e` on ctx's date, best first."""
    s, cls = p.S[e.subject_id], p.C[e.class_id]
    sp = span(p, e) or []
    t = f"{p.slots[sp[0]].start}" if sp else "?"
    day = today_entries(entries, ctx)
    week = defaultdict(int)
    for x in entries:
        week[x.faculty_id] += x.duration
    # who already teaches what to whom (from the regular timetable)
    teaches = defaultdict(set)
    for x in entries:
        teaches[x.faculty_id].add((x.subject_id, x.class_id))
    same_dept = p.w("substitute_same_department_only") > 0
    W = lambda k, dflt: p.w(k, dflt)

    out = []
    for f in p.faculty:
        if f.id == e.faculty_id:
            continue
        reasons, hard_ok, score = [], True, 0.0

        def check(ok, yes, no, hard=True):
            nonlocal hard_ok
            reasons.append({"ok": ok, "text": yes if ok else no})
            if hard and not ok:
                hard_ok = False

        qualified = e.subject_id in f.subject_ids
        check(qualified, f"Teaches {s.name}", f"Not authorized to teach {s.name}")
        busy = _busy(p, day, f.id)
        clash = next((busy[i] for i in sp if i in busy), None)
        check(clash is None, f"Free at {t}",
              f"Busy at {t}: {p.S[clash.subject_id].name} for {cls_name(p, clash)}" if clash else "")
        check(not ctx.is_absent(p, f.id, sp), "Present on this date", "Also absent on this date")
        blocked = {(d, sl) for d, sl in f.unavailable}
        check(not any((ctx.day_id, p.slots[i].id) in blocked for i in sp), "Available in this period",
              "Marked unavailable in this period")
        d_load = sum(x.duration for x in day if x.faculty_id == f.id)
        w_load = week[f.id] + ctx.week_extra.get(f.id, 0)
        check(d_load + e.duration <= f.max_per_day or override_workload,
              f"Daily load {d_load + e.duration}/{f.max_per_day} within limit",
              f"Would exceed daily limit ({d_load + e.duration}/{f.max_per_day})")
        check(w_load + e.duration <= f.max_per_week or override_workload,
              f"Weekly workload {w_load + e.duration}/{f.max_per_week} within limit",
              f"Would exceed weekly limit ({w_load + e.duration}/{f.max_per_week})")
        if same_dept:
            check(f.department_id == cls.department_id, "Same department", "Different department (policy)")

        # ---- ranking (soft) ----
        if (e.subject_id, e.class_id) in teaches[f.id]:
            score += W("sub_same_subject_same_class", 50)
            reasons.append({"ok": True, "text": f"Already teaches {s.name} to {cls.name}"})
        elif any(sid == e.subject_id and p.C[cid].year_level == cls.year_level for sid, cid in teaches[f.id]):
            score += W("sub_same_subject_same_year", 25)
            reasons.append({"ok": True, "text": f"Teaches {s.name} to another {cls.year_level} class"})
        elif any(sid == e.subject_id for sid, _ in teaches[f.id]):
            score += W("sub_same_subject", 15)
            reasons.append({"ok": True, "text": f"Currently teaches {s.name}"})
        if any(cid == e.class_id for _, cid in teaches[f.id]):
            score += W("sub_teaches_class", 15)
            reasons.append({"ok": True, "text": f"Already teaches {cls.name} (knows the class)"})
        score += W("sub_daily_load_weight", 4) * (f.max_per_day - d_load)
        score += W("sub_weekly_load_weight", 1) * (f.max_per_week - w_load)
        run = 1 + _run(busy, sp[0] - 1, -1) + _run(busy, sp[-1] + 1, 1) if sp else 0
        if run + e.duration - 1 > f.max_consecutive:
            score -= W("sub_consecutive_penalty", 10)
            reasons.append({"ok": False, "text": f"Would make {run + e.duration - 1} consecutive periods"})
        if any((ctx.day_id, p.slots[i].id) in {tuple(x) for x in f.preferred} for i in sp):
            score += W("sub_preferred_slot_bonus", 5)
        if hard_ok:
            reasons.append({"ok": True, "text": "No conflict"})
        out.append(dict(faculty_id=f.id, name=f.name, qualified=qualified, eligible=hard_ok,
                        score=round(score, 1), daily_load=d_load, weekly_load=w_load, reasons=reasons))
    out.sort(key=lambda c: (not c["eligible"], not c["qualified"], -c["score"]))
    return out


def _run(busy: dict, i: int, step: int) -> int:
    n = 0
    while i in busy:
        n += 1
        i += step
    return n


def as_substitute(e: Entry, faculty_id: int) -> Entry:
    return replace(e, faculty_id=faculty_id, locked=False)


def auto_plan(p: Problem, entries: list[Entry], todo: list[Entry], ctx: DateContext) -> list[dict]:
    """Greedy: give each affected lecture its best eligible candidate, updating
    the context after every pick so two lectures never get the same free teacher."""
    ctx = replace(ctx, extra=list(ctx.extra), removed=set(ctx.removed), week_extra=dict(ctx.week_extra))
    plan = []
    for e in todo:
        cands = candidates(p, entries, e, ctx)
        best = next((c for c in cands if c["eligible"]), None)
        plan.append({"entry": e, "best": best, "alternatives": sum(c["eligible"] for c in cands) - bool(best)})
        if best:
            ctx.removed.add(e.id)
            ctx.extra.append(as_substitute(e, best["faculty_id"]))
            ctx.week_extra[best["faculty_id"]] = ctx.week_extra.get(best["faculty_id"], 0) + e.duration
    return plan


def reschedule_options(p: Problem, entries: list[Entry], e: Entry, contexts: list[DateContext],
                       limit: int = 8) -> list[dict]:
    """Free (date, slot, room) where the original teacher, the class and a room are all free."""
    opts = []
    for ctx in contexts:
        day = today_entries(entries, ctx)
        for s in p.slots:
            sp = p.block(s.id, e.duration)
            if not sp or ctx.is_absent(p, e.faculty_id, sp):
                continue
            if any((ctx.day_id, p.slots[i].id) in {tuple(x) for x in p.F[e.faculty_id].unavailable} for i in sp):
                continue
            units = set(p.units(e.class_id, e.batch_id))
            taken = [x for x in day if set(span(p, x) or []) & set(sp)]
            if any(x.faculty_id == e.faculty_id or units & set(p.units(x.class_id, x.batch_id)) for x in taken):
                continue
            if sum(x.duration for x in day if x.faculty_id == e.faculty_id) + e.duration > p.F[e.faculty_id].max_per_day:
                continue
            used = {x.room_id for x in taken}
            room = e.room_id if e.room_id not in used else next(
                (r.id for r in p.eligible_rooms(p.D[e.demand_id]) if r.id not in used), None) if e.demand_id in p.D else None
            if room is None:
                continue
            opts.append(dict(date=ctx.date, day_id=ctx.day_id, slot_id=s.id, room_id=room,
                             label=f"{ctx.date} · {when(p, ctx.day_id, s.id, e.duration)} · {p.R[room].code}"))
            if len(opts) >= limit:
                return opts
    return opts
