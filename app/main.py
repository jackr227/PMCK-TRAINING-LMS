from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

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

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["UserRole"] = UserRole
templates.env.globals["AssignmentStatus"] = AssignmentStatus
templates.env.globals["CourseType"] = CourseType

app.add_middleware(SessionMiddleware, secret_key="pmck-training-demo-ui")


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
# UI helpers
# ----------------------------


def set_flash(request: Request, category: str, message: str) -> None:
    request.session["_flash"] = {"category": category, "message": message}


def pop_flash(request: Request) -> Optional[Dict[str, str]]:
    flash = request.session.get("_flash")
    if flash:
        request.session.pop("_flash")
    return flash


def get_ui_user(request: Request, session: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = session.get(User, user_id)
    if not user or not user.is_active:
        request.session.pop("user_id", None)
        return None
    return user


def get_ui_brand_context(
    request: Request, user: User, session: Session
) -> Dict[str, Optional[Brand]]:
    brand_scope_ids = get_brand_scope(user, session)
    available_brands: List[Brand] = []
    if brand_scope_ids:
        available_brands = list(
            session.scalars(select(Brand).where(Brand.id.in_(brand_scope_ids))).all()
        )
    else:
        if user.role == UserRole.SUPER_ADMIN:
            available_brands = list(session.scalars(select(Brand)).all())
    brand_lookup = {brand.id: brand for brand in available_brands}
    preferred_brand_id = request.session.get("brand_id")
    active_brand: Optional[Brand] = None
    if preferred_brand_id:
        active_brand = brand_lookup.get(preferred_brand_id)
        if active_brand is None and preferred_brand_id:
            request.session.pop("brand_id", None)
    if active_brand is None:
        if user.brand_id and user.brand_id in brand_lookup:
            active_brand = brand_lookup[user.brand_id]
        elif available_brands:
            active_brand = available_brands[0]

    return {
        "active_brand": active_brand,
        "available_brands": available_brands,
    }


def build_layout_context(
    request: Request, session: Session, user: User, *, current_path: str
) -> Dict[str, object]:
    brand_context = get_ui_brand_context(request, user, session)
    flash = pop_flash(request)
    return {
        "request": request,
        "active_user": user,
        "active_brand": brand_context.get("active_brand"),
        "available_brands": brand_context.get("available_brands", []),
        "flash": flash,
        "current_path": current_path,
    }


def users_in_scope(user: User, session: Session) -> List[User]:
    if user.role == UserRole.SUPER_ADMIN:
        return list(session.scalars(select(User).where(User.is_active.is_(True))).all())
    if user.role == UserRole.ADMIN:
        if not user.brand_id:
            return []
        return list(
            session.scalars(
                select(User).where(User.brand_id == user.brand_id, User.is_active.is_(True))
            ).all()
        )
    store_ids = get_store_scope(user, session)
    if not store_ids:
        return [user]
    user_query = (
        select(User)
        .join(StoreMembership, StoreMembership.user_id == User.id)
        .where(StoreMembership.store_id.in_(store_ids), User.is_active.is_(True))
        .distinct()
    )
    return list(session.scalars(user_query).all())


# ----------------------------
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


# ----------------------------
# Browser-based UI
# ----------------------------


@app.get("/", response_class=HTMLResponse)
def login_page(request: Request, session: Session = Depends(get_session)):
    user = get_ui_user(request, session)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    brands = list(session.scalars(select(Brand).order_by(Brand.name)).all())
    users = list(
        session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.role, User.display_name))
        .all()
    )
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "brands": brands,
            "users": users,
        },
    )


@app.post("/ui/login")
def ui_login(
    request: Request,
    session: Session = Depends(get_session),
    user_id: int = Form(...),
    brand_id: Optional[int] = Form(default=None),
):
    user = session.get(User, user_id)
    if not user or not user.is_active:
        set_flash(request, "error", "That account is not available. Try another user.")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    request.session["user_id"] = user.id
    request.session.pop("brand_id", None)
    if brand_id:
        try:
            ensure_brand_permission(user, brand_id, session)
        except HTTPException:
            set_flash(request, "error", "You cannot open that brand. Pick one you manage.")
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        request.session["brand_id"] = brand_id
    set_flash(request, "success", f"Welcome back, {user.display_name or user.first_name}!")
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
def ui_logout(request: Request) -> RedirectResponse:
    request.session.pop("user_id", None)
    request.session.pop("brand_id", None)
    set_flash(request, "success", "Signed out successfully.")
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/ui/brand/switch")
def switch_brand(
    request: Request,
    session: Session = Depends(get_session),
    brand_id: int = Form(...),
):
    user = get_ui_user(request, session)
    if not user:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    try:
        ensure_brand_permission(user, brand_id, session)
    except HTTPException:
        set_flash(request, "error", "Brand outside your scope.")
    else:
        request.session["brand_id"] = brand_id
        set_flash(request, "success", "Brand theme updated.")
    referer = request.headers.get("referer") or "/dashboard"
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


