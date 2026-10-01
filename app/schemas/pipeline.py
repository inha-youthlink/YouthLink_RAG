from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Profile(BaseModel):
    age: int | None = Field(default=None, ge=0)
    gender: str | None = None
    region_code: str | None = None
    marriage_status_code: str | None = None
    annual_income: int | None = Field(default=None, ge=0)
    major_code: str | None = None
    job_code: str | None = None
    school_code: str | None = None
    special_target_code: str | None = None


class PipelineInput(BaseModel):
    question: str = Field(min_length=1)
    profile: Profile = Field(default_factory=Profile)


class Chunk(BaseModel):
    chunk_id: UUID
    policy_no: str
    chunk_index: int
    chunk_type: str | None = None
    content: str
    score: float


class PolicyItem(BaseModel):
    policy_no: str
    policy_name: str
    application_start_date: date | None = None
    application_end_date: date | None = None
    application_url: str | None = None
    score: float


class PipelineOutput(BaseModel):
    answer: str
    policies: list[PolicyItem]
    trace: dict[str, Any]
