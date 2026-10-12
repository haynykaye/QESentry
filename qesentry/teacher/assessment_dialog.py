"""New / Edit Assessment dialog (Title, Category, Google Form Link, Target Section(s), optional open / close
schedule) and the Re-Open dialog (pick a new schedule, or none)."""
from datetime import datetime, timedelta

from PyQt6.QtCore import QDate, Qt, QTime, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qesentry.core import db
from qesentry.core.schedule import schedule_problem
from qesentry.core.timeutil import format_local, to_local, to_utc
from qesentry.core.form_url import InvalidFormUrl
from qesentry.ui.forms import FormDialog
from qesentry.core.sections import SECTION_HINT, validate_sections
from qesentry.core.validators import BAD_FORM_URL, SECTIONS_HELP, form_url_check
from qesentry.ui.pickers import DateField, TimeField, ToggleSwitch
from qesentry.ui.theme import StyledComboBox, set_state


# ----------------------------------------------------------------------------- optional open / close schedule
SCHEDULE_HELP = ("Turn on Schedule assessment to choose when students can start and when it closes. "
                 "Leave it off to keep the assessment open until you close it yourself.")
REOPEN_HELP = ("Turn on Schedule assessment to choose a new opening and closing time. "
               "Leave it off to re-open it now with no schedule.")


def _next_5_minutes(value):
    """`value` rounded up to the next multiple of 5 minutes (a tidy default for a new time)."""
    value = value.replace(second=0, microsecond=0)
    return value + timedelta(minutes=(5 - value.minute % 5) % 5 or 5)


class _TimeRow(QWidget):
    """Opens / Closes label + date field + time field."""
    changed = pyqtSignal()

    def __init__(self, label):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.caption = QLabel(label)
        self.caption.setMinimumWidth(52)
        self.date = DateField()
        self.time = TimeField()
        lay.addWidget(self.caption)
        lay.addWidget(self.date, 5)
        lay.addWidget(self.time, 4)
        self.date.changed.connect(self.changed)
        self.time.changed.connect(self.changed)

    def value(self):
        """Local datetime (to the minute)."""
        d, t = self.date.date(), self.time.time()
        return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())

    def set_value(self, value):
        self.date.setDate(QDate(value.year, value.month, value.day))
        self.time.setTime(QTime(value.hour, value.minute))


class ScheduleBox(QWidget):
    """'Schedule assessment' switch. Off = no schedule (open until the teacher closes it). On = an Opens and a
    Closes date + time. Everything typed here is local time; values_utc() gives what the database stores."""
    changed = pyqtSignal()

    def __init__(self, original_closes_local=None):
        super().__init__()
        self._loading = False
        self._original_closes = original_closes_local.replace(second=0, microsecond=0) if original_closes_local else None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.switch = ToggleSwitch()
        self.switch_label = QLabel("Schedule assessment")
        self.switch_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_label.mousePressEvent = lambda _e: self.switch.toggle()          # the words toggle it too
        head.addWidget(self.switch)
        head.addWidget(self.switch_label)
        head.addStretch(1)
        lay.addLayout(head)

        self.rows = QWidget()
        rl = QHBoxLayout(self.rows)
        rl.setContentsMargins(12, 0, 0, 0)
        rl.setSpacing(14)
        rail = QFrame()
        rail.setObjectName("PopupRule")                      # thin grey vertical line on the left
        rail.setFixedWidth(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.opens, self.closes = _TimeRow("Opens"), _TimeRow("Closes")
        col.addWidget(self.opens)
        col.addWidget(self.closes)
        rl.addWidget(rail)
        rl.addLayout(col, 1)
        self.rows.setVisible(False)
        lay.addWidget(self.rows)

        self.msg = QLabel(SCHEDULE_HELP)
        self.msg.setObjectName("Muted")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)

        self.switch.toggled.connect(self._toggled)
        self.opens.changed.connect(self.changed)
        self.closes.changed.connect(self.changed)

    def _toggled(self, on):
        self.rows.setVisible(on)
        if on and not self._loading:                         # offer sensible times: soon, and an hour later
            start = _next_5_minutes(datetime.now())
            self.opens.set_value(start)
            self.closes.set_value(start + timedelta(hours=1))
        self.changed.emit()

    def is_scheduled(self):
        return self.switch.isChecked()

    def set_utc(self, opens_at, closes_at):
        """Fill from database values (naive UTC). With neither value the switch stays off."""
        self._loading = True
        try:
            if opens_at is None and closes_at is None:
                self.switch.setChecked(False)
                return
            now = datetime.now().replace(second=0, microsecond=0)
            opens, closes = to_local(opens_at), to_local(closes_at)
            if closes is None:                                # older one-sided schedules: fill the missing side
                closes = opens + timedelta(hours=1)
            if opens is None:
                opens = min(now, closes - timedelta(hours=1))
            self.opens.set_value(opens)
            self.closes.set_value(closes)
            self.switch.setChecked(True)
        finally:
            self._loading = False

    def values_utc(self):
        """(opens_at, closes_at) as naive UTC for the database; (None, None) while the switch is off."""
        if not self.is_scheduled():
            return None, None
        return to_utc(self.opens.value()), to_utc(self.closes.value())

    def problem(self):
        """A sentence describing what is wrong with the chosen times, or ''."""
        if not self.is_scheduled():
            return ""
        closes = self.closes.value()
        unchanged = closes == self._original_closes           # editing a due assessment is allowed
        return schedule_problem(self.opens.value(), closes, datetime.now(), closing_must_be_future=not unchanged)


