from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Diet = Literal["unset", "omnivore", "vegetarian"]
CompetitionStatus = Literal["draft", "open", "closed", "ended", "cancelled"]
RegistrationStatus = Literal["confirmed", "waitlisted", "cancelled"]


class PublicMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    distinguishing_note: str | None
    level: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class AuthResponse(BaseModel):
    username: str
    display_name: str | None = None
    csrf_token: str
    admin_id: str
    version: int
    must_change_password: bool


class MemberInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    distinguishing_note: str | None = Field(default=None, max_length=100)
    legacy_number: str | None = Field(default=None, max_length=50)
    level: int = Field(ge=1, le=10)
    diet: Diet = "omnivore"
    is_active: bool = True

    @field_validator("name", "distinguishing_note", "legacy_number")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str | None) -> str:
        if not value:
            raise ValueError("姓名不可空白")
        return value


class MemberCreate(MemberInput):
    pass


class MemberUpdate(MemberInput):
    version: int = Field(ge=1)


class AdminMember(MemberInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    created_at: datetime
    updated_at: datetime


class AuditEntry(BaseModel):
    id: str
    action: str
    changes: dict[str, dict[str, object]]
    admin_username: str
    created_at: datetime


class CompetitionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    competition_date: date
    capacity: int = Field(ge=1, le=10000)
    registration_deadline: datetime
    notes: str | None = Field(default=None, max_length=5000)
    status: CompetitionStatus = "draft"
    registration_mode: Literal["individual", "doubles"] = "individual"
    doubles_min_total_level: int | None = Field(default=None, ge=2, le=20, strict=True)

    @field_validator("name", "notes")
    @classmethod
    def normalize_competition_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("name")
    @classmethod
    def competition_name_required(cls, value: str | None) -> str:
        if not value:
            raise ValueError("比賽名稱不可空白")
        return value

    @field_validator("registration_deadline")
    @classmethod
    def deadline_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("報名截止時間必須包含時區")
        return value

    @model_validator(mode="after")
    def deadline_not_after_competition(self):
        if self.registration_deadline.date() > self.competition_date:
            raise ValueError("報名截止時間不可晚於比賽日期")
        return self


class CompetitionCreate(CompetitionInput):
    @model_validator(mode="after")
    def default_doubles_rule(self):
        if self.registration_mode == "doubles" and "doubles_min_total_level" not in self.model_fields_set:
            self.doubles_min_total_level = 10
        return self


class CompetitionUpdate(CompetitionInput):
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class CompetitionSummary(BaseModel):
    confirmed: int
    waitlisted: int
    cancelled: int
    remaining: int
    pending_promotions: int
    diet_counts: dict[Diet, int]
    level_counts: dict[int, int]
    competition_level_counts: dict[int, int]


class DoublesSummary(BaseModel):
    waiting_partner: int
    pending: int
    confirmed: int
    waitlisted: int
    cancelled: int
    remaining: int
    pending_promotions: int


class AdminCompetition(CompetitionInput):
    deleted_at: datetime | None
    id: str
    version: int
    created_at: datetime
    updated_at: datetime
    effective_registration_open: bool
    summary: CompetitionSummary
    doubles_summary: DoublesSummary | None = None


class RegistrationMember(BaseModel):
    id: str
    name: str
    distinguishing_note: str | None
    level: int
    diet: Diet


class RegistrationCreate(BaseModel):
    member_id: str = Field(min_length=1, max_length=36)
    diet: Diet | None = None
    reason: str | None = Field(default=None, max_length=500)
    request_id: str = Field(min_length=8, max_length=64)


class RegistrationMutation(BaseModel):
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)
    request_id: str = Field(min_length=8, max_length=64)


class RegistrationDietUpdate(RegistrationMutation):
    diet: Diet


