"""Conversions between ServiceNow's string values and stored Python values, per field type (see schema.py)."""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sim.vendors.servicenow.schema import Field

SYS_ID = re.compile(r"^[0-9a-f]{32}$")
_GS_DATE = re.compile(r"^javascript:gs\.dateGenerate\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)$")


class BadValue(ValueError):
    pass


def parse_datetime(text: str) -> datetime:
    """'2026-10-07 09:00:00', '2026-10-07', or javascript:gs.dateGenerate('2026-10-07','09:00:00'); UTC."""
    text = text.strip()
    if m := _GS_DATE.match(text):
        text = f"{m.group(1)} {m.group(2)}"
    try:
        v = datetime.fromisoformat(text.replace("T", " ").replace("Z", "+00:00"))
    except ValueError as e:
        raise BadValue(f"Invalid date/time: {text}") from e
    return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)


def parse_duration(text: str) -> int:
    """'1970-01-01 02:30:00', '02:30:00' or seconds → seconds."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    m = re.match(r"^(?:1970-01-(\d\d) )?(\d+):(\d\d):(\d\d)$", text)
    if not m:
        raise BadValue(f"Invalid duration: {text}")
    days = int(m.group(1)) - 1 if m.group(1) else 0
    return days * 86400 + int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))


def to_db(f: Field, raw: Any) -> Any:
    """A value from a request body or query → the stored value. Empty means NULL (or '' for strings)."""
    if raw is None:
        return None
    if isinstance(raw, dict):  # {"value": ..., "display_value": ...} as some clients echo back
        raw = raw.get("value")
    text = str(raw).strip() if not isinstance(raw, bool) else ("true" if raw else "false")
    if f.type in ("string",):
        return str(raw)
    if text == "":
        return None
    try:
        if f.type in ("integer", "choice"):
            return int(Decimal(text))
        if f.type == "decimal":
            return Decimal(text.replace(",", ""))
    except InvalidOperation as e:
        raise BadValue(f"Invalid number for {f.name}: {text}") from e
    if f.type == "boolean":
        return text.lower() in ("true", "1", "yes")
    if f.type in ("glide_date_time", "glide_date"):
        return parse_datetime(text)
    if f.type == "glide_duration":
        return parse_duration(text)
    return text  # reference: sys_id (resolved by the caller)


def to_value(f: Field, v: Any) -> str:
    """Stored value → ServiceNow's value string."""
    if v is None:
        return ""
    if f.type == "boolean":
        return "true" if v else "false"
    if f.type == "glide_date_time":
        return v.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    if f.type == "glide_date":
        return v.astimezone(UTC).strftime("%Y-%m-%d")
    if f.type == "glide_duration":
        d, rest = divmod(int(v), 86400)
        return f"1970-01-{d + 1:02d} {rest // 3600:02d}:{rest % 3600 // 60:02d}:{rest % 60:02d}"
    if f.type == "decimal":
        return f"{Decimal(v):.2f}"
    return str(v)


def to_display(f: Field, v: Any) -> str:
    """Stored value → display value (references are resolved by the caller)."""
    if v is None:
        return ""
    if f.type == "choice":
        return (f.choices or {}).get(int(v), str(v))
    if f.type == "glide_duration":
        d, rest = divmod(int(v), 86400)
        parts = [(d, "Day"), (rest // 3600, "Hour"), (rest % 3600 // 60, "Minute"), (rest % 60, "Second")]
        return " ".join(f"{n} {unit}{'s' if n != 1 else ''}" for n, unit in parts if n) or "0 Seconds"
    if f.type == "decimal":
        return f"{Decimal(v):,.2f}"
    if f.type == "integer":
        return f"{int(v):,}"
    return to_value(f, v)
