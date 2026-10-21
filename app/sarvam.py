"""Sarvam AI client for Hisaab.

Sarvam's `sarvam-105b-conversations` model is a strong Hindi/Hinglish model,
which makes it a good fit for the outcome-extraction step: reading a Bolna
call transcript and pulling out {outcome, promise_date, notes}.

The SDK reads SARVAM_API_KEY from the environment on its own, but we pass it
explicitly so a missing key fails with a clear message instead of an opaque
SDK error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from sarvamai import SarvamAI

from app.config import SARVAM_API_KEY

MODEL = "sarvam-105b-conversations"

# Reference date for resolving relative dates like "friday" or "agle hafte".
# The Bolna call happens now, so "now" is the right reference point - but it
# is injected into the prompt rather than left to the model's training cutoff.
TODAY = date.today()


class Outcome(str, Enum):
    """The four ways a Hisaab call can end."""

    PROMISED = "promised"
    NO_MONEY_NOW = "no_money_now"
    DISPUTED = "disputed"
    NO_ANSWER = "no_answer"
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    outcome: Outcome
    promise_date: date | None
    notes: str
    claimed_amount: int | None = None
    raw: dict[str, Any] | None = None


SYSTEM_PROMPT = """\
You extract a payment outcome from a phone call transcript between a shop's
voice agent and a customer who owes money (udhaar) at a kirana store in India.

The call is in Hindi or Hinglish. The transcript is ASR output: it may contain
spelling errors, missing punctuation, and English words mixed into Hindi
script. Read it for meaning, not for exact spelling.

The four possible outcomes:

