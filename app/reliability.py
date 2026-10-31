from __future__ import annotations

import hmac
import json
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CallState(StrEnum):
    QUEUED = "queued"
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


ALLOWED_CALL_TRANSITIONS: dict[str, set[str]] = {
    CallState.QUEUED: {CallState.INITIATED, CallState.CANCELLED, CallState.FAILED},
    CallState.INITIATED: {CallState.IN_PROGRESS, CallState.COMPLETED, CallState.NO_ANSWER, CallState.BUSY, CallState.FAILED, CallState.TIMED_OUT, CallState.CANCELLED},
    CallState.IN_PROGRESS: {CallState.COMPLETED, CallState.NO_ANSWER, CallState.BUSY, CallState.FAILED, CallState.TIMED_OUT, CallState.CANCELLED},
    CallState.COMPLETED: set(),
    CallState.NO_ANSWER: set(),
    CallState.BUSY: set(),
    CallState.FAILED: set(),
    CallState.TIMED_OUT: set(),
    CallState.CANCELLED: set(),
}


def can_transition(current: str, target: str) -> bool:
    return current == target or target in ALLOWED_CALL_TRANSITIONS.get(current, set())


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promise_date: date | None = None
    promise_amount: float | None = Field(default=None, gt=0)
    dispute: bool = False
    customer_requested_no_calls: bool = False


def parse_extraction(value: Any) -> Extraction:
    if isinstance(value, str):
        value = json.loads(value)
    return Extraction.model_validate(value)


def validate_promise(
    promise_date: date | None,
    promise_amount: float | None,
    amount_due: float,
    *,
    today: date,
) -> tuple[bool, bool]:
    date_valid = promise_date is None or today <= promise_date <= today + timedelta(days=60)
    amount_valid = promise_amount is None or 0 < promise_amount <= amount_due
    return date_valid, amount_valid


def constant_time_equal(left: str | None, right: str | None) -> bool:
    return bool(left and right and hmac.compare_digest(left, right))


def bolna_status_to_state(status: str) -> str:
    return {
        "queued": CallState.QUEUED,
        "initiated": CallState.INITIATED,
        "ringing": CallState.INITIATED,
        "in-progress": CallState.IN_PROGRESS,
        "call-disconnected": CallState.IN_PROGRESS,
        "completed": CallState.COMPLETED,
        "no-answer": CallState.NO_ANSWER,
        "busy": CallState.BUSY,
        "failed": CallState.FAILED,
        "error": CallState.FAILED,
    }.get(status.lower(), CallState.IN_PROGRESS)
