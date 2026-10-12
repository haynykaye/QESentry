"""CSV export of the live monitor table (pure Python: no Qt, no database, easy to test)."""
import csv

from qesentry.core.timeutil import to_local

HEADERS = ["Student ID", "Name", "Section", "Category", "Assessment", "Status", "Lockdown", "Alerts",
           "Start Time", "End Time"]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise spreadsheet formulas. A student can type '=HYPERLINK(...)' as their name; Excel would run it
    when a teacher opens the file, so any text starting with = + - @ gets a leading apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _fmt(ts):
    local = to_local(ts)
    return local.strftime("%Y-%m-%d %H:%M:%S") if local else ""


def row_to_cells(row):
    """One monitor_rows() dict -> list of CSV cells in HEADERS order."""
    status = "RELEASED" if row["status"] == "RELEASED_BY_TEACHER" else row["status"]
    return [csv_safe(x) for x in (row["student_id"], (row["full_name"] or "").upper(), row["section"], row["category"],
                                  row["exam_title"], status, row["lockdown"], row["alerts"],
                                  _fmt(row["login_time"]), _fmt(row["ended_time"]))]


def export_rows(rows, path):
    """Write monitor rows to `path` (UTF-8 with BOM so Excel shows names correctly). Returns the row count."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        for r in rows:
            w.writerow(row_to_cells(r))
    return len(rows)
