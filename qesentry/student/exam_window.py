"""The exam window itself.

- ExamWindow          full-screen, always-on-top window that shows the Google Form and a bottom status bar.
- GuardedPage         the web page behind it; only allows approved addresses and blocks new windows.
- ConfirmSubmitDialog "Are you sure?" prompt shown when the student says they are finished.
- CompletionScreen    the sign-off screen shown after the student confirms.

Submission is detected two ways, both ending in the same `exam_finished(source)` signal:
    "form_redirect"     Google's post-submit page (.../formResponse) finished loading in the web view
    "student_confirmed" the student pressed the finished button and confirmed

Run alone for a demo:  python -m qesentry.student.exam_window <google-form-url>
"""
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from qesentry.core import alerts
from qesentry.core import logger as log
from qesentry.core.form_url import is_submission_url
from qesentry.ui.popups import PopupDialog
from qesentry.student.warning_bubble import WarningBubble, key_warning
from qesentry.ui.theme import APP_NAME, BG, FOOTER_TEXT, GOLD, MAROON, SURFACE, apply_theme, make_header

# Browser identity sent to Google. Modern desktop Chrome UA so Google Forms renders its normal page instead of an "unsupported browser" view.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

# Always allowed, regardless of config, so embedded form assets / Google sign-in redirects never get blocked.
REQUIRED_PREFIXES = (
    "https://docs.google.com/",
    "https://accounts.google.com/",
)

# Bottom HUD + completion screen (colours come from theme.py; everything else is in the global stylesheet).
EXAM_QSS = f"""
QFrame#BottomBar {{
    background-color: {SURFACE};
    border: none;
    border-top: 3px solid {MAROON};
}}
QLabel#StatusLabel {{
    color: {MAROON};
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.6px;
    background: transparent;
}}
QPushButton#DoneButton {{ padding: 10px 26px; }}

QFrame#CompletionPage {{ background-color: {BG}; border: none; }}
QLabel#SuccessMark {{
    background-color: {MAROON}; color: #FFFFFF;
    border: 4px solid {GOLD}; border-radius: 40px;
    font-size: 36px; font-weight: 700;
}}
QFrame#GoldRule {{ background-color: {GOLD}; border: none; }}
"""


def build_url(cfg, student_id):
    """Return the form URL, with the student ID pre-filled into the form if "student_field" is configured."""
    url = cfg["exam_url"]
    field = cfg.get("student_field")
    if field and student_id:  # pre-fill a short-answer question with the student number
        parts = urlsplit(url)
        q = parse_qsl(parts.query, keep_blank_values=True) + [(field, student_id)]
        url = urlunsplit(parts._replace(query=urlencode(q)))
    return url


class GuardedPage(QWebEnginePage):
    """Web page that refuses to leave the allowed Google Forms addresses and never opens new windows."""

    def __init__(self, profile, allowed_prefixes, parent=None):
        super().__init__(profile, parent)
        # Config prefixes + the Google ones that must always work (order kept, duplicates dropped).
        self.allowed = tuple(dict.fromkeys([*REQUIRED_PREFIXES, *(allowed_prefixes or [])]))

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """Qt calls this before every navigation. Return True to allow it, False to block it."""
        if not is_main_frame:          # iframes (reCAPTCHA, embeds) are allowed in the MVP
            return True
        target = url.toString()
        # Allowed only if the address starts with an approved prefix; otherwise log and block.
        if any(target.startswith(p) for p in self.allowed):
            return True
        log.emit("NAV_BLOCKED", url=target)
        parts = urlsplit(target)                      # host + path only: query strings can hold tokens
        alerts.report("BLOCKED_URL", f"Blocked navigation to {parts.hostname or ''}{parts.path}"[:200])
        return False

    def createWindow(self, _type):     # target=_blank / window.open -> no new windows or tabs
        """Qt calls this when the page tries to open a new window/tab. Returning None refuses it."""
        log.emit("NEW_WINDOW_BLOCKED")
        alerts.report("BLOCKED_URL", "Page tried to open a new window or tab")
        return None


# ----------------------------------------------------------------------------- submission workflow
class ConfirmSubmitDialog(PopupDialog):
    """Step 1: 'Are you sure?'  exec() == Accepted  ->  student chose 'Yes, Exit'. Same look as every QESentry prompt."""

    def __init__(self, parent=None, category="Exam"):
        label = category.lower()                          # 'exam' or 'quiz'
        super().__init__(parent, "Confirm Submission",
                         f"Are you sure you have completed and submitted your {label} through the form?",
                         note=f"Selecting “Yes, Exit {category.title()}” will end your session.",
                         yes=f"Yes, Exit {category.title()}", no=f"No, Return to {category.title()}")