- "promised": the customer gave a date or timeframe to pay ("Friday ko
  dunga", "agle hafte", "12 ko de dunga", "salary aane ke baad").
- "no_money_now": the customer cannot pay yet and gave no date. The customer
  says they have no money, or the call ended without any commitment.
- "disputed": the customer says the amount is wrong ("amount galat hai",
  "Rs 300 hi hai"), that they already paid, or that the debt is not theirs.
  A disagreement about the amount is ALWAYS disputed, even if the customer
  also mentions a date. Disputed wins over promised.
- "no_answer": nobody spoke - an empty transcript, or the customer never
  picked up. Use this when there is no substantive customer speech at all.

Rules:

- The amount in the transcript is the shop's ledger amount. If the customer
  claims a DIFFERENT amount, that is a dispute - record the claim in
  claimed_amount, and set outcome to "disputed". Do not "correct" the ledger.
- promise_date: the date the customer committed to paying, resolved to a real
  calendar date. If the customer gave a relative reference ("friday",
  "agle hafte", "next Tuesday"), resolve it against today's date. If the
  customer gave a vague non-date timeframe ("jaldi", "baad mein", "jab
  paise aayenge"), set promise_date to null and keep the timeframe in notes.
- If the customer gave a date, but it is impossible or absurd (a date in the
  past that they described as future, or a year far in the future), set
  promise_date to null and explain in notes.
- If the customer gave both a date and a reason, keep both in notes.
- notes: one short sentence, in the customer's own words where possible,
  in Hinglish. What did they actually say? This is shown to the shopkeeper.
  Do not write an English summary of the whole call. Do not include the
  amount in notes - it has its own field.
- Never invent a date the customer did not say. A missing date is null, not
  a guess.
"""


def get_client() -> SarvamAI:
    """Build a Sarvam client from the environment."""
    if not SARVAM_API_KEY:
        raise RuntimeError(
            "SARVAM_API_KEY is not set. Add it to .env and restart the app."
        )
    return SarvamAI(api_subscription_key=SARVAM_API_KEY)


def _build_schema() -> dict[str, Any]:
    """JSON schema for the structured output.

    Every field is required so the API always returns the same shape; "null"
    is expressed as an empty string for the date, and as 0 for the amount.
    """
    return {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": [
                    Outcome.PROMISED.value,
                    Outcome.NO_MONEY_NOW.value,
                    Outcome.DISPUTED.value,
                    Outcome.NO_ANSWER.value,
                ],
            },
            "promise_date": {
                "type": "string",
                "description": (
                    "Payment date as YYYY-MM-DD, or an empty string if the "
                    "customer gave no resolvable date."
                ),
            },
            "notes": {
                "type": "string",
                "description": (
                    "One short Hinglish sentence capturing what the customer "
                    "actually said. Empty string if nothing was said."
                ),
            },
            "claimed_amount": {
                "type": "integer",
                "description": (
                    "The amount the customer claimed, in rupees, if they "
                    "disputed the ledger amount. 0 if they did not dispute it."
                ),
            },
        },
        "required": ["outcome", "promise_date", "notes", "claimed_amount"],
        "additionalProperties": False,
    }


def _resolve_relative_date(reference: str) -> date | None:
    """Resolve a relative date phrase in Hinglish against today's date.

    The model is asked to resolve dates itself, but this is a cheap safety
    net for the common cases the model sometimes leaves alone. Returns None
    if the phrase is not one we recognise.
    """
    text = reference.strip().lower()
    weekday = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
        "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3,
        "shukravar": 4, "shanivar": 5, "ravivar": 6,
    }
    days_ahead = {"aaj": 0, "aj": 0, "kal": 1, "parso": 2, "agle hafte": 7}

    for name, offset in days_ahead.items():
        if name in text:
            return TODAY + timedelta(days=offset)

    for name, index in weekday.items():
        if name in text:
            # Upcoming occurrence, including today if the customer means it.
            delta = (index - TODAY.weekday()) % 7
            return TODAY + timedelta(days=delta)

    return None


def _parse_date(value: str) -> date | None:
    """Parse the model's promise_date. Handles ISO dates and relative phrases."""
    value = (value or "").strip()
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass

    return _resolve_relative_date(value)


def extract_outcome(
    transcript: str,
    *,
    amount_due: int | None = None,
    call_status: str | None = None,
) -> ExtractionResult:
    """Extract {outcome, promise_date, notes} from a call transcript.

    transcript:   the "transcript" field from the Bolna execution.
    amount_due:   the ledger amount, so the model can spot a disputed amount.
    call_status:  the Bolna execution status. "no-answer" and friends map
                  straight to Outcome.NO_ANSWER without calling the model.
    """
    # Nothing to extract from a call that never connected - skip the API call.
    if call_status in {"no-answer", "busy", "canceled", "stopped", "error", "failed"}:
        return ExtractionResult(
            outcome=Outcome.NO_ANSWER,
            promise_date=None,
            notes="",
        )

    if not transcript or not transcript.strip():
        return ExtractionResult(
            outcome=Outcome.NO_ANSWER,
            promise_date=None,
            notes="",
        )

    client = get_client()

    amount_line = (
        f"\n\nThe shop's ledger amount for this customer is Rs {amount_due}. "
        "If the customer states a different amount, that is a dispute."
        if amount_due is not None
        else ""
    )

    today_line = TODAY.strftime("%Y-%m-%d (%A)")

    response = client.chat.completions(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Today is {today_line}. Resolve relative dates against "
                    f"this date.{amount_line}\n\n"
                    f"Call transcript:\n\n{transcript}"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "udhaar_outcome",
                "description": "Payment outcome extracted from a udhaar call",
                "schema": _build_schema(),
                "strict": True,
            },
        },
    )

    text = response.choices[0].message.content or ""
    if not text:
        return ExtractionResult(
            outcome=Outcome.UNKNOWN,
            promise_date=None,
            notes="",
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ExtractionResult(
            outcome=Outcome.UNKNOWN,
            promise_date=None,
            notes="",
            raw={"unparsed": text},
        )

    try:
        outcome = Outcome(data["outcome"])
    except (KeyError, ValueError):
        outcome = Outcome.UNKNOWN

    promise_date = _parse_date(data.get("promise_date", ""))

    claimed = data.get("claimed_amount") or 0
    claimed_amount = int(claimed) if claimed else None

    return ExtractionResult(
        outcome=outcome,
        promise_date=promise_date,
        notes=(data.get("notes") or "").strip(),
        claimed_amount=claimed_amount,
        raw=data,
    )
