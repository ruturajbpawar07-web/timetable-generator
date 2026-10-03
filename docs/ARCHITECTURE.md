# Architecture

```
frontend/   Next.js 16 + TypeScript + Tailwind v4, Recharts, dnd-kit. Calls /api/* (proxied to FastAPI).
backend/    FastAPI app
  main.py        HTTP routes only
  services.py    DB <-> engine adapter; every mutation validated, then audited
  db.py          SQLAlchemy relational model (SQLite default, DATABASE_URL for PostgreSQL)
  importer.py    CSV/XLSX folder -> DB (the data-import layer)
  assistant.py   NL query -> intent -> deterministic function (read-only, proposes actions)
  export.py      CSV/XLSX exports (PDF = browser print stylesheet)
scheduler/  Pure Python engine. No DB, no HTTP. Testable on JSON.
  model.py       Standardized input/output dataclasses (Problem, Demand, Entry, ...)
  solver.py      CP-SAT: faculty workload balancer + timetable optimiser
  validator.py   Conflict engine, move validation, explanations, quality metrics
  substitution.py Absence impact, substitute eligibility/ranking, reschedule options
data/dummy/ Dummy college dataset (CSV) — replace with real files
tests/      Engine tests (pytest)
```

Stack note: shadcn/ui was not used — its CLI generates dozens of files; a
~200-line `components/ui.tsx` (Card, Button, Modal, Table, Toast, …) covers what
the app needs. Everything else follows the requested stack.

## Data model (backend/db.py)

College → Department → Program; AcademicYear → Semester; Division (class, with
`home_room`) → StudentBatch (practical batches). Subject carries `credits`
**separately** from `lecture_sessions_per_week`, `tutorial_sessions_per_week`,
`practical_sessions_per_week`, `practical_duration_periods`.
SubjectRequirement = what one division (or batch) needs per week for one
component; FacultyClassAssignment says who teaches it (NULL → workload
balancer chooses). FacultySubject = authorization (also governs substitutes).
FacultyAvailability (UNAVAILABLE / PREFERRED per day×slot), FacultyAbsence
(per date, NULL slot = full day), WorkingDay, TimeSlot (`is_break`),
Timetable (DRAFT/ACTIVE/ARCHIVED) → TimetableEntry (`locked`, `explanation`),
Substitution (SUBSTITUTED / CANCELLED / RESCHEDULED, date-specific, with the
reasons it was chosen), ConstraintConfiguration (all weights), GenerationRun,
AuditLog (timestamp, user, action, previous, new, reason).

Deliberate simplifications vs the requested entity list:
- **Lab** is `Room.kind = 'LAB'` + `lab_type` (rooms and labs share capacity/scheduling logic).
- **LockedSlot** is `TimetableEntry.locked`; locking a day/class/faculty/practical block locks the matching entries.
- **Conflict** is computed live by `scheduler/validator.py` rather than stored, so it can never go stale.

All relationships are integer foreign keys; codes (F01, CE301) exist only in import files.

## How the scheduler works

**Input**: `Problem` (see SCHEDULER_IO.md) — days, slots, faculty, subjects,
classes+batches, rooms, *demands* (requirement × sessions × block length ×
teacher), fixed/locked entries, weights.

**Pre-check** (`validator.precheck`): readable infeasibility reasons before solving
(teacher over weekly limit, class needs more periods than exist, no room big
enough, teacher not authorized…).

**Phase 1 — workload balancer** (CP-SAT, `assign_faculty`): demands with no
teacher get one of the qualified faculty, minimising the maximum utilisation
(load / max_per_week), tie-broken toward teachers who already know the class.

**Phase 2 — timetabling** (CP-SAT, `solve`): a boolean `x[demand, day, start, room]`
exists only for placements that are already legal: block fits without crossing
a break, teacher not unavailable/absent, no collision with locked entries,
room of the right kind/lab type/capacity. Then:

Hard constraints (never violated):
- `Σ x = required sessions` per demand (minus locked ones) — subject credits
- AtMostOne per (faculty, day, period), per (student unit, day, period), per (room, day, period).
  A whole-class session occupies every batch; parallel batch practicals may share a period.
- faculty `max_per_day`, `max_per_week`; `max_same_subject_per_day`

Soft constraints (weights from ConstraintConfiguration, all tunable in Settings):
faculty/student gaps (extra busy blocks per day), consecutive-run limits,
same-subject-same-day, core subjects back-to-back, daily balance (busiest day),
fair share of first/last periods, preferred slots, morning-preferred subjects,
home room, room capacity waste.

Solver: 8 workers, configurable time limit (default 20 s), seed varies on
"Regenerate". Output is re-validated by the independent conflict engine.

**Quality metrics** (`validator.metrics`): hard violations, unscheduled
sessions, workload σ, student/faculty gaps, room/lab utilisation, preference
satisfaction, subject spread, time. Score =
`0 if any hard violation or unscheduled session, else 100 × mean(subject_spread,
student_compactness, faculty_compactness, preference_satisfaction, daily_balance)`.

**Explainability**: every entry stores the checks it passed
(`validator.explain`) — teacher free, class free, room fits, n/m sessions,
no same-day repeat, load today/week, preferences, locked, auto-assigned.

## Substitution engine

Affected lectures = the absent teacher's entries overlapping the absent periods.
For each lecture every other teacher is evaluated. **Hard filter**: authorized
for the subject, free (incl. other substitutions that date), present, not
unavailable, within daily/weekly limits (admin override possible), optional
same-department policy. **Rank** (weights `sub_*`): already teaches this
subject to this class > same subject same year > same subject; knows the
class; remaining daily/weekly capacity; penalty for long consecutive runs;
preferred slot. Every ✓/✗ reason is returned. Auto-assign is greedy with state
updates so one teacher never gets two simultaneous covers. If nobody is
eligible: reschedule options in the next 7 days where teacher, class and a
room are free. Substitutions are date-specific; the weekly timetable is untouched.

## Smart assistant

`assistant.py`: regex/keyword intent detection + entity extraction (faculty
surname, subject name/code/acronym, day/tomorrow, "11 AM"/"Period 4") →
calls the same deterministic functions as the UI. It never writes; proposed
changes come back as actions the admin confirms, which then go through the
normal validated endpoints. An LLM can later replace `detect` logic only.

## Future ML (not implemented on purpose)

Training data accumulates in Substitution (who was chosen, with which
features), AuditLog (manual edits = revealed preferences), FacultyAbsence
(absence patterns) and GenerationRun (weights → metrics). Hook points:
- substitute ranking: replace the score in `substitution.candidates` with a learned model; the hard filter stays.
- weight recommendation: learn ConstraintConfiguration values from accepted/edited timetables.
- absence forecasting: pre-compute cover plans with the what-if simulator.

Rule everywhere: ML recommendation → constraint engine (`validator` / hard
filter) → accept or reject. No model output reaches the DB unvalidated.
