"""QESentry entry point: role selector -> Student Portal or Teacher Portal.

Run:  python main.py            (real lockdown for students)
      python main.py --dev      (student portal in safe mode: no keyboard hook, flag-only watchdog)

Student Portal  -> login (ID / name / section / exam) -> row in `student_logins` -> locked exam window.
Teacher Portal  -> login or create account -> dashboard (live monitor, assessments, settings).
"Back to Role Selection" and "Log Out" return here; the student session ends the app when the exam is over.

Credentials: the Teacher Portal uses config.json, the Student Portal uses config.student.json (a restricted
database user). A student build ships only config.student.json, so its Teacher Portal is switched off.
"""
import os
import sys

# Remove environment variables that could switch on browser devtools or extra Chromium flags.
for _var in ("QTWEBENGINE_REMOTE_DEBUGGING", "QTWEBENGINE_CHROMIUM_FLAGS"):
    os.environ.pop(_var, None)

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog

from qesentry.core import db
from qesentry.core.config import available_roles, load_config, resource_path
from qesentry.ui.popups import inform, warn
from qesentry.student.process_watchdog import ProcessWatchdog
from qesentry.teacher.auth_dialogs import RegisterTeacherDialog, TeacherLoginDialog
from qesentry.teacher.dashboard import ProctorDashboard
from qesentry.ui.role_selector import RoleSelector
from qesentry.student.session import run_student_session
from qesentry.student.login_dialog import StudentLoginDialog
from qesentry.ui.theme import APP_NAME, apply_theme


def main(start=None):
    """Run the app. start="teacher" opens the Teacher Portal directly (used by teacher_app.py)."""
    dev = "--dev" in sys.argv                   # developer mode: never hook the keyboard or kill programs
    if sys.platform == "win32":                  # own taskbar identity, so the shield icon shows instead of python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QESentry.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(resource_path("assets/qesentry.png")))   # every window and the taskbar use the shield
    app.setQuitOnLastWindowClosed(False)         # we quit explicitly when a portal ends

    roles = available_roles()
    selector = RoleSelector(student_ok="student" in roles, teacher_ok="teacher" in roles)
    selector.quit_requested.connect(app.quit)
    holder = {}                                  # keeps the dashboard alive while it is open

    def go_student():
        """Student Portal: database check -> login -> lockdown session."""
        selector.hide()
        cfg = load_config("student")
        if dev:
            cfg["process_mode"] = "flag"
        try:
            db.connect(cfg)
            db.check_connection()
        except db.DatabaseError as e:
            warn(None, "Database Unavailable", str(e), note="Ask your teacher to check the exam server settings.")
            selector.show()
            return
        watchdog = ProcessWatchdog(cfg["denylist"], cfg["process_mode"])
        login = StudentLoginDialog(cfg, watchdog.scan_once)
        if login.exec() != QDialog.DialogCode.Accepted:
            selector.show()                      # "Back to Role Selection" / window closed
            return
        run_student_session(app, cfg, login, watchdog, dev)

    def go_teacher():
        """Teacher Portal: database (+ first-run table setup) -> login -> dashboard."""
        selector.hide()
        cfg = load_config("teacher")
        try:
            db.connect(cfg)
            db.init_db()
        except db.DatabaseError as e:
            warn(None, "Database Unavailable", str(e))
            selector.show()
            return
        prefill = ""
        while True:
            login = TeacherLoginDialog(cfg=cfg, prefill=prefill)
            if login.exec() == QDialog.DialogCode.Accepted:
                break
            if login.want_register:                  # "No account yet? Create one": sign-up window, then back to login
                reg = RegisterTeacherDialog(None, cfg.get("teacher_registration_code", ""))
                if reg.exec() == QDialog.DialogCode.Accepted:
                    inform(None, "Account Created", f"Your teacher account “{reg.username}” has been created.",
                           note="Sign in with your new password.")
                    prefill = reg.username
                continue
            selector.show()                          # "Back to Role Selection" / window closed
            return
        win = ProctorDashboard(cfg, login.teacher)
        holder["win"] = win
        win.logged_out.connect(lambda: back_to_selector(win))
        win.show()

    def back_to_selector(win):
        """Log Out: dispose of the dashboard and show the role selector again."""
        win.hide()
        win.deleteLater()
        holder.pop("win", None)
        selector.show()

    selector.student_selected.connect(go_student)
    selector.teacher_selected.connect(go_teacher)
    if start == "teacher":
        QTimer.singleShot(0, go_teacher)
    else:
        selector.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
