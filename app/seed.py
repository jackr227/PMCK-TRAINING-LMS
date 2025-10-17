from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    AreaManagerStore,
    AssignmentTarget,
    Brand,
    Course,
    CourseAssignment,
    CourseVisibility,
    Enrollment,
    Flag,
    Lesson,
    MembershipStatus,
    Module,
    Store,
    StoreMembership,
    StoreRole,
    User,
    UserFlag,
    UserRole,
)
from .security import hash_password
from .services import apply_course_audience


BRANDS: List[Dict[str, str]] = [
    {
        "slug": "bossa",
        "display_name": "Bossa",
        "primary": "#000000",
        "secondary": "#c9a227",
        "accent": "#ffd369",
        "background": "#111111",
        "text": "#ffffff",
        "emoji": "🥂",
        "greeting": "Bossa welcomes you",
        "cta": "Pour the good times",
    },
    {
        "slug": "spur",
        "display_name": "Spur",
        "primary": "#000000",
        "secondary": "#c62828",
        "accent": "#ff8a80",
        "background": "#151515",
        "text": "#ffffff",
        "emoji": "🤠",
        "greeting": "Howdy from Spur",
        "cta": "Ride to training",
    },
    {
        "slug": "john-dorys",
        "display_name": "John Dory's",
        "primary": "#000000",
        "secondary": "#1565c0",
        "accent": "#64b5f6",
        "background": "#101722",
        "text": "#ffffff",
        "emoji": "🐟",
        "greeting": "Dive in with John Dory's",
        "cta": "Cast off",
    },
    {
        "slug": "rocomamas",
        "display_name": "RocoMamas",
        "primary": "#000000",
        "secondary": "#ff6f00",
        "accent": "#ffab40",
        "background": "#14100b",
        "text": "#ffffff",
        "emoji": "🍔",
        "greeting": "RocoMamas says smash it",
        "cta": "Let's cook",
    },
    {
        "slug": "panarottis",
        "display_name": "Panarottis",
        "primary": "#000000",
        "secondary": "#2e7d32",
        "accent": "#81c784",
        "background": "#101a12",
        "text": "#ffffff",
        "emoji": "🍕",
        "greeting": "Panarottis plates are ready",
        "cta": "Spin up training",
    },
    {
        "slug": "jackson-black",
        "display_name": "Jackson & Black",
        "primary": "#000000",
        "secondary": "#e0e0e0",
        "accent": "#fafafa",
        "background": "#000000",
        "text": "#ffffff",
        "emoji": "🥩",
        "greeting": "Jackson & Black",
        "cta": "Sharpen the knives",
    },
]