# ----------------------------------------------------------------------------- compact modals
class AssessmentDialog(FormDialog):
    """Create or edit an exam / quiz: Title, Category, Google Form Link, Target Section(s), optional schedule.
    On success: .exam. The button stays grey until the title is filled and the link, sections and times are valid."""

    def __init__(self, teacher, parent=None, exam=None):
        super().__init__(parent, "Edit Assessment" if exam else "New Assessment",
                         "Update the details below. Changes apply to students who log in next." if exam
                         else "Fill out the details below to publish a new assessment to the student portal.")
        self.teacher, self.exam, self._editing = teacher, None, exam
        self.title_f = self.add_field("Title", "e.g., Midterm – Data Structures")
        self.category = StyledComboBox()
        self.category.addItems(db.CATEGORIES)
        self.add_widget_field("Category", self.category)
        self.url_f = self.add_field("Google Form Link", "https://docs.google.com/forms/d/e/…/viewform")
        self.url_f.edit.setClearButtonEnabled(True)
        self._url_ok, self._url_focused = False, False
        self.url_f.edit.focused.connect(lambda: self._url_focus(True))
        self.url_f.edit.blurred.connect(lambda: self._url_focus(False))
        self.sec_f = self.add_field("Target Section(s)", "e.g., BSIT 3-1, BSIT 3-1N, BSCS 2-2")
        self.sched = ScheduleBox(to_local(exam["closes_at"]) if exam else None)
        self.add_widget_field("Schedule (optional)", self.sched)
        self.note = self.add_message()
        self.err = self.add_message()
        self.ok_btn = self.add_actions("Save Changes" if exam else "Create Assessment", ok_slot=self._save)
        self.ok_btn.setEnabled(False)

        if exam:
            self.title_f.edit.setText(exam["title"])
            self.category.setCurrentText(exam["category"])
            self.url_f.edit.setText(exam["form_url"])
            self.sec_f.edit.setText(", ".join(exam["sections"]))
            self.sched.set_utc(exam["opens_at"], exam["closes_at"])
            if exam.get("students"):
                self.say(self.note, f"{exam['students']} student(s) already joined. Changes apply to new logins; "
                                    "students inside keep the form they loaded.", "")
        self.title_f.edit.textChanged.connect(self._validate)
        self.url_f.edit.textChanged.connect(self._validate)
        self.sec_f.edit.textChanged.connect(self._validate)
        self.sched.changed.connect(self._validate)
        self._validate()
        self.title_f.edit.setFocus()

    def _url_focus(self, focused):
        self._url_focused = focused
        self._paint_url()

    def _paint_url(self):
        """Google Form box: red outline + message while the link is wrong; green outline (+ tint) only while a valid
        link is being edited with the box focused; plain neutral grey otherwise (e.g. after clicking Title)."""
        text = self.url_f.edit.text()
        if text.strip() and not self._url_ok:
            set_state(self.url_f.edit, "invalid")
            self.say(self.url_f.msg, BAD_FORM_URL, "error")
        elif self._url_ok and self._url_focused:
            set_state(self.url_f.edit, "valid")
            self.say(self.url_f.msg, "✓ Valid Google Form link.", "ok")
        else:
            set_state(self.url_f.edit, "")
            self.say(self.url_f.msg, "", "")

    def _validate(self):
        self._url_ok, _msg = form_url_check(self.url_f.edit.text())
        url_ok = self._url_ok
        self._paint_url()
        _sections, bad = validate_sections(self.sec_f.edit.text())
        if bad:                                              # red only when wrong; no colour when correct
            set_state(self.sec_f.edit, "invalid")
            self.say(self.sec_f.msg, f"{', '.join(bad)} is not accepted. {SECTION_HINT}", "error")
        else:
            set_state(self.sec_f.edit, "")
            self.say(self.sec_f.msg, SECTIONS_HELP, "hint")
        problem = self.sched.problem()
        if problem:
            self.say(self.sched.msg, problem, "error")
        else:
            self.say(self.sched.msg, SCHEDULE_HELP, "hint")
        if self.err.isVisible():
            self.say(self.err, "", "")
        self.ok_btn.setEnabled(url_ok and not bad and not problem and bool(self.title_f.edit.text().strip()))

    def _save(self):
        args = (self.title_f.edit.text(), self.category.currentText(), self.url_f.edit.text(), self.sec_f.edit.text(),
                *self.sched.values_utc())
        try:
            if self._editing:
                self.exam = db.update_exam(self._editing["id"], self.teacher["id"], *args)
            else:
                self.exam = db.create_exam(self.teacher["id"], *args)
        except (InvalidFormUrl, ValueError, db.DatabaseError) as e:
            self.say(self.err, str(e), "error")
            return
        self.accept()


class ReopenDialog(FormDialog):
    """Re-Open a closed assessment. The teacher may give it a new opening / closing date and time, or tick nothing
    to re-open it right away with no schedule. On accept: .opens_at / .closes_at (naive UTC, None where not set)."""

    def __init__(self, exam, parent=None):
        due = exam["status"] == "ACTIVE" and exam["closes_at"] is not None
        sub = (f"“{exam['title']}” closed automatically on {format_local(exam['closes_at'])}." if due
               else f"“{exam['title']}” is closed.") + " Choose how it should open again."
        super().__init__(parent, "Re-Open Assessment", sub)
        self.opens_at = self.closes_at = None
        self.sched = ScheduleBox()
        self.add_widget_field("Schedule (optional)", self.sched)
        self.ok_btn = self.add_actions("Re-Open", ok_slot=self._accept)
        self.sched.changed.connect(self._validate)
        self._validate()

    def _validate(self):
        problem = self.sched.problem()
        self.say(self.sched.msg, problem or REOPEN_HELP, "error" if problem else "hint")
        self.ok_btn.setEnabled(not problem)

    def _accept(self):
        self.opens_at, self.closes_at = self.sched.values_utc()
        self.accept()
