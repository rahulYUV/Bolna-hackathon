"""Fetch and safely save one Bolna call execution payload."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = PROJECT_ROOT / "last_execution_payload.json"
PHONE_NUMBER_PATTERN = re.compile(r"(?<!\w)(?:\+?91[\s().-]*)?[6-9](?:[\s().-]*\d){9}(?!\w)")
SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?:api[-_]?key|secret|auth|token|password|credential)", re.IGNORECASE
)


def redact_payload(value, *, field_name: str = "", inside_secret: bool = False):
    """Redact private values without changing object keys or nesting."""
    if isinstance(value, dict):
        return {
            key: redact_payload(
                child,
                field_name=str(key),
                inside_secret=inside_secret or bool(SENSITIVE_FIELD_PATTERN.search(str(key))),
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            redact_payload(child, field_name=field_name, inside_secret=inside_secret)
            for child in value
        ]
    if inside_secret:
        return "REDACTED"

    normalized_field = re.sub(r"[^a-z]", "", field_name.lower())
    is_phone_field = any(part in normalized_field for part in ("phone", "mobile", "telephone")) or normalized_field in {
        "fromnumber", "tonumber", "usernumber", "agentnumber", "callernumber", "recipientnumber"
    }
    if is_phone_field:
        return "+91XXXXXXXXXX" if value is not None and str(value).strip() else value
    if not isinstance(value, str):
        return value

    if "recording" in normalized_field and "url" in normalized_field:
        value = value.split("?", 1)[0]
    return PHONE_NUMBER_PATTERN.sub("+91XXXXXXXXXX", value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and redact a Bolna execution payload.")
    parser.add_argument("execution_id", help="Bolna execution ID returned when the call was placed")
    args = parser.parse_args()

    env = dotenv_values(PROJECT_ROOT / ".env")
    api_key = env.get("BOLNA_API_KEY")
    if not api_key:
        print("BOLNA_API_KEY is missing or empty in the project-root .env file.", file=sys.stderr)
        return 1

    url = f"https://api.bolna.ai/executions/{quote(args.execution_id, safe='')}"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
    except httpx.RequestError:
        print("Could not connect to Bolna to fetch this execution.", file=sys.stderr)
        return 1

    if response.is_error:
        print(f"Bolna returned HTTP {response.status_code} for this execution.", file=sys.stderr)
        return 1

    try:
        payload = response.json()
    except ValueError:
        print("Bolna returned a response that was not valid JSON.", file=sys.stderr)
        return 1

    try:
        OUTPUT_PATH.write_text(
            json.dumps(redact_payload(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        print("Could not write last_execution_payload.json in the project root.", file=sys.stderr)
        return 1

    print("Saved redacted execution payload to last_execution_payload.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
