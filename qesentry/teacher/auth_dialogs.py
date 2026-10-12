"""Teacher sign-in and sign-up dialogs, plus the teacher-credential prompt used on a student PC.

- TeacherLoginDialog     username/email + password; \"Create Teacher Account\"; \"Back to Role Selection\"
- RegisterTeacherDialog  Full Name, Email/Username, Password, Confirm Password
- ask_exit_auth()        teacher-credential prompt on a student PC (only when override_mode = \"teacher_login\")
"""
import math
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from qesentry.core import db
from qesentry.core import logger as log
from qesentry.ui.forms import (BUTTON_HEIGHT, FORM_WIDTH, GAP_FIELD, GAP_LABEL_INPUT, GAP_SUBTITLE_BODY, GAP_TITLE_SUBTITLE, MARGINS,
                   FormDialog, fit_height)
from qesentry.ui.popups import warn
from qesentry.core.validators import LOGIN_BAD_CREDENTIALS, LOGIN_NO_ACCOUNT, login_submit_problem
from qesentry.ui.theme import APP_NAME, INSTITUTION, FocusLineEdit, add_password_toggle, ghost, make_header, secondary, set_feedback, set_state
from qesentry.teacher.form_helpers import make_label, password_hints, reject_new_passwords


# Failed-login tracking lives at module level so the counter survives closing and reopening a dialog.
_fail = {"count": 0, "locked_until": 0.0}      # locked_until is a time.monotonic() value


MAX_TRIES = 3


LOCKOUT_SECONDS = 30


def _locked_wait():
    return _fail["locked_until"] - time.monotonic()


def _register_failure():
    """Count a wrong password. Returns attempts left (0 = lockout just started)."""
    _fail["count"] += 1
    if _fail["count"] >= MAX_TRIES:
        _fail.update(count=0, locked_until=time.monotonic() + LOCKOUT_SECONDS)
        return 0
    return MAX_TRIES - _fail["count"]


# ----------------------------------------------------------------------------- login / registration
class RegisterTeacherDialog(FormDialog):
    """Create Teacher Account. The button stays grey until every field is filled and the passwords match.
    On success .username holds the new login."""

    def __init__(self, parent=None, code_required=""):
        super().__init__(parent, "Create Teacher Account", "Enter your details to set up a new teacher account.")
        self.username = ""
        self._code_required = code_required
        self.name_f = self.add_field("Full Name", "e.g., Maria L. Santos")
        self.user_f = self.add_field("Email / Username", "e.g., msantos@pup.edu.ph")
        self.pw_f = self.add_field("Password", "At least 8 characters", password=True)
        self.pw2_f = self.add_field("Confirm Password", "Re-enter your password", password=True)
        self.code_f = self.add_field("Registration Code", "Ask your administrator", password=True) if code_required else None
        self.err = self.add_message()
        self.ok_btn = self.add_actions("Create Account", ok_slot=self._create)
        self.ok_btn.setEnabled(False)
        self._fields = [(self.name_f, "Please enter your full name."), (self.user_f, "Please enter your email or username."),
                        (self.pw_f, "Please enter your password."), (self.pw2_f, "Please confirm your password.")]
        if self.code_f is not None:
            self._fields.append((self.code_f, "Please enter the registration code."))
        for f, _msg in self._fields:
            f.edit.textChanged.connect(self._update)
        self.pw_f.edit.textChanged.connect(self._hints)
        self.pw2_f.edit.textChanged.connect(self._hints)
        self.pw_f.edit.blurred.connect(self._hints)
        self.name_f.edit.setFocus()

    def _hints(self):
        password_hints(self, self.pw_f, self.pw2_f)

    def _update(self):
        """The button turns active as soon as anything is typed; the checks run when it is clicked."""
        self.ok_btn.setEnabled(any(f.edit.text() for f, _m in self._fields))
        if self.err.isVisible():
            self.say(self.err, "", "")

    def _create(self):
        missing = [(f, m) for f, m in self._fields if not f.edit.text().strip()]
        if missing:
            for f, m in missing:
                self.flag(f, m)
            missing[0][0].edit.setFocus()
            return
        if not reject_new_passwords(self, self.pw_f, self.pw2_f, "✕ Passwords do not match."):
            return
        if self._code_required and self.code_f.edit.text() != self._code_required:
            self.say(self.err, "Incorrect registration code.", "error")
            return
        try:
            t = db.register_teacher(self.name_f.edit.text(), self.user_f.edit.text(), self.pw_f.edit.text())
        except (ValueError, db.DatabaseError) as e:
            self.say(self.err, str(e), "error")
            return
        self.username = t["username"]
        self.accept()


