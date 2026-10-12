"""One locked-down exam session, from the moment the student is logged in until the app exits.

run_student_session() builds the exam window and the monitors (keyboard hook, process watchdog, focus monitor,
clipboard cleaner), then wires the lifecycle:

    submission detected / confirmed -> row SUBMITTED  -> unlock
    teacher presses "Release Student" -> heartbeat sees RELEASED_BY_TEACHER -> unlock, no alert
    leave attempt (Alt+F4 / hotkey)   -> alert logged; ends only via teacher release (or teacher login, see
                                         config "override_mode")

It returns immediately; the caller keeps running the Qt event loop, and the session calls app.quit() at the end.
"""
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from qesentry.core import alerts
from qesentry.core import db
from qesentry.core import logger as log
from qesentry.student.exam_window import ExamWindow
from qesentry.student.keyboard_guard import ClipboardCleaner, KeyboardGuard, apply_policies, protect_window, restore_policies
from qesentry.student.process_watchdog import FocusMonitor
from qesentry.ui.popups import inform
from qesentry.teacher.auth_dialogs import ask_exit_auth

_keep = []        # strong references so nothing is garbage-collected while the session runs


class Heartbeat(QObject):
    """Background thread that tells the database this client is alive, and notices a teacher release.

    release_requested is emitted (once) from the worker thread; Qt delivers it to the main thread.
    """
    release_requested = pyqtSignal()

    def __init__(self, login_id, interval):
        super().__init__()
        self.login_id, self.interval = login_id, interval
        self._stop = threading.Event()
        self._failed = False
        self._released = False
        self._thread = threading.Thread(target=self._run, name="qesentry-heartbeat", daemon=True)

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                status = db.heartbeat(self.login_id)
                self._failed = False
            except db.DatabaseError:
                if not self._failed:                 # log the outage once, not every beat
                    self._failed = True
                    log.emit("HEARTBEAT_FAILED")
                continue
            if status == db.STATUS_RELEASED and not self._released:
                self._released = True
                self.release_requested.emit()

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()


def run_student_session(app, cfg, login, watchdog, dev):
    """Start the lockdown for a logged-in student (`login` is the accepted StudentLoginDialog)."""
    exam, login_id = login.exam, login.login_id
    cfg["exam_url"] = exam["form_url"]

    log.start_session(login.student_id)
    alerts.start(login_id)
    beat = Heartbeat(login_id, int(cfg["heartbeat_seconds"]))
    log.emit("APP_START", dev=dev, monitors=len(app.screens()), exam_url=cfg["exam_url"], login_id=login_id,
             exam_id=exam["id"], category=exam["category"], section=login.section)
    if len(app.screens()) > 1:
        log.emit("MULTI_MONITOR_DETECTED", count=len(app.screens()))
        alerts.report(db.EVENT_MONITOR, f"{len(app.screens())} monitors detected")

    win = ExamWindow(cfg, login.student_id, login.full_name, login.section, exam["title"], exam["category"])
    focus = FocusMonitor(win)                   # pulls focus back if another window appears
    clip = ClipboardCleaner()                   # keeps the clipboard empty
    kb = KeyboardGuard(cfg["exit_hotkey"])      # blocks shortcuts, listens for the leave hotkey
    retry = QTimer()
    _keep.extend([win, focus, clip, kb, beat, retry])
    state = {"prompting": False, "done": False, "saved": False, "source": None, "tries": 0}

    def end_session():
        """Stop every monitor / hook and restore policies. Safe to call more than once."""
        if state["done"]:
            return
        state["done"] = True
        beat.stop()
        if not dev:
            kb.stop()
        watchdog.stop(); focus.stop(); clip.stop()
        try:
            watchdog.violation.disconnect(win.warn_app)      # the watchdog outlives this session
        except TypeError:
            pass
        if cfg["use_policies"] and not dev:
            restore_policies()
        log.emit("SESSION_END")

    # ---- submission
    def save_submission():
        """Write SUBMITTED to the database. Returns True once saved; failures are retried (see retry_save)."""
        if state["saved"]:
            return True
        if state["source"] is None:              # no submission happened (release / override) -> nothing to save
            return False
        try:
            db.mark_submitted(login_id, state["source"])
            state["saved"] = True
            log.emit("SUBMISSION_RECORDED", source=state["source"])
        except db.DatabaseError:
            log.emit("SUBMISSION_RECORD_FAILED", attempt=state["tries"] + 1)
        return state["saved"]

    def retry_save():
        """Server was unreachable at submit time: keep trying every 5 s (the completion screen stays open)."""
        state["tries"] += 1
        if save_submission() or state["tries"] >= 36:
            retry.stop()

    retry.timeout.connect(retry_save)

    def finish_up():
        """Last chance on exit: save a pending submission, flush alerts."""
        save_submission()
        alerts.stop()

    app.aboutToQuit.connect(finish_up)

    def on_finished(source):
        """Submission detected (form redirect) or confirmed by the student: record it, then unlock."""
        state["source"] = source
        try:
            if not save_submission():
                retry.start(5000)
        finally:
            end_session()                        # the student is never kept locked in by a database problem

    # ---- teacher release (remote)
    def on_release():
        """The teacher pressed Release Student: unlock cleanly. Not an alert, not an improper exit."""
        if state["done"]:
            return
        log.emit("RELEASED_BY_TEACHER")
        try:
            db.mark_release_acked(login_id)
        except db.DatabaseError:
            log.emit("RELEASE_RECORD_FAILED")
        end_session()
        win.release()

    # ---- leaving early
    def shutdown():
        end_session()
        win.allow_close()
        win.close()
        app.quit()

    def attempt_exit():
        """Alt+F4 / exit hotkey. Always an alert; how it ends depends on config "override_mode"."""
        if state["prompting"] or state["done"]:
            return
        state["prompting"] = True
        log.emit("EXIT_ATTEMPT")
        alerts.report(db.EVENT_EXIT, "Tried to close the exam window")
        try:
            if dev:                                              # developer mode: never trap the developer
                shutdown()
            elif cfg.get("override_mode") == "teacher_login":
                teacher = ask_exit_auth(win)
                if teacher:
                    log.emit("EXIT_AUTHORIZED", teacher_id=teacher["id"], teacher=teacher["username"])
                    try:
                        db.mark_overridden(login_id)
                    except db.DatabaseError:
                        log.emit("OVERRIDE_RECORD_FAILED")
                    shutdown()
                else:
                    log.emit("EXIT_DENIED")
            else:
                inform(win, "Session Locked", "This session can only be ended by your teacher.",
                       note="If you have a problem, raise your hand and ask to be released.")
        finally:
            state["prompting"] = False

    win.exam_finished.connect(on_finished)
    win.exit_requested.connect(attempt_exit)
    beat.release_requested.connect(on_release)
    kb.exit_hotkey.connect(attempt_exit)
    kb.blocked.connect(lambda k: log.emit("KEY_BLOCKED", key=k))
    kb.blocked.connect(win.warn_key)                 # floating warning bubble (queued to the GUI thread)
    focus.focus_lost.connect(win.warn_focus)
    watchdog.violation.connect(win.warn_app)

    # ---- go
    win.start()
    win.showFullScreen()
    win.raise_()
    win.activateWindow()
    protect_window(int(win.winId()))
    watchdog.start(); focus.start(); clip.start(); beat.start()
    if not dev:                                  # keyboard hook / policies are skipped in --dev (never get locked out)
        kb.start()
        if cfg["use_policies"]:
            apply_policies()
