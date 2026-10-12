"""Visual theme for the whole app: one palette + one global stylesheet, applied once with apply_theme(app).

Every window (role selector, student login, teacher portal, exam window, dialogs) uses this file, so spacing,
fonts, buttons, inputs, tables and scroll bars look identical everywhere.

Widgets opt in to special looks through Qt properties / object names:
    QLineEdit    property state   = "valid" | "invalid" | ""            green / red / neutral border
    QPushButton  property variant = "secondary" | "danger" | "ghost"    (default = filled primary)
    object names Title, Subtitle, Muted, FieldLabel, FieldError, FieldOk, Card, PortalCard, Header, ...
Helpers: secondary()/danger()/ghost(), make_header(), build_dialog(), scroll_area(), fit_window(),
         BadgeDelegate (coloured status pills in tables), CheckRow (check box with a real tick).
"""
import math
import sys
import time
from string import Template

import datetime as _dt

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPixmap, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPalette, QPen, QTextDocument
from PyQt6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame,
                             QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
                             QSizePolicy, QStyle,
                             QStyledItemDelegate, QStyleOptionViewItem, QTabBar, QTableView, QVBoxLayout, QWidget)

# ------------------------------------------------------------------ palette (neutral slate + one brand accent)
MAROON = "#7A0016"          # brand accent (primary buttons, links, focus)
MAROON_DARK = "#5C0011"     # hover
MAROON_DEEP = "#40000C"     # pressed
GOLD = "#C9A227"            # thin highlight rules
GOLD_BRIGHT = "#F2C94C"     # small highlights on the dark header
INK = "#1E293B"             # dark slate: header band, exam bottom bar
BG = "#F3F4F6"              # window background (light neutral)
SURFACE = "#FFFFFF"         # cards, inputs, tables
BORDER = "#E5E7EB"
INPUT_BORDER = "#D1D5DB"
TEXT = "#111827"
TEXT_SOFT = "#374151"
MUTED = "#6B7280"
DANGER = "#DC2626"          # red accent
DANGER_BG = "#FEF2F2"
DANGER_SOFT = "#FCA5A5"     # light red border (password mismatch)
SUCCESS = "#16A34A"         # green accent
SUCCESS_BG = "#F0FDF4"      # light green tint (valid link while focused)
SUCCESS_SOFT = "#DCFCE7"    # lighter green tint (passwords match)
SLATE = "#64748B"           # muted helper text
AMBER = "#D97706"           # "you skipped something" helper text

FONT_FAMILY = '"Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
APP_NAME = "QESentry"
INSTITUTION = "Polytechnic University of the Philippines"
FOOTER_TEXT = f"© 2026 Group 3  ·  Academic Project  ·  {INSTITUTION}"      # bottom of the welcome and submitted screens

# Status badge colours: key -> (text colour, background). Used by BadgeDelegate and anywhere a pill is drawn.
BADGES = {
    "ACTIVE": ("#1D4ED8", "#DBEAFE"),                  # blue
    "OPEN": ("#1D4ED8", "#DBEAFE"),                    # assessment open for students (blue)
    "SCHEDULED": ("#B45309", "#FEF3C7"),               # assessment waiting for its opening time (amber)
    "RE-OPENED": ("#4338CA", "#E0E7FF"),               # closed once, opened again by the teacher (indigo)
    "SUBMITTED": ("#15803D", "#DCFCE7"),               # green
    "FLAGGED": ("#B91C1C", "#FEE2E2"),                 # red
    "LOCKED": ("#0F766E", "#CCFBF1"),                  # teal
    "UNLOCKED": ("#4B5563", "#E5E7EB"),                # grey
    "RELEASED_BY_TEACHER": ("#6D28D9", "#EDE9FE"),     # violet
    "TERMINATED": ("#9F1239", "#FFE4E6"),              # rose
    "OVERRIDDEN": ("#9F1239", "#FFE4E6"),
    "CLOSED": ("#4B5563", "#E5E7EB"),
    "Exam": ("#1D4ED8", "#DBEAFE"),
    "Quiz": ("#7C3AED", "#EDE9FE"),
    "FOCUS_LOSS": ("#B45309", "#FEF3C7"),
    "BANNED_PROCESS": ("#B91C1C", "#FEE2E2"),
    "BLOCKED_URL": ("#9F1239", "#FFE4E6"),
    "KEYBOARD_VIOLATION": ("#6D28D9", "#EDE9FE"),
}
_BADGE_DEFAULT = ("#374151", "#E5E7EB")

