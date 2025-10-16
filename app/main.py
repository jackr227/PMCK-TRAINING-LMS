from __future__ import annotations

import csv
import io
import secrets
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select, delete
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, engine, get_session
from .models import (
    AreaManagerStore,
    AssignmentTarget,
    AuditLog,
    Brand,
    Course,
    CourseAssignment,
    CourseVisibility,
    Enrollment,
    Flag,
    Lesson,
    LessonProgress,
    MembershipStatus,
    Module,
    Store,
    StoreMembership,
    StoreRole,
    User,
    UserRole,
)
from .security import (
    SESSION_BRAND_KEY,
    SESSION_USER_KEY,
    generate_csrf_token,
    hash_password,
    validate_csrf,
    verify_password,
)
from .services import (
    PermissionError,
    aggregate_store_completion,
    apply_course_audience,
    brand_by_slug,
    brand_scope,
    can_manage_role,
    enforce_brand_scope,
    enforce_store_scope,
    resolve_course_audience,
    store_scope,
)

app = FastAPI(title="PMCK Training LMS")
app.add_middleware(SessionMiddleware, secret_key="pmck-training-demo-session")
app.state.csrf_secret = secrets.token_hex(32)


async def _security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.add_middleware(BaseHTTPMiddleware, dispatch=_security_headers)


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["UserRole"] = UserRole
templates.env.globals["MembershipStatus"] = MembershipStatus
templates.env.globals["CourseVisibility"] = CourseVisibility

COURSE_WIZARD_KEY = "course_wizard"
TEMP_PASSWORD = "TempPass123!"


def _current_user(request: Request, session: Session) -> Optional[User]:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    user = session.get(User, user_id)
    if not user or user.disabled:
        request.session.pop(SESSION_USER_KEY, None)
        return None
    return user


def _active_brand(request: Request, session: Session) -> Optional[Brand]:
    slug = request.session.get(SESSION_BRAND_KEY)
    if not slug:
        return None
    return brand_by_slug(session, slug)


def _require_brand(request: Request, session: Session) -> Brand:
    brand = _active_brand(request, session)
    if not brand:
        raise HTTPException(status_code=404, detail="Select a brand to continue")
    return brand


def _require_user(request: Request, session: Session) -> User:
    user = _current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def _build_nav(user: Optional[User], brand: Optional[Brand]) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = [{"label": "Home", "href": "/"}]
    if brand:
        links.append({"label": brand.display_name, "href": f"/brand/{brand.slug}"})
    if user:
        links.append({"label": "Dashboard", "href": "/dashboard"})
        links.append({"label": "Courses", "href": "/courses"})
        if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR, UserRole.TRAINER}:
            links.append({"label": "Create Course", "href": "/courses/create"})
            links.append({"label": "Assignments", "href": "/assignments"})
        if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
            links.append({"label": "Users", "href": "/admin/users"})
            links.append({"label": "Stores", "href": "/admin/stores"})
        if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.AREA_MANAGER, UserRole.OPERATOR, UserRole.TRAINER}:
            links.append({"label": "Reports", "href": "/reports"})
        if user.role in {UserRole.OPERATOR, UserRole.TRAINER}:
            links.append({"label": "Approvals", "href": "/approvals"})
        links.append({"label": "Logout", "href": "/logout"})
    else:
        links.append({"label": "Login", "href": "/login"})
    return links


def _render(request: Request, template: str, session: Session, context: Dict[str, Any]) -> Response:
    user = _current_user(request, session)
    brand = _active_brand(request, session)
    brand_choices: List[Brand] = []
    if user and user.role == UserRole.SUPER_ADMIN:
        brand_choices = session.scalars(select(Brand).order_by(Brand.display_name)).all()
    context.update(
        {
            "request": request,
            "active_user": user,
            "active_brand": brand,
            "nav_links": _build_nav(user, brand),
            "csrf_token": generate_csrf_token(request),
            "brand_choices": brand_choices,
        }
    )
    return templates.TemplateResponse(template, context)


def _log_action(session: Session, actor: Optional[User], action: str, subject_type: str, subject_id: str, meta: str | None = None) -> None:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        meta=meta,
        created_at=datetime.utcnow(),
    )
    session.add(entry)