class CompletionScreen(QFrame):
    """Step 2: sign-off screen shown after the student confirms."""
    close_requested = pyqtSignal()

    def __init__(self, student_id="", category="Exam", parent=None):
        super().__init__(parent)
        label = category.lower()
        self.setObjectName("CompletionPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(make_header("Secure Assessment Platform"))
        page.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(580)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 36, 40, 32)
        cl.setSpacing(12)

        mark = self.mark = QLabel("✓")
        mark.setObjectName("SuccessMark")
        mark.setFixedSize(80, 80)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = self.title_label = QLabel(f"{category.title()} Submitted")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rule = QFrame()
        rule.setObjectName("GoldRule")
        rule.setFixedSize(56, 3)

        msg = self.msg_label = QLabel(f"Well done! Your {label} has been submitted. "
                                      "You may now close the application.")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cl.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        cl.addWidget(title)
        cl.addWidget(rule, 0, Qt.AlignmentFlag.AlignHCenter)
        cl.addWidget(msg)
        if student_id:
            who = QLabel(f"Student ID: {student_id}")
            who.setObjectName("Muted")
            who.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(who)
        cl.addSpacing(10)
        self.close_btn = QPushButton("Close Application")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested)
        cl.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        page.addLayout(row)
        page.addStretch(1)

        foot = QLabel(FOOTER_TEXT)
        foot.setObjectName("Muted")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setContentsMargins(0, 0, 0, 18)
        page.addWidget(foot)


    def set_content(self, title, message, mark="✓"):
        """Change the sign-off wording (used for 'released by your teacher')."""
        self.title_label.setText(title)
        self.msg_label.setText(message)
        self.mark.setText(mark)