_QSS = Template("""
QWidget { font-family: $FONT; font-size: 14px; color: $TEXT; }
QDialog, QMessageBox, QMainWindow { background-color: $BG; }
QToolTip { background-color: $INK; color: #FFFFFF; border: none; padding: 5px 9px; border-radius: 4px; }

/* ---------- text ---------- */
QLabel { background: transparent; }
QLabel#Title      { color: $INK; font-size: 22px; font-weight: 700; }
QLabel#Heading    { color: $INK; font-size: 16px; font-weight: 700; }
QLabel#Subtitle   { color: $TEXT_SOFT; font-size: 14px; }
QLabel#Muted      { color: $MUTED; font-size: 12px; }
QLabel#FieldHint  { color: $SLATE;   font-size: 12px; }
QLabel#FieldWarn  { color: $AMBER;   font-size: 12px; }
QLabel#FieldError { color: $DANGER;  font-size: 12px; font-weight: 600; }
QLabel#FieldOk    { color: $SUCCESS; font-size: 12px; font-weight: 600; }
QLabel#FieldLabel { color: $TEXT_SOFT; font-size: 13px; font-weight: 600; }
QLabel#Stat       { color: $INK; font-size: 13px; font-weight: 600; }
QLabel#HeroTitle  { color: $INK; font-size: 34px; font-weight: 700; }
QLabel#HeroSub    { color: $TEXT_SOFT; font-size: 17px; }
QLabel#CardTitle  { color: $INK; font-size: 20px; font-weight: 700; }
QLabel#CardDesc   { color: $TEXT_SOFT; font-size: 13px; }
QLabel#LinkLine   { color: $MUTED; font-size: 12px; }

/* ---------- header band ---------- */
QFrame#Header { background-color: $MAROON; border: none; border-bottom: 3px solid $GOLD; }
QLabel#HeaderTitle { color: #FFFFFF; font-size: 20px; font-weight: 700; letter-spacing: 0.4px; }
QLabel#HeaderSub   { color: $GOLD_BRIGHT; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#HeaderWelcome { color: #F3E3E6; font-size: 14px; }

/* ---------- cards ---------- */
QFrame#Card { background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 14px; }
QFrame#Card QLabel { background: transparent; }
QFrame#Toolbar { background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 12px; }
QFrame#Toolbar QLabel { background: transparent; }
QFrame#PortalCard { background-color: $SURFACE; border: 2px solid $BORDER; border-radius: 18px; }
QFrame#PortalCard:hover { border: 2px solid $MAROON; }
QFrame#PortalCard[enabled_card="false"], QFrame#PortalCard[enabled_card="false"]:hover { background-color: #F9FAFB; border: 2px dashed $INPUT_BORDER; }
QFrame#PortalCard QLabel { background: transparent; }
QLabel#PortalIcon { background-color: #F9ECEE; color: $MAROON; border-radius: 34px; font-size: 32px; }
QLabel#PortalIconTeacher { background-color: #E8EEFB; color: #1D4ED8; border-radius: 34px; font-size: 32px; }

QFrame#AppStatus { background-color: $SURFACE; border: 1px solid $BORDER; border-left: 4px solid $MUTED; border-radius: 8px; }
QFrame#AppStatus[state="blocked"] { border-left: 4px solid $DANGER; }
QFrame#AppStatus[state="clear"]   { border-left: 4px solid $SUCCESS; }
QFrame#AppStatus QLabel { background: transparent; }
QFrame#Notice { background-color: #FFFBEB; border: 1px solid #F3E4A8; border-left: 4px solid $GOLD; border-radius: 8px; }
QFrame#Notice QLabel { background: transparent; }

/* ---------- inputs ---------- */
QLineEdit {
    outline: none;
    background-color: $SURFACE; color: $TEXT;
    border: 1px solid transparent; border-radius: 8px;      /* colour is painted by draw_snapped_border() */
    padding: 10px 12px; font-size: 14px; min-height: 20px;
    selection-background-color: $MAROON; selection-color: #FFFFFF;
}
QDateTimeEdit {
    outline: none;
    background-color: $SURFACE; color: $TEXT;
    border: 1px solid $INPUT_BORDER; border-radius: 8px;
    padding: 10px 12px; font-size: 14px; min-height: 20px;
    selection-background-color: $MAROON; selection-color: #FFFFFF;
}
QDateTimeEdit:focus { border: 1px solid $MAROON; }
QLineEdit:disabled, QDateTimeEdit:disabled { background-color: #F3F4F6; color: $MUTED; }
QLineEdit[state="valid"], QLineEdit[state="valid"]:focus { background-color: $SUCCESS_BG; }
QLineEdit[state="match"], QLineEdit[state="match"]:focus { background-color: $SUCCESS_BG; }
QLineEdit[state="mismatch"], QLineEdit[state="mismatch"]:focus { background-color: $DANGER_BG; }
QLineEdit[state="invalid"], QLineEdit[state="invalid"]:focus { background-color: $DANGER_BG; }
QLineEdit QToolButton { background: transparent; border: none; padding: 0 4px; outline: none; }

/* ---------- drop-downs: rounded field + floating card list (see StyledComboBox) ---------- */
QComboBox {
    combobox-popup: 0; outline: none;
    background-color: $SURFACE; color: $TEXT;
    border: 1px solid transparent; border-radius: 10px;     /* colour is painted by draw_snapped_border() */
    padding: 10px 40px 10px 14px; font-size: 14px; min-height: 20px;
}
QComboBox:disabled { background-color: #F3F4F6; color: $MUTED; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 36px; border: none; background: transparent; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QListWidget#ComboList { background: transparent; border: none; outline: 0; padding: 0; }
QListWidget#ComboList::item { padding: 9px 14px; border-radius: 8px; color: $TEXT; }
QListWidget#ComboList::item:hover, QListWidget#ComboList::item:selected { background-color: #F9ECEE; color: $TEXT; }
QListWidget#ComboList QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 0 2px 0; }
QListWidget#ComboList QScrollBar::handle:vertical { background: #D1D5DB; border-radius: 3px; min-height: 28px; margin: 0 1px; }
QListWidget#ComboList QScrollBar::handle:vertical:hover { background: #9CA3AF; }

/* ---------- date / time fields with a leading icon (see qesentry/ui/pickers.py) ---------- */
QFrame#IconField { background-color: $SURFACE; border: 1px solid transparent; border-radius: 10px; }
QFrame#IconField QLabel { background: transparent; font-size: 14px; color: $TEXT; }
QFrame#IconField QDateTimeEdit, QFrame#IconField QDateTimeEdit:focus, QFrame#IconField QDateTimeEdit:hover {
    border: none; background: transparent; padding: 9px 0; min-height: 20px; font-size: 14px; }
QFrame#IconField QLineEdit { border: none; background: transparent; padding: 0; }
QCalendarWidget QWidget { background-color: $SURFACE; }
QCalendarWidget QToolButton { color: $TEXT; background: transparent; border: none; border-radius: 6px; padding: 4px 8px; font-weight: 600; }
QCalendarWidget QToolButton:hover { background-color: #F9ECEE; }
QCalendarWidget QMenu { background-color: $SURFACE; border: 1px solid $BORDER; }
QCalendarWidget QSpinBox { border: 1px solid $INPUT_BORDER; border-radius: 6px; padding: 2px 6px; }
QCalendarWidget QAbstractItemView:enabled { color: $TEXT; background-color: $SURFACE; selection-background-color: $MAROON; selection-color: #FFFFFF; outline: 0; border: none; }
QCalendarWidget QAbstractItemView:disabled { color: #9CA3AF; }

/* ---------- buttons ---------- */
QPushButton {
    outline: none;
    background-color: $MAROON; color: #FFFFFF;
    border: 1px solid $MAROON_DARK; border-radius: 8px;
    padding: 9px 20px; font-size: 14px; font-weight: 600;
}
QPushButton:hover   { background-color: $MAROON_DARK; }
QPushButton:pressed { background-color: $MAROON_DEEP; }
QPushButton:focus   { border: 2px solid $GOLD; outline: none; }
QPushButton:disabled { background-color: #E5E7EB; color: #9CA3AF; border: 1px solid #E5E7EB; outline: none; }
QPushButton[variant="secondary"] { background-color: $SURFACE; color: $MAROON; border: 2px solid $MAROON; padding: 8px 19px; }
QPushButton[variant="secondary"]:hover   { background-color: #FBF1F2; }
QPushButton[variant="secondary"]:pressed { background-color: #F3DCDF; }
QPushButton[variant="secondary"]:disabled { background-color: $SURFACE; color: #9CA3AF; border: 2px solid #E5E7EB; }
QPushButton[variant="danger"] { background-color: $SURFACE; color: $DANGER; border: 2px solid $DANGER; padding: 8px 19px; }
QPushButton[variant="danger"]:hover   { background-color: $DANGER_BG; }
QPushButton[variant="danger"]:pressed { background-color: #FEE2E2; }
QPushButton[variant="danger"]:disabled { background-color: $SURFACE; color: #9CA3AF; border: 2px solid #E5E7EB; }
QPushButton[variant="ghost"] { background-color: transparent; color: $TEXT_SOFT; border: 1px solid transparent; padding: 8px 12px; }
QPushButton[variant="ghost"]:hover { background-color: #E5E7EB; }
QPushButton[variant="ghost"]:pressed { background-color: #D1D5DB; }

QPushButton[compact="true"] { padding: 5px 12px; font-size: 13px; border-radius: 6px; min-height: 18px; }
QPushButton[compact="true"][variant="secondary"], QPushButton[compact="true"][variant="danger"] { padding: 4px 11px; }

/* ---------- search / sort / filter icon buttons + popups ---------- */
QToolButton#IconButton {
    background-color: $SURFACE; border: 2px solid $INPUT_BORDER; border-radius: 8px; padding: 0;
}
QToolButton#IconButton:hover { background-color: #FBF1F2; border: 2px solid $MAROON; }
QToolButton#IconButton:pressed { background-color: #F3DCDF; border: 2px solid $MAROON; }
QToolButton#IconButton:focus { border: 2px solid $MAROON; }
QToolButton#RowIcon { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0; }
QToolButton#RowIcon:hover { background-color: #F3F4F6; border: 1px solid $INPUT_BORDER; }
QToolButton#RowIcon[danger="true"]:hover { background-color: $DANGER_BG; border: 1px solid $DANGER_SOFT; }
QToolButton#RowIcon:pressed { background-color: #E5E7EB; }
QFrame#PopupBody { background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 12px; }
QFrame#PopupBody QLabel { background: transparent; }
QLabel#PopupHeading { color: $MUTED; font-size: 14px; padding: 0 0 4px 2px; }
QFrame#PopupRule { background-color: $BORDER; border: none; }
QRadioButton { background: transparent; spacing: 12px; padding: 6px 4px; font-size: 14px; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 9px; border: 2px solid #9CA3AF; background: $SURFACE; }
QRadioButton::indicator:hover { border: 2px solid $MAROON; }
QRadioButton::indicator:checked {
    border: 2px solid $MAROON;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 $MAROON, stop:0.45 $MAROON, stop:0.55 $SURFACE, stop:1 $SURFACE);
}
QToolButton#SortDir {
    background: transparent; color: $TEXT; border: 1px solid transparent; border-radius: 8px;
    padding: 7px 8px; text-align: left; font-size: 14px;
}
QToolButton#SortDir:hover { background-color: #F3F4F6; }
QToolButton#SortDir:checked { background-color: #FBF1F2; color: $MAROON; border: 1px solid $MAROON; }

/* ---------- live-monitor stat chips ---------- */
QFrame#StatChip { background-color: #F9FAFB; border: 1px solid $BORDER; border-radius: 16px; }
QLabel#StatValue   { color: $INK; font-size: 15px; font-weight: 700; }
QLabel#StatCaption { color: $MUTED; font-size: 13px; }

QToolButton, QAbstractButton, QComboBox, QTabBar { outline: none; }
QMessageBox QLabel { font-size: 14px; }
QMessageBox QPushButton { min-width: 88px; }

/* ---------- tables ---------- */
QTableWidget, QTableView {
    background-color: $SURFACE; alternate-background-color: #F9FAFB;
    border: 1px solid $BORDER; border-radius: 10px; gridline-color: #EEF0F3;
    selection-background-color: #F9ECEE; selection-color: $TEXT; outline: none;
}
QTableWidget::item { padding: 6px 8px; border: none; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background-color: #F3F4F6; color: $TEXT_SOFT; padding: 10px 12px;
    border: none; border-bottom: 1px solid $BORDER; font-weight: 700; font-size: 12px;
}
QTableCornerButton::section { background-color: #F3F4F6; border: none; }

/* ---------- tabs ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: $MUTED; padding: 12px 22px; margin-right: 4px;
    border: none; border-bottom: 3px solid rgba(122, 0, 22, 50); font-weight: 600; font-size: 14px;
}
QTabBar::tab:selected { color: $MAROON; border-bottom: 3px solid $MAROON; }
QTabBar::tab:hover:!selected { color: $TEXT; border-bottom: 3px solid rgba(122, 0, 22, 130); }

/* ---------- scrolling ---------- */
QScrollArea { background: transparent; border: none; }
QWidget#ScrollBody { background-color: $BG; }
QScrollBar:vertical   { background: transparent; width: 12px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:vertical   { background: #C4C8D0; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:horizontal { background: #C4C8D0; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:hover { background: $MUTED; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
""")