class TeacherLoginDialog(QDialog):
    """Teacher Authentication. On success: .teacher = {id, username, full_name}.

    went_back is True for Back / close; want_register is True when 'Create one' was clicked.
    override=True turns it into the compact 'teacher authorization' prompt used on a student PC.
    Sign In stays grey until both fields are filled (and while a lockout countdown runs).
    """

    def __init__(self, parent=None, override=False, cfg=None, prefill=""):
        super().__init__(parent)
        self.teacher = None
        self.went_back = False
        self.want_register = False
        self.override = override
        self._cfg = cfg or {}
        self._locked = False
        self.setWindowTitle(f"{APP_NAME} – {'Teacher Authorization' if override else 'Teacher Login'}")
        self.setFixedWidth(FORM_WIDTH)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, override)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(make_header("Teacher Authorization" if override else INSTITUTION))

        form = QVBoxLayout()
        form.setContentsMargins(*MARGINS)
        form.setSpacing(0)
        if not override:
            self.back_btn = ghost(QPushButton("← Back"))
            self.back_btn.setAutoDefault(False)
            self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            row = QHBoxLayout()
            row.addWidget(self.back_btn)
            row.addStretch(1)
            form.addLayout(row)
            form.addSpacing(10)
            self.back_btn.clicked.connect(self._back)
        form.addWidget(make_label("Authorization Required" if override else "Teacher Login", "Title"))
        form.addSpacing(GAP_TITLE_SUBTITLE)
        sub = make_label("Enter your teacher credentials to end this session. Only an authorized teacher may do so "
                     "before the exam is submitted." if override
                     else "Sign in with your email or username and your password.", "Subtitle")
        sub.setWordWrap(True)
        form.addWidget(sub)
        form.addSpacing(GAP_SUBTITLE_BODY)

        form.addWidget(make_label("Email / Username"))
        form.addSpacing(GAP_LABEL_INPUT)
        self.ident = FocusLineEdit()
        self.ident.setPlaceholderText("you@school.edu")
        form.addWidget(self.ident)
        form.addSpacing(GAP_FIELD)
        form.addWidget(make_label("Password"))
        form.addSpacing(GAP_LABEL_INPUT)
        self.pw = FocusLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("Password")
        add_password_toggle(self.pw)                     # eye button: show / hide the password
        form.addWidget(self.pw)
        self.feedback = QLabel("")                       # 12px microcopy under the fields (see validators.login_hint)
        self.feedback.setObjectName("FieldError")
        self.feedback.setWordWrap(True)
        self.feedback.setVisible(False)                  # nothing is shown until Sign In is clicked
        form.addSpacing(GAP_LABEL_INPUT)
        form.addWidget(self.feedback)
        if not override:
            self.signup = QLabel("No account yet? <a href='create' style='color:#7A0016; font-weight:600;'>Create one</a>")
            self.signup.setObjectName("LinkLine")
            self.signup.setTextFormat(Qt.TextFormat.RichText)
            self.signup.setOpenExternalLinks(False)
            self.signup.setCursor(Qt.CursorShape.PointingHandCursor)
            self.signup.linkActivated.connect(lambda _link: self._register())
            form.addSpacing(GAP_LABEL_INPUT)
            form.addWidget(self.signup)
        outer.addLayout(form)

        footer = QFrame()
        footer.setObjectName("Toolbar")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 12, 20, 12)
        fl.setSpacing(10)
        fl.addStretch(1)
        self.ok_btn = QPushButton("Authorize" if override else "Sign In")
        self.ok_btn.setMinimumHeight(BUTTON_HEIGHT)
        self.ok_btn.setMinimumWidth(130)
        self.ok_btn.setDefault(True)
        self.ok_btn.setEnabled(False)
        if override:
            cancel = secondary(QPushButton("Cancel"))
            cancel.setMinimumHeight(BUTTON_HEIGHT)
            cancel.setMinimumWidth(110)
            cancel.setAutoDefault(False)
            cancel.clicked.connect(self._back)
            fl.addWidget(cancel)
        fl.addWidget(self.ok_btn)
        outer.addWidget(footer)

        self.ident.textChanged.connect(self._edited)
        self.pw.textChanged.connect(self._edited)
        for box in (self.ident, self.pw):                # clicking a red box, or Tab-ing into it, returns it to normal
            box.clicked.connect(self._clear_errors)
            box.focused.connect(lambda b=box: self._focus_clears(b))
        self.ok_btn.clicked.connect(self._check)
        self._lock_timer = QTimer(self)                  # counts the lockout down once a second
        self._lock_timer.timeout.connect(self._tick_lock)
        if prefill:
            self.ident.setText(prefill)
            self.pw.setFocus()
        else:
            self.ident.setFocus()
        if _locked_wait() > 0:                           # reopened during a lockout: keep counting
            self._start_lock_countdown()

    def showEvent(self, event):
        super().showEvent(event)
        fit_height(self)

    def _update_ok(self):
        """Sign In turns active once either box has text (and while no lockout countdown is running)."""
        self.ok_btn.setEnabled(bool(self.ident.text().strip() or self.pw.text()) and not self._locked)

    def _focus_clears(self, box):
        """Focus the user moved there (click / Tab) clears the red; focus the dialog set itself (after a failed
        sign-in) does not, or the red would vanish the moment it appeared."""
        if getattr(box, "focus_reason", None) in (Qt.FocusReason.MouseFocusReason, Qt.FocusReason.TabFocusReason,
                                                  Qt.FocusReason.BacktabFocusReason):
            self._clear_errors()

    def _clear_errors(self):
        """Back to normal: red boxes and their message go (a running lockout countdown message stays)."""
        if "invalid" not in (self.ident.property("state"), self.pw.property("state")):
            return
        set_state(self.ident, "")
        set_state(self.pw, "")
        if not self._locked:
            self._say("", "")

    def mousePressEvent(self, event):
        """Clicking empty space in the window also clears the red."""
        self._clear_errors()
        super().mousePressEvent(event)

    def _edited(self):
        """Typing removes the red boxes and the message (the lockout countdown message stays)."""
        set_state(self.ident, "")
        set_state(self.pw, "")
        if not self._locked:
            self._say("", "")
        self._update_ok()

    def _back(self):
        self.went_back = True
        self.reject()

    def closeEvent(self, event):
        self.went_back = self.teacher is None
        super().closeEvent(event)

    def _register(self):
        """'Create one' link: close this window. The caller opens the registration window and, afterwards,
        shows this login again."""
        self.want_register = True
        self.reject()

    def _say(self, text, kind):
        if text == self.feedback.text() and self.feedback.isVisible() == bool(text):
            return
        set_feedback(self.feedback, text, kind)
        self.feedback.setVisible(bool(text))
        fit_height(self)

    def _tick_lock(self):
        """One step of the lockout countdown: 30, 29, ... 1, then 'you can try again'."""
        wait = _locked_wait()
        if wait > 0:
            n = math.ceil(wait)
            self._locked = True
            self._say(f"Too many incorrect attempts. Try again in {n} second{'s' if n != 1 else ''}.", "error")
        else:
            self._locked = False
            self._lock_timer.stop()
            self._say("You can try again now.", "ok")
        self._update_ok()

    def _start_lock_countdown(self):
        self._tick_lock()
        self._lock_timer.start(1000)

    def _check(self):
        if _locked_wait() > 0:
            self._tick_lock()
            return
        problem = login_submit_problem(self.ident.text(), self.pw.text())
        if problem:
            message, boxes = problem
            if "ident" in boxes:
                self.pw.clear()                          # (clearing resets the red boxes, so mark them afterwards)
            for name in boxes:
                set_state(getattr(self, name), "invalid")
            self._say(message, "error")
            getattr(self, boxes[0]).setFocus()
            return
        try:
            teacher = db.authenticate_teacher(self.ident.text(), self.pw.text())
        except db.DatabaseError as e:
            self._say(str(e), "error")
            return
        if teacher:
            _fail["count"] = 0
            self.teacher = teacher
            self.accept()
            return
        log.emit("TEACHER_AUTH_FAIL", override=self.override, count=_fail["count"] + 1)
        try:
            exists = db.teacher_exists(self.ident.text())
        except db.DatabaseError:
            exists = True                                # cannot tell: fall back to the generic message
        self.pw.clear()                                  # (clearing resets the red boxes, so mark them afterwards)
        set_state(self.pw, "invalid")
        if exists:
            self.pw.setFocus()                           # right account, wrong password: only the password is marked
        else:
            set_state(self.ident, "invalid")             # no such account: mark the username too
            self.ident.setFocus()
        if _register_failure() == 0:
            self._start_lock_countdown()
        else:
            self._say(LOGIN_BAD_CREDENTIALS if exists else LOGIN_NO_ACCOUNT, "error")


def ask_exit_auth(parent):
    """Student-PC override (only when override_mode = "teacher_login"): the teacher dict, or None."""
    wait = _locked_wait()
    if wait > 0:
        warn(parent, "Access Locked", f"Too many incorrect attempts. Please try again in {int(wait) + 1} seconds.")
        return None
    dlg = TeacherLoginDialog(parent, override=True)
    return dlg.teacher if dlg.exec() == QDialog.DialogCode.Accepted else None
