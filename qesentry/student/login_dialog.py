"""Student login window (Student Portal).

StudentLoginDialog collects Student ID, Full Name, Section and the assessment (pick an open one, or paste its
Google Form link), runs the pre-flight checks (no banned apps, conditions accepted), then logs the student into
the `student_logins` table with status ACTIVE. On success the dialog exposes:
    .student_id  .full_name  .section  .login_id  .exam   (the assessment dict: form_url / title / category ...)
If the student presses "Back" (or closes the window) `.went_back` is True.

Layout: header and footer are fixed; the form between them scrolls, so the Start button is always reachable,
whatever the screen height or display scaling.
"""
import html
import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from qesentry.core import db
from qesentry.ui.forms import BUTTON_HEIGHT, GAP_FIELD, GAP_LABEL_INPUT, GAP_SUBTITLE_BODY, GAP_TITLE_SUBTITLE, MARGINS
from qesentry.core.form_url import InvalidFormUrl, format_form_url
from qesentry.ui.theme import (INSTITUTION, MAROON, SUCCESS, CheckRow, FocusLineEdit, fit_window, ghost, make_header, StyledComboBox,
                   repolish, scroll_area, secondary, set_feedback, set_state)

MANUAL = -1          # combo "userData" meaning "I'll paste the link myself"


def normalize_student_id(text):
    """Trim whitespace and upper-case, so '2022-01234-mn-0 ' becomes '2022-01234-MN-0'."""
    return (text or "").strip().upper()