def build_qss():
    """Return the stylesheet text with the palette colours substituted in."""
    return _QSS.substitute(
        FONT=FONT_FAMILY, TEXT=TEXT, TEXT_SOFT=TEXT_SOFT, MAROON=MAROON, MAROON_DARK=MAROON_DARK,
        MAROON_DEEP=MAROON_DEEP, GOLD=GOLD, GOLD_BRIGHT=GOLD_BRIGHT, INK=INK, BG=BG, SURFACE=SURFACE,
        BORDER=BORDER, INPUT_BORDER=INPUT_BORDER, MUTED=MUTED, DANGER=DANGER, DANGER_BG=DANGER_BG,
        DANGER_SOFT=DANGER_SOFT, SUCCESS=SUCCESS, SUCCESS_BG=SUCCESS_BG, SUCCESS_SOFT=SUCCESS_SOFT,
        SLATE=SLATE, AMBER=AMBER)


def _colorref(hex_color):
    """'#RRGGBB' -> Windows COLORREF (0x00BBGGRR)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def _tint_title_bar(widget):
    """Colour the native Windows title bar maroon (Windows 11, build 22000+; silently ignored elsewhere)."""
    try:
        import ctypes
        hwnd = ctypes.c_void_p(int(widget.winId()))
        dwm = ctypes.windll.dwmapi
        for attr, color in ((35, MAROON), (36, "#FFFFFF"), (34, MAROON_DARK)):   # caption, text, border
            value = ctypes.c_int(_colorref(color))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


# ------------------------------------------------------------------ pixel-snapped field borders
FIELD_BORDER_W = 2                                                  # logical px: thickness of every field outline


def draw_snapped_border(widget, color, radius):
    """Paint a field's outline so it is the same thickness in every field.

    On a scaled display (125 % / 150 % ...) a 1 px stylesheet border is anti-aliased across device pixels, so it
    looks 1 px thick in one field and 2 px in the next depending on where the field sits. Here the outline is drawn
    in whole device pixels, aligned to the pixel grid, so every field gets the identical crisp line."""
    dpr = widget.devicePixelRatioF()
    origin = widget.mapTo(widget.window(), QPoint(0, 0))
    qround = lambda v: int(math.floor(v + 0.5))                    # Qt's rounding (Python's round() is banker's)
    left, top = qround(origin.x() * dpr), qround(origin.y() * dpr)
    right = qround((origin.x() + widget.width()) * dpr)
    bottom = qround((origin.y() + widget.height()) * dpr)
    thick = max(1, qround(FIELD_BORDER_W * dpr))
    w, h = max(2 * thick, right - left), max(2 * thick, bottom - top)
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(1.0 / dpr, 1.0 / dpr)                                  # 1 unit = 1 device pixel
    p.translate(left - origin.x() * dpr, top - origin.y() * dpr)   # lock the corners to the pixel grid
    pen = QPen(QColor(color), thick)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    r = QRectF(thick / 2.0, thick / 2.0, w - thick, h - thick)
    rad = radius * dpr - thick / 2.0
    p.drawRoundedRect(r, rad, rad)
    p.end()


def _line_edit_border(edit):
    state = edit.property("state")
    if not edit.isEnabled():
        return INPUT_BORDER
    if state in ("valid", "match"):
        return SUCCESS
    if state == "mismatch":
        return DANGER_SOFT
    if state == "invalid":
        return DANGER
    return MAROON if edit.hasFocus() else INPUT_BORDER


_KEEPS_FOCUS = (QLineEdit, QComboBox, QAbstractButton, QAbstractItemView, QTabBar)


def _clear_table_selection(target, global_pos=None):
    """A click anywhere that is not a row of the table un-highlights its selected row(s): another part of the window,
    a button, or the blank space below the last row. Tables that act on their selection through buttons (the Live
    Monitor's 'Release Student') opt out of the button case with the property keep_selection_on_buttons=True."""
    if target is None:
        return
    on_button = False
    w = target
    while w is not None:
        if isinstance(w, (QAbstractButton, QComboBox)):
            on_button = True
            break
        w = w.parentWidget()
    window = target.window()
    if window is None:
        return
    for table in window.findChildren(QTableView):
        if not table.isVisible() or not table.selectionModel() or not table.selectionModel().hasSelection():
            continue
        if on_button and table.property("keep_selection_on_buttons"):
            continue
        if table is target or table.isAncestorOf(target):
            # inside the table: only a click on the empty area of the grid (no row under the cursor) clears it
            if target is not table.viewport() or global_pos is None:
                continue
            if table.indexAt(table.viewport().mapFromGlobal(global_pos)).isValid():
                continue
        table.clearSelection()
        table.setCurrentIndex(table.rootIndex())             # also drop the focus rectangle / current cell


def _sync_button_cursor(button):
    """Pointing hand while a button can be clicked; the plain arrow while it is greyed out."""
    shape = Qt.CursorShape.PointingHandCursor if button.isEnabled() else Qt.CursorShape.ArrowCursor
    if button.cursor().shape() != shape:
        button.setCursor(shape)


class _AppEvents(QObject):
    """Two small app-wide behaviours:
    * clicking blank space (a label, a card, the window background) takes keyboard focus away from a text box,
      so its highlighted border disappears - the same behaviour the scrolling student form always had;
    * on Windows 11, every top-level window gets a maroon title bar to match the header.
    """

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            try:
                hit = QApplication.widgetAt(event.globalPosition().toPoint())
            except Exception:
                hit = None
            if hit is not None and event.button() == Qt.MouseButton.LeftButton:
                _clear_table_selection(hit, event.globalPosition().toPoint())
            focus = QApplication.focusWidget()
            if isinstance(focus, QLineEdit):
                try:
                    target = QApplication.widgetAt(event.globalPosition().toPoint())
                except Exception:
                    target = None
                if target is not None and target is not focus and not isinstance(target, _KEEPS_FOCUS):
                    focus.clearFocus()
        elif kind == QEvent.Type.Show and sys.platform == "win32" and isinstance(obj, QWidget) and obj.isWindow():
            _tint_title_bar(obj)
        if kind in (QEvent.Type.EnabledChange, QEvent.Type.Polish, QEvent.Type.Show) and isinstance(obj, QPushButton):
            _sync_button_cursor(obj)
        return False


def _light_palette():
    """A fixed light palette. Without it, Qt copies the Windows dark-mode palette and every part the stylesheet does
    not paint (combo-box pop-ups, scroll corners, tooltips...) turns black."""
    p = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                        (QPalette.ColorRole.Base, SURFACE), (QPalette.ColorRole.AlternateBase, "#F9FAFB"),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, MAROON),
                        (QPalette.ColorRole.HighlightedText, "#FFFFFF"), (QPalette.ColorRole.ToolTipBase, INK),
                        (QPalette.ColorRole.ToolTipText, "#FFFFFF"), (QPalette.ColorRole.PlaceholderText, "#9CA3AF"),
                        (QPalette.ColorRole.Link, MAROON), (QPalette.ColorRole.Light, "#FFFFFF"),
                        (QPalette.ColorRole.Mid, BORDER), (QPalette.ColorRole.Midlight, "#F3F4F6"),
                        (QPalette.ColorRole.Dark, INPUT_BORDER), (QPalette.ColorRole.Shadow, "#9CA3AF")):
        p.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9CA3AF"))
    return p


