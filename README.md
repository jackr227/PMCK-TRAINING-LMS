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

1. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **One-file quickstart**
   ```bash
   python run_pmck_training.py
   ```

   The script creates a SQLite database (`pmck_training.db`), seeds demo data, prints
   ready-to-use account IDs, and starts the FastAPI server on
   `http://127.0.0.1:8000`.

3. **Run manually (optional)**
   ```bash
   uvicorn app.main:app --reload
   ```

4. **Authenticate requests**

   Supply an `X-User-Id` header that corresponds to a user in the database. Bootstrapping usually starts by inserting a Super Admin via the SQLite database:
   ```sql
   INSERT INTO users (id, first_name, last_name, email, role, is_active)
   VALUES (1, 'Super', 'Admin', 'super@pmck.local', 'super_admin', 1);
   ```

5. **Explore the API**

   Visit `http://127.0.0.1:8000/docs` for interactive Swagger documentation. Use the
   header box at the top-right to set `X-User-Id`.

6. **Quick demo calls**

   ```bash
   curl -H "X-User-Id: 1" http://127.0.0.1:8000/brands
   curl -H "X-User-Id: 4" http://127.0.0.1:8000/courses
   ```

   Demo accounts seeded by `run_pmck_training.py`:
   `1` Super Admin, `2` Brand Admin, `3` Area Manager, `4` Operator,
   `5` Trainer, `6` Trainee.

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