class StudentLoginDialog(QDialog):
    """Student ID / name / section / assessment + pre-flight (prohibited apps, consent)."""

    def __init__(self, cfg, scan):
        super().__init__()
        self.cfg = cfg
        self.scan = scan                          # callable -> list[str] of banned apps currently running
        self._id_re = re.compile(cfg["student_id_pattern"])
        self._exams = []                          # open assessments from the database
        self._apps_clear = False
        self._fields_ok = False
        self._sid_focus = False                   # the Student ID box has the keyboard focus
        self.went_back = False
        self.student_id = self.full_name = self.section = ""
        self.login_id = None
        self.exam = None
        self.setWindowTitle("QESentry – Student Login")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(make_header(INSTITUTION))

        # ---- scrollable form
        form = QWidget()
        body = QVBoxLayout(form)
        body.setContentsMargins(26, 20, 26, 14)
        body.setSpacing(12)

        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(*MARGINS)
        cl.setSpacing(0)

        self.back_btn = ghost(QPushButton("← Back"))
        self.back_btn.setAutoDefault(False)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addStretch(1)
        cl.addLayout(top)
        cl.addSpacing(10)
        title = QLabel("Student Login")
        title.setObjectName("Title")
        intro = QLabel("Enter your details and choose your assessment. Your login is recorded for your teacher.")
        intro.setObjectName("Subtitle")
        intro.setWordWrap(True)
        cl.addWidget(title)
        cl.addSpacing(GAP_TITLE_SUBTITLE)
        cl.addWidget(intro)
        cl.addSpacing(GAP_SUBTITLE_BODY)

        self.sid, self.sid_msg = self._field(cl, "Student ID", f"e.g., {cfg['student_id_example']}", FocusLineEdit)
        self.sid.setMaxLength(30)
        self.name, _ = self._field(cl, "Full Name", "e.g., Juan A. Dela Cruz")
        self.name.setMaxLength(120)
        self.section_edit, self.section_msg = self._field(cl, "Section", "e.g., BSCS 3-1")
        self.section_edit.setMaxLength(40)

        lab = QLabel("Assessment")
        lab.setObjectName("FieldLabel")
        cl.addWidget(lab)
        cl.addSpacing(GAP_LABEL_INPUT)
        self.exam_combo = StyledComboBox()
        self.exam_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.exam_combo.setMinimumContentsLength(16)
        refresh = secondary(QPushButton("Refresh"))
        refresh.setAutoDefault(False)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.exam_combo, 1)
        row.addWidget(refresh)
        cl.addLayout(row)
        self.link = FocusLineEdit()
        self.link.setPlaceholderText("Paste the Google Form link from your teacher")
        self.link.setClearButtonEnabled(True)
        cl.addSpacing(GAP_LABEL_INPUT)
        cl.addWidget(self.link)
        self.exam_msg = self._msg()
        cl.addSpacing(GAP_LABEL_INPUT)
        cl.addWidget(self.exam_msg)
        body.addWidget(card)

        self.app_status = QFrame()
        self.app_status.setObjectName("AppStatus")
        al = QVBoxLayout(self.app_status)
        al.setContentsMargins(16, 12, 16, 12)
        self.app_status_text = QLabel()
        self.app_status_text.setTextFormat(Qt.TextFormat.RichText)
        self.app_status_text.setWordWrap(True)
        al.addWidget(self.app_status_text)
        body.addWidget(self.app_status)

        notice = QFrame()
        notice.setObjectName("Notice")
        nl = QVBoxLayout(notice)
        nl.setContentsMargins(16, 12, 16, 12)
        warn = QLabel("This assessment environment is locked. Leaving the application or switching active "
                      "windows without submitting is prohibited and is reported to your teacher.\n\n"
                      "•  Prohibited applications are closed automatically.\n"
                      "•  Copy, paste and screen capture are disabled.\n"
                      "•  Only your teacher can end the session before you submit.")
        warn.setWordWrap(True)
        nl.addWidget(warn)
        body.addWidget(notice)

        self.consent = CheckRow("I have read and agree to the assessment conditions, and acknowledge "
                                "that my activity is monitored and recorded.")
        body.addWidget(self.consent)
        body.addStretch(1)
        outer.addWidget(scroll_area(form), 1)

        # ---- fixed footer (always visible)
        footer = QFrame()
        footer.setObjectName("Toolbar")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(20, 12, 20, 12)
        fl.setSpacing(8)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        fl.addWidget(self.status)
        self.start_btn = QPushButton("Start Assessment")
        self.start_btn.setEnabled(False)
        self.start_btn.setDefault(True)
        self.start_btn.setMinimumHeight(BUTTON_HEIGHT)
        self.start_btn.setMinimumWidth(170)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.start_btn)
        fl.addLayout(btns)
        outer.addWidget(footer)

        for w in (self.sid, self.name, self.section_edit, self.link):
            w.textChanged.connect(self._validate)
        self.sid.focused.connect(lambda: self._set_sid_focus(True))
        self.sid.blurred.connect(lambda: self._set_sid_focus(False))
        self.exam_combo.currentIndexChanged.connect(self._exam_changed)
        self.consent.toggled.connect(self._validate)
        refresh.clicked.connect(self._load_exams)
        self.start_btn.clicked.connect(self._submit)
        self.back_btn.clicked.connect(self._back)

        self._timer = QTimer(self)                # re-scan for banned apps every 2 s
        self._timer.timeout.connect(self._check_apps)
        self._timer.start(2000)

        self._load_exams()
        self._check_apps()
        fit_window(self, 680, 860, min_size=(440, 380))
        self.sid.setFocus()

    # ---- small builders
    def _field(self, layout, label, placeholder, edit_cls=FocusLineEdit):
        """Label + input + a helper line that takes no space until it has text; consistent gaps between fields."""
        lab = QLabel(label)
        lab.setObjectName("FieldLabel")
        edit = edit_cls()
        edit.setPlaceholderText(placeholder)
        msg = self._msg()
        layout.addWidget(lab)
        layout.addSpacing(GAP_LABEL_INPUT)
        layout.addWidget(edit)
        layout.addSpacing(GAP_LABEL_INPUT)
        layout.addWidget(msg)
        layout.addSpacing(GAP_FIELD - GAP_LABEL_INPUT)
        return edit, msg

    @staticmethod
    def _msg():
        """A feedback line under a field. Hidden while empty, so it takes no space (no big gaps between fields)."""
        m = QLabel("")
        m.setObjectName("Muted")
        m.setWordWrap(True)
        m.setVisible(False)
        return m

    @staticmethod
    def _feedback(label, text, kind):
        set_feedback(label, text, kind)
        label.setVisible(bool(text))

    def _set_sid_focus(self, has_focus):
        self._sid_focus = has_focus
        self._validate()

    # ---- back / close
    def _back(self):
        self.went_back = True
        self._timer.stop()
        self.reject()

    def closeEvent(self, event):
        self.went_back = not self.login_id
        self._timer.stop()
        super().closeEvent(event)

    def reject(self):
        self.went_back = not self.login_id
        self._timer.stop()
        super().reject()

    # ---- assessments
    def _load_exams(self):
        """(Re)read the open assessments from the database into the combo box."""
        keep = self.exam_combo.currentData()
        try:
            self._exams = db.list_exams(active_only=True)
            err = ""
        except db.DatabaseError as e:
            self._exams, err = [], str(e)
        self.exam_combo.blockSignals(True)
        self.exam_combo.clear()
        for x in self._exams:
            until = f"  ·  closes {db.format_local(x['closes_at'])}" if x.get("closes_at") else ""
            self.exam_combo.addItem(f"[{x['category']}] {x['title']}  ·  {x['teacher_name']}{until}", x["id"])
        self.exam_combo.addItem("My assessment isn't listed – I'll paste the link", MANUAL)
        i = self.exam_combo.findData(keep)
        self.exam_combo.setCurrentIndex(i if i >= 0 else 0)
        self.exam_combo.blockSignals(False)
        self._feedback(self.exam_msg, err or ("" if self._exams else "No assessments are open right now."),
                       "error" if err else "")
        self._exam_changed()

    def _selected_exam(self):
        eid = self.exam_combo.currentData()
        return next((x for x in self._exams if x["id"] == eid), None)

    def _exam_changed(self):
        self.link.setVisible(self.exam_combo.currentData() == MANUAL)
        self._validate()

    # ---- validation
    def _validate(self):
        ok = True
        text = self.sid.text()
        valid_id = bool(self._id_re.fullmatch(normalize_student_id(text)))
        if not text.strip():
            set_state(self.sid, ""); self._feedback(self.sid_msg, "", ""); ok = False
        elif valid_id:
            if self._sid_focus:                   # green only while the student is still on this box
                set_state(self.sid, "valid"); self._feedback(self.sid_msg, "✓ Student ID accepted.", "ok")
            else:
                set_state(self.sid, ""); self._feedback(self.sid_msg, "", "")
        else:
            set_state(self.sid, "invalid")
            self._feedback(self.sid_msg, f"Please enter a valid Student ID, e.g. {self.cfg['student_id_example']}", "error")
            ok = False

        ok &= len(" ".join(self.name.text().split())) >= 3

        sec = " ".join(self.section_edit.text().split()).upper()
        exam = self._selected_exam()
        allowed = exam["sections"] if exam else []
        if not sec:
            set_state(self.section_edit, ""); self._feedback(self.section_msg, "", ""); ok = False
        elif allowed and sec not in allowed:
            set_state(self.section_edit, "invalid")
            self._feedback(self.section_msg, f"This assessment is for: {', '.join(allowed)}", "error"); ok = False
        else:
            set_state(self.section_edit, ""); self._feedback(self.section_msg, "", "")      # correct = no colour

        if self.exam_combo.currentData() == MANUAL:
            if not self.link.text().strip():
                set_state(self.link, ""); ok = False
            else:
                try:
                    format_form_url(self.link.text()); set_state(self.link, "valid"); self._feedback(self.exam_msg, "", "")
                except InvalidFormUrl as e:
                    set_state(self.link, "invalid"); self._feedback(self.exam_msg, str(e), "error"); ok = False
        elif exam is None:
            ok = False

        self._fields_ok = bool(ok)
        self._update_start()

    def _check_apps(self):
        bad = self.scan()
        self._apps_clear = not bad
        if bad:
            self.app_status_text.setText("Please close the following applications before proceeding:<br>"
                                         f"<span style='color:{MAROON}; font-weight:600;'>{html.escape(', '.join(bad))}</span>")
            self.app_status.setProperty("state", "blocked")
        else:
            self.app_status_text.setText(f"<span style='color:{SUCCESS}; font-weight:600;'>✓ No prohibited applications detected.</span>")
            self.app_status.setProperty("state", "clear")
        repolish(self.app_status)
        self._update_start()

    def _update_start(self):
        self.start_btn.setEnabled(self._fields_ok and self._apps_clear and self.consent.isChecked())

    # ---- submit: log to the database, then close
    def _submit(self):
        if not self.start_btn.isEnabled():
            return
        sid, name = normalize_student_id(self.sid.text()), " ".join(self.name.text().split()).upper()
        sec = " ".join(self.section_edit.text().split()).upper()
        try:
            exam = self._selected_exam()
            if exam is None:                                      # pasted link -> find the matching open assessment
                exam = db.find_exam_by_link(self.link.text(), sec)
                if exam is None:
                    raise db.LoginRejected("No open assessment matches that link for your section. "
                                           "Check the link and section with your teacher.")
            res = db.register_student_login(sid, name, sec, exam["id"])
        except (db.LoginRejected, db.DatabaseError, InvalidFormUrl) as e:
            self._feedback(self.status, str(e), "error")
            return
        self.student_id, self.full_name, self.section = sid, name, sec
        self.login_id, self.exam = res["login_id"], res["exam"]
        self._timer.stop()
        self.accept()