def apply_theme(app):
    """Set the style, default font and global stylesheet. Call once, right after creating the QApplication.

    The 'Fusion' style gives identical rendering on every Windows version (no native blue selection bars,
    consistent combo boxes and scroll bars) and lets the stylesheet control everything.
    """
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_qss())
    app._app_events = _AppEvents(app)                    # keep a reference
    app.installEventFilter(app._app_events)


# ------------------------------------------------------------------ helpers
def repolish(widget):
    """Re-apply the stylesheet after a dynamic property / objectName change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_state(line_edit, state):
    """state: "valid" | "match" | "mismatch" | "invalid" | "" (neutral). Drives the green / red input border."""
    line_edit.setProperty("state", state)
    repolish(line_edit)


def set_feedback(label, text, kind):
    """kind: "error" (red) | "ok" (green) | "warn" (amber) | "hint" (slate) | "" (grey). Message under a field."""
    label.setObjectName({"error": "FieldError", "ok": "FieldOk", "warn": "FieldWarn", "hint": "FieldHint"}.get(kind, "Muted"))
    label.setText(text)
    repolish(label)


def _variant(button, name):
    button.setProperty("variant", name)
    repolish(button)
    return button


def secondary(button):
    """Outlined 'secondary' button (Cancel / No / Back). Returns the button."""
    return _variant(button, "secondary")


def danger(button):
    """Red outlined button for destructive actions (Delete, Release, Log Out). Returns the button."""
    return _variant(button, "danger")


def ghost(button):
    """Flat, borderless button (low-emphasis links such as 'Back to Role Selection'). Returns the button."""
    return _variant(button, "ghost")


def compact(button):
    """Small button size for use inside table rows. Returns the button."""
    button.setProperty("compact", "true")
    repolish(button)
    return button


def polish_combo(combo):
    """Make a combo box's pop-up list follow the stylesheet (padding, hover colour, no dark frame)."""
    combo.setItemDelegate(QStyledItemDelegate(combo))
    return combo


