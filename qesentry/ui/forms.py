"""One layout for every compact modal (forms and prompts), so they all look and space the same.

    ┌ 28px ─────────────────────────────┐
    │ Title                (22px, bold) │
    │   6px                             │
    │ Subtitle / description (14px)     │
    │   18px                            │
    │ Field label          (13px)       │
    │   6px                             │
    │ [ input ]                         │
    │   6px   helper / warning text     │  <- only takes space while it has text
    │   14px                            │
    │ ... next field ...                │
    │   22px                            │
    │             [ Cancel ] [ Action ] │
    └───────────────────────────────────┘
All modals are 480px wide; the height always fits the content (no empty space, no cramped stacking).
"""
from collections import namedtuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from qesentry.ui.theme import APP_NAME, FocusLineEdit, add_password_toggle, secondary, set_feedback, set_state

FORM_WIDTH = 480
MARGINS = (28, 24, 28, 24)
GAP_TITLE_SUBTITLE = 6
GAP_SUBTITLE_BODY = 18
GAP_LABEL_INPUT = 6
GAP_FIELD = 14
GAP_BODY_ACTIONS = 22
BUTTON_HEIGHT = 40

Field = namedtuple("Field", "edit msg")


def fit_height(dialog):
    """Make `dialog` exactly as tall as its content at its (fixed) width."""
    lay = dialog.layout()
    lay.invalidate()                                  # drop cached sizes: a section that was just hidden or shown has
    lay.activate()                                    # a new height the layout has not measured yet
    h = lay.totalHeightForWidth(dialog.width()) if lay.hasHeightForWidth() else lay.sizeHint().height()
    if h > 0:
        dialog.setFixedHeight(h)


class FormDialog(QDialog):
    """Title + subtitle + body (fields / notes) + action bar. Subclasses fill `self.body` and call add_actions()."""

    def __init__(self, parent, title, subtitle="", window_title=None, on_top=False):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – {window_title or title}")
        self.setModal(True)
        self.setFixedWidth(FORM_WIDTH)
        flags = Qt.WindowType.Dialog
        if on_top or (parent is not None and parent.window().windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
            flags |= Qt.WindowType.WindowStaysOnTopHint            # stay above a locked-down exam window
        self.setWindowFlags(flags)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(*MARGINS)
        self._root.setSpacing(0)
        head = QLabel(title)
        head.setObjectName("Title")
        head.setWordWrap(True)
        self._root.addWidget(head)
        self._flagged = set()
        self._flag_fields = {}                                 # edit -> Field, so a click can clear a red box
        self.subtitle = None
        if subtitle:
            self._root.addSpacing(GAP_TITLE_SUBTITLE)
            self.subtitle = QLabel(subtitle)
            self.subtitle.setObjectName("Subtitle")
            self.subtitle.setWordWrap(True)
            self._root.addWidget(self.subtitle)
        self._root.addSpacing(GAP_SUBTITLE_BODY)
        self.body = QVBoxLayout()
        self.body.setSpacing(0)
        self._root.addLayout(self.body)

    # ---- building blocks
    def add_field(self, label, placeholder="", password=False):
        """Label + input + a helper line that is hidden until it has text. Returns Field(edit, msg)."""
        group = QVBoxLayout()
        group.setSpacing(GAP_LABEL_INPUT)
        lab = QLabel(label)
        lab.setObjectName("FieldLabel")
        edit = FocusLineEdit()
        edit.setPlaceholderText(placeholder)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            add_password_toggle(edit)                       # eye button on the right edge
        msg = self.make_message()
        group.addWidget(lab)
        group.addWidget(edit)
        group.addWidget(msg)
        self.body.addLayout(group)
        self.body.addSpacing(GAP_FIELD)
        field = Field(edit, msg)
        edit.textChanged.connect(lambda _t, f=field: self._unflag(f))
        edit.clicked.connect(lambda f=field: self._unflag(f))     # clicking a red box returns it to normal
        return field

    def mousePressEvent(self, event):
        """Clicking empty space clears every red box that flag() marked."""
        for e in list(self._flagged):
            self._unflag(self._flag_fields[e])
        super().mousePressEvent(event)

    def flag(self, field, message):
        """Mark `field` red with a red message under it (used when the action button is clicked and the box is
        wrong or empty). The mark disappears as soon as the user types in that box."""
        self._flagged.add(field.edit)
        self._flag_fields[field.edit] = field
        set_state(field.edit, "invalid")
        self.say(field.msg, message, "error")

    def _unflag(self, field):
        if field.edit in self._flagged:
            self._flagged.discard(field.edit)
            set_state(field.edit, "")
            self.say(field.msg, "", "")

    def add_widget_field(self, label, widget):
        """Same label spacing for a non-text input (e.g. a combo box). Returns the widget."""
        group = QVBoxLayout()
        group.setSpacing(GAP_LABEL_INPUT)
        lab = QLabel(label)
        lab.setObjectName("FieldLabel")
        group.addWidget(lab)
        group.addWidget(widget)
        self.body.addLayout(group)
        self.body.addSpacing(GAP_FIELD)
        return widget

    def make_message(self):
        """A helper/warning line, hidden until it has text. Use say() to change it."""
        m = QLabel("")
        m.setObjectName("Muted")
        m.setWordWrap(True)
        m.setVisible(False)
        return m

    def add_message(self):
        """A free-standing message line at the end of the body (for errors that belong to the whole form)."""
        m = self.make_message()
        self.body.addWidget(m)
        return m

    def say(self, label, text, kind=""):
        """Show `text` in a helper line ('error' = red, 'ok' = green, '' = grey) and re-fit the window."""
        set_feedback(label, text, kind)
        label.setVisible(bool(text))
        self.refit()

    def add_actions(self, ok_text, cancel_text="Cancel", ok_slot=None, safe_default=False):
        """Right-aligned [Cancel] [Action] bar. Returns the action button.
        safe_default=True makes Cancel the default button (for destructive questions)."""
        self._root.addSpacing(GAP_BODY_ACTIONS - GAP_FIELD)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        ok = QPushButton(ok_text)
        ok.setMinimumHeight(BUTTON_HEIGHT)
        ok.setMinimumWidth(130)
        if cancel_text:
            cancel = secondary(QPushButton(cancel_text))
            cancel.setMinimumHeight(BUTTON_HEIGHT)
            cancel.setMinimumWidth(110)
            cancel.setAutoDefault(False)
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
            if safe_default:
                cancel.setAutoDefault(True)
                cancel.setDefault(True)
                ok.setAutoDefault(False)
        if not (cancel_text and safe_default):
            ok.setDefault(True)
        row.addWidget(ok)
        self._root.addLayout(row)
        if ok_slot is not None:
            ok.clicked.connect(ok_slot)
        return ok

    # ---- sizing
    def refit(self):
        """Make the window exactly as tall as its content at the fixed width."""
        try:
            fit_height(self)
        except RuntimeError:                  # a late focus-out signal arriving while the dialog is being destroyed
            pass
        QTimer.singleShot(0, self._refit_again)   # nested widgets finish re-measuring a moment later: fit once more

    def _refit_again(self):
        try:
            fit_height(self)
        except RuntimeError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.refit()