def seed_demo(session: Session) -> bool:
    brand_count = session.scalar(select(func.count(Brand.id)))
    if brand_count and brand_count > 0:
        return False

    super_admin = User(
        first_name="Super",
        last_name="Admin",
        display_name="PMCK Super Admin",
        email="super.admin@pmck.training",
        password_hash=hash_password("Password123!"),
        role=UserRole.SUPER_ADMIN,
        disabled=False,
        must_change_password=False,
    )
    session.add(super_admin)
    session.flush()

    for brand_index, meta in enumerate(BRANDS, start=1):
        brand = Brand(
            slug=meta["slug"],
            display_name=meta["display_name"],
            primary_color=meta["primary"],
            secondary_color=meta["secondary"],
            accent_color=meta["accent"],
            background_color=meta["background"],
            text_color=meta["text"],
            emoji=meta["emoji"],
            tone_greeting=meta["greeting"],
            tone_cta=meta["cta"],
            border_radius="14px",
        )
        session.add(brand)
        session.flush()

        stores = []
        for idx in range(1, 4):
            store = Store(
                brand_id=brand.id,
                name=f"{brand.slug}-store-{idx}",
                display_name=f"{brand.display_name} Store {idx}",
                code=f"{brand.slug[:3].upper()}-{idx:02d}",
                region=["Gauteng", "Western Cape", "KZN"][idx - 1],
            )
            session.add(store)
            session.flush()
            stores.append(store)

        flags = []
        for flag_name in ["Student", "Kitchen"]:
            flag = Flag(brand_id=brand.id, name=flag_name)
            session.add(flag)
            session.flush()
            flags.append(flag)

        admin = User(
            first_name="Brand",
            last_name="Admin",
            display_name=f"{brand.display_name} Admin",
            email=f"admin@{brand.slug}.local",
            password_hash=hash_password("Password123!"),
            role=UserRole.ADMIN,
            brand_id=brand.id,
        )
        area_manager = User(
            first_name="Area",
            last_name="Manager",
            display_name=f"{brand.display_name} Area Manager",
            email=f"area@{brand.slug}.local",
            password_hash=hash_password("Password123!"),
            role=UserRole.AREA_MANAGER,
            brand_id=brand.id,
        )
        operator = User(
            first_name="Store",
            last_name="Operator",
            display_name=f"{brand.display_name} Operator",
            email=f"operator@{brand.slug}.local",
            password_hash=hash_password("Password123!"),
            role=UserRole.OPERATOR,
            brand_id=brand.id,
        )
        trainer = User(
            first_name="Lead",
            last_name="Trainer",
            display_name=f"{brand.display_name} Trainer",
            email=f"trainer@{brand.slug}.local",
            password_hash=hash_password("Password123!"),
            role=UserRole.TRAINER,
            brand_id=brand.id,
        )
        trainee = User(
            first_name="New",
            last_name="Starter",
            display_name=f"{brand.display_name} Trainee",
            email=f"trainee@{brand.slug}.local",
            password_hash=hash_password("Password123!"),
            role=UserRole.TRAINEE,
            brand_id=brand.id,
        )
        session.add_all([admin, area_manager, operator, trainer, trainee])
        session.flush()

        session.add_all(
            [
                AreaManagerStore(user_id=area_manager.id, store_id=stores[0].id),
                AreaManagerStore(user_id=area_manager.id, store_id=stores[1].id),
            ]
        )

        session.add_all(
            [
                StoreMembership(
                    user_id=operator.id,
                    store_id=stores[0].id,
                    role=StoreRole.OPERATOR,
                    status=MembershipStatus.ACTIVE,
                ),
                StoreMembership(
                    user_id=trainer.id,
                    store_id=stores[0].id,
                    role=StoreRole.TRAINER,
                    status=MembershipStatus.ACTIVE,
                ),
                StoreMembership(
                    user_id=trainee.id,
                    store_id=stores[0].id,
                    role=StoreRole.TRAINEE,
                    status=MembershipStatus.PENDING,
                ),
            ]
        )
        session.add(UserFlag(user_id=trainee.id, flag_id=flags[0].id))

        # Local course owned by operator
        local_course = Course(
            title=f"{brand.display_name} Local SOP",
            summary="Store-level procedures",
            description="Step through the daily checklist for this store.",
            brand_id=brand.id,
            visibility=CourseVisibility.LOCAL,
            owner_user_id=operator.id,
            owner_role=UserRole.OPERATOR,
            owner_brand_id=brand.id,
            required_default=True,
            published_at=datetime.utcnow(),
        )
        session.add(local_course)
        session.flush()
        module = Module(course_id=local_course.id, title="Daily Routine", order_index=1)
        session.add(module)
        session.flush()
        session.add_all(
            [
                Lesson(module_id=module.id, title="Opening", content="Unlock and prep", order_index=1),
                Lesson(module_id=module.id, title="Closing", content="Secure store", order_index=2),
            ]
        )
        local_course.assignments.append(
            CourseAssignment(
                course_id=local_course.id,
                target_type=AssignmentTarget.STORE,
                target_id=str(stores[0].id),
                required=True,
            )
        )

        # Brand global course owned by admin
        brand_course = Course(
            title=f"{brand.display_name} Brand Standards",
            summary="Brand-level expectations",
            description="Hospitality standards for the brand.",
            brand_id=brand.id,
            visibility=CourseVisibility.GLOBAL,
            owner_user_id=admin.id,
            owner_role=UserRole.ADMIN,
            owner_brand_id=brand.id,
            required_default=True,
            published_at=datetime.utcnow(),
        )
        session.add(brand_course)
        session.flush()
        module2 = Module(course_id=brand_course.id, title="Brand Story", order_index=1)
        session.add(module2)
        session.flush()
        session.add(Lesson(module_id=module2.id, title="Our Story", content="History and mission", order_index=1))
        brand_course.assignments.append(
            CourseAssignment(
                course_id=brand_course.id,
                target_type=AssignmentTarget.BRAND,
                target_id=str(brand.id),
                required=True,
            )
        )

        apply_course_audience(session, local_course)
        apply_course_audience(session, brand_course)

        # Mark some progress
        for enrollment in local_course.enrollments:
            if enrollment.user_id == trainer.id:
                enrollment.completed = True
                enrollment.completed_at = datetime.utcnow() - timedelta(days=2)
        for enrollment in brand_course.enrollments:
            if enrollment.user_id == admin.id:
                enrollment.completed = True
                enrollment.completed_at = datetime.utcnow() - timedelta(days=5)

    # Super global course
    global_course = Course(
        title="PMCK Global Safety",
        summary="Cross-brand safety training",
        description="Required health and safety standards.",
        brand_id=None,
        visibility=CourseVisibility.GLOBAL,
        owner_user_id=super_admin.id,
        owner_role=UserRole.SUPER_ADMIN,
        owner_brand_id=None,
        required_default=True,
        published_at=datetime.utcnow(),
    )
    session.add(global_course)
    session.flush()
    module = Module(course_id=global_course.id, title="Safety Essentials", order_index=1)
    session.add(module)
    session.flush()
    session.add(Lesson(module_id=module.id, title="Fire Safety", content="Follow evacuation plan", order_index=1))

    for brand in session.scalars(select(Brand)).all():
        global_course.assignments.append(
            CourseAssignment(
                course_id=global_course.id,
                target_type=AssignmentTarget.BRAND,
                target_id=str(brand.id),
                required=True,
            )
        )
    apply_course_audience(session, global_course)

    return True
