"""Floating warning banner shown on top of the exam when a student tries to leave or cheat
(Alt+Tab, Win key, Alt+F4, copy/paste, clicking another window, opening a banned app ...).

Two looks, like the usual alert banners:
    YELLOW  "warning"  - a violation was just attempted; the right-hand label counts the strike ("Strike 2 of 3").
    RED     "error"    - the student has reached the strike limit (flag_threshold) and is now FLAGGED.

The banner is a small, always-on-top, click-through window: it never takes keyboard focus (so it cannot cause a
focus-loss alert itself), fades in at the top-centre of the exam screen and fades out by itself after a few seconds.
"""
from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

WARNING_COLOR = "#ECAE40"     # yellow: a violation was attempted
ERROR_COLOR = "#E5533F"       # red: the strike limit is reached

SHOW_MS = 4500                # how long the banner stays fully visible
FADE_MS = 220
TOP_MARGIN = 28               # px below the top edge of the screen
WIDTH = 680

_SWITCHING = {"alt+tab", "alt+shift+tab", "ctrl+alt+tab", "alt+esc", "ctrl+esc", "ctrl+shift+esc", "windows key"}
_CLOSING = {"alt+f4", "ctrl+w", "ctrl+f4", "ctrl+t", "ctrl+n", "ctrl+shift+n", "ctrl+shift+t"}
_CLIPBOARD = {"ctrl+c", "ctrl+v", "ctrl+x", "ctrl+insert", "shift+insert"}
_SCREENSHOT = {"print screen", "alt+print screen"}


def key_warning(hotkey):
    """Short, plain sentence for a blocked shortcut, e.g. 'alt+tab' -> 'Switching to other apps is not allowed.'"""
    hk = (hotkey or "").lower()
    if hk in _SWITCHING:
        return "Switching to other apps or windows is not allowed."
    if hk in _CLOSING:
        return "Closing or opening windows is not allowed during the exam."
    if hk in _CLIPBOARD:
        return "Copy and paste are disabled during the exam."
    if hk in _SCREENSHOT:
        return "Screenshots are not allowed during the exam."
    return f"The {hk.title()} shortcut is disabled during the exam."


def banner_level(strikes, limit):
    """'error' (red) once the student has reached the strike limit, otherwise 'warning' (yellow)."""
    return "error" if strikes >= limit else "warning"


def banner_texts(message, strikes, limit):
    """(main text, right-hand label) for the banner."""
    if banner_level(strikes, limit) == "error":
        return f"You have been flagged for too many violations. {message}", "Flagged"
    return message, (f"Strike {strikes} of {limit}" if strikes > 0 else "Warning")


def _icon(level, color):
    """White triangle (warning) or diamond (error) with a coloured '!' inside, drawn so no image files are needed."""
    size = 44
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    if level == "error":
        p.drawPolygon(QPolygonF([QPointF(22, 3), QPointF(41, 22), QPointF(22, 41), QPointF(3, 22)]))
    else:
        p.drawPolygon(QPolygonF([QPointF(22, 4), QPointF(41, 38), QPointF(3, 38)]))
    p.setPen(QColor(color))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(24)
    p.setFont(font)
    p.drawText(pm.rect().adjusted(0, 4 if level == "warning" else 0, 0, 0), Qt.AlignmentFlag.AlignCenter, "!")
    p.end()
    return QIcon(pm)


class WarningBubble(QWidget):
    """show_message(text, strikes, limit) pops the banner up (or refreshes it if it is already showing)."""

    def __init__(self, host):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        super().__init__(None, flags)
        self._host = host
        self.level = "warning"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.frame = QFrame(self)
        self.frame.setObjectName("WarningBanner")
        fx = QGraphicsDropShadowEffect(self.frame)
        fx.setBlurRadius(24)
        fx.setOffset(0, 5)
        fx.setColor(QColor(0, 0, 0, 80))
        self.frame.setGraphicsEffect(fx)

        self.icon = QLabel()
        self.icon.setFixedSize(26, 26)
        self.icon.setScaledContents(True)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.strike = QLabel("")                                  # right-hand label, underlined like the "Action" link
        self.strike.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row = QHBoxLayout(self.frame)
        row.setContentsMargins(18, 14, 20, 14)
        row.setSpacing(14)
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.message, 1)
        row.addWidget(self.strike, 0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 12, 20, 28)          # room for the shadow
        outer.addWidget(self.frame)
        self.setFixedWidth(WIDTH)
        self._apply_level("warning")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._after_fade)
        self._fading_out = False

    def _apply_level(self, level):
        self.level = level
        color = ERROR_COLOR if level == "error" else WARNING_COLOR
        self.frame.setStyleSheet(f"QFrame#WarningBanner {{ background-color: {color}; border: none; border-radius: 6px; }}"
                                 "QFrame#WarningBanner QLabel { background: transparent; color: #FFFFFF; }")
        self.message.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.strike.setStyleSheet("font-size: 13px; font-weight: 700; text-decoration: underline;")
        self.icon.setPixmap(_icon(level, color).pixmap(44, 44))

    def show_message(self, text, strikes=0, limit=3):
        """Show `text` at the top-centre of the exam screen: yellow, or red once strikes >= limit."""
        main, tag = banner_texts(text, strikes, limit)
        self._apply_level(banner_level(strikes, limit))
        self.message.setText(main)
        self.strike.setText(tag)
        self.layout().activate()
        self.setFixedHeight(self.layout().totalHeightForWidth(self.width()))
        screen = self._host.screen() if self._host is not None else None
        if screen is not None:
            area = screen.geometry()
            self.move(area.center().x() - self.width() // 2, area.top() + TOP_MARGIN)
        self._anim.stop()
        self._fading_out = False
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self.raise_()
        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(SHOW_MS)

    def _fade_out(self):
        self._fading_out = True
        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _after_fade(self):
        if self._fading_out:
            self.hide()

    def dismiss(self):
        """Hide immediately (the exam ended)."""
        self._timer.stop()
        self._anim.stop()
        self.hide()