def ensure_ui_authenticated(
    request: Request, session: Session
) -> Optional[RedirectResponse]:
    user = get_ui_user(request, session)
    if not user:
        set_flash(request, "error", "Please choose a demo user to continue.")
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    request.state.active_user = user
    return None


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    context = build_layout_context(request, session, user, current_path="/dashboard")
    store_ids = get_store_scope(user, session)
    assignments = list(
        session.scalars(
            select(CourseAssignment).where(CourseAssignment.user_id == user.id)
        ).all()
    )
    pending_assignments = [a for a in assignments if a.status != AssignmentStatus.COMPLETED]
    completed_assignments = [a for a in assignments if a.status == AssignmentStatus.COMPLETED]
    required_assignments = [a for a in assignments if a.required]
    today = date.today()
    overdue_assignments = [
        assignment
        for assignment in pending_assignments
        if assignment.due_date and assignment.due_date < today
    ]
    due_window = today + timedelta(days=7)
    due_soon = sorted(
        [
            assignment
            for assignment in pending_assignments
            if assignment.due_date and today <= assignment.due_date <= due_window
        ],
        key=lambda a: a.due_date,
    )
    completion_rate = (
        int(round((len(completed_assignments) / len(assignments)) * 100))
        if assignments
        else 0
    )
    required_completion_rate = (
        int(
            round(
                (
                    len(
                        [
                            assignment
                            for assignment in required_assignments
                            if assignment.status == AssignmentStatus.COMPLETED
                        ]
                    )
                    / len(required_assignments)
                )
                * 100
            )
        )
        if required_assignments
        else 0
    )
    managed_users = users_in_scope(user, session)
    managed_user_ids = [member.id for member in managed_users]
    stores = []
    if store_ids:
        stores = list(session.scalars(select(Store).where(Store.id.in_(store_ids))).all())
    brand_context = get_ui_brand_context(request, user, session)
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        audit_query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
        audits = list(session.scalars(audit_query).all())
    else:
        audits = []
    team_assignments = []
    if managed_user_ids:
        team_assignments = list(
            session.scalars(
                select(CourseAssignment).where(CourseAssignment.user_id.in_(managed_user_ids))
            ).all()
        )
    team_total = len(team_assignments)
    team_completed = len([a for a in team_assignments if a.status == AssignmentStatus.COMPLETED])
    team_required_assignments = [assignment for assignment in team_assignments if assignment.required]
    team_completion_rate = int(round((team_completed / team_total) * 100)) if team_total else 0
    team_required_completion_rate = (
        int(
            round(
                (
                    len(
                        [
                            assignment
                            for assignment in team_required_assignments
                            if assignment.status == AssignmentStatus.COMPLETED
                        ]
                    )
                    / len(team_required_assignments)
                )
                * 100
            )
        )
        if team_required_assignments
        else 0
    )
    role_breakdown_counter = Counter(member.role for member in managed_users)
    role_breakdown = [
        {
            "label": role.value.replace("_", " ").title(),
            "count": count,
        }
        for role, count in sorted(
            role_breakdown_counter.items(), key=lambda item: (-item[1], item[0].value)
        )
    ]
    store_progress: List[Dict[str, object]] = []
    if stores:
        for store in stores:
            active_memberships = [
                membership
                for membership in store.memberships
                if membership.status == MembershipStatus.ACTIVE
            ]
            member_ids = [membership.user_id for membership in active_memberships]
            store_assignments = [
                assignment for assignment in team_assignments if assignment.user_id in member_ids
            ]
            completed = len(
                [assignment for assignment in store_assignments if assignment.status == AssignmentStatus.COMPLETED]
            )
            percent = int(
                round((completed / len(store_assignments)) * 100)
            ) if store_assignments else 0
            store_progress.append(
                {
                    "store": store,
                    "members": len(active_memberships),
                    "assignments": len(store_assignments),
                    "completed": completed,
                    "percent": percent,
                }
            )
    store_progress.sort(key=lambda entry: entry["percent"], reverse=True)
    context.update(
        {
            "pending_assignments": pending_assignments,
            "completed_assignments": completed_assignments,
            "required_assignments": required_assignments,
            "overdue_assignments": overdue_assignments,
            "due_soon_assignments": due_soon,
            "completion_rate": completion_rate,
            "required_completion_rate": required_completion_rate,
            "team_completion_rate": team_completion_rate,
            "team_required_completion_rate": team_required_completion_rate,
            "managed_users": managed_users,
            "stores": stores,
            "brand_context": brand_context,
            "audits": audits,
            "role_breakdown": role_breakdown,
            "store_progress": store_progress,
            "team_assignment_total": team_total,
            "team_required_total": len(team_required_assignments),
        }
    )
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/ui/brands", response_class=HTMLResponse)
def manage_brands(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        set_flash(request, "error", "Only admins can view brand settings.")
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    context = build_layout_context(request, session, user, current_path="/ui/brands")
    brand_query = select(Brand).order_by(Brand.name)
    if user.role == UserRole.ADMIN and user.brand_id:
        brand_query = brand_query.where(Brand.id == user.brand_id)
    brands = list(session.scalars(brand_query).all())
    brand_cards = [
        {
            "brand": brand,
            "store_total": len(brand.stores),
        }
        for brand in brands
    ]
    brand_stats = {
        "total_brands": len(brands),
        "total_stores": sum(card["store_total"] for card in brand_cards),
    }
    context.update({"brands": brands, "brand_cards": brand_cards, "brand_stats": brand_stats})
    return templates.TemplateResponse("brands.html", context)


@app.post("/ui/brands/create")
def create_brand_ui(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    theme_primary_color: Optional[str] = Form(default=None),
    theme_secondary_color: Optional[str] = Form(default=None),
    tone: Optional[str] = Form(default=None),
    logo_url: Optional[str] = Form(default=None),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    if user.role != UserRole.SUPER_ADMIN:
        set_flash(request, "error", "Only super admins can create brands.")
        return RedirectResponse("/ui/brands", status_code=status.HTTP_303_SEE_OTHER)
    brand = Brand(
        name=name.strip(),
        theme_primary_color=theme_primary_color or None,
        theme_secondary_color=theme_secondary_color or None,
        tone=tone or None,
        logo_url=logo_url or None,
    )
    session.add(brand)
    session.flush()
    log_action(session, user, "create", "brand", brand.id, details=f"UI created {brand.name}")
    session.commit()
    set_flash(request, "success", f"Brand '{brand.name}' created.")
    return RedirectResponse("/ui/brands", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/ui/stores", response_class=HTMLResponse)
def manage_stores(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    context = build_layout_context(request, session, user, current_path="/ui/stores")
    brand_context = get_ui_brand_context(request, user, session)
    active_brand: Optional[Brand] = brand_context.get("active_brand")  # type: ignore[assignment]
    store_ids = get_store_scope(user, session)
    store_query = select(Store)
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        if active_brand:
            store_query = store_query.where(Store.brand_id == active_brand.id)
    elif store_ids:
        store_query = store_query.where(Store.id.in_(store_ids))
    else:
        store_query = store_query.where(False)
    stores = list(session.scalars(store_query.order_by(Store.name)).all())
    region_counter = Counter((store.region or "Unassigned") for store in stores)
    region_summary = [
        {"region": region, "count": count}
        for region, count in sorted(region_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    store_cards = []
    for store in stores:
        active_memberships = [
            membership
            for membership in store.memberships
            if membership.status == MembershipStatus.ACTIVE
        ]
        role_counts = Counter(membership.role for membership in active_memberships)
        store_cards.append(
            {
                "store": store,
                "active_members": len(active_memberships),
                "role_breakdown": [
                    {
                        "label": role.value.replace("_", " ").title(),
                        "count": count,
                    }
                    for role, count in sorted(
                        role_counts.items(), key=lambda item: (-item[1], item[0].value)
                    )
                ],
            }
        )
    context.update(
        {
            "stores": stores,
            "active_brand": active_brand,
            "store_cards": store_cards,
            "region_summary": region_summary,
        }
    )
    return templates.TemplateResponse("stores.html", context)


@app.post("/ui/stores/create")
def create_store_ui(
    request: Request,
    session: Session = Depends(get_session),
    name: str = Form(...),
    code: str = Form(...),
    region: Optional[str] = Form(default=None),
    brand_id: Optional[int] = Form(default=None),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    brand_to_use = brand_id or request.session.get("brand_id") or user.brand_id
    if brand_to_use is None:
        set_flash(request, "error", "Choose a brand before adding a store.")
        return RedirectResponse("/ui/stores", status_code=status.HTTP_303_SEE_OTHER)
    try:
        ensure_brand_permission(user, int(brand_to_use), session)
    except HTTPException:
        set_flash(request, "error", "You cannot create stores for that brand.")
        return RedirectResponse("/ui/stores", status_code=status.HTTP_303_SEE_OTHER)
    store = Store(
        name=name.strip(),
        code=code.strip(),
        region=(region or "").strip() or None,
        brand_id=int(brand_to_use),
    )
    session.add(store)
    session.flush()
    log_action(session, user, "create", "store", store.id, details=f"UI created {store.name}")
    session.commit()
    set_flash(request, "success", f"Store '{store.name}' added.")
    return RedirectResponse("/ui/stores", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/ui/users", response_class=HTMLResponse)
def manage_users(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    context = build_layout_context(request, session, user, current_path="/ui/users")
    visible_users = users_in_scope(user, session)
    store_ids = get_store_scope(user, session)
    stores = []
    if store_ids:
        stores = list(session.scalars(select(Store).where(Store.id.in_(store_ids))).all())
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        brand_ids = get_brand_scope(user, session)
        if not brand_ids and user.brand_id:
            brand_ids = [user.brand_id]
        brands = list(session.scalars(select(Brand).where(Brand.id.in_(brand_ids))).all()) if brand_ids else []
    else:
        brand_context = get_ui_brand_context(request, user, session)
        brands = [brand_context.get("active_brand")] if brand_context.get("active_brand") else []
    role_counter = Counter(user.role for user in visible_users)
    membership_counter = Counter(
        membership.status for user in visible_users for membership in user.memberships
    )
    context.update(
        {
            "users": visible_users,
            "stores": stores,
            "brands": brands,
            "role_breakdown": [
                {
                    "label": role.value.replace("_", " ").title(),
                    "count": count,
                }
                for role, count in sorted(
                    role_counter.items(), key=lambda item: (-item[1], item[0].value)
                )
            ],
            "membership_status_breakdown": [
                {
                    "label": status.value.replace("_", " ").title(),
                    "count": count,
                }
                for status, count in sorted(
                    membership_counter.items(), key=lambda item: (-item[1], item[0].value)
                )
            ],
        }
    )
    return templates.TemplateResponse("users.html", context)


@app.post("/ui/users/create")
def create_user_ui(
    request: Request,
    session: Session = Depends(get_session),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: UserRole = Form(...),
    brand_id: Optional[int] = Form(default=None),
    store_id: Optional[int] = Form(default=None),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    actor: User = request.state.active_user
    try:
        ensure_can_create_role(actor, role)
    except HTTPException:
        set_flash(request, "error", "You do not have permission to create that role.")
        return RedirectResponse("/ui/users", status_code=status.HTTP_303_SEE_OTHER)
    if brand_id:
        try:
            ensure_brand_permission(actor, brand_id, session)
        except HTTPException:
            set_flash(request, "error", "Brand is outside your scope.")
            return RedirectResponse("/ui/users", status_code=status.HTTP_303_SEE_OTHER)
    brand_for_user = brand_id or actor.brand_id
    new_user = User(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        display_name=f"{first_name.strip()} {last_name.strip()}",
        email=email.strip(),
        role=role,
        brand_id=brand_for_user,
        is_active=True,
    )
    session.add(new_user)
    session.flush()
    if store_id:
        try:
            ensure_store_permission(actor, [store_id], session)
        except HTTPException:
            set_flash(request, "error", "That store is outside your scope.")
            session.rollback()
            return RedirectResponse("/ui/users", status_code=status.HTTP_303_SEE_OTHER)
        membership = StoreMembership(
            user_id=new_user.id,
            store_id=store_id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
        session.add(membership)
    session.flush()
    log_action(
        session,
        actor,
        "create",
        "user",
        new_user.id,
        details=f"UI created {new_user.display_name} ({new_user.role.value})",
    )
    session.commit()
    set_flash(request, "success", f"User '{new_user.display_name}' created.")
    return RedirectResponse("/ui/users", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/ui/courses", response_class=HTMLResponse)
def manage_courses(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    context = build_layout_context(request, session, user, current_path="/ui/courses")
    brand_ids = get_brand_scope(user, session)
    course_query = select(Course).order_by(Course.created_at.desc())
    if brand_ids:
        course_query = course_query.where((Course.brand_id.is_(None)) | (Course.brand_id.in_(brand_ids)))
    courses = list(session.scalars(course_query).all())
    assignable_users = users_in_scope(user, session)
    stores = []
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.AREA_MANAGER, UserRole.OPERATOR, UserRole.TRAINER}:
        store_ids = get_store_scope(user, session)
        if store_ids:
            stores = list(session.scalars(select(Store).where(Store.id.in_(store_ids))).all())
    course_type_counts = Counter(course.course_type for course in courses)
    course_stats = {
        "total": len(courses),
        "global": course_type_counts.get(CourseType.GLOBAL, 0),
        "local": course_type_counts.get(CourseType.LOCAL, 0),
        "required": len([course for course in courses if course.required]),
        "modules": sum(len(course.modules) for course in courses),
        "lessons": sum(len(module.lessons) for course in courses for module in course.modules),
        "scoped": len([course for course in courses if course.audience_rules]),
    }
    due_soon_courses = sorted(
        [course for course in courses if course.due_date], key=lambda course: course.due_date
    )[:4]
    context.update(
        {
            "courses": courses,
            "assignable_users": assignable_users,
            "stores": stores,
            "course_stats": course_stats,
            "due_soon_courses": due_soon_courses,
        }
    )
    return templates.TemplateResponse("courses.html", context)


@app.post("/ui/courses/create")
def create_course_ui(
    request: Request,
    session: Session = Depends(get_session),
    title: str = Form(...),
    summary: str = Form(...),
    course_type: CourseType = Form(...),
    required: Optional[str] = Form(default=None),
    due_date: Optional[str] = Form(default=None),
    module_title: str = Form(...),
    lesson_title: str = Form(...),
    lesson_content: str = Form(...),
    store_scope: Optional[int] = Form(default=None),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    actor: User = request.state.active_user
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR, UserRole.TRAINER}:
        set_flash(request, "error", "You cannot create courses with this role.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    brand_context = get_ui_brand_context(request, actor, session)
    brand = brand_context.get("active_brand")
    brand_id = brand.id if brand else actor.brand_id
    if course_type == CourseType.GLOBAL and actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        set_flash(request, "error", "Only admins can create global courses.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    if brand_id:
        try:
            ensure_brand_permission(actor, brand_id, session)
        except HTTPException:
            set_flash(request, "error", "Brand outside your scope.")
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    course = Course(
        title=title.strip(),
        summary=summary.strip(),
        brand_id=brand_id,
        course_type=course_type,
        creator_id=actor.id,
        required=bool(required),
    )
    if due_date:
        try:
            course.due_date = date.fromisoformat(due_date)
        except ValueError:
            set_flash(request, "error", "Due date must be YYYY-MM-DD.")
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    session.add(course)
    session.flush()
    module = CourseModule(course_id=course.id, title=module_title.strip(), order_index=1)
    session.add(module)
    session.flush()
    lesson = Lesson(
        module_id=module.id,
        title=lesson_title.strip(),
        content=lesson_content.strip(),
        order_index=1,
    )
    session.add(lesson)
    if store_scope:
        try:
            ensure_store_permission(actor, [store_scope], session)
        except HTTPException:
            set_flash(request, "error", "Store outside your scope.")
            session.rollback()
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
        course.audience_rules.append(
            CourseAudienceRule(
                course_id=course.id,
                rule_type=CourseAudienceRuleType.INCLUDE,
                dimension=AudienceDimension.STORE,
                value=str(store_scope),
            )
        )
    session.flush()
    log_action(session, actor, "create", "course", course.id, details=f"UI created {course.title}")
    session.commit()
    set_flash(request, "success", f"Course '{course.title}' created.")
    return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/ui/courses/{course_id}/assign")
def assign_course_ui(
    course_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user_id: int = Form(...),
    due_date: Optional[str] = Form(default=None),
    required: Optional[str] = Form(default=None),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    actor: User = request.state.active_user
    course = session.get(Course, course_id)
    if not course:
        set_flash(request, "error", "Course not found.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    target_user = session.get(User, user_id)
    if not target_user:
        set_flash(request, "error", "User not found.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    if actor.role == UserRole.TRAINEE:
        set_flash(request, "error", "Trainees cannot assign courses.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    if course.brand_id:
        try:
            ensure_brand_permission(actor, course.brand_id, session)
        except HTTPException:
            set_flash(request, "error", "This course is outside your scope.")
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        store_ids = get_store_scope(actor, session)
        target_store_ids = {membership.store_id for membership in target_user.memberships}
        if not (set(store_ids) & target_store_ids):
            set_flash(request, "error", "That teammate is outside your stores.")
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    existing = session.scalars(
        select(CourseAssignment).where(
            CourseAssignment.course_id == course.id,
            CourseAssignment.user_id == target_user.id,
        )
    ).first()
    if existing:
        set_flash(request, "error", "That user already has the course assigned.")
        return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    assignment = CourseAssignment(
        course_id=course.id,
        user_id=target_user.id,
        status=AssignmentStatus.ASSIGNED,
        required=bool(required),
    )
    if due_date:
        try:
            assignment.due_date = date.fromisoformat(due_date)
        except ValueError:
            set_flash(request, "error", "Due date must be YYYY-MM-DD.")
            return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)
    session.add(assignment)
    session.flush()
    log_action(
        session,
        actor,
        "assign",
        "course_assignment",
        assignment.id,
        details=f"UI assigned {course.title} to {target_user.display_name or target_user.email}",
    )
    session.commit()
    set_flash(request, "success", "Course assigned successfully.")
    return RedirectResponse("/ui/courses", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/learning", response_class=HTMLResponse)
def my_learning(request: Request, session: Session = Depends(get_session)):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    context = build_layout_context(request, session, user, current_path="/learning")
    assignments = list(
        session.scalars(
            select(CourseAssignment)
            .where(CourseAssignment.user_id == user.id)
            .order_by(CourseAssignment.due_date.is_(None), CourseAssignment.due_date)
        ).all()
    )
    status_counter = Counter(assignment.status for assignment in assignments)
    required_assignments = [assignment for assignment in assignments if assignment.required]
    completed_count = status_counter.get(AssignmentStatus.COMPLETED, 0)
    completion_ratio = int(round((completed_count / len(assignments)) * 100)) if assignments else 0
    required_completion_ratio = (
        int(
            round(
                (
                    len(
                        [
                            assignment
                            for assignment in required_assignments
                            if assignment.status == AssignmentStatus.COMPLETED
                        ]
                    )
                    / len(required_assignments)
                )
                * 100
            )
        )
        if required_assignments
        else 0
    )
    next_due = next((assignment for assignment in assignments if assignment.due_date), None)
    context.update(
        {
            "assignments": assignments,
            "assignment_status_counts": [
                {
                    "label": status.value.replace("_", " ").title(),
                    "count": count,
                }
                for status, count in sorted(
                    status_counter.items(), key=lambda item: (-item[1], item[0].value)
                )
            ],
            "required_assignments": required_assignments,
            "completion_ratio": completion_ratio,
            "required_completion_ratio": required_completion_ratio,
            "next_due_assignment": next_due,
            "completed_count": completed_count,
        }
    )
    return templates.TemplateResponse("learning.html", context)


@app.post("/ui/assignments/{assignment_id}/complete")
def complete_assignment_ui(
    assignment_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    redirect = ensure_ui_authenticated(request, session)
    if redirect:
        return redirect
    user: User = request.state.active_user
    assignment = session.get(CourseAssignment, assignment_id)
    if not assignment or assignment.user_id != user.id:
        set_flash(request, "error", "Assignment not found.")
        return RedirectResponse("/learning", status_code=status.HTTP_303_SEE_OTHER)
    assignment.status = AssignmentStatus.COMPLETED
    assignment.completed_at = datetime.utcnow()
    session.flush()
    log_action(
        session,
        user,
        "complete",
        "course_assignment",
        assignment.id,
        details=f"UI completion by {user.display_name or user.email}",
    )
    session.commit()
    set_flash(request, "success", "Nice work! Assignment marked complete.")
    return RedirectResponse("/learning", status_code=status.HTTP_303_SEE_OTHER)
