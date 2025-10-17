from __future__ import annotations

import argparse
import importlib
import time
import webbrowser
from textwrap import dedent

REQUIRED_MODULES = {
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "sqlalchemy": "sqlalchemy",
    "jinja2": "jinja2",
    "itsdangerous": "itsdangerous",
    "passlib": "passlib",
}


def ensure_dependencies() -> None:  # pragma: no cover - Windows helper
    missing = []
    for module, label in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            missing.append(label)
    if missing:
        raise SystemExit(
            dedent(
                """
                Missing dependencies detected: {packages}.
                Run setup_pmck_training.bat or install requirements.txt to continue.
                """
            ).strip().format(packages=", ".join(sorted(missing)))
        )


def _schema_out_of_date(engine, metadata) -> bool:
    """Return True when any declared table is missing or lacks columns."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables:
        return False

    for name, table in metadata.tables.items():
        if name not in existing_tables:
            return True
        declared_columns = {column.name for column in table.columns}
        actual_columns = {column_info["name"] for column_info in inspector.get_columns(name)}
        if not declared_columns.issubset(actual_columns):
            return True
    return False


def seed_database() -> bool:
    ensure_dependencies()
    from app.database import Base, engine, session_scope
    from app.seed import seed_demo

    schema_reset = False
    if _schema_out_of_date(engine, Base.metadata):
        print("Detected outdated database schema. Rebuilding tables...")
        Base.metadata.drop_all(bind=engine)
        schema_reset = True

    Base.metadata.create_all(bind=engine)
    with session_scope() as session:
        seeded = seed_demo(session)
        if schema_reset and not seeded:
            # If the database was reset we expect fresh data; force a seed.
            seeded = seed_demo(session)
        return seeded


def run_health_check() -> None:
    ensure_dependencies()
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")
    if response.status_code != 200:
        raise SystemExit("/health check failed")
    print("Health endpoint OK")


def launch_server(open_browser: bool = True) -> None:
    ensure_dependencies()
    from app.services import find_available_port
    import uvicorn

    port = find_available_port(3000)
    url = f"http://127.0.0.1:{port}/"
    print("PMCK Training LMS starting...")
    print(f"Visit {url} to begin.")
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    if open_browser:
        time.sleep(0.5)
        webbrowser.open(url)
    server.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="PMCK Training LMS helper")
    parser.add_argument("--seed-only", action="store_true", help="Seed the database and exit")
    parser.add_argument("--health-check", action="store_true", help="Run /health check and exit")
    args = parser.parse_args()

    if args.health_check:
        run_health_check()
        return
    seeded = seed_database()
    if args.seed_only:
        print("Database seeded." if seeded else "Database already populated.")
        return
    launch_server(open_browser=True)


if __name__ == "__main__":
    main()
