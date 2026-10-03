# Dream Timetable — AI-powered college timetabling & faculty substitution

Constraint-optimised weekly timetables (Google OR-Tools CP-SAT), a faculty
absence/substitution engine with explainable rankings, conflict detection,
validated drag-and-drop editing, workload/credit analytics and a rule-based
smart assistant. Runs on realistic dummy data for *Dream Institute of
Technology*; swap in real data by replacing CSV/XLSX files.

## Run

Requirements: Python 3.12 (OR-Tools wheels), Node 20+.

```bash
# backend (from project root)
uv venv -p python3.12 backend/.venv && uv pip install -p backend/.venv/bin/python -r backend/requirements.txt
backend/.venv/bin/uvicorn backend.main:app --port 8000 --reload --reload-dir backend --reload-dir scheduler

# frontend
cd frontend && npm install && npm run dev        # http://localhost:3000
```

First API start imports `data/dummy/`, generates a timetable (~20 s) and accepts it.
Reset everything: stop the API, delete `backend/timetable.db`, start again.
API docs: http://localhost:8000/docs

```bash
backend/.venv/bin/python -m pytest tests -q                          # engine tests (no DB/UI)
backend/.venv/bin/python -m scheduler data/sample_problem.json        # solver on raw JSON
backend/.venv/bin/python -m backend.importer data/college            # load real data
```

## Demo scenarios

| | Where | What to do |
|---|---|---|
| A Generation | Generate Timetable | Click **Generate** → 0 hard violations, metrics, Accept |
| B Absence | Absences | Prof. Anil Sharma, a weekday, full day → affected lectures listed |
| C Smart substitute | Absences | Recommended teacher with ✓ reasons → Assign / Auto assign all |
| D No substitute | Absences | Prof. Amit Verma on the day he teaches Computer Graphics (sole qualified teacher) → reasons + reschedule options |
| E Manual change | Timetable → Edit manually | Drag a card; target turns green/red while validating |
| F Conflict | Timetable | Drop onto a busy slot → "Cannot move lecture. … already teaches …"; or mark a taught slot unavailable on a faculty profile → Conflicts → Resolve automatically |
| G Credits | Subjects → Credit tracker, Classes | Required vs scheduled per class/subject/batch |
| H Regeneration | Timetable → Lock class / day / practicals → Generate | Locked entries unchanged, rest re-optimised |
| What-if | Absences → What-if simulation | Counts of coverable vs reschedule-needed lectures, nothing saved |

More: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/DATA_IMPORT.md](docs/DATA_IMPORT.md) · [docs/SCHEDULER_IO.md](docs/SCHEDULER_IO.md)