def _scoped_user_ids(user: User, session: Session) -> Optional[List[int]]:
    if user.role == UserRole.SUPER_ADMIN:
        return None
    if user.role == UserRole.ADMIN:
        return list(session.scalars(select(User.id).where(User.brand_id == user.brand_id)))
    ids = set([user.id])
    scoped_stores = store_scope(user, session)
    if scoped_stores:
        ids.update(
            session.scalars(
                select(StoreMembership.user_id).where(StoreMembership.store_id.in_(scoped_stores))
            )
        )
    return sorted(ids)


def _scoped_users(user: User, session: Session) -> List[User]:
    ids = _scoped_user_ids(user, session)
    stmt = select(User).order_by(User.first_name, User.last_name)
    if ids is not None:
        if not ids:
            return []
        stmt = stmt.where(User.id.in_(ids))
    return list(session.scalars(stmt))


def _scoped_stores(user: User, session: Session) -> List[Store]:
    store_ids = store_scope(user, session)
    if not store_ids:
        return []
    return list(
        session.scalars(
            select(Store).where(Store.id.in_(store_ids)).order_by(Store.display_name)
        )
    )


def _brand_flags(brand_id: int, session: Session) -> List[Flag]:
    return list(session.scalars(select(Flag).where(Flag.brand_id == brand_id).order_by(Flag.name)))


def _parse_date(raw: str | None) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _wizard_state(request: Request) -> Dict[str, Any]:
    return request.session.setdefault(COURSE_WIZARD_KEY, {})


def _clear_wizard(request: Request) -> None:
    request.session.pop(COURSE_WIZARD_KEY, None)


def _course_visibility_options(user: User) -> List[CourseVisibility]:
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        return [CourseVisibility.GLOBAL, CourseVisibility.LOCAL]
    if user.role in {UserRole.OPERATOR, UserRole.TRAINER}:
        return [CourseVisibility.LOCAL]
    return []


def _manageable_courses(user: User, session: Session) -> List[Course]:
    if user.role == UserRole.SUPER_ADMIN:
        return list(session.scalars(select(Course).order_by(Course.created_at.desc())).unique())
    if user.role == UserRole.ADMIN:
        return list(
            session.scalars(
                select(Course)
                .where((Course.brand_id == user.brand_id) | (Course.owner_user_id == user.id))
                .order_by(Course.created_at.desc())
            ).unique()
        )
    return list({course for course in user.owned_courses})


def _ensure_user_in_scope(actor: User, target: User, session: Session) -> None:
    ids = _scoped_user_ids(actor, session)
    if ids is None:
        return
    if target.id not in ids:
        raise HTTPException(status_code=403, detail="User outside scope")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health", response_class=HTMLResponse)
def health() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)) -> Response:
    brands = session.scalars(select(Brand).order_by(Brand.display_name)).all()
    return _render(request, "home.html", session, {"brands": brands})


