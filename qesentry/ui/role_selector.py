"""Landing screen: choose "Student Portal" or "Teacher Portal".

RoleSelector emits student_selected / teacher_selected. A portal this install has no credentials for
(see config.available_roles) is shown greyed out with an explanation instead of being hidden.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from qesentry.ui.popups import confirm
from qesentry.ui.theme import APP_NAME, FOOTER_TEXT, add_shadow, fit_window, make_header, scroll_area, secondary


class PortalCard(QFrame):
    """A large clickable card: icon, title, description, and a button. Clicking anywhere on it counts."""
    chosen = pyqtSignal()

    def __init__(self, icon, title, description, button_text, enabled=True, note="", teacher=False):
        super().__init__()
        self.setObjectName("PortalCard")
        self._enabled_card = enabled
        self.setProperty("enabled_card", "true" if enabled else "false")
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        add_shadow(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(10)
        ic = QLabel(icon)
        ic.setObjectName("PortalIconTeacher" if teacher else "PortalIcon")
        ic.setFixedSize(68, 68)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d = QLabel(description)
        d.setObjectName("CardDesc")
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)
        lay.addWidget(t)
        lay.addWidget(d, 1)
        self.button = QPushButton(button_text if enabled else "Not available")
        self.button.setEnabled(enabled)
        self.button.setMinimumHeight(40)
        if teacher:
            secondary(self.button)
        lay.addSpacing(8)
        lay.addWidget(self.button)
        if note and not enabled:
            n = QLabel(note)
            n.setObjectName("Muted")
            n.setWordWrap(True)
            n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(n)
        self.button.clicked.connect(self.chosen)

    def mouseReleaseEvent(self, event):
        if self._enabled_card and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.chosen.emit()
        super().mouseReleaseEvent(event)


class RoleSelector(QWidget):
    """The window shown at launch and whenever a portal hands control back ('Back to Role Selection', 'Log Out')."""
    student_selected = pyqtSignal()
    teacher_selected = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, student_ok=True, teacher_ok=True):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self._quitting = False

        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(32, 28, 32, 24)
        col.setSpacing(6)
        col.addStretch(1)
        hello = QLabel(f"Welcome to {APP_NAME}")
        hello.setObjectName("HeroTitle")
        hello.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Secure online exams and quizzes. Choose how you want to continue.")
        sub.setObjectName("HeroSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        col.addWidget(hello)
        col.addWidget(sub)
        col.addSpacing(18)

        cards = QHBoxLayout()
        cards.setSpacing(22)
        cards.addStretch(1)
        student = PortalCard("🎓", "Student Portal", "Log in with your student ID and take your exam or quiz in a secure, locked-down window.",
                             "Continue as Student", student_ok, "The student portal is not set up on this device.")
        teacher = PortalCard("📋", "Teacher Portal", "Create exams and quizzes, watch students live, review alerts and export results.",
                             "Continue as Teacher", teacher_ok, "The Teacher Portal is not available on student devices.", teacher=True)
        cards.addWidget(student)
        cards.addWidget(teacher)
        cards.addStretch(1)
        col.addLayout(cards)
        col.addStretch(2)

        foot = QLabel(FOOTER_TEXT)          # centred, same as the "Exam / Quiz Submitted" screen
        foot.setObjectName("Muted")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(foot)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(make_header("Secure Assessment Platform"))
        outer.addWidget(scroll_area(page), 1)

        student.chosen.connect(self.student_selected)
        teacher.chosen.connect(self.teacher_selected)
        fit_window(self, 920, 640, min_size=(460, 420))

    def _confirm_quit(self):
        """Ask before closing the whole app (the window's X)."""
        if confirm(self, "Quit QESentry", "Are you sure you want to quit?", note="Any open portal will be closed.",
                   yes="Yes, Quit", no="Cancel"):
            self._quitting = True
            self.quit_requested.emit()

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
        else:
            event.ignore()                       # never leave an invisible background process: ask first
            self._confirm_quit()
