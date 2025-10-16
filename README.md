# PMCK Training LMS

A FastAPI-powered learning and operations platform that expresses the PMCK Training requirements end-to-end: six themed brands, Discord-style permissions, scoped stores, global vs local courses, certificates, reporting, and Windows one-click scripts that do the heavy lifting for you.

## Feature highlights

- **Brand-first UX** – six brands with colour tokens, tone strings, and certificate styling.
- **Roles & scope** – Super Admin, Admin, Area Manager, Operator, Trainer, Trainee with brand/store clamping baked into every page.
- **Audience builder** – Discord-style include/exclude targeting with preview counts and due-date control.
- **Approvals & auditing** – store-level approvals for trainees plus audit trails for user, store, and course actions.
- **Reports** – coverage metrics per store with CSV export, respecting the viewer’s scope.
- **Certificates** – downloadable completion certificates carrying the learner name and completion date.

## Quick start

### Windows (double-click workflow)

1. **Run `setup_pmck_training.bat`.** The script creates `.venv`, upgrades pip tooling, installs dependencies, seeds demo data, and exercises the `/health` endpoint so you know everything works before you continue.
2. **Launch `run_pmck_training.bat`.** It finds a free port starting at `3000`, seeds again if necessary, opens your browser to `http://127.0.0.1:PORT/`, and keeps the console open for logs.

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pmck_training.py
```

The helper script seeds the SQLite database (`pmck_training.db`), then runs Uvicorn. Visit the printed URL (default `http://127.0.0.1:3000/`).

## Demo accounts

The seed process provisions the full hierarchy per brand plus a cross-brand Super Admin:

| ID | Role | Email |
|----|------|-------|
| 1  | Super Admin | `super.admin@pmck.training` |
| 2  | Brand Admin | `admin@bossa.local` (mirrors across brands) |
| 3  | Area Manager | `area@bossa.local` |
| 4  | Operator | `operator@bossa.local` |
| 5  | Trainer | `trainer@bossa.local` |
| 6  | Trainee | `trainee@bossa.local` |

All demo accounts share the password `Password123!` on first login. Newly created users receive `TempPass123!` and must change it on first use.

## Common flows

1. Select a brand tile on the home page to theme the UI.
2. Log in with a seeded user to land on the role-aware dashboard.
3. Operators/Trainers manage approvals and create local courses scoped to their stores.
4. Admins and Super Admins create brand/global courses via the three-step wizard.
5. Learners complete lessons and download certificates once finished.
6. Leaders export CSVs from the Reports view for coverage tracking.

## Development notes

- The server uses SQLite by default and creates tables automatically on startup.
- Routes live in `app/main.py`; models and enums are defined in `app/models.py`.
- `run_pmck_training.py` can seed only (`--seed-only`), health-check (`--health-check`), or start the server.

MIT licence.