@app.get("/brand/{slug}", response_class=HTMLResponse)
def brand_home(slug: str, request: Request, session: Session = Depends(get_session)) -> Response:
    brand = brand_by_slug(session, slug)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    request.session[SESSION_BRAND_KEY] = slug
    user = _current_user(request, session)
    scoped_stores = _scoped_stores(user, session) if user else []
    return _render(
        request,
        "brand_home.html",
        session,
        {
            "brand": brand,
            "scoped_stores": scoped_stores,
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _active_brand(request, session)
    if not brand:
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", session, {"brand": brand, "error": None})


@app.post("/login")
def login(  # noqa: PLR0913
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    brand = _active_brand(request, session)
    if not brand:
        return RedirectResponse("/", status_code=303)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        return _render(request, "login.html", session, {"brand": brand, "error": "Session expired. Refresh and try again."})
    user = session.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.password_hash):
        return _render(request, "login.html", session, {"brand": brand, "error": "Invalid credentials"})
    if user.brand_id and user.brand_id != brand.id:
        return _render(request, "login.html", session, {"brand": brand, "error": "Account belongs to another brand"})
    if user.disabled:
        return _render(request, "login.html", session, {"brand": brand, "error": "Account disabled"})
    request.session[SESSION_USER_KEY] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request) -> Response:
    request.session.pop(SESSION_USER_KEY, None)
    return RedirectResponse("/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    enrollments = list(user.enrollments)
    required_courses = [en.course for en in enrollments if en.course.required_default]
    assigned_courses = [en.course for en in enrollments]
    completed_courses = [en.course for en in enrollments if en.completed]
    in_progress = [en.course for en in enrollments if not en.completed]
    stats = {
        "required": len(required_courses),
        "assigned": len(assigned_courses),
        "completed": len(completed_courses),
    }
    return _render(
        request,
        "dashboard.html",
        session,
        {
            "brand": brand,
            "stats": stats,
            "required_courses": required_courses,
            "assigned_courses": assigned_courses,
            "in_progress": in_progress,
            "completed_courses": completed_courses,
        },
    )


def _course_scope_query(user: User, session: Session):
    if user.role == UserRole.SUPER_ADMIN:
        return select(Course)
    if user.role == UserRole.ADMIN:
        return select(Course).where((Course.brand_id == user.brand_id) | (Course.brand_id.is_(None)))
    owned_ids = [course.id for course in user.owned_courses]
    enrollment_ids = [en.course_id for en in user.enrollments]
    ids = owned_ids + enrollment_ids
    if not ids:
        return select(Course).where(Course.id == -1)
    return select(Course).where(Course.id.in_(ids))


@app.get("/courses", response_class=HTMLResponse)
def courses(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    stmt = _course_scope_query(user, session).order_by(Course.created_at.desc())
    course_list = list(session.scalars(stmt).unique())
    tab = request.query_params.get("tab", "assigned")
    assigned_ids = {en.course_id for en in user.enrollments}
    created_ids = {course.id for course in user.owned_courses}
    tabs = {
        "assigned": [course for course in course_list if course.id in assigned_ids],
        "required": [course for course in course_list if course.required_default],
        "created": [course for course in course_list if course.id in created_ids],
        "global": [course for course in course_list if course.visibility == CourseVisibility.GLOBAL],
        "local": [course for course in course_list if course.visibility == CourseVisibility.LOCAL],
        "all": course_list,
    }
    return _render(
        request,
        "courses.html",
        session,
        {
            "brand": brand,
            "tab": tab,
            "tabs": tabs,
            "courses": tabs.get(tab, course_list),
        },
    )


@app.get("/courses/{course_id}", response_class=HTMLResponse)
def course_detail(course_id: int, request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _active_brand(request, session)
    user = _current_user(request, session)
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    enrollment = None
    completed_lessons: set[int] = set()
    if user:
        enrollment = session.scalar(
            select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id)
        )
        if enrollment:
            completed_lessons = {
                progress.lesson_id
                for progress in session.scalars(
                    select(LessonProgress).where(
                        LessonProgress.user_id == user.id,
                        LessonProgress.lesson_id.in_(
                            select(Lesson.id).where(
                                Lesson.module_id.in_(
                                    select(Module.id).where(Module.course_id == course.id)
                                )
                            )
                        ),
                        LessonProgress.completed.is_(True),
                    )
                )
            }
    return _render(
        request,
        "course_detail.html",
        session,
        {
            "brand": brand,
            "course": course,
            "enrollment": enrollment,
            "completed_lessons": completed_lessons,
        },
    )


@app.post("/courses/{course_id}/enroll")
def enroll_course(
    course_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    user = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    existing = session.scalar(
        select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id)
    )
    if not existing:
        session.add(Enrollment(user_id=user.id, course_id=course.id, completed=False))
    return RedirectResponse(f"/courses/{course.id}", status_code=303)


@app.post("/lessons/{lesson_id}/complete")
def complete_lesson(
    lesson_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    user = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    progress = session.scalar(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.lesson_id == lesson.id,
        )
    )
    if not progress:
        progress = LessonProgress(user_id=user.id, lesson_id=lesson.id, completed=True, completed_at=datetime.utcnow())
        session.add(progress)
    else:
        progress.completed = True
        progress.completed_at = datetime.utcnow()
    enrollment = session.scalar(
        select(Enrollment).where(Enrollment.course_id == lesson.module.course_id, Enrollment.user_id == user.id)
    )
    if enrollment:
        total_lessons = session.scalar(
            select(func.count(Lesson.id)).where(
                Lesson.module_id.in_(select(Module.id).where(Module.course_id == lesson.module.course_id))
            )
        )
        completed_count = session.scalar(
            select(func.count(LessonProgress.id)).where(
                LessonProgress.user_id == user.id,
                LessonProgress.completed.is_(True),
                LessonProgress.lesson_id.in_(
                    select(Lesson.id).where(
                        Lesson.module_id.in_(select(Module.id).where(Module.course_id == lesson.module.course_id))
                    )
                ),
            )
        )
        if total_lessons and completed_count == total_lessons:
            enrollment.completed = True
            enrollment.completed_at = datetime.utcnow()
    return RedirectResponse(f"/courses/{lesson.module.course_id}", status_code=303)


@app.get("/courses/{course_id}/certificate", response_class=HTMLResponse)
def download_certificate(
    course_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    user = _require_user(request, session)
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    enrollment = session.scalar(
        select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id)
    )
    if not enrollment or not enrollment.completed:
        raise HTTPException(status_code=400, detail="Course incomplete")
    response = templates.TemplateResponse(
        "certificate.html",
        {
            "request": request,
            "course": course,
            "user": user,
            "completed_at": enrollment.completed_at or datetime.utcnow(),
        },
    )
    response.headers["Content-Disposition"] = f"attachment; filename=certificate-{course.id}-{user.id}.html"
    return response


@app.get("/courses/create", response_class=HTMLResponse)
def create_course_form(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    wizard = _wizard_state(request)
    wizard.setdefault('basics', {})
    wizard.setdefault('includes', {'brands': [], 'stores': [], 'roles': [], 'flags': [], 'users': []})
    wizard.setdefault('excludes', {'stores': [], 'roles': [], 'users': []})
    wizard.setdefault('requirements', {})
    visibility_options = _course_visibility_options(user)
    scoped_brands = brand_scope(user, session)
    scoped_stores = _scoped_stores(user, session)
    scoped_users = _scoped_users(user, session)
    flags = _brand_flags(brand.id, session)
    return _render(
        request,
        "course_wizard.html",
        session,
        {
            "brand": brand,
            "wizard": wizard,
            "step": int(request.query_params.get("step", "1")),
            "visibility_options": visibility_options,
            "scoped_brands": session.scalars(select(Brand).where(Brand.id.in_(scoped_brands))).all()
            if scoped_brands
            else [],
            "stores": scoped_stores,
            "users": scoped_users,
            "flags": flags,
        },
    )


@app.post("/courses/create")
async def create_course_submit(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    form = await request.form()
    step = int(form.get("step", "1"))
    token = form.get("csrf_token")
    try:
        validate_csrf(request, token or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    wizard = _wizard_state(request)

    if step == 1:
        wizard["basics"] = {
            "title": form.get("title", "").strip(),
            "summary": form.get("summary", "").strip(),
            "description": form.get("description", "").strip(),
            "cover_image": form.get("cover_image", "").strip(),
            "certificate": form.get("certificate", "").strip(),
        }
        return RedirectResponse("/courses/create?step=2", status_code=303)

    if step == 2:
        includes = {
            "brands": [int(b) for b in form.getlist("include_brands")],
            "stores": [int(s) for s in form.getlist("include_stores")],
            "roles": form.getlist("include_roles"),
            "flags": [int(f) for f in form.getlist("include_flags")],
            "users": [int(u) for u in form.getlist("include_users")],
        }
        excludes = {
            "stores": [int(s) for s in form.getlist("exclude_stores")],
            "roles": form.getlist("exclude_roles"),
            "users": [int(u) for u in form.getlist("exclude_users")],
        }
        wizard["visibility"] = form.get("visibility", CourseVisibility.LOCAL.value)
        wizard["includes"] = includes
        wizard["excludes"] = excludes
        preview_course = Course(assignments=[])
        assignment_objects: List[CourseAssignment] = []
        scoped_brands = brand_scope(user, session)
        scoped_stores = store_scope(user, session)
        scoped_users = _scoped_user_ids(user, session)
        required_default = wizard.get("requirements", {}).get("required", True)
        due_date = wizard.get("requirements", {}).get("due_date")
        for brand_id in includes["brands"]:
            if scoped_brands and brand_id not in scoped_brands:
                continue
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.BRAND,
                    target_id=str(brand_id),
                    required=required_default,
                    due_date=_parse_date(due_date),
                )
            )
        for store_id in includes["stores"]:
            if store_id not in scoped_stores:
                continue
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.STORE,
                    target_id=str(store_id),
                    required=required_default,
                    due_date=_parse_date(due_date),
                )
            )
        for role_value in includes["roles"]:
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.ROLE,
                    target_id=role_value,
                    required=required_default,
                    due_date=_parse_date(due_date),
                )
            )
        for flag_id in includes["flags"]:
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.FLAG,
                    target_id=str(flag_id),
                    required=required_default,
                    due_date=_parse_date(due_date),
                )
            )
        for user_id in includes["users"]:
            if scoped_users is not None and user_id not in scoped_users:
                continue
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.USER,
                    target_id=str(user_id),
                    required=required_default,
                    due_date=_parse_date(due_date),
                )
            )
        for store_id in excludes["stores"]:
            if store_id not in scoped_stores:
                continue
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.STORE,
                    target_id=str(store_id),
                    required=False,
                    is_exclusion=True,
                )
            )
        for role_value in excludes["roles"]:
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.ROLE,
                    target_id=role_value,
                    required=False,
                    is_exclusion=True,
                )
            )
        for user_id in excludes["users"]:
            if scoped_users is not None and user_id not in scoped_users:
                continue
            assignment_objects.append(
                CourseAssignment(
                    target_type=AssignmentTarget.USER,
                    target_id=str(user_id),
                    required=False,
                    is_exclusion=True,
                )
            )
        preview_course.assignments = assignment_objects
        total = len(resolve_course_audience(session, preview_course))
        wizard["preview_total"] = total
        wizard["preview_sample"] = [u.id for u in _scoped_users(user, session)[:5]]
        return RedirectResponse("/courses/create?step=3", status_code=303)

    if step == 3:
        required_toggle = form.get("required", "on") == "on"
        due_date = _parse_date(form.get("due_date"))
        notify = form.get("notify") == "on"
        wizard["requirements"] = {
            "required": required_toggle,
            "due_date": due_date.isoformat() if due_date else None,
            "notify": notify,
        }
        basics = wizard.get("basics")
        includes = wizard.get("includes", {})
        excludes = wizard.get("excludes", {})
        if not basics:
            raise HTTPException(status_code=400, detail="Missing course details")
        visibility_value = wizard.get("visibility", CourseVisibility.LOCAL.value)
        visibility = CourseVisibility(visibility_value)
        course_brand_id = brand.id if visibility == CourseVisibility.LOCAL else brand.id if user.role != UserRole.SUPER_ADMIN else None
        course = Course(
            title=basics.get("title", "Untitled Course"),
            summary=basics.get("summary", ""),
            description=basics.get("description"),
            brand_id=course_brand_id,
            visibility=visibility,
            owner_user_id=user.id,
            owner_role=user.role,
            owner_brand_id=user.brand_id,
            cover_image=basics.get("cover_image"),
            cert_template=basics.get("certificate"),
            required_default=required_toggle,
            due_date_default=due_date,
            published_at=datetime.utcnow(),
        )
        session.add(course)
        session.flush()
        module = Module(course_id=course.id, title="Introduction", order_index=1)
        session.add(module)
        session.flush()
        session.add(
            Lesson(
                module_id=module.id,
                title="Welcome",
                content=basics.get("description") or basics.get("summary") or "Welcome to this course.",
                order_index=1,
            )
        )
        scoped_brands = set(brand_scope(user, session))
        scoped_stores = set(store_scope(user, session))
        scoped_users = _scoped_user_ids(user, session)
        due_value = due_date
        for brand_id in includes.get("brands", []):
            if scoped_brands and brand_id not in scoped_brands:
                continue
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.BRAND,
                    target_id=str(brand_id),
                    required=required_toggle,
                    due_date=due_value,
                )
            )
        for store_id in includes.get("stores", []):
            if store_id not in scoped_stores:
                continue
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.STORE,
                    target_id=str(store_id),
                    required=required_toggle,
                    due_date=due_value,
                )
            )
        for role_value in includes.get("roles", []):
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.ROLE,
                    target_id=role_value,
                    required=required_toggle,
                    due_date=due_value,
                )
            )
        for flag_id in includes.get("flags", []):
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.FLAG,
                    target_id=str(flag_id),
                    required=required_toggle,
                    due_date=due_value,
                )
            )
        for user_id in includes.get("users", []):
            if scoped_users is not None and user_id not in scoped_users:
                continue
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.USER,
                    target_id=str(user_id),
                    required=required_toggle,
                    due_date=due_value,
                )
            )
        for store_id in excludes.get("stores", []):
            if store_id not in scoped_stores:
                continue
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.STORE,
                    target_id=str(store_id),
                    required=False,
                    is_exclusion=True,
                )
            )
        for role_value in excludes.get("roles", []):
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.ROLE,
                    target_id=role_value,
                    required=False,
                    is_exclusion=True,
                )
            )
        for user_id in excludes.get("users", []):
            if scoped_users is not None and user_id not in scoped_users:
                continue
            course.assignments.append(
                CourseAssignment(
                    target_type=AssignmentTarget.USER,
                    target_id=str(user_id),
                    required=False,
                    is_exclusion=True,
                )
            )
        apply_course_audience(session, course)
        _log_action(session, user, "course:create", "course", str(course.id), meta=course.title)
        _clear_wizard(request)
        return RedirectResponse(f"/courses/{course.id}", status_code=303)

    raise HTTPException(status_code=400, detail="Unsupported step")


