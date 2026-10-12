"""Search / Sort / Filter controls shared by the teacher dashboard tabs.

    make_search(placeholder)             search box with a magnifier icon and a clear (x) button
    SortButton(options, key, ascending)  icon button -> popup "Sort by" (radio list) + Ascending / Descending
    FilterButton(fields, on_reset)       icon button -> popup with labelled drop-downs and a Reset button;
                                         shows a small dot while a filter is active (set_active)

All icons are painted with QPainter (no image files), like the password eye icon in theme.py.
"""
import time

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QRadioButton, QToolButton, QVBoxLayout)

from qesentry.ui.theme import DANGER, MAROON, SLATE, TEXT_SOFT, FocusLineEdit, add_shadow, compact, ghost

_ICON = 20          # icons are drawn on a 20 x 20 grid


# ----------------------------------------------------------------------------- painted icons
def _icon(draw, color):
    pm = QPixmap(_ICON * 2, _ICON * 2)                      # drawn at 2x so it stays sharp on high-DPI screens
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p)
    p.end()
    return QIcon(pm)


def _draw_search(p):
    p.drawEllipse(QPointF(8.5, 8.5), 5.3, 5.3)
    p.drawLine(QPointF(12.5, 12.5), QPointF(17, 17))


def _draw_sort(p):                                           # three bars, getting shorter
    for y, x2 in ((5, 17), (10, 13), (15, 9)):
        p.drawLine(QPointF(3, y), QPointF(x2, y))


def _draw_filter(p):                                         # funnel outline
    f = QPainterPath()
    f.moveTo(3, 4.5)
    f.lineTo(17, 4.5)
    f.lineTo(11.6, 10.8)
    f.lineTo(11.6, 16)
    f.lineTo(8.4, 14.4)
    f.lineTo(8.4, 10.8)
    f.closeSubpath()
    p.drawPath(f)


def _draw_arrow(up):
    def draw(p):
        p.drawLine(QPointF(10, 16), QPointF(10, 4))
        tip, d = (4, 5.2) if up else (16, -5.2)
        p.drawLine(QPointF(10, tip), QPointF(10 - 5.2, tip + d))
        p.drawLine(QPointF(10, tip), QPointF(10 + 5.2, tip + d))
    return draw


def _lock_body(p):
    p.drawRoundedRect(QRectF(4.5, 9, 11, 8), 2, 2)
    p.drawPoint(QPointF(10, 13))


def _draw_lock_closed(p):                                    # padlock, shackle down: "close this assessment"
    _lock_body(p)
    sh = QPainterPath()
    sh.moveTo(7, 9)
    sh.lineTo(7, 7)
    sh.cubicTo(7, 2.2, 13, 2.2, 13, 7)
    sh.lineTo(13, 9)
    p.drawPath(sh)


def _draw_lock_open(p):                                      # padlock, shackle lifted: "re-open"
    _lock_body(p)
    sh = QPainterPath()
    sh.moveTo(7, 9)
    sh.lineTo(7, 6)
    sh.cubicTo(7, 1.8, 13, 1.8, 13, 5)
    p.drawPath(sh)


def _draw_trash(p):
    p.drawLine(QPointF(4, 5.5), QPointF(16, 5.5))
    h = QPainterPath()
    h.moveTo(8, 5.5)
    h.lineTo(8, 3.5)
    h.lineTo(12, 3.5)
    h.lineTo(12, 5.5)
    p.drawPath(h)
    b = QPainterPath()
    b.moveTo(5.5, 5.5)
    b.lineTo(6.4, 16.5)
    b.lineTo(13.6, 16.5)
    b.lineTo(14.5, 5.5)
    p.drawPath(b)
    p.drawLine(QPointF(8.6, 8.5), QPointF(8.6, 13.5))
    p.drawLine(QPointF(11.4, 8.5), QPointF(11.4, 13.5))


_ROW_ICONS = {"close": (_draw_lock_closed, TEXT_SOFT), "reopen": (_draw_lock_open, TEXT_SOFT), "delete": (_draw_trash, DANGER)}


def row_icon_button(kind, tip):
    """Small icon-only button for a table row's Actions cell. kind: "close" | "reopen" | "delete"."""
    draw, color = _ROW_ICONS[kind]
    b = QToolButton()
    b.setObjectName("RowIcon")
    b.setProperty("danger", "true" if kind == "delete" else "false")
    b.setIcon(_icon(draw, color))
    b.setIconSize(QSize(_ICON, _ICON))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setFixedSize(32, 32)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def search_icon():
    return _icon(_draw_search, SLATE)


def _toggle_icon(draw):
    """Grey when off, maroon when the (checkable) button is selected."""
    ic = _icon(draw, TEXT_SOFT)
    on = _icon(draw, MAROON).pixmap(QSize(_ICON, _ICON))
    ic.addPixmap(on, QIcon.Mode.Normal, QIcon.State.On)
    return ic


# ----------------------------------------------------------------------------- search box
def make_search(placeholder):
    """A search line edit with a leading magnifier and a clear button."""
    edit = FocusLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setClearButtonEnabled(True)
    edit.addAction(search_icon(), QLineEdit.ActionPosition.LeadingPosition)
    return edit


