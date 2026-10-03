# Scheduling engine input / output

Full example: `data/sample_problem.json` (exported from the dummy data).
Run: `backend/.venv/bin/python -m scheduler data/sample_problem.json`.

## Input

```json
{
  "academic_year": "2026-27",
  "semester": 5,
  "working_days": [{"id": 1, "name": "Monday"}],
  "time_slots":   [{"id": 1, "index": 1, "start": "09:00", "end": "10:00", "is_break": false}],
  "faculty":  [{"id": 1, "name": "Prof. Anil Sharma", "department_id": 1, "subject_ids": [6, 1],
                "max_per_day": 5, "max_per_week": 18, "min_per_week": 10, "max_consecutive": 3,
                "unavailable": [[5, 6]], "preferred": [[1, 1]]}],
  "subjects": [{"id": 6, "code": "CE301", "name": "Database Management Systems", "department_id": 1,
                "is_core": true, "morning_preferred": false, "lab_type": null}],
  "classes":  [{"id": 3, "name": "TE-CE-A", "department_id": 1, "year_level": "TE", "strength": 68,
                "batches": [{"id": 5, "name": "A1", "strength": 34}], "home_room_id": 3}],
  "rooms":    [{"id": 3, "code": "CR103", "kind": "CLASSROOM", "capacity": 72, "lab_type": null}],
  "demands":  [{"id": 20, "class_id": 3, "subject_id": 6, "component": "L", "sessions": 4,
                "duration": 1, "batch_id": null, "faculty_id": 1}],
  "locked":   [],
  "weights":  {"faculty_gap_penalty": 5, "same_subject_same_day_penalty": 8}
}
```

`unavailable`/`preferred` are `[day_id, slot_id]` pairs. Rooms and labs share one
list (`kind`). `faculty_id: null` in a demand = workload balancer chooses.
`locked` entries are kept exactly and count towards their demand's sessions.

## Output

```json
{
  "status": "OPTIMAL | FEASIBLE | INFEASIBLE | INVALID_INPUT",
  "generation_time": 20.2,
  "hard_constraint_violations": 0,
  "soft_score": 89.7,
  "metrics": {"unscheduled_sessions": 0, "student_gaps": 4, "faculty_gaps": 1, "...": "...", "score_formula": "..."},
  "conflicts": [],
  "auto_assigned": {"12": 12},
  "issues": [],
  "entries": [{"demand_id": 20, "class_id": 3, "subject_id": 6, "component": "L", "faculty_id": 1,
               "room_id": 3, "day_id": 2, "slot_id": 2, "duration": 1, "batch_id": null,
               "locked": false, "explanation": ["✓ Prof. Anil Sharma available and free on Tuesday P2 …"]}]
}
```
