# PMCK Training LMS

A FastAPI-based learning management platform that implements the PMCK Training vision with multi-brand governance, scoped roles, course creation, and assignment tracking. The API enforces Discord-style permissions so store teams can create local training while head office launches global programs.

## Features

- Brand management with theme metadata for certificates and UI styling.
- Store directory scoped to brands.
- Flag/tag catalogue for audience targeting.
- Hierarchical roles: Super Admin, Admin, Area Manager, Operator, Trainer, Trainee.
- Role-aware user provisioning with store memberships and optional flags.
- Course builder supporting global and local courses, modules, lessons, and audience rules.
- Scoped course listing based on brand and store visibility.
- Course assignments with required/due-date tracking.
- Audit log for key actions (brand/store/user/course/assignment creation).

## Getting Started

### Windows (double-click setup)

1. Run `setup_pmck_training.bat`. The script checks for Python 3.10+, reports the interpreter it finds, upgrades pip/setuptools/wheel, and installs dependencies while preferring prebuilt wheels (handy for Python 3.13). Re-run this script anytime new packages are added.
2. Launch `run_pmck_training.bat`. A terminal will open, seed demo data (if needed), and start the FastAPI server on `http://127.0.0.1:8000`. If any dependency is missing, the launcher now explains how to finish setup instead of crashing with a Python traceback.
3. Open that URL in your browser. The new visual dashboard lets you pick a seeded demo user and explore each role’s permissions without touching headers or scripts.

### macOS / Linux

1. Install dependencies manually:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Launch the seeded demo:
   ```bash
   python run_pmck_training.py
   ```
   or run the API directly with:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Visit `http://127.0.0.1:8000` for the UI or `http://127.0.0.1:8000/docs` to exercise the API.

### API access & demo accounts

If you want to call endpoints manually, supply an `X-User-Id` header that matches a user in the database.

The launcher seeds these demo users:
`1` Super Admin, `2` Brand Admin, `3` Area Manager, `4` Operator,
`5` Trainer, `6` Trainee.

Quick examples:

```bash
curl -H "X-User-Id: 1" http://127.0.0.1:8000/brands
curl -H "X-User-Id: 4" http://127.0.0.1:8000/courses
```

## Database

The service uses SQLite (`pmck_training.db`) by default. Tables are created automatically at startup using SQLAlchemy models defined in `app/models.py`.

## Testing the Workflow

A typical flow looks like:

1. Super Admin creates a brand (`POST /brands`).
2. Admin (brand) creates stores, flags, and users mapped to stores.
3. Operators or Trainers create local courses scoped to their stores.
4. Admins publish global courses with include/exclude rules.
5. Operators/Trainers assign courses to trainees and review progress.
6. Admins review the audit log for compliance oversight.

## Extending

- Add authentication/SSO by swapping `get_current_user` for a real identity provider.
- Expand reporting by aggregating data from `CourseAssignment` and `Course` tables.
- Introduce certificate rendering and notification delivery.

## License

MIT