class PopupCard(QFrame):
    """A small floating card (rounded corners, soft shadow) that closes when you click anywhere else.
    Put content in `.lay`. Used by the drop-down list and the calendar."""
    hidden = pyqtSignal()
    MARGINS = (12, 6, 12, 16)                 # transparent room around the card for its shadow

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.last_hidden = 0.0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*self.MARGINS)
        self.body = QFrame()
        self.body.setObjectName("PopupBody")
        add_shadow(self.body, blur=22, alpha=45)
        outer.addWidget(self.body)
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(6, 6, 6, 6)
        self.lay.setSpacing(0)

    def hideEvent(self, event):
        self.last_hidden = time.monotonic()
        super().hideEvent(event)
        self.hidden.emit()

    def recently_closed(self):
        """True for a moment after closing: the click that just closed the card must not re-open it."""
        return time.monotonic() - self.last_hidden < 0.25

    def open_below(self, anchor, gap=6):
        """Show the card under `anchor` (left edges lined up, a small gap), or above it when there is no room."""
        self.adjustSize()
        left, top, right, bottom = self.MARGINS
        below = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(below) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = below.x() - left
        y = below.y() + gap - top
        if y + self.height() > area.bottom():                       # not enough room underneath: open upwards
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - gap - (self.height() - bottom)
        x = max(area.left(), min(x, area.right() - self.width()))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(x, y)
        self.show()


