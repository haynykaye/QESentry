"""Sorting and filtering for the teacher dashboard tables (pure Python, no Qt, so it is easy to unit-test).

Live Monitor rows   sort by  "name" | "login" (login time) | "submitted" (submitted time)
Assessments         sort by  "title" | "created" (date created); filter by category and state (OPEN / SCHEDULED / CLOSED)
"""
from datetime import datetime

LIVE_SORT_KEYS = ("name", "login", "submitted")
EXAM_SORT_KEYS = ("title", "created")


def sort_live_rows(rows, key="login", ascending=False):
    """Return the live-monitor rows ordered by `key`. Students who have not submitted yet always sit at the
    bottom of a 'submitted' sort, whichever direction is chosen."""
    if key == "name":
        return sorted(rows, key=lambda r: ((r["full_name"] or "").casefold(), r["student_id"] or ""), reverse=not ascending)
    if key == "submitted":
        done = sorted((r for r in rows if r.get("submitted_time")), key=lambda r: r["submitted_time"], reverse=not ascending)
        return done + [r for r in rows if not r.get("submitted_time")]
    return sorted(rows, key=lambda r: r["login_time"] or datetime.min, reverse=not ascending)


def filter_exams(exams, search="", category=None, status=None):
    """Keep the assessments whose title contains `search` (case-insensitive) and that match the category and the
    state (OPEN / SCHEDULED / CLOSED - a due assessment counts as CLOSED)."""
    needle = (search or "").strip().casefold()
    return [x for x in exams
            if (not needle or needle in x["title"].casefold())
            and (not category or x["category"] == category)
            and (not status or x["state"] == status)]


def sort_exams(exams, key="created", ascending=False):
    """Return the assessments ordered by title (A-Z) or by the date they were created."""
    if key == "title":
        return sorted(exams, key=lambda x: (x["title"].casefold(), x["id"]), reverse=not ascending)
    return sorted(exams, key=lambda x: x["created_at"] or datetime.min, reverse=not ascending)
