from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from .models import (
    AssignmentStatus,
    AudienceDimension,
    CourseAudienceRuleType,
    CourseType,
    MembershipStatus,
    UserRole,
)


class BrandBase(BaseModel):
    name: str
    theme_primary_color: Optional[str] = None
    theme_secondary_color: Optional[str] = None
    tone: Optional[str] = None
    logo_url: Optional[str] = None


class BrandCreate(BrandBase):
    pass


class BrandRead(BrandBase):
    id: int

    class Config:
        orm_mode = True


class StoreBase(BaseModel):
    name: str
    code: str
    region: Optional[str] = None


class StoreCreate(StoreBase):
    brand_id: int


class StoreRead(StoreBase):
    id: int
    brand_id: int

    class Config:
        orm_mode = True


class FlagCreate(BaseModel):
    name: str


class FlagRead(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class MembershipCreate(BaseModel):
    store_id: int
    role: UserRole
    status: MembershipStatus = MembershipStatus.PENDING


class MembershipRead(BaseModel):
    id: int
    store_id: int
    role: UserRole
    status: MembershipStatus

    class Config:
        orm_mode = True


class UserBase(BaseModel):
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    id_number: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole
    brand_id: Optional[int] = None
    is_active: bool = True


class UserCreate(UserBase):
    memberships: List[MembershipCreate] = Field(default_factory=list)
    flag_ids: List[int] = Field(default_factory=list)


class UserRead(UserBase):
    id: int
    created_at: datetime
    memberships: List[MembershipRead] = Field(default_factory=list)
    flags: List[FlagRead] = Field(default_factory=list)

    class Config:
        orm_mode = True


class LessonCreate(BaseModel):
    title: str
    content: str
    order_index: int


class LessonRead(LessonCreate):
    id: int

    class Config:
        orm_mode = True


class ModuleCreate(BaseModel):
    title: str
    order_index: int
    lessons: List[LessonCreate]


class ModuleRead(BaseModel):
    id: int
    title: str
    order_index: int
    lessons: List[LessonRead]

    class Config:
        orm_mode = True


class CourseAudienceRuleCreate(BaseModel):
    rule_type: CourseAudienceRuleType
    dimension: AudienceDimension
    value: str


class CourseBase(BaseModel):
    title: str
    summary: str
    brand_id: Optional[int] = None
    course_type: CourseType
    required: bool = False
    due_date: Optional[date] = None
    notify_on_publish: bool = False
    modules: List[ModuleCreate]
    audience_rules: List[CourseAudienceRuleCreate] = Field(default_factory=list)


class CourseCreate(CourseBase):
    pass


class CourseRead(BaseModel):
    id: int
    title: str
    summary: str
    brand_id: Optional[int]
    course_type: CourseType
    creator_id: int
    required: bool
    due_date: Optional[date]
    notify_on_publish: bool
    created_at: datetime
    modules: List[ModuleRead]

    class Config:
        orm_mode = True


class AssignmentCreate(BaseModel):
    user_id: int
    due_date: Optional[date] = None
    required: bool = False


class AssignmentRead(BaseModel):
    id: int
    user_id: int
    status: AssignmentStatus
    due_date: Optional[date]
    required: bool
    completed_at: Optional[datetime]

    class Config:
        orm_mode = True


class AuditLogRead(BaseModel):
    id: int
    actor_id: int
    action: str
    entity_type: str
    entity_id: int
    details: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True