# ----------------------------------------------------------------------------- popup + icon button
class _PopupPanel(QFrame):
    """A small floating card that closes when you click anywhere else."""

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.last_hidden = 0.0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 16)              # room for the drop shadow
        self.body = QFrame()
        self.body.setObjectName("PopupBody")
        add_shadow(self.body, blur=22, alpha=45)
        outer.addWidget(self.body)
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(14, 12, 14, 12)
        self.lay.setSpacing(4)

    def hideEvent(self, event):
        self.last_hidden = time.monotonic()
        super().hideEvent(event)

    def show_below(self, button):
        """Open under `button`, right edges lined up, kept inside the screen."""
        self.adjustSize()
        g = button.mapToGlobal(QPoint(button.width(), button.height()))
        x, y = g.x() - self.width() + 12, g.y() - 4
        screen = QGuiApplication.screenAt(g) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = max(area.left(), min(x, area.right() - self.width()))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(x, y)
        self.show()


class _IconButton(QToolButton):
    """Square icon-only button that opens a popup panel."""

    def __init__(self, icon, tip, parent=None):
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setIcon(icon)
        self.setIconSize(QSize(_ICON, _ICON))
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setFixedSize(42, 42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._popup = _PopupPanel(self)
        self.clicked.connect(self._toggle)

    def _toggle(self):
        if self._popup.isVisible():
            self._popup.hide()
        elif time.monotonic() - self._popup.last_hidden > 0.25:   # the click that just closed it must not re-open it
            self._popup.show_below(self)


def _heading(text):
    lab = QLabel(text)
    lab.setObjectName("PopupHeading")
    return lab


def _rule():
    line = QFrame()
    line.setObjectName("PopupRule")
    line.setFixedHeight(1)
    return line


# ----------------------------------------------------------------------------- sort
class SortButton(_IconButton):
    """Sort icon. Popup: 'Sort by' radio list, then Ascending / Descending. Emits sortChanged on every change.

    options: list of (label, key).   Read the choice from .key and .ascending.
    """
    sortChanged = pyqtSignal()

    def __init__(self, options, key, ascending=True, parent=None):
        super().__init__(_icon(_draw_sort, TEXT_SOFT), "Sort", parent)
        self.key, self.ascending = key, ascending
        lay = self._popup.lay
        lay.addWidget(_heading("Sort by"))
        self._by = QButtonGroup(self)
        for label, k in options:
            rb = QRadioButton(label)
            rb.setChecked(k == key)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.toggled.connect(lambda on, k=k: on and self._set(key=k))
            self._by.addButton(rb)
            lay.addWidget(rb)
        lay.addSpacing(4)
        lay.addWidget(_rule())
        lay.addSpacing(4)
        self._dir = QButtonGroup(self)
        self._dir_buttons = {}
        for label, asc, up in (("Ascending", True, True), ("Descending", False, False)):
            b = QToolButton()
            b.setObjectName("SortDir")
            b.setText(label)
            b.setIcon(_toggle_icon(_draw_arrow(up)))
            b.setIconSize(QSize(_ICON, _ICON))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setCheckable(True)
            b.setChecked(asc == ascending)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=asc: self._set(ascending=a))
            self._dir.addButton(b)
            self._dir_buttons[asc] = b
            lay.addWidget(b)
        self._popup.body.setMinimumWidth(230)

    def _set(self, key=None, ascending=None):
        changed = False
        if key is not None and key != self.key:
            self.key, changed = key, True
        if ascending is not None and ascending != self.ascending:
            self.ascending, changed = ascending, True
        if changed:
            self.sortChanged.emit()


# ----------------------------------------------------------------------------- filter
class FilterButton(_IconButton):
    """Filter icon. Popup: one labelled widget (usually a combo box) per field, plus a Reset button.

    fields: list of (label, widget).  on_reset: called when Reset is pressed.
    set_active(True) draws a dot on the icon so the teacher can see a filter is on.
    """

    def __init__(self, fields, on_reset, parent=None):
        super().__init__(_icon(_draw_filter, TEXT_SOFT), "Filter", parent)
        self._active = False
        self._idle, self._on = _icon(_draw_filter, TEXT_SOFT), _icon(_draw_filter, MAROON)
        lay = self._popup.lay
        lay.setSpacing(6)
        lay.addWidget(_heading("Filter"))
        for label, widget in fields:
            cap = QLabel(label)
            cap.setObjectName("FieldLabel")
            lay.addSpacing(2)
            lay.addWidget(cap)
            lay.addWidget(widget)
        lay.addSpacing(6)
        row = QHBoxLayout()
        row.addStretch(1)
        reset = compact(ghost(QPushButton("Reset filters")))
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(on_reset)
        row.addWidget(reset)
        lay.addLayout(row)
        self._popup.body.setMinimumWidth(270)

    def set_active(self, active):
        if active != self._active:
            self._active = active
            self.setIcon(self._on if active else self._idle)
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._active:                                      # small maroon dot, top-right of the icon
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(QColor(MAROON))
            p.drawEllipse(QPointF(self.width() - 10, 10), 4.2, 4.2)
            p.end()
