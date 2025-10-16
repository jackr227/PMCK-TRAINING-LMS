from __future__ import annotations

from datetime import date
from typing import Iterable, List

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_session
from .models import (
    AssignmentStatus,
    AudienceDimension,
    AuditLog,
    Brand,
    Course,
    CourseAudienceRule,
    CourseModule,
    CourseType,
    CourseAssignment,
    Flag,
    Lesson,
    Store,
    StoreMembership,
    User,
    UserFlag,
    UserRole,
    MembershipStatus,
)
from .schemas import (
    AssignmentCreate,
    AssignmentRead,
    BrandCreate,
    BrandRead,
    CourseCreate,
    CourseRead,
    FlagCreate,
    FlagRead,
    ModuleCreate,
    StoreCreate,
    StoreRead,
    UserCreate,
    UserRead,
)

app = FastAPI(title="PMCK Training LMS")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


# ----------------------------
# Dependencies & utilities
# ----------------------------

def get_current_user(
    session: Session = Depends(get_session),
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
) -> User:
    if x_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header")
    user = session.get(User, x_user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def get_brand_scope(user: User, session: Session) -> List[int]:
    if user.role == UserRole.SUPER_ADMIN:
        brand_ids = session.scalars(select(Brand.id)).all()
        return brand_ids
    if user.role == UserRole.ADMIN:
        return [user.brand_id] if user.brand_id else []
    brand_ids = {
        membership.store.brand_id for membership in user.memberships if membership.store is not None
    }
    if user.brand_id:
        brand_ids.add(user.brand_id)
    return list(brand_ids)


def get_store_scope(user: User, session: Session) -> List[int]:
    if user.role == UserRole.SUPER_ADMIN:
        return session.scalars(select(Store.id)).all()
    if user.role == UserRole.ADMIN:
        if not user.brand_id:
            return []
        return session.scalars(select(Store.id).where(Store.brand_id == user.brand_id)).all()
    return [membership.store_id for membership in user.memberships]


def ensure_brand_permission(actor: User, brand_id: int | None, session: Session) -> None:
    if brand_id is None:
        return
    if actor.role == UserRole.SUPER_ADMIN:
        return
    if actor.role == UserRole.ADMIN:
        if actor.brand_id != brand_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand outside admin scope")
    else:
        store_brands = {membership.store.brand_id for membership in actor.memberships if membership.store is not None}
        if brand_id not in store_brands:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand outside store scope")


def ensure_store_permission(actor: User, store_ids: Iterable[int], session: Session) -> None:
    allowed_store_ids = set(get_store_scope(actor, session))
    missing = set(store_ids) - allowed_store_ids
    if missing:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Stores outside scope: {sorted(missing)}")


def ensure_can_create_role(actor: User, target_role: UserRole) -> None:
    if actor.role == UserRole.SUPER_ADMIN:
        return
    if actor.role == UserRole.ADMIN:
        if target_role == UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create super admins")
        return
    if actor.role == UserRole.AREA_MANAGER:
        if target_role not in {UserRole.OPERATOR, UserRole.TRAINER, UserRole.TRAINEE}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Area Manager cannot create this role")
        return
    if actor.role == UserRole.OPERATOR:
        if target_role not in {UserRole.TRAINER, UserRole.TRAINEE}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator cannot create this role")
        return
    if actor.role == UserRole.TRAINER:
        if target_role != UserRole.TRAINEE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trainer can only create trainees")
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to create users")


def log_action(
    session: Session,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: int,
    details: str | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    session.add(entry)


# ----------------------------
# Brand endpoints
# ----------------------------


@app.post("/brands", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
def create_brand(
    payload: BrandCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> Brand:
    if actor.role not in {UserRole.SUPER_ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can create brands")
    brand = Brand(**payload.dict())
    session.add(brand)
    session.flush()
    log_action(session, actor, "create", "brand", brand.id, details=brand.name)
    return brand


@app.get("/brands", response_model=List[BrandRead])
def list_brands(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[Brand]:
    brand_ids = get_brand_scope(actor, session)
    if not brand_ids and actor.role != UserRole.SUPER_ADMIN:
        return []
    query = select(Brand)
    if actor.role != UserRole.SUPER_ADMIN:
        query = query.where(Brand.id.in_(brand_ids))
    return session.scalars(query).all()


# ----------------------------
# Store endpoints
# ----------------------------


@app.post("/stores", response_model=StoreRead, status_code=status.HTTP_201_CREATED)
def create_store(
    payload: StoreCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> Store:
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to create stores")
    ensure_brand_permission(actor, payload.brand_id, session)
    store = Store(**payload.dict())
    session.add(store)
    session.flush()
    log_action(session, actor, "create", "store", store.id, details=store.name)
    return store


@app.get("/stores", response_model=List[StoreRead])
def list_stores(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[Store]:
    store_ids = get_store_scope(actor, session)
    if actor.role == UserRole.SUPER_ADMIN:
        return session.scalars(select(Store)).all()
    if not store_ids:
        return []
    return session.scalars(select(Store).where(Store.id.in_(store_ids))).all()


# ----------------------------
# Flag endpoints
# ----------------------------


@app.post("/flags", response_model=FlagRead, status_code=status.HTTP_201_CREATED)
def create_flag(
    payload: FlagCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> Flag:
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can manage flags")
    flag = Flag(**payload.dict())
    session.add(flag)
    session.flush()
    log_action(session, actor, "create", "flag", flag.id, details=flag.name)
    return flag


@app.get("/flags", response_model=List[FlagRead])
def list_flags(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[Flag]:
    return session.scalars(select(Flag)).all()


# ----------------------------
# User endpoints
# ----------------------------


def attach_memberships(
    session: Session,
    user: User,
    memberships_payload: List[dict],
    actor: User,
) -> None:
    if not memberships_payload:
        return
    store_ids = [item["store_id"] for item in memberships_payload]
    ensure_store_permission(actor, store_ids, session)
    for item in memberships_payload:
        membership = StoreMembership(
            user=user,
            store_id=item["store_id"],
            role=item["role"],
            status=item.get("status") or MembershipStatus.PENDING,
        )
        session.add(membership)


def attach_flags(session: Session, user: User, flag_ids: Iterable[int]) -> None:
    if not flag_ids:
        return
    flags = session.scalars(select(Flag).where(Flag.id.in_(flag_ids))).all()
    for flag in flags:
        session.add(UserFlag(user=user, flag=flag))


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> User:
    ensure_can_create_role(actor, payload.role)
    ensure_brand_permission(actor, payload.brand_id, session)
    user = User(**payload.dict(exclude={"memberships", "flag_ids"}))
    session.add(user)
    session.flush()
    attach_memberships(session, user, [m.dict() for m in payload.memberships], actor)
    attach_flags(session, user, payload.flag_ids)
    log_action(session, actor, "create", "user", user.id, details=user.email)
    session.refresh(user)
    return user


@app.get("/users", response_model=List[UserRead])
def list_users(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[User]:
    if actor.role == UserRole.SUPER_ADMIN:
        return session.scalars(select(User)).all()
    brand_ids = get_brand_scope(actor, session)
    store_ids = get_store_scope(actor, session)
    query = select(User).distinct()
    if brand_ids:
        query = query.where((User.brand_id.in_(brand_ids)) | (User.brand_id.is_(None)))
    if store_ids:
        query = query.join(User.memberships, isouter=True).where(
            (StoreMembership.store_id.in_(store_ids)) | (StoreMembership.store_id.is_(None))
        )
    return session.scalars(query).all()


@app.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if actor.role == UserRole.SUPER_ADMIN:
        return user
    brand_ids = get_brand_scope(actor, session)
    store_ids = set(get_store_scope(actor, session))
    user_store_ids = {m.store_id for m in user.memberships}
    if user.brand_id and user.brand_id in brand_ids:
        return user
    if store_ids & user_store_ids:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User outside scope")


# ----------------------------
# Course helpers
# ----------------------------


def ensure_course_permission(actor: User, payload: CourseCreate, session: Session) -> None:
    if payload.course_type == CourseType.GLOBAL and actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create global courses")
    if payload.course_type == CourseType.LOCAL and actor.role not in {
        UserRole.ADMIN,
        UserRole.OPERATOR,
        UserRole.TRAINER,
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role cannot create local courses")
    if payload.brand_id:
        ensure_brand_permission(actor, payload.brand_id, session)


def ensure_audience_scope(actor: User, payload: CourseCreate, session: Session) -> None:
    allowed_brand_ids = set(get_brand_scope(actor, session))
    allowed_store_ids = set(get_store_scope(actor, session))
    for rule in payload.audience_rules:
        if rule.dimension == AudienceDimension.BRAND and rule.value not in {"*"}:
            brand_id = int(rule.value)
            if actor.role != UserRole.SUPER_ADMIN and brand_id not in allowed_brand_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audience brand outside scope")
        if rule.dimension == AudienceDimension.STORE:
            store_id = int(rule.value)
            if actor.role != UserRole.SUPER_ADMIN and store_id not in allowed_store_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audience store outside scope")


def create_course_modules(session: Session, course: Course, modules: List[ModuleCreate]) -> None:
    for module_payload in modules:
        module = CourseModule(
            course=course,
            title=module_payload.title,
            order_index=module_payload.order_index,
        )
        session.add(module)
        session.flush()
        for lesson_payload in module_payload.lessons:
            lesson = Lesson(
                module=module,
                title=lesson_payload.title,
                content=lesson_payload.content,
                order_index=lesson_payload.order_index,
            )
            session.add(lesson)


def create_audience_rules(session: Session, course: Course, rules_payload) -> None:
    for rule in rules_payload:
        session.add(
            CourseAudienceRule(
                course=course,
                rule_type=rule.rule_type,
                dimension=rule.dimension,
                value=rule.value,
            )
        )


@app.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> Course:
    ensure_course_permission(actor, payload, session)
    ensure_audience_scope(actor, payload, session)
    course = Course(
        title=payload.title,
        summary=payload.summary,
        brand_id=payload.brand_id,
        course_type=payload.course_type,
        creator_id=actor.id,
        required=payload.required,
        due_date=payload.due_date,
        notify_on_publish=payload.notify_on_publish,
    )
    session.add(course)
    session.flush()
    create_course_modules(session, course, payload.modules)
    create_audience_rules(session, course, payload.audience_rules)
    log_action(session, actor, "create", "course", course.id, details=course.title)
    session.refresh(course)
    return course


@app.get("/courses", response_model=List[CourseRead])
def list_courses(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[Course]:
    query = select(Course)
    if actor.role == UserRole.SUPER_ADMIN:
        return session.scalars(query).all()
    brand_ids = get_brand_scope(actor, session)
    store_ids = set(get_store_scope(actor, session))
    if brand_ids:
        query = query.where((Course.brand_id.in_(brand_ids)) | (Course.brand_id.is_(None)))
    courses = session.scalars(query).all()
    visible_courses = []
    for course in courses:
        if not course.audience_rules:
            visible_courses.append(course)
            continue
        if any(
            rule.dimension == AudienceDimension.STORE and int(rule.value) in store_ids
            for rule in course.audience_rules
        ):
            visible_courses.append(course)
            continue
        if actor.brand_id and any(
            rule.dimension == AudienceDimension.BRAND and int(rule.value) == actor.brand_id
            for rule in course.audience_rules
        ):
            visible_courses.append(course)
    return visible_courses


# ----------------------------
# Assignments & Progress
# ----------------------------


def calculate_assignment_status(due_date: date | None, completed: bool) -> AssignmentStatus:
    if completed:
        return AssignmentStatus.COMPLETED
    if due_date and due_date < date.today():
        return AssignmentStatus.OVERDUE
    return AssignmentStatus.ASSIGNED


@app.post("/courses/{course_id}/assignments", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(
    course_id: int,
    payload: AssignmentCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> AssignmentRead:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR, UserRole.TRAINER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to assign courses")
    ensure_brand_permission(actor, course.brand_id, session)
    target_user = session.get(User, payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")
    ensure_store_permission(actor, [m.store_id for m in target_user.memberships], session)
    existing = session.scalars(
        select(CourseAssignment)
        .where(CourseAssignment.course_id == course_id)
        .where(CourseAssignment.user_id == payload.user_id)
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Assignment already exists")
    assignment = CourseAssignment(
        course_id=course_id,
        user_id=payload.user_id,
        due_date=payload.due_date,
        required=payload.required,
        status=calculate_assignment_status(payload.due_date, False),
    )
    session.add(assignment)
    log_action(session, actor, "assign", "course", course_id, details=f"user={payload.user_id}")
    session.flush()
    return assignment


@app.get("/courses/{course_id}/assignments", response_model=List[AssignmentRead])
def list_assignments(
    course_id: int,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[AssignmentRead]:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if actor.role == UserRole.SUPER_ADMIN:
        return course.assignments
    brand_ids = get_brand_scope(actor, session)
    if course.brand_id and course.brand_id not in brand_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course outside scope")
    store_ids = set(get_store_scope(actor, session))
    visible_assignments = []
    for assignment in course.assignments:
        user_store_ids = {m.store_id for m in assignment.user.memberships}
        if store_ids & user_store_ids:
            visible_assignments.append(assignment)
    return visible_assignments


@app.get("/audit", response_model=List[str])
def list_audit_entries(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> List[str]:
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit requires admin access")
    query = select(AuditLog)
    if actor.role == UserRole.ADMIN:
        brand_ids = get_brand_scope(actor, session)
        user_ids = session.scalars(select(User.id).where(User.brand_id.in_(brand_ids))).all()
        query = query.where(AuditLog.actor_id.in_(user_ids))
    entries = session.scalars(query.order_by(AuditLog.created_at.desc())).all()
    return [
        f"{entry.created_at.isoformat()} :: user={entry.actor_id} :: {entry.action} {entry.entity_type}#{entry.entity_id}"
        for entry in entries
    ]
