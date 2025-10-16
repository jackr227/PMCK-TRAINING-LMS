from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

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


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"


class CourseType(str, Enum):
    GLOBAL = "global"
    LOCAL = "local"


class CourseAudienceRuleType(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class AudienceDimension(str, Enum):
    BRAND = "brand"
    STORE = "store"
    ROLE = "role"
    FLAG = "flag"
    USER = "user"


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    theme_primary_color = Column(String(20))
    theme_secondary_color = Column(String(20))
    tone = Column(String(100))
    logo_url = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    stores = relationship("Store", back_populates="brand", cascade="all, delete-orphan")
    admins = relationship("User", back_populates="brand", cascade="all")


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("brand_id", "code", name="uq_store_brand_code"),)

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    code = Column(String(50), nullable=False)
    region = Column(String(120))

    brand = relationship("Brand", back_populates="stores")
    memberships = relationship("StoreMembership", back_populates="store", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"))
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)
    display_name = Column(String(120))
    id_number = Column(String(80))
    email = Column(String(120), unique=True, nullable=False)
    phone = Column(String(40))
    role = Column(SqlEnum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    brand = relationship("Brand", back_populates="admins")
    memberships = relationship("StoreMembership", back_populates="user", cascade="all, delete-orphan")
    flags = relationship("UserFlag", back_populates="user", cascade="all, delete-orphan")
    created_courses = relationship("Course", back_populates="creator")
    assignments = relationship("CourseAssignment", back_populates="user")


class StoreMembership(Base):
    __tablename__ = "store_memberships"
    __table_args__ = (UniqueConstraint("user_id", "store_id", name="uq_membership_user_store"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    role = Column(SqlEnum(UserRole), nullable=False)
    status = Column(SqlEnum(MembershipStatus), default=MembershipStatus.PENDING, nullable=False)

    user = relationship("User", back_populates="memberships")
    store = relationship("Store", back_populates="memberships")


class Flag(Base):
    __tablename__ = "flags"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)

    user_links = relationship("UserFlag", back_populates="flag", cascade="all, delete-orphan")


class UserFlag(Base):
    __tablename__ = "user_flags"
    __table_args__ = (UniqueConstraint("user_id", "flag_id", name="uq_user_flag"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    flag_id = Column(Integer, ForeignKey("flags.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="flags")
    flag = relationship("Flag", back_populates="user_links")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    title = Column(String(150), nullable=False)
    summary = Column(Text, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"))
    course_type = Column(SqlEnum(CourseType), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    due_date = Column(Date)
    notify_on_publish = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    brand = relationship("Brand")
    creator = relationship("User", back_populates="created_courses")
    modules = relationship("CourseModule", back_populates="course", cascade="all, delete-orphan")
    audience_rules = relationship("CourseAudienceRule", back_populates="course", cascade="all, delete-orphan")
    assignments = relationship("CourseAssignment", back_populates="course", cascade="all, delete-orphan")


class CourseModule(Base):
    __tablename__ = "course_modules"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(150), nullable=False)
    order_index = Column(Integer, nullable=False)

    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    module_id = Column(Integer, ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False)

    module = relationship("CourseModule", back_populates="lessons")


class CourseAudienceRule(Base):
    __tablename__ = "course_audience_rules"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    rule_type = Column(SqlEnum(CourseAudienceRuleType), nullable=False)
    dimension = Column(SqlEnum(AudienceDimension), nullable=False)
    value = Column(String(120), nullable=False)

    course = relationship("Course", back_populates="audience_rules")


class CourseAssignment(Base):
    __tablename__ = "course_assignments"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_assignment_user_course"),
    )

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(SqlEnum(AssignmentStatus), default=AssignmentStatus.ASSIGNED, nullable=False)
    due_date = Column(Date)
    required = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime)

    course = relationship("Course", back_populates="assignments")
    user = relationship("User", back_populates="assignments")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(120), nullable=False)
    entity_type = Column(String(120), nullable=False)
    entity_id = Column(Integer, nullable=False)
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")
