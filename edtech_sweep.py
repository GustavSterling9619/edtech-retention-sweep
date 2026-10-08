"""Retention decisions for course delivery, deadlines, and reports."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CourseDelivery(BaseModel):
    kind: Literal["course_delivery"]
    record_id: str
    status: Literal["active", "completed", "cancelled"]
    closed_at: datetime | None = None
    object_keys: list[str] = Field(default_factory=list)


class LearnerDeadline(BaseModel):
    kind: Literal["learner_deadline"]
    record_id: str
    status: Literal["open", "submitted", "waived"]
    resolved_at: datetime | None = None
    object_keys: list[str] = Field(default_factory=list)


class EducatorReport(BaseModel):
    kind: Literal["educator_report"]
    record_id: str
    status: Literal["draft", "published"]
    published_at: datetime | None = None
    object_keys: list[str] = Field(default_factory=list)


EdtechRecord = Annotated[
    Union[CourseDelivery, LearnerDeadline, EducatorReport],
    Field(discriminator="kind"),
]


class SweepRequest(BaseModel):
    as_of: datetime
    records: list[EdtechRecord]


class SweepDecision(BaseModel):
    stale_record_ids: list[str]
    delete_keys: list[str]
    retained_record_ids: list[str]


def _eligible(record: EdtechRecord, as_of: datetime) -> bool:
    if isinstance(record, CourseDelivery):
        return (
            record.status in {"completed", "cancelled"}
            and record.closed_at is not None
            and record.closed_at <= as_of - timedelta(days=365)
        )
    if isinstance(record, LearnerDeadline):
        return (
            record.status in {"submitted", "waived"}
            and record.resolved_at is not None
            and record.resolved_at <= as_of - timedelta(days=180)
        )
    return (
        record.status == "published"
        and record.published_at is not None
        and record.published_at <= as_of - timedelta(days=730)
    )


def decide_sweep(request: SweepRequest) -> SweepDecision:
    stale = [record for record in request.records if _eligible(record, request.as_of)]
    stale_ids = {record.record_id for record in stale}
    return SweepDecision(
        stale_record_ids=[record.record_id for record in stale],
        delete_keys=[key for record in stale for key in record.object_keys],
        retained_record_ids=[
            record.record_id
            for record in request.records
            if record.record_id not in stale_ids
        ],
    )