class _ComboList(PopupCard):
    """The pop-up list of a StyledComboBox: one row per item, a scroll bar only when there are many."""
    chosen = pyqtSignal(int)
    MAX_ROWS = 7

    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo
        self.list = QListWidget()
        self.list.setObjectName("ComboList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSpacing(1)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setMouseTracking(True)
        self.list.itemClicked.connect(lambda item: self.chosen.emit(self.list.row(item)))
        self.list.itemActivated.connect(lambda item: self.chosen.emit(self.list.row(item)))
        self.lay.addWidget(self.list)

    def populate(self):
        """Rebuild the rows from the combo box and size the card: exactly as tall as the items, up to MAX_ROWS."""
        self.list.clear()
        for i in range(self.combo.count()):
            item = QListWidgetItem(self.combo.itemText(i))
            tip = self.combo.itemData(i, Qt.ItemDataRole.ToolTipRole)
            if tip:
                item.setToolTip(str(tip))
            self.list.addItem(item)
        self.list.setCurrentRow(self.combo.currentIndex())
        rows = max(1, min(self.combo.count(), self.MAX_ROWS))
        row_h = (self.list.sizeHintForRow(0) if self.combo.count() else 38) + self.list.spacing()
        self.list.setFixedHeight(rows * row_h + self.list.spacing() + 2)
        self.body.setFixedWidth(max(self.combo.width(), 120))
        self.adjustSize()


class StyledComboBox(QComboBox):
    """Drop-down with a rounded field, a chevron that flips while open, and a floating rounded card for the list
    (soft shadow, small gap under the field, pale hover rows). The list only gets a scroll bar when it is long.
    Use it everywhere instead of a plain QComboBox; the look itself lives in the stylesheet above."""
    GAP = 6                    # space between the field and the list

    def __init__(self, parent=None):
        super().__init__(parent)
        polish_combo(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("open", "false")
        self._popup = None                                   # built the first time the list is opened

    def _list(self):
        if self._popup is None:
            self._popup = _ComboList(self)
            self._popup.chosen.connect(self._choose)
            self._popup.hidden.connect(self._closed)
        return self._popup

    def _choose(self, row):
        self._popup.hide()
        if row >= 0:
            self.setCurrentIndex(row)
            self.activated.emit(row)

    def _closed(self):
        self.setProperty("open", "false")
        repolish(self)

    def showPopup(self):
        popup = self._list()
        if popup.isVisible() or popup.recently_closed() or not self.count():
            return
        popup.populate()
        self.setProperty("open", "true")
        repolish(self)
        popup.open_below(self, self.GAP)
        popup.list.setFocus()

    def hidePopup(self):
        if self._popup is not None:
            self._popup.hide()

    def paintEvent(self, event):
        super().paintEvent(event)                            # field, current text
        opened = self.property("open") == "true"
        if not self.isEnabled():
            edge = INPUT_BORDER
        elif opened or self.hasFocus():
            edge = MAROON
        else:
            edge = "#9CA3AF" if self.underMouse() else INPUT_BORDER
        draw_snapped_border(self, edge, 10)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(MAROON if opened or self.hasFocus() else SLATE), 1.9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx, cy = self.width() - 20.0, self.height() / 2.0
        d = -2.6 if opened else 2.6                          # chevron points up while the list is open
        path = QPainterPath()
        path.moveTo(QPointF(cx - 5, cy - d))
        path.lineTo(QPointF(cx, cy + d))
        path.lineTo(QPointF(cx + 5, cy - d))
        p.drawPath(path)
        p.end()

    def wheelEvent(self, event):
        event.ignore()                                       # scrolling a page must not change a drop-down by accident


class StatChip(QFrame):
    """Rounded 'pill' with a coloured dot, a number and a caption, e.g.  ● 4 Submitted."""

    def __init__(self, caption, color, parent=None):
        super().__init__(parent)
        self.setObjectName("StatChip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 14, 6)
        lay.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.value = QLabel("0")
        self.value.setObjectName("StatValue")
        cap = QLabel(caption)
        cap.setObjectName("StatCaption")
        lay.addWidget(dot)
        lay.addWidget(self.value)
        lay.addWidget(cap)

    def set_value(self, n):
        """Show a new count."""
        self.value.setText(str(n))


def make_header(subtitle="", title=APP_NAME):
    """Dark band with a gold rule: 'QESentry' + a small institutional/section line."""
    header = QFrame()
    header.setObjectName("Header")
    header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(header)
    lay.setContentsMargins(28, 14, 28, 12)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("HeaderTitle")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle.upper())
        s.setObjectName("HeaderSub")
        lay.addWidget(s)
    return header


def _greeting(now=None):
    hour = (now or _dt.datetime.now()).hour
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


def make_welcome_header(name, now=None):
    """Header for a signed-in portal: 'QESentry', then 'Good afternoon, <name>' underneath."""
    header = QFrame()
    header.setObjectName("Header")
    header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(header)
    lay.setContentsMargins(28, 14, 28, 14)
    lay.setSpacing(2)
    title = QLabel(APP_NAME)
    title.setObjectName("HeaderTitle")
    welcome = QLabel(f"{_greeting(now)}, <span style='color:{GOLD_BRIGHT}; font-weight:700;'>{_html_escape(name)}</span>")
    welcome.setObjectName("HeaderWelcome")
    welcome.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(title)
    lay.addWidget(welcome)
    return header


def _html_escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def add_shadow(widget, blur=22, alpha=30):
    """Subtle soft shadow for cards (leave >= `blur` px of margin around the card)."""
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, 3)
    fx.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(fx)


def build_dialog(dialog, header_sub, margins=(24, 22, 24, 22)):
    """Standard compact-dialog skeleton: header band on top, padded body below. Returns the body layout.
    Pass header_sub=None for a header-less dialog (e.g. a confirmation prompt)."""
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    if header_sub is not None:
        outer.addWidget(make_header(header_sub))
    body = QVBoxLayout()
    body.setContentsMargins(*margins)
    body.setSpacing(12)
    outer.addLayout(body)
    return body


def scroll_area(inner):
    """Wrap `inner` in a scroll area (vertical + horizontal bars appear only when needed).

    The area has no frame and the same background as the window, so the page looks the same - it just
    becomes scrollable when the screen is too small, so nothing (e.g. the Start button) is ever cut off.
    """
    inner.setObjectName("ScrollBody")
    inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setWidget(inner)
    return area


def fit_window(widget, width, height, min_size=(420, 320)):
    """Resize to the preferred size but never larger than ~92% of the available screen, then centre.

    Keeps windows fully on-screen on small / scaled displays; contents scroll instead of clipping.
    """
    screen = widget.screen() or QGuiApplication.primaryScreen()
    avail = screen.availableGeometry()
    w, h = min(width, int(avail.width() * 0.92)), min(height, int(avail.height() * 0.92))
    widget.setMinimumSize(min(min_size[0], w), min(min_size[1], h))
    widget.resize(w, h)
    widget.move(avail.center().x() - w // 2, avail.center().y() - h // 2)


# ------------------------------------------------------------------ status pills in tables
def _pill_font(base):
    """The font used inside status pills: the same size as the other cells, in a semi-bold weight."""
    font = QFont(base)
    font.setWeight(QFont.Weight.DemiBold)
    return font


class BadgeDelegate(QStyledItemDelegate):
    """Draws a cell as a coloured pill. The colour comes from BADGES[item.data(UserRole)]; the text is the
    cell's display text. Cells with no UserRole key are drawn normally, so one delegate can serve a column
    that is sometimes a badge (e.g. Alerts: plain number, or a red FLAGGED pill)."""

    def paint(self, painter, option, index):
        key = index.data(Qt.ItemDataRole.UserRole)
        if not key:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)   # row background / selection
        fg, bg = BADGES.get(key, _BADGE_DEFAULT)
        font = _pill_font(opt.font)
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(text) + 20, fm.height() + 6          # tight pill: 3px / 10px padding
        rect = QRectF(opt.rect.x() + 8, opt.rect.center().y() - h / 2 + 0.5, w, h)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, h / 2, h / 2)
        painter.setFont(font)
        painter.setPen(QColor(fg))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        if not index.data(Qt.ItemDataRole.UserRole):
            return base
        fm = QFontMetrics(_pill_font(option.font))
        text = str(index.data(Qt.ItemDataRole.DisplayRole))
        return QSize(fm.horizontalAdvance(text) + 20 + 8 + 12, base.height())      # never makes the row taller