class RegistrationLevelUpdate(RegistrationMutation):
    model_config = ConfigDict(extra="forbid")
    competition_level: int = Field(ge=1, le=10, strict=True)
    @field_validator("reason")
    @classmethod
    def optional_level_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class AdminRegistration(BaseModel):
    id: str
    competition_id: str
    member_id: str
    member_name: str
    distinguishing_note: str | None
    status: RegistrationStatus
    diet: Diet
    hard_level_snapshot: int
    competition_level: int
    queue_sequence: int
    version: int
    created_by_username: str
    updated_by_username: str
    created_at: datetime
    updated_at: datetime


class CompetitionDetail(BaseModel):
    competition: AdminCompetition
    registrations: list[AdminRegistration]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicRegistrationCreate(StrictInput):
    member_id: str = Field(min_length=1, max_length=36)
    diet: Literal["omnivore", "vegetarian"]
    request_id: str = Field(min_length=8, max_length=64)
    turnstile_token: str | None = Field(default=None, max_length=2048)


class PublicCandidate(BaseModel):
    id: str
    name: str
    distinguishing_note: str | None


class PublicCompetition(BaseModel):
    id: str
    name: str
    competition_date: date
    registration_deadline: datetime
    notes: str | None
    capacity: int
    confirmed: int
    waitlisted: int
    remaining: int
    registration_mode: Literal["individual", "doubles"] = "individual"
    doubles_min_total_level: int | None = None
    doubles_summary: DoublesSummary | None = None
    effective_registration_open: bool = True


class PublicRegistrationResult(BaseModel):
    status: RegistrationStatus
    member_name: str
    distinguishing_note: str | None
    diet: Diet


class CsrfResponse(BaseModel):
    csrf_token: str


class ActorAuditEntry(BaseModel):
    id: str
    action: str
    actor_kind: Literal["admin", "public", "system"]
    actor_name: str
    created_at: datetime
    registration_id: str
    member_name: str
    distinguishing_note: str | None
    queue_sequence: int
    reason: str | None
    changes: dict[str, dict[str, object]]


DoublesStatus = Literal["waiting_partner", "pending", "confirmed", "waitlisted", "cancelled"]


class DoublesCreate(StrictInput):
    member_ids: list[str] = Field(min_length=1, max_length=2)
    request_id: str = Field(min_length=8, max_length=64)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("member_ids")
    @classmethod
    def distinct_members(cls, value):
        if len(set(value)) != len(value) or any(not mid or len(mid)>36 for mid in value):
            raise ValueError("請選擇一或兩位不同會員")
        return value


class PublicDoublesCreate(StrictInput):
    member_ids: list[str] = Field(min_length=1, max_length=2)
    request_id: str = Field(min_length=8, max_length=64)
    turnstile_token: str | None = Field(default=None, max_length=2048)
    _distinct = field_validator("member_ids")(DoublesCreate.distinct_members.__func__)


class DoublesMutation(StrictInput):
    version: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class PublicDoublesMember(BaseModel):
    member_id: str
    name: str
    distinguishing_note: str | None
    level_snapshot: int


class PublicDoublesEntry(BaseModel):
    id: str
    status: DoublesStatus
    sequence: int
    members: list[PublicDoublesMember]
    total_level: int | None
    min_total_level: int | None
    meets_level_rule: bool | None


class AdminDoublesEntry(PublicDoublesEntry):
    version: int
    created_at: datetime
    updated_at: datetime


class PublicDoublesResult(BaseModel):
    entry: PublicDoublesEntry


class AdminDoublesResult(BaseModel):
    entry: AdminDoublesEntry
    waiting_entries: list[AdminDoublesEntry] = Field(default_factory=list)


class PublicDoublesRoster(BaseModel):
    competition: PublicCompetition
    entries: list[PublicDoublesEntry]


class AdminDoublesRoster(BaseModel):
    competition: AdminCompetition
    entries: list[AdminDoublesEntry]


class DoublesHistoryEntry(BaseModel):
    id: str
    entry_id: str
    action: str
    actor_kind: Literal["admin", "public", "system"]
    actor_name: str
    reason: str | None
    changes: dict[str, object]
    created_at: datetime
