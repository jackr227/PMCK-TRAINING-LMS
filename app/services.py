from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AreaManagerStore,
    AssignmentTarget,
    Brand,
    Course,
    CourseAssignment,
    Enrollment,
    Flag,
    MembershipStatus,
    Store,
    StoreMembership,
    StoreRole,
    User,
    UserFlag,
    UserRole,
)


class PermissionError(Exception):
    """Raised when a guard fails."""


def brand_by_slug(session: Session, slug: str) -> Brand | None:
    return session.scalar(select(Brand).where(Brand.slug == slug))


def brand_scope(user: User, session: Session) -> List[int]:
    if user.role == UserRole.SUPER_ADMIN:
        return list(session.scalars(select(Brand.id)))
    if user.brand_id:
        return [user.brand_id]
    return []


def store_scope(user: User, session: Session) -> List[int]:
    if user.role == UserRole.SUPER_ADMIN:
        return list(session.scalars(select(Store.id)))
    if user.role == UserRole.ADMIN:
        return list(
            session.scalars(
                select(Store.id).where(Store.brand_id == user.brand_id)
            )
        )
    if user.role == UserRole.AREA_MANAGER:
        return [link.store_id for link in user.area_manager_stores]
    return [m.store_id for m in user.memberships if m.status == MembershipStatus.ACTIVE]


def enforce_brand_scope(user: User, brand_id: int) -> None:
    if user.role == UserRole.SUPER_ADMIN:
        return
    if user.brand_id != brand_id:
        raise PermissionError("Brand outside scope")


def enforce_store_scope(user: User, store_ids: Iterable[int], session: Session) -> None:
    allowed = set(store_scope(user, session))
    missing = set(store_ids) - allowed
    if missing:
        raise PermissionError("Store outside scope")


def can_manage_role(actor: User, target_role: UserRole) -> bool:
    if actor.role == UserRole.SUPER_ADMIN:
        return True
    if actor.role == UserRole.ADMIN:
        return target_role != UserRole.SUPER_ADMIN
    if actor.role == UserRole.AREA_MANAGER:
        return target_role in {UserRole.OPERATOR, UserRole.TRAINER, UserRole.TRAINEE}
    if actor.role == UserRole.OPERATOR:
        return target_role in {UserRole.TRAINER, UserRole.TRAINEE}
    if actor.role == UserRole.TRAINER:
        return target_role == UserRole.TRAINEE
    return False


def _match_assignment_users(session: Session, assignment: CourseAssignment) -> List[int]:
    if assignment.target_type == AssignmentTarget.BRAND:
        brand_id = int(assignment.target_id)
        return list(
            session.scalars(
                select(User.id).where(User.brand_id == brand_id, User.disabled.is_(False))
            )
        )
    if assignment.target_type == AssignmentTarget.STORE:
        store_id = int(assignment.target_id)
        stmt = select(StoreMembership.user_id).where(
            StoreMembership.store_id == store_id,
            StoreMembership.status == MembershipStatus.ACTIVE,
        )
        return list(session.scalars(stmt))
    if assignment.target_type == AssignmentTarget.ROLE:
        role_value = assignment.target_id
        stmt = select(User.id).where(User.role == role_value, User.disabled.is_(False))
        return list(session.scalars(stmt))
    if assignment.target_type == AssignmentTarget.FLAG:
        flag_id = int(assignment.target_id)
        stmt = select(UserFlag.user_id).where(UserFlag.flag_id == flag_id)
        return list(session.scalars(stmt))
    if assignment.target_type == AssignmentTarget.USER:
        return [int(assignment.target_id)]
    return []


def resolve_course_audience(session: Session, course: Course) -> List[int]:
    includes = [a for a in course.assignments if not a.is_exclusion]
    excludes = [a for a in course.assignments if a.is_exclusion]

    include_ids: set[int] = set()
    for assignment in includes:
        include_ids.update(_match_assignment_users(session, assignment))

    exclude_ids: set[int] = set()
    for assignment in excludes:
        exclude_ids.update(_match_assignment_users(session, assignment))

    return sorted(include_ids - exclude_ids)


def apply_course_audience(session: Session, course: Course) -> None:
    user_ids = resolve_course_audience(session, course)
    existing_map = {enrollment.user_id: enrollment for enrollment in course.enrollments}
    for user_id in user_ids:
        if user_id not in existing_map:
            session.add(Enrollment(user_id=user_id, course=course, completed=False))
    for enrollment in list(course.enrollments):
        if enrollment.user_id not in user_ids:
            session.delete(enrollment)


def audience_preview(
    session: Session,
    include_rules: Sequence[CourseAssignment],
    exclude_rules: Sequence[CourseAssignment],
) -> Tuple[int, List[User]]:
    temp_course = Course(assignments=list(include_rules) + list(exclude_rules))
    user_ids = resolve_course_audience(session, temp_course)
    if not user_ids:
        return 0, []
    users = list(session.scalars(select(User).where(User.id.in_(user_ids)).limit(20)))
    return len(user_ids), users


def aggregate_store_completion(session: Session, stores: Sequence[Store]) -> List[dict[str, object]]:
    rows: List[dict[str, object]] = []
    for store in stores:
        memberships = list(
            session.scalars(
                select(StoreMembership).where(
                    StoreMembership.store_id == store.id,
                    StoreMembership.status == MembershipStatus.ACTIVE,
                )
            )
        )
        active_users = len(memberships)
        completed = 0
        for membership in memberships:
            completed += sum(1 for enrollment in membership.user.enrollments if enrollment.completed)
        rows.append(
            {
                "store": store,
                "active_users": active_users,
                "completed_courses": completed,
            }
        )
    return rows


def find_available_port(start_port: int = 3000) -> int:
    import socket

    port = start_port
    for offset in range(20):
        candidate = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", candidate)) != 0:
                return candidate
    return start_port
