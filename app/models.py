from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AREA_MANAGER = "area_manager"
    OPERATOR = "operator"
    TRAINER = "trainer"
    TRAINEE = "trainee"


class StoreRole(str, Enum):
    OPERATOR = "operator"
    TRAINER = "trainer"
    TRAINEE = "trainee"


class MembershipStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"


class CourseVisibility(str, Enum):
    GLOBAL = "global"
    LOCAL = "local"


class AssignmentTarget(str, Enum):
    BRAND = "brand"
    STORE = "store"
    ROLE = "role"
    FLAG = "flag"
    USER = "user"


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    slug = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(120), nullable=False)
    primary_color = Column(String(20), nullable=False)
    secondary_color = Column(String(20), nullable=False)
    accent_color = Column(String(20), nullable=False)
    background_color = Column(String(20), nullable=False, default="#0b0b0d")
    text_color = Column(String(20), nullable=False, default="#ffffff")
    logo_url = Column(String(255))
    emoji = Column(String(10))
    tone_greeting = Column(String(160), nullable=False, default="Welcome back")
    tone_cta = Column(String(160), nullable=False, default="Get started")
    border_radius = Column(String(10), nullable=False, default="12px")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    stores = relationship("Store", back_populates="brand", cascade="all, delete-orphan")
    users = relationship("User", back_populates="brand")
    flags = relationship("Flag", back_populates="brand", cascade="all, delete-orphan")
    courses = relationship("Course", back_populates="brand")


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("brand_id", "code", name="uq_store_brand_code"),
    )

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    display_name = Column(String(160), nullable=False)
    code = Column(String(80), nullable=False)
    region = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    brand = relationship("Brand", back_populates="stores")
    memberships = relationship("StoreMembership", back_populates="store", cascade="all, delete-orphan")
    area_manager_links = relationship("AreaManagerStore", back_populates="store", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"))
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)
    display_name = Column(String(160))
    id_number = Column(String(80))
    phone = Column(String(40))
    email = Column(String(160), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SqlEnum(UserRole), nullable=False)
    disabled = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    brand = relationship("Brand", back_populates="users")
    memberships = relationship("StoreMembership", back_populates="user", cascade="all, delete-orphan")
    area_manager_stores = relationship("AreaManagerStore", back_populates="user", cascade="all, delete-orphan")
    flags = relationship("UserFlag", back_populates="user", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="user", cascade="all, delete-orphan")
    lesson_progress = relationship("LessonProgress", back_populates="user", cascade="all, delete-orphan")
    owned_courses = relationship("Course", back_populates="owner", cascade="all")
    audit_logs = relationship("AuditLog", back_populates="actor", cascade="all")


class StoreMembership(Base):
    __tablename__ = "store_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_membership"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    role = Column(SqlEnum(StoreRole), nullable=False)
    status = Column(SqlEnum(MembershipStatus), nullable=False, default=MembershipStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="memberships")
    store = relationship("Store", back_populates="memberships")


class AreaManagerStore(Base):
    __tablename__ = "area_manager_stores"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_area_manager_store"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="area_manager_stores")
    store = relationship("Store", back_populates="area_manager_links")


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="uq_flag_brand_name"),
    )

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)

    brand = relationship("Brand", back_populates="flags")
    users = relationship("UserFlag", back_populates="flag", cascade="all, delete-orphan")


class UserFlag(Base):
    __tablename__ = "user_flags"
    __table_args__ = (
        UniqueConstraint("user_id", "flag_id", name="uq_user_flag"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    flag_id = Column(Integer, ForeignKey("flags.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="flags")
    flag = relationship("Flag", back_populates="users")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=False)
    description = Column(Text)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"))
    visibility = Column(SqlEnum(CourseVisibility), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    owner_role = Column(SqlEnum(UserRole), nullable=False)
    owner_brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"))
    cover_image = Column(String(255))
    cert_template = Column(String(120))
    required_default = Column(Boolean, default=False, nullable=False)
    due_date_default = Column(Date)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    brand = relationship("Brand", foreign_keys=[brand_id], back_populates="courses")
    owner = relationship("User", back_populates="owned_courses")
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan")
    assignments = relationship("CourseAssignment", back_populates="course", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    order_index = Column(Integer, nullable=False, default=1)

    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False, default=1)

    module = relationship("Module", back_populates="lessons")
    progresses = relationship("LessonProgress", back_populates="lesson", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollment"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="lesson_progress")
    lesson = relationship("Lesson", back_populates="progresses")


class CourseAssignment(Base):
    __tablename__ = "course_assignments"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(SqlEnum(AssignmentTarget), nullable=False)
    target_id = Column(String(120), nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    due_date = Column(Date)
    is_exclusion = Column(Boolean, default=False, nullable=False)

    course = relationship("Course", back_populates="assignments")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(200), nullable=False)
    subject_type = Column(String(120), nullable=False)
    subject_id = Column(String(120), nullable=False)
    meta = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User", back_populates="audit_logs")