@app.get("/assignments", response_class=HTMLResponse)
def assignments(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    courses = _manageable_courses(user, session)
    return _render(
        request,
        "assignments.html",
        session,
        {
            "brand": brand,
            "courses": courses,
        },
    )


@app.post("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    request: Request,
    required: bool = Form(False),
    due_date: str | None = Form(None),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    user = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    assignment = session.get(CourseAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    course = assignment.course
    if course.owner_user_id != user.id and user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Not allowed")
    assignment.required = required
    assignment.due_date = _parse_date(due_date)
    apply_course_audience(session, course)
    _log_action(session, user, "assignment:update", "course", str(course.id))
    return RedirectResponse("/assignments", status_code=303)


@app.get("/approvals", response_class=HTMLResponse)
def approvals(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    if user.role not in {UserRole.OPERATOR, UserRole.TRAINER}:
        raise HTTPException(status_code=403, detail="Approvals limited to store leaders")
    store_ids = store_scope(user, session)
    pending = list(
        session.scalars(
            select(StoreMembership)
            .where(
                StoreMembership.store_id.in_(store_ids),
                StoreMembership.status == MembershipStatus.PENDING,
            )
            .order_by(StoreMembership.created_at.desc())
        )
    )
    return _render(
        request,
        "approvals.html",
        session,
        {
            "brand": brand,
            "pending": pending,
        },
    )


@app.post("/approvals/{membership_id}")
def process_approval(
    membership_id: int,
    request: Request,
    decision: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    user = _require_user(request, session)
    if user.role not in {UserRole.OPERATOR, UserRole.TRAINER}:
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    membership = session.get(StoreMembership, membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    enforce_store_scope(user, [membership.store_id], session)
    membership.status = (
        MembershipStatus.ACTIVE if decision == "approve" else MembershipStatus.REJECTED
    )
    _log_action(
        session,
        user,
        "membership:update",
        "store_membership",
        str(membership.id),
        meta=decision,
    )
    return RedirectResponse("/approvals", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def users_list(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    scoped_users = _scoped_users(user, session)
    role_filter = request.query_params.get("role")
    store_filter = request.query_params.get("store")
    status_filter = request.query_params.get("status")
    export = request.query_params.get("format") == "csv"

    filtered = scoped_users
    if role_filter:
        filtered = [u for u in filtered if u.role.value == role_filter]
    if store_filter:
        store_id = int(store_filter)
        filtered = [
            u
            for u in filtered
            if any(m.store_id == store_id and m.status == MembershipStatus.ACTIVE for m in u.memberships)
        ]
    if status_filter == "disabled":
        filtered = [u for u in filtered if u.disabled]
    elif status_filter == "active":
        filtered = [u for u in filtered if not u.disabled]

    if export:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ID", "Name", "Email", "Role", "Brand", "Stores", "Disabled"])
        for entry in filtered:
            stores = ", ".join(sorted({m.store.display_name for m in entry.memberships if m.store}))
            writer.writerow(
                [
                    entry.id,
                    f"{entry.first_name} {entry.last_name}",
                    entry.email,
                    entry.role.value,
                    entry.brand.display_name if entry.brand else "All",
                    stores,
                    "Yes" if entry.disabled else "No",
                ]
            )
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})

    stores = _scoped_stores(user, session)
    return _render(
        request,
        "users.html",
        session,
        {
            "brand": brand,
            "users": filtered,
            "stores": stores,
        },
    )


@app.get("/admin/users/new", response_class=HTMLResponse)
def user_create_form(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    user = _require_user(request, session)
    stores = _scoped_stores(user, session)
    available_roles = [role for role in UserRole if can_manage_role(user, role)]
    return _render(
        request,
        "user_form.html",
        session,
        {
            "brand": brand,
            "mode": "new",
            "stores": stores,
            "roles": available_roles,
            "user_record": None,
            "flags": _brand_flags(brand.id, session),
        },
    )


@app.post("/admin/users/new")
def user_create_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    store_ids: List[int] = Form(default=[]),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    target_role = UserRole(role)
    if not can_manage_role(actor, target_role):
        raise HTTPException(status_code=403, detail="Role not permitted")
    if session.scalar(select(User.id).where(User.email == email.lower())):
        raise HTTPException(status_code=400, detail="Email already exists")
    new_user = User(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        display_name=f"{first_name.strip()} {last_name.strip()}",
        email=email.lower(),
        password_hash=hash_password(TEMP_PASSWORD),
        role=target_role,
        brand_id=None if target_role == UserRole.SUPER_ADMIN else brand.id,
        must_change_password=True,
    )
    session.add(new_user)
    session.flush()
    if target_role in {UserRole.OPERATOR, UserRole.TRAINER, UserRole.TRAINEE}:
        enforce_store_scope(actor, store_ids, session)
        for sid in store_ids:
            session.add(
                StoreMembership(
                    user_id=new_user.id,
                    store_id=sid,
                    role=StoreRole[target_role.name] if target_role != UserRole.TRAINEE else StoreRole.TRAINEE,
                    status=MembershipStatus.PENDING if target_role == UserRole.TRAINEE else MembershipStatus.ACTIVE,
                )
            )
    if target_role == UserRole.AREA_MANAGER:
        enforce_store_scope(actor, store_ids, session)
        for sid in store_ids:
            session.add(AreaManagerStore(user_id=new_user.id, store_id=sid))
    _log_action(session, actor, "user:create", "user", str(new_user.id))
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
def user_edit_form(user_id: int, request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    user_record = session.get(User, user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_in_scope(actor, user_record, session)
    stores = _scoped_stores(actor, session)
    return _render(
        request,
        "user_form.html",
        session,
        {
            "brand": brand,
            "mode": "edit",
            "stores": stores,
            "roles": [user_record.role],
            "user_record": user_record,
            "flags": _brand_flags(brand.id, session),
        },
    )


@app.post("/admin/users/{user_id}/edit")
def user_edit_submit(
    user_id: int,
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(""),
    disabled: bool = Form(False),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    user_record = session.get(User, user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_in_scope(actor, user_record, session)
    user_record.first_name = first_name.strip()
    user_record.last_name = last_name.strip()
    user_record.display_name = f"{user_record.first_name} {user_record.last_name}"
    user_record.phone = phone.strip()
    user_record.disabled = disabled
    _log_action(session, actor, "user:update", "user", str(user_record.id))
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/reset")
def user_reset_password(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    user_record = session.get(User, user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_in_scope(actor, user_record, session)
    user_record.password_hash = hash_password(TEMP_PASSWORD)
    user_record.must_change_password = True
    _log_action(session, actor, "user:reset_password", "user", str(user_record.id))
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/stores")
def user_update_stores(
    user_id: int,
    request: Request,
    store_ids: List[int] = Form(default=[]),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    user_record = session.get(User, user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_in_scope(actor, user_record, session)
    enforce_store_scope(actor, store_ids, session)
    session.execute(delete(StoreMembership).where(StoreMembership.user_id == user_record.id))
    for sid in store_ids:
        session.add(
            StoreMembership(
                user_id=user_record.id,
                store_id=sid,
                role=StoreRole.TRAINEE if user_record.role == UserRole.TRAINEE else StoreRole.TRAINER,
                status=MembershipStatus.ACTIVE,
            )
        )
    _log_action(session, actor, "user:update_stores", "user", str(user_record.id))
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/admin/stores", response_class=HTMLResponse)
def stores_list(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    stores = _scoped_stores(actor, session)
    export = request.query_params.get("format") == "csv"
    if export:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ID", "Name", "Code", "Region"])
        for store in stores:
            writer.writerow([store.id, store.display_name, store.code, store.region])
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=stores.csv"})
    return _render(
        request,
        "stores.html",
        session,
        {
            "brand": brand,
            "stores": stores,
        },
    )


@app.get("/admin/stores/new", response_class=HTMLResponse)
def store_create_form(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Not allowed")
    return _render(
        request,
        "store_form.html",
        session,
        {
            "brand": brand,
            "mode": "new",
            "store": None,
        },
    )


@app.post("/admin/stores/new")
def store_create_submit(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    region: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    store = Store(
        brand_id=brand.id,
        name=name.strip(),
        display_name=name.strip(),
        code=code.strip(),
        region=region.strip(),
    )
    session.add(store)
    _log_action(session, actor, "store:create", "store", store.code)
    return RedirectResponse("/admin/stores", status_code=303)


@app.get("/admin/stores/{store_id}/edit", response_class=HTMLResponse)
def store_edit_form(store_id: int, request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _require_brand(request, session)
    actor = _require_user(request, session)
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    enforce_store_scope(actor, [store.id], session)
    return _render(
        request,
        "store_form.html",
        session,
        {
            "brand": brand,
            "mode": "edit",
            "store": store,
        },
    )


@app.post("/admin/stores/{store_id}/edit")
def store_edit_submit(
    store_id: int,
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    region: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    enforce_store_scope(actor, [store.id], session)
    store.name = name.strip()
    store.display_name = name.strip()
    store.code = code.strip()
    store.region = region.strip()
    _log_action(session, actor, "store:update", "store", str(store.id))
    return RedirectResponse("/admin/stores", status_code=303)


@app.post("/admin/stores/{store_id}/delete")
def store_delete(
    store_id: int,
    request: Request,
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    actor = _require_user(request, session)
    try:
        validate_csrf(request, csrf_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token")
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    enforce_store_scope(actor, [store.id], session)
    session.delete(store)
    _log_action(session, actor, "store:delete", "store", str(store_id))
    return RedirectResponse("/admin/stores", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request, session: Session = Depends(get_session)) -> Response:
    brand = _active_brand(request, session)
    actor = _require_user(request, session)
    scoped_users = _scoped_users(actor, session)
    user_ids = [u.id for u in scoped_users]
    enrollments_query = select(Enrollment).join(User)
    if user_ids:
        enrollments_query = enrollments_query.where(Enrollment.user_id.in_(user_ids))
    enrollments = list(session.scalars(enrollments_query))
    total_courses = len({enrollment.course_id for enrollment in enrollments})
    completed = sum(1 for enrollment in enrollments if enrollment.completed)
    required = sum(1 for enrollment in enrollments if enrollment.course.required_default)
    stores = _scoped_stores(actor, session)
    store_rows = aggregate_store_completion(session, stores)
    export = request.query_params.get("format") == "csv"
    if export:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Store", "Active Users", "Completed Courses"])
        for row in store_rows:
            writer.writerow([row["store"].display_name, row["active_users"], row["completed_courses"]])
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=report.csv"})
    return _render(
        request,
        "reports.html",
        session,
        {
            "brand": brand,
            "summary": {
                "users": len(scoped_users),
                "courses": total_courses,
                "required_enrollments": required,
                "completed": completed,
            },
            "stores": store_rows,
        },
    )
