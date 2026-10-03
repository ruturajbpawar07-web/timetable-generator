"""Standardized scheduling input/output.

The solver, validator and substitution engine only ever see these
structures — never the database or the UI. `Problem.from_dict` accepts the
JSON format documented in docs/SCHEDULER_IO.md, so the engine can be run
and tested on plain JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Day:
    id: int
    name: str


@dataclass
class Slot:
    id: int
    index: int          # ordering within the day
    start: str          # "09:00"
    end: str
    is_break: bool = False


@dataclass
class Faculty:
    id: int
    name: str
    department_id: int
    subject_ids: list[int]                      # authorized/qualified subjects
    max_per_day: int = 5
    max_per_week: int = 20
    min_per_week: int = 0
    max_consecutive: int = 3
    unavailable: list[tuple[int, int]] = field(default_factory=list)  # (day_id, slot_id)
    preferred: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Subject:
    id: int
    code: str
    name: str
    department_id: int
    is_core: bool = False
    morning_preferred: bool = False
    lab_type: Optional[str] = None


@dataclass
class Batch:
    id: int
    name: str
    strength: int


@dataclass
class ClassGroup:
    id: int
    name: str
    department_id: int
    year_level: str
    strength: int
    batches: list[Batch] = field(default_factory=list)
    home_room_id: Optional[int] = None


@dataclass
class Room:
    id: int
    code: str
    kind: str            # CLASSROOM | LAB
    capacity: int
    lab_type: Optional[str] = None


@dataclass
class Demand:
    """One subject requirement for a class (or a batch of it).

    `sessions` sessions of `duration` consecutive periods each, per week.
    `faculty_id=None` means "let the workload balancer pick a qualified teacher".
    """
    id: int
    class_id: int
    subject_id: int
    component: str               # L (lecture) | T (tutorial) | P (practical)
    sessions: int
    duration: int = 1
    batch_id: Optional[int] = None
    faculty_id: Optional[int] = None


@dataclass
class Entry:
    demand_id: int
    class_id: int
    subject_id: int
    component: str
    faculty_id: int
    room_id: int
    day_id: int
    slot_id: int                 # first slot of the block
    duration: int = 1
    batch_id: Optional[int] = None
    locked: bool = False
    id: Optional[int] = None
    explanation: list[str] = field(default_factory=list)


@dataclass
class Problem:
    days: list[Day]
    slots: list[Slot]
    faculty: list[Faculty]
    subjects: list[Subject]
    classes: list[ClassGroup]
    rooms: list[Room]
    demands: list[Demand]
    locked: list[Entry] = field(default_factory=list)   # fixed entries (locked or out of scope)
    weights: dict[str, float] = field(default_factory=dict)
    academic_year: str = ""
    semester: Optional[int] = None

    # ---- lookups (built lazily, cheap) ----
    def __post_init__(self):
        self.slots = sorted(self.slots, key=lambda s: s.index)
        self.F = {f.id: f for f in self.faculty}
        self.S = {s.id: s for s in self.subjects}
        self.C = {c.id: c for c in self.classes}
        self.R = {r.id: r for r in self.rooms}
        self.D = {d.id: d for d in self.demands}
        self.DAY = {d.id: d for d in self.days}
        self.pos = {s.id: i for i, s in enumerate(self.slots)}   # slot id -> position

    def w(self, key: str, default: float = 0) -> float:
        return float(self.weights.get(key, default))

    def block(self, slot_id: int, duration: int) -> Optional[list[int]]:
        """Positions covered by a block, or None if it runs past the day or into a break."""
        p = self.pos.get(slot_id)
        if p is None or p + duration > len(self.slots):
            return None
        span = list(range(p, p + duration))
        return None if any(self.slots[i].is_break for i in span) else span

    def units(self, class_id: int, batch_id: Optional[int]) -> list[tuple[int, Optional[int]]]:
        """Student 'units' a session occupies: a whole-class session blocks every batch."""
        c = self.C[class_id]
        if batch_id is not None:
            return [(class_id, batch_id)]
        return [(class_id, b.id) for b in c.batches] or [(class_id, None)]

    def strength(self, class_id: int, batch_id: Optional[int]) -> int:
        c = self.C[class_id]
        return next((b.strength for b in c.batches if b.id == batch_id), c.strength)

    def eligible_rooms(self, d: Demand) -> list[Room]:
        need = self.strength(d.class_id, d.batch_id)
        subj = self.S[d.subject_id]
        if d.component == "P":
            return [r for r in self.rooms if r.kind == "LAB" and r.capacity >= need
                    and (not subj.lab_type or r.lab_type == subj.lab_type)]
        return [r for r in self.rooms if r.kind == "CLASSROOM" and r.capacity >= need]

    @staticmethod
    def from_dict(d: dict) -> "Problem":
        return Problem(
            days=[Day(**x) for x in d["working_days"]],
            slots=[Slot(**x) for x in d["time_slots"]],
            faculty=[Faculty(**{**x, "unavailable": [tuple(u) for u in x.get("unavailable", [])],
                                "preferred": [tuple(u) for u in x.get("preferred", [])]})
                     for x in d["faculty"]],
            subjects=[Subject(**x) for x in d["subjects"]],
            classes=[ClassGroup(**{**x, "batches": [Batch(**b) for b in x.get("batches", [])]})
                     for x in d["classes"]],
            rooms=[Room(**x) for x in d["rooms"]],
            demands=[Demand(**x) for x in d["demands"]],
            locked=[Entry(**x) for x in d.get("locked", [])],
            weights=d.get("weights", {}),
            academic_year=d.get("academic_year", ""),
            semester=d.get("semester"),
        )

    def to_dict(self) -> dict:
        return {
            "academic_year": self.academic_year, "semester": self.semester,
            "working_days": [asdict(x) for x in self.days],
            "time_slots": [asdict(x) for x in self.slots],
            "faculty": [asdict(x) for x in self.faculty],
            "subjects": [asdict(x) for x in self.subjects],
            "classes": [asdict(x) for x in self.classes],
            "rooms": [asdict(x) for x in self.rooms],
            "demands": [asdict(x) for x in self.demands],
            "locked": [asdict(x) for x in self.locked],
            "weights": self.weights,
        }