class LabelledLinesDelegate(QStyledItemDelegate):
    """Draws a multi-line cell whose lines look like 'Opens: Oct 11, 2026 · 6:10 PM' with the word before the first
    colon in bold. A cell with no such lines (e.g. 'No schedule') is drawn normally."""

    @staticmethod
    def _html(text):
        rows = []
        for line in text.split("\n"):
            head, sep, rest = line.partition(": ")
            esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            rows.append(f"<b>{esc(head)}:</b> {esc(rest)}" if sep else esc(line))
        return "<br>".join(rows)

    def paint(self, painter, option, index):
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if ": " not in text:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)   # row background / selection
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(0)
        doc.setHtml(f"<div style='color:{TEXT};'>{self._html(text)}</div>")
        painter.save()
        painter.translate(opt.rect.x() + 8, opt.rect.center().y() - doc.size().height() / 2)
        doc.drawContents(painter)
        painter.restore()


# ------------------------------------------------------------------ check box with a real tick
class CheckBox(QCheckBox):
    """Brand-coloured check box that draws a white tick when checked (QSS alone can't draw the tick)."""
    SIZE = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def sizeHint(self):
        """Always a fixed square."""
        return QSize(self.SIZE, self.SIZE)

    def paintEvent(self, _event):
        """Draw the box (grey / brand / gold focus ring) and, when checked, the white tick."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = float(self.SIZE)
        box = QRectF(1.5, 1.5, size - 3, size - 3)
        if self.isChecked():
            fill, edge = QColor(MAROON), QColor(MAROON_DARK)
        else:
            fill = QColor(SURFACE)
            edge = QColor(MAROON if self.underMouse() else "#9CA3AF")
        if self.hasFocus():
            edge = QColor(GOLD)
        p.setPen(QPen(edge, 1.5))
        p.setBrush(fill)
        p.drawRoundedRect(box, 5, 5)
        if self.isChecked():
            tick = QPainterPath()
            tick.moveTo(size * 0.26, size * 0.53)
            tick.lineTo(size * 0.43, size * 0.70)
            tick.lineTo(size * 0.76, size * 0.32)
            pen = QPen(QColor("#FFFFFF"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(tick)


class FocusLineEdit(QLineEdit):
    """A line edit that tells you when it gains or loses keyboard focus (used to show 'accepted' only while typing)."""
    focused = pyqtSignal()
    blurred = pyqtSignal()
    clicked = pyqtSignal()                                # a mouse click inside the box (even if it already had focus)

    def paintEvent(self, event):
        super().paintEvent(event)
        draw_snapped_border(self, _line_edit_border(self), 8)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_reason = event.reason()
        self.focused.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.blur_reason = event.reason()
        self.blurred.emit()

    def left_by_user(self):
        """True if focus last moved to another widget (Tab / click), not because the window was deactivated."""
        return getattr(self, "blur_reason", None) not in (Qt.FocusReason.ActiveWindowFocusReason,
                                                          Qt.FocusReason.PopupFocusReason)


def _eye_icon(hidden):
    """Vector eye icon (slashed when the text is currently hidden), drawn so no image files are needed."""
    pm = QPixmap(40, 40)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(SLATE), 3.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    eye = QPainterPath()
    eye.moveTo(5, 20)
    eye.quadTo(20, 4, 35, 20)
    eye.quadTo(20, 36, 5, 20)
    p.drawPath(eye)
    p.drawEllipse(QRectF(14.5, 14.5, 11, 11))
    if hidden:
        p.setPen(QPen(QColor(SLATE), 3.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(8, 33, 32, 7)
    p.end()
    return QIcon(pm)


def add_password_toggle(edit):
    """Put an eye button on the right edge of a password box; clicking it switches Password <-> Normal echo."""
    action = QAction(edit)
    action.setCheckable(False)

    def refresh():
        hidden = edit.echoMode() == QLineEdit.EchoMode.Password
        action.setIcon(_eye_icon(hidden))
        action.setToolTip("Show password" if hidden else "Hide password")

    def toggle():
        edit.setEchoMode(QLineEdit.EchoMode.Normal if edit.echoMode() == QLineEdit.EchoMode.Password
                         else QLineEdit.EchoMode.Password)
        refresh()

    action.triggered.connect(toggle)
    refresh()
    edit.addAction(action, QLineEdit.ActionPosition.TrailingPosition)
    for button in edit.findChildren(QAbstractButton):          # the action's tool button
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    edit.eye_action = action
    return action


class _ClickLabel(QLabel):
    """A label that emits clicked when the left mouse button is released on it."""
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class CheckRow(QWidget):
    """Check box + wrapped, clickable text (QCheckBox itself can't wrap long text)."""
    toggled = pyqtSignal(bool)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.box = CheckBox()
        self.label = _ClickLabel(text)
        self.label.setWordWrap(True)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setContentsMargins(0, 1, 0, 0)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self.box, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.label, 1)
        self.label.clicked.connect(self.box.click)
        self.box.toggled.connect(self.toggled)

    def isChecked(self):
        """True if the tick box is currently checked."""
        return self.box.isChecked()
