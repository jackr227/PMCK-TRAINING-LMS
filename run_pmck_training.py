"""PMCK Training LMS demo launcher.

Run this file with `python run_pmck_training.py` to seed a demo dataset and start
an API server powered by FastAPI + SQLite. The script creates helpful demo data
only the first time you launch it.
"""

from __future__ import annotations

from datetime import date
from textwrap import dedent

import uvicorn
from sqlalchemy import select

from app.database import Base, engine, session_scope
from app.models import (
    AssignmentStatus,
    AudienceDimension,
    AuditLog,
    Brand,
    Course,
    CourseAudienceRule,
    CourseAudienceRuleType,
    CourseModule,
    CourseType,
    CourseAssignment,
    Flag,
    Lesson,
    MembershipStatus,
    Store,
    StoreMembership,
    User,
    UserFlag,
    UserRole,
)


SUPER_ADMIN_EMAIL = "super.admin@pmck.training"


def bootstrap_demo_data() -> bool:
    """Create the SQLite schema and seed a guided walkthrough dataset.

    Returns True if demo data was created on this run, False if the database already
    contained the seed accounts.
    """
    Base.metadata.create_all(bind=engine)

    with session_scope() as session:
        existing = session.scalars(select(User.id).where(User.email == SUPER_ADMIN_EMAIL)).first()
        if existing:
            return False

        brand = Brand(
            name="PMCK Coffee",
            theme_primary_color="#D97706",
            theme_secondary_color="#92400E",
            tone="Warm, energising, and barista-friendly",
            logo_url="https://example.com/pmck-coffee-logo.png",
        )
        session.add(brand)
        session.flush()

        downtown_store = Store(
            brand_id=brand.id,
            name="PMCK Coffee — Downtown",
            code="PMCK-DT",
            region="Metro",
        )
        uptown_store = Store(
            brand_id=brand.id,
            name="PMCK Coffee — Uptown",
            code="PMCK-UT",
            region="Metro",
        )
        session.add_all([downtown_store, uptown_store])
        session.flush()

        super_admin = User(
            id=1,
            first_name="Super",
            last_name="Admin",
            display_name="Super Admin",
            email=SUPER_ADMIN_EMAIL,
            role=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        brand_admin = User(
            id=2,
            brand_id=brand.id,
            first_name="Avery",
            last_name="Admin",
            display_name="Avery (Brand Admin)",
            email="avery.admin@pmck.training",
            role=UserRole.ADMIN,
            is_active=True,
        )
        area_manager = User(
            id=3,
            brand_id=brand.id,
            first_name="Morgan",
            last_name="Area",
            display_name="Morgan (Area Manager)",
            email="morgan.area@pmck.training",
            role=UserRole.AREA_MANAGER,
            is_active=True,
        )
        operator = User(
            id=4,
            brand_id=brand.id,
            first_name="Riley",
            last_name="Operator",
            display_name="Riley (Operator)",
            email="riley.operator@pmck.training",
            role=UserRole.OPERATOR,
            is_active=True,
        )
        trainer = User(
            id=5,
            brand_id=brand.id,
            first_name="Jordan",
            last_name="Trainer",
            display_name="Jordan (Trainer)",
            email="jordan.trainer@pmck.training",
            role=UserRole.TRAINER,
            is_active=True,
        )
        trainee = User(
            id=6,
            brand_id=brand.id,
            first_name="Casey",
            last_name="Trainee",
            display_name="Casey (Trainee)",
            email="casey.trainee@pmck.training",
            role=UserRole.TRAINEE,
            is_active=True,
        )
        session.add_all([super_admin, brand_admin, area_manager, operator, trainer, trainee])
        session.flush()

        memberships = [
            StoreMembership(
                user_id=area_manager.id,
                store_id=downtown_store.id,
                role=UserRole.AREA_MANAGER,
                status=MembershipStatus.ACTIVE,
            ),
            StoreMembership(
                user_id=area_manager.id,
                store_id=uptown_store.id,
                role=UserRole.AREA_MANAGER,
                status=MembershipStatus.ACTIVE,
            ),
            StoreMembership(
                user_id=operator.id,
                store_id=downtown_store.id,
                role=UserRole.OPERATOR,
                status=MembershipStatus.ACTIVE,
            ),
            StoreMembership(
                user_id=trainer.id,
                store_id=downtown_store.id,
                role=UserRole.TRAINER,
                status=MembershipStatus.ACTIVE,
            ),
            StoreMembership(
                user_id=trainee.id,
                store_id=downtown_store.id,
                role=UserRole.TRAINEE,
                status=MembershipStatus.ACTIVE,
            ),
        ]
        session.add_all(memberships)

        kitchen_flag = Flag(name="Kitchen")
        session.add(kitchen_flag)
        session.flush()
        session.add(UserFlag(user_id=trainee.id, flag_id=kitchen_flag.id))

        global_course = Course(
            title="Global Onboarding",
            summary="Orientation for all PMCK team members across every store.",
            brand_id=brand.id,
            course_type=CourseType.GLOBAL,
            creator_id=super_admin.id,
            required=True,
            due_date=date.today(),
            notify_on_publish=True,
        )
        local_course = Course(
            title="Downtown Espresso SOP",
            summary="Dial-in steps and cleaning checklist for the downtown espresso bar.",
            brand_id=brand.id,
            course_type=CourseType.LOCAL,
            creator_id=trainer.id,
            required=True,
            due_date=date.today(),
        )
        session.add_all([global_course, local_course])
        session.flush()

        global_module = CourseModule(course_id=global_course.id, title="Welcome to PMCK", order_index=1)
        global_lesson = Lesson(
            module_id=global_module.id,
            title="Our Promise",
            content="We deliver consistent hospitality with local flair across every PMCK brand.",
            order_index=1,
        )
        local_module = CourseModule(course_id=local_course.id, title="Machine Prep", order_index=1)
        local_lesson = Lesson(
            module_id=local_module.id,
            title="Dial-In Checklist",
            content="Purge the group head, weigh the dose, time the shot, and log the results.",
            order_index=1,
        )
        session.add_all([global_module, global_lesson, local_module, local_lesson])

        local_course.audience_rules.append(
            CourseAudienceRule(
                rule_type=CourseAudienceRuleType.INCLUDE,
                dimension=AudienceDimension.STORE,
                value=str(downtown_store.id),
            )
        )

        local_assignment = CourseAssignment(
            course_id=local_course.id,
            user_id=trainee.id,
            status=AssignmentStatus.ASSIGNED,
            required=True,
            due_date=date.today(),
        )
        global_assignment = CourseAssignment(
            course_id=global_course.id,
            user_id=trainee.id,
            status=AssignmentStatus.IN_PROGRESS,
            required=True,
            due_date=date.today(),
        )
        session.add_all([local_assignment, global_assignment])

        session.add(
            AuditLog(
                actor_id=super_admin.id,
                action="seed_demo",
                entity_type="system",
                entity_id=0,
                details="Initial demo dataset created by run_pmck_training.py",
            )
        )

    return True


def print_instructions() -> None:
    message = dedent(
        """
        PMCK Training LMS demo server is starting on http://127.0.0.1:8000

        Sign in by supplying the X-User-Id header in requests or inside the Swagger UI.
        Demo accounts:
          • 1 — Super Admin (cross-brand control)
          • 2 — Brand Admin (brand-scoped)
          • 3 — Area Manager (two stores)
          • 4 — Operator (Downtown store)
          • 5 — Trainer (Downtown store)
          • 6 — Trainee (Downtown store)

        Useful endpoints once the server is running:
          GET  /brands              – list available brands
          GET  /stores              – list stores you can see
          GET  /courses             – courses within your scope
          POST /courses/{id}/assign – assign a course (Operator/Trainer scope)

        For a quick test, try:
          curl -H "X-User-Id: 1" http://127.0.0.1:8000/brands
          curl -H "X-User-Id: 4" http://127.0.0.1:8000/courses

        Interactive docs are at http://127.0.0.1:8000/docs
        Press Ctrl+C in this window to stop the server.
        """
    ).strip()
    print(message)


if __name__ == "__main__":
    seeded = bootstrap_demo_data()
    if seeded:
        print("Created pmck_training.db with demo brands, stores, users, and courses.")
    else:
        print("Found existing pmck_training.db demo data – skipping reseed.")
    print_instructions()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
