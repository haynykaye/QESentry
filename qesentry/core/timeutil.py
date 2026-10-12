"""UTC helpers shared by the database layer, alerts and the CSV exporter (no third-party imports)."""
import datetime as dt


def utcnow():
    """Current time as a naive UTC datetime - the format stored in every database column."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def to_local(value):
    """Naive-UTC datetime from the database -> local datetime for display (None passes through)."""
    if value is None:
        return None
    return value.replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)


def to_utc(value):
    """Local datetime typed by the teacher (naive) -> naive UTC for the database (None passes through)."""
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)      # a naive value is read as local time


def format_local(value):
    """Naive-UTC datetime from the database -> text such as 'Oct 12, 2026 8:00 AM' in local time ('' for None)."""
    local = to_local(value)
    if local is None:
        return ""
    hour = local.hour % 12 or 12
    return f"{local:%b} {local.day}, {local.year} {hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def format_schedule(value):
    """Naive-UTC datetime from the database -> 'Mar 8, 2026 · 4:30 PM' (local time) for the Schedule column ('' for None)."""
    local = to_local(value)
    if local is None:
        return ""
    hour = local.hour % 12 or 12
    return f"{local:%b} {local.day}, {local.year} · {hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