# ----------------------------------------------------------------------------- main window
class ExamWindow(QMainWindow):
    """Main kiosk window. Page 0 of its stack is the exam; page 1 is the completion screen."""
    exit_requested = pyqtSignal()      # someone tried to close the window (Alt+F4 etc.) -> teacher-auth path
    exam_finished = pyqtSignal(str)    # submission detected/confirmed; arg = source. main.py updates the DB and unlocks

    def __init__(self, cfg, student_id="", student_name="", section="", exam_title="", exam_category="Exam"):
        super().__init__()
        self._allow_close = False          # closeEvent only really closes when this is True
        self._finished = False             # submission already reported (guards against double signals)
        self._student_id = student_id
        self._category = exam_category if exam_category in ("Exam", "Quiz") else "Exam"
        self._auto_detect = bool(cfg.get("auto_detect_submission", True))
        self._grace_ms = int(cfg.get("submit_grace_ms", 2500))
        self._strike_limit = max(1, int(cfg.get("flag_threshold", 3)))      # same number that marks a student FLAGGED
        self.setWindowTitle(f"{APP_NAME} – Secure Browser")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(EXAM_QSS)

        # --- browser engine setup ---
        profile = QWebEngineProfile(self)          # unnamed = off-the-record (no cookies kept on disk)
        profile.setHttpUserAgent(cfg.get("user_agent") or DEFAULT_USER_AGENT)
        profile.downloadRequested.connect(self._block_download)

        page = GuardedPage(profile, cfg.get("allowed_prefixes", []), self)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)

        # Page 0: the exam. 0px margins / 0px spacing so the web view and the bar sit flush, no gaps.
        exam_page = QWidget()
        root = QVBoxLayout(exam_page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.view = QWebEngineView(self)
        self.view.setPage(page)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)  # no right-click menu
        self.view.loadFinished.connect(self._on_load_finished)   # web-frame hook for submission detection
        self.view.load(QUrl(build_url(cfg, student_id)))
        root.addWidget(self.view, 1)                 # takes ALL remaining vertical space
        root.addWidget(self._build_bottom_bar(), 0)

        # Page 1: completion screen
        self.completion = CompletionScreen(student_id, self._category)
        self.completion.close_requested.connect(self._close_application)

        # Stack = two "pages" in one window; show_completion() switches from the exam to the sign-off screen.
        self.stack = QStackedWidget(self)
        self.stack.addWidget(exam_page)
        self.stack.addWidget(self.completion)
        self.setCentralWidget(self.stack)
        self._fade = None                           # keeps the fade animation alive while it plays
        self.bubble = WarningBubble(self)           # floating "Warning" pop-up for blocked attempts

    # --- floating warning bubble (slots, so signals from the keyboard / monitor threads are queued to the GUI thread) ---
    def warn(self, text):
        """Pop up the floating warning bubble with `text` (ignored once the exam has ended)."""
        if not self._finished:
            strikes = alerts.session_count()
            self.bubble.show_message(text, strikes, self._strike_limit)

    @pyqtSlot(str)
    def warn_key(self, hotkey):
        self.warn(key_warning(hotkey))

    @pyqtSlot()
    def warn_focus(self):
        self.warn("You left the exam window. Please stay on your exam.")

    @pyqtSlot(str, str)
    def warn_app(self, app_name, action):
        self.warn(f"{app_name} is not allowed during the exam." + (" It was closed." if action == "killed" else ""))

    def _build_bottom_bar(self):
        """Slim HUD: lockdown status on the left, single 'finished' button on the right."""
        bar = QFrame(self)
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        self.status_label = QLabel("🔒  SECURE ASSESSMENT MODE")
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        category_label = self._category.lower()                      # 'exam' or 'quiz'
        confirmation_text = f"I have finished and submitted the {category_label}".title()   # "I Have Finished And ..."
        self.done_button = QPushButton(confirmation_text)
        self.done_button.setObjectName("DoneButton")
        self.done_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_button.clicked.connect(self.handle_exam_completion)
        layout.addWidget(self.done_button)
        return bar

    # --- submission: automatic (form redirect) or manual (confirm dialog) ---
    def _on_load_finished(self, ok):
        """Web-frame hook: Google's post-submit page is docs.google.com/forms/.../formResponse."""
        if ok and self._auto_detect and not self._finished and is_submission_url(self.view.url().toString()):
            log.emit("FORM_SUBMISSION_DETECTED")
            # Keep the confirmation page visible briefly (and the lockdown on) before unlocking.
            QTimer.singleShot(self._grace_ms, lambda: self.complete("form_redirect"))

    def handle_exam_completion(self):
        """Student pressed 'I have finished': ask once, then finish."""
        if self._finished or ConfirmSubmitDialog(self, self._category).exec() != QDialog.DialogCode.Accepted:
            return                                   # "No, Return to Test"
        log.emit("EXAM_FINISHED_CONFIRMED")
        self.complete("student_confirmed")

    def complete(self, source):
        """Report the submission exactly once, then show the sign-off screen."""
        if self._finished:
            return
        self._finished = True
        self._allow_close = True
        self.exam_finished.emit(source)              # main.py: DB -> SUBMITTED, stop hooks/monitors (direct call)
        self.show_completion()

    def show_completion(self):
        """Disable the form and fade in the completion screen."""
        self.bubble.dismiss()
        self.view.setEnabled(False)
        self.stack.setCurrentWidget(self.completion)
        fx = QGraphicsOpacityEffect(self.completion)
        fx.setOpacity(0.0)
        self.completion.setGraphicsEffect(fx)
        self._fade = QPropertyAnimation(fx, b"opacity", self)
        self._fade.setDuration(450)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(lambda: QTimer.singleShot(0, lambda: self.completion.setGraphicsEffect(None)))
        self._fade.start()

    def release(self):
        """Teacher released this student: end the lockdown cleanly (no alert, no improper-exit flag)."""
        if self._finished:
            return
        self._finished = True
        self._allow_close = True
        self.completion.set_content("Session Ended by Your Teacher",
                                    "Your teacher has ended your lockdown session. You may now close the application.", "!")
        self.show_completion()

    def _close_application(self):
        """Handler for the Close Application button on the completion screen."""
        self._allow_close = True
        self.close()                                 # closeEvent quits the application

    def start(self):
        """Show the window full-screen and bring it to the front."""
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def allow_close(self):
        """Permit the window to really close (used after a successful teacher override)."""
        self._allow_close = True

    def _block_download(self, download):
        """Cancel any file download the page attempts, and log it."""
        download.cancel()
        log.emit("DOWNLOAD_BLOCKED")
        alerts.report("DOWNLOAD_BLOCKED", "A file download was blocked")

    def closeEvent(self, event):
        """Alt+F4 / taskbar close: ignored (and routed to the teacher-auth prompt) unless closing was authorized."""
        if self._allow_close:
            event.accept()
            QApplication.quit()
        else:
            event.ignore()
            self.exit_requested.emit()

    def changeEvent(self, event):
        """If the window is un-fullscreened (minimized / restored), log it and snap straight back to full screen."""
        if event.type() == QEvent.Type.WindowStateChange and not self.isFullScreen() and not self._allow_close:
            log.emit("WINDOW_STATE_RESTORED")
            alerts.report("WINDOW_VIOLATION", "Exam window was minimized or left full screen")
            self.warn("Leaving full screen or minimizing the exam is not allowed.")
            QTimer.singleShot(0, self.showFullScreen)
        super().changeEvent(event)


if __name__ == "__main__":
    # Demo: open one form with no teacher authorization and no database.
    if len(sys.argv) < 2:
        sys.exit("usage: python -m qesentry.student.exam_window <google-form-url>")
    app = QApplication(sys.argv)
    apply_theme(app)
    w = ExamWindow({"exam_url": sys.argv[1], "allowed_prefixes": ["https://forms.gle/"]}, "2022-01234-MN-0")
    w.exit_requested.connect(lambda: (w.allow_close(), w.close()))   # demo only: no auth
    w.exam_finished.connect(lambda src: print("submitted via", src))
    w.start()
    sys.exit(app.exec())