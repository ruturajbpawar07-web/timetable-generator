# Importing real college data

Create `data/college/` with these files (each may be `.csv` **or** `.xlsx`,
first sheet, first row = header). Copy `data/dummy/` as a template, then:

```bash
backend/.venv/bin/python -m backend.importer data/college
```

This **replaces** the database contents. Afterwards open Generate Timetable
and generate. Unknown codes fail with the file and row number.

| File | Columns |
|---|---|
| settings | key, value, description — weights & policies (see dummy file for every key) |
| departments | code, name, program_code, program_name |
| working_days | name (Monday…), order |
| time_slots | index, start, end, is_break (1/0), label |
| rooms | code, name, kind (CLASSROOM/LAB), capacity, lab_type, department |
| subjects | code, name, department, semester, credits, lecture_sessions_per_week, tutorial_sessions_per_week, practical_sessions_per_week, practical_duration_periods, lab_type, is_core, morning_preferred |
| classes | code, department, program, year_level, semester, division, strength, home_room, batches (`A1:36;A2:36`) |
| faculty | code, name, department, designation, max_per_day, max_per_week, min_per_week, max_consecutive, subjects (`CE301;CE302` = authorized) |
| assignments | class, subject, component (L/T/P), batch (blank = whole class), faculty (blank = auto-balance), optional sessions, duration overrides |
| availability | faculty, day, period_index, kind (UNAVAILABLE/PREFERRED) |

Notes
- Credits never drive session counts directly; the `*_sessions_per_week` columns do, and `assignments.sessions` can override per class.
- Saturday or half days: add the day to `working_days`; block unused periods via `availability` or add per-day slots later (TODO).
- Electives: model each elective group as a subject taught to the class (see CE405). Parallel elective groups are a TODO.
