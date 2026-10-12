"""Schedule picker widgets (painted icons, no image files):

    ToggleSwitch   on/off switch (maroon when on, with a tick)
    DateField      [calendar icon] Oct 11, 2026  - click opens a calendar card
    TimeField      [clock icon]    06:00 PM      - click a part and type, or use the arrow keys / mouse wheel
"""
from PyQt6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QTextCharFormat
from PyQt6.QtWidgets import QAbstractButton, QCalendarWidget, QFrame, QHBoxLayout, QLabel, QTimeEdit

from qesentry.ui.theme import GOLD, INPUT_BORDER, MAROON, SLATE, TEXT, PopupCard, draw_snapped_border, repolish

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ICON = 18


def _pixmap(draw, color=SLATE):
    pm = QPixmap(_ICON * 2, _ICON * 2)                       # drawn at 2x so it stays sharp on high-DPI screens
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p)
    p.end()
    return pm


def _draw_calendar(p):                                       # 18 x 18 grid
    p.drawRoundedRect(QRectF(2.5, 3.5, 13, 12), 2.5, 2.5)
    p.drawLine(QPointF(2.5, 7.5), QPointF(15.5, 7.5))
    p.drawLine(QPointF(6, 1.8), QPointF(6, 5))
    p.drawLine(QPointF(12, 1.8), QPointF(12, 5))


def _draw_clock(p):
    p.drawEllipse(QPointF(9, 9), 7, 7)
    p.drawLine(QPointF(9, 5), QPointF(9, 9))
    p.drawLine(QPointF(9, 9), QPointF(12, 11))


def _icon_label(draw):
    lab = QLabel()
    lab.setPixmap(_pixmap(draw))
    lab.setFixedSize(_ICON, _ICON)
    return lab


class ToggleSwitch(QAbstractButton):
    """Pill switch. Off = grey with the knob on the left; on = maroon with a white tick and the knob on the right."""
    W, H = 46, 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.W, self.H)

    def sizeHint(self):
        return QSize(self.W, self.H)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QRectF(1, 1, self.W - 2, self.H - 2)
        p.setPen(QPen(QColor(GOLD), 1.8) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(QColor(MAROON if on else "#CBD0D8"))
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        r = 9.0
        cx = self.W - 1 - 3 - r if on else 1 + 3 + r
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(cx, self.H / 2), r, r)
        if on:                                               # tick on the free (left) side of the track
            tick = QPainterPath()
            tick.moveTo(10.5, 13.4)
            tick.lineTo(13.3, 16.2)
            tick.lineTo(18.2, 10.2)
            pen = QPen(QColor("#FFFFFF"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(tick)
        p.end()


class _IconField(QFrame):
    """Rounded field with an icon on the left. `active` draws the maroon outline."""

    def __init__(self, draw):
        super().__init__()
        self.setObjectName("IconField")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(12, 0, 12, 0)
        self.lay.setSpacing(10)
        self.lay.addWidget(_icon_label(draw))

    def set_active(self, on):
        self.setProperty("active", "true" if on else "false")
        repolish(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        edge = MAROON if self.property("active") == "true" else ("#9CA3AF" if self.underMouse() else INPUT_BORDER)
        draw_snapped_border(self, edge, 10)


class DateField(_IconField):
    """[calendar] Oct 11, 2026 - the whole field is a button that opens a calendar card."""
    changed = pyqtSignal()

    def __init__(self, date=None):
        super().__init__(_draw_calendar)
        self._date = QDate(date) if date else QDate.currentDate()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.text = QLabel()
        self.lay.addWidget(self.text, 1)
        self._popup = self._cal = None                       # the calendar card is built the first time it is opened
        self._show()

    def _build_popup(self):
        self._popup = PopupCard(self)
        self._cal = QCalendarWidget()
        self._cal.setGridVisible(False)
        self._cal.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)
        self._cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self._cal.setMinimumSize(280, 230)
        plain = QTextCharFormat()                            # Qt paints weekends red by default; keep them neutral
        plain.setForeground(QColor(TEXT))
        for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
            self._cal.setWeekdayTextFormat(day, plain)
        self._cal.clicked.connect(self._picked)
        self._popup.lay.addWidget(self._cal)
        self._popup.hidden.connect(lambda: self.set_active(False))

    def date(self):
        return QDate(self._date)

    def setDate(self, date):
        if date != self._date:
            self._date = QDate(date)
            self._show()
            self.changed.emit()

    def _show(self):
        d = self._date
        self.text.setText(f"{_MONTHS[d.month() - 1]} {d.day()}, {d.year()}")

    def _picked(self, date):
        self._popup.hide()
        self.setDate(date)

    def _open(self):
        if self._popup is None:
            self._build_popup()
        if self._popup.isVisible() or self._popup.recently_closed():
            return
        self._cal.setSelectedDate(self._date)
        self._cal.showSelectedDate()
        self.set_active(True)
        self._popup.open_below(self, 6)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Down):
            self._open()
        else:
            super().keyPressEvent(event)


class _FocusTimeEdit(QTimeEdit):
    focusChanged = pyqtSignal(bool)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focusChanged.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusChanged.emit(False)


class TimeField(_IconField):
    """[clock] 06:00 PM - an editable time (hour, minute, AM/PM). No spin arrows: type, or use Up / Down / the wheel."""
    changed = pyqtSignal()

    def __init__(self, time=None):
        super().__init__(_draw_clock)
        self.setMinimumHeight(40)
        self.edit = _FocusTimeEdit()
        self.edit.setDisplayFormat("hh:mm AP")
        self.edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self.edit.setFrame(False)
        self.edit.setTime(time or QTime.currentTime())
        self.lay.addWidget(self.edit, 1)
        self.edit.focusChanged.connect(self.set_active)
        self.edit.timeChanged.connect(lambda _t: self.changed.emit())

    def time(self):
        return self.edit.time()

    def setTime(self, time):
        self.edit.setTime(time)
