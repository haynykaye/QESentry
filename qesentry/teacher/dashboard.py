"""Teacher dashboard: tabs Live Monitor | Assessments | Settings.

  Live Monitor  search box + Sort (name / login time / submitted time) + Filter (Section, Category, Assessment) icons,
                live table with status badges, double-click a row = alert timeline, Release Student, Export CSV
  Assessments   search box + Sort (title / date created) + Filter (Category, Status) icons;
                create / edit / close / delete exams and quizzes
  Settings      edit profile, change password, Log Out

The dashboard reads the database on a background thread, so a slow server never freezes the window.
"""
import time

from PyQt6.QtCore import QItemSelectionModel, QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QMainWindow, QPushButton, QTableWidget,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from qesentry.core import csv_export
from qesentry.core import db
from qesentry.core.listing import filter_exams, sort_exams, sort_live_rows
from qesentry.ui.list_controls import FilterButton, SortButton, make_search, row_icon_button
from qesentry.ui.popups import confirm, inform, warn
from qesentry.ui.theme import (APP_NAME, BadgeDelegate, LabelledLinesDelegate, StatChip, StyledComboBox, danger, fit_window,
    make_welcome_header, scroll_area, secondary)
from qesentry.teacher.account_dialogs import ChangePasswordDialog, ProfileDialog
from qesentry.teacher.alert_timeline import AlertTimelineDialog
from qesentry.teacher.assessment_dialog import AssessmentDialog, ReopenDialog
from qesentry.teacher.form_helpers import make_label


# ----------------------------------------------------------------------------- background refresh
class _Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class _FetchTask(QRunnable):
    """Runs fn() on a pool thread so a slow database never freezes the dashboard."""

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)            # the dashboard keeps the reference until the result arrives

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except db.DatabaseError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:               # never let a worker die silently
            self.signals.failed.emit(f"Unexpected error: {e}")


LIVE_COLUMNS = ["Student ID", "Name", "Section", "Category", "Assessment", "Login Time", "Lockdown", "Status", "Alerts"]


EXAM_COLUMNS = ["Title", "Category", "Target Section(s)", "Status", "Schedule", "Students", "Created", "Actions"]


def _table(columns, stretch=(), widths=None):
    """A read-only table. `widths` ({column: pixels}) pins columns to a fixed width; columns in `stretch` share the
    spare width; every other column is exactly as wide as its content. If the window is too narrow the table scrolls sideways instead of squeezing the text."""
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.verticalHeader().setVisible(False)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    hh = t.horizontalHeader()
    hh.setMinimumSectionSize(80)
    hh.setStretchLastSection(False)
    hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for c in range(len(columns)):
        if widths and c in widths:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            t.setColumnWidth(c, widths[c])
        else:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch if c in stretch else QHeaderView.ResizeMode.ResizeToContents)
    t.setMinimumHeight(260)
    return t


def _badge_item(text, key):
    item = QTableWidgetItem(text)
    item.setData(Qt.ItemDataRole.UserRole, key)
    return item


class ProctorDashboard(QMainWindow):
    """The Teacher Portal home: Live Monitor, Assessments, Settings. Emits logged_out when the teacher signs out."""
    logged_out = pyqtSignal()

    def __init__(self, cfg, teacher):
        super().__init__()
        self.cfg, self.teacher = cfg, teacher
        self._task = None
        self._rows = []                       # last rows shown in the live table, in display order (CSV export uses these)
        self._live_raw = []                   # the same rows before sorting, so a sort change needs no new database read
        self._exams = []                      # every assessment of this teacher
        self._exams_shown = []                # the ones matching the search / filter, in display order
        self._exams_sig = None                # what the Assessments table currently shows
        self._logging_out = False
        self.setWindowTitle(f"{APP_NAME} – Teacher Portal")

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header_holder = QVBoxLayout()
        outer.addLayout(self.header_holder)
        self._set_header()
        self.tabs = QTabWidget()
        self.tabs.setContentsMargins(20, 0, 20, 0)
        self.tabs.addTab(scroll_area(self._build_live()), "Live Monitor")
        self.tabs.addTab(scroll_area(self._build_assessments()), "Assessments")
        self.tabs.addTab(scroll_area(self._build_settings()), "Settings")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        fit_window(self, 1280, 780, min_size=(560, 420))
        self._update_buttons()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(int(cfg["dashboard_refresh_ms"]))
        self._fill_combo(self.f_section, [], "All sections")
        self._fill_combo(self.f_exam, [], "All assessments")
        self.refresh()

    def _set_header(self):
        while self.header_holder.count():
            w = self.header_holder.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.header_holder.addWidget(make_welcome_header(self.teacher["full_name"]))

    # ------------------------------------------------------------- Live Monitor tab
    def _build_live(self):
        page = QWidget()
        page.setMinimumWidth(980)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)

        bar = QFrame()
        bar.setObjectName("Toolbar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 10)
        self.release_btn = danger(QPushButton("Release Student"))
        self.release_btn.setToolTip("Unlock the selected student(s). Their app exits lockdown within a few seconds, without an alert.")
        self.export_btn = secondary(QPushButton("Export CSV"))
        self.chips = {}
        bl.setSpacing(8)
        for key, caption, color in (("total", "Students", "#374151"), ("active", "Active", "#1D4ED8"),
                                    ("submitted", "Submitted", "#15803D"), ("flagged", "Flagged", "#B91C1C")):
            self.chips[key] = StatChip(caption, color)
            bl.addWidget(self.chips[key])
        bl.addStretch(1)
        bl.addWidget(self.release_btn)
        bl.addWidget(self.export_btn)
        lay.addWidget(bar)

        flt = QFrame()
        flt.setObjectName("Toolbar")
        fl = QHBoxLayout(flt)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(8)
        self.f_section, self.f_category, self.f_exam = (StyledComboBox() for _ in range(3))
        self.f_category.addItem("All categories", None)
        for c in db.CATEGORIES:
            self.f_category.addItem(c, c)
        self.f_search = make_search("Search student ID or name…")
        self.sort_btn = SortButton([("Name", "name"), ("Login time", "login"), ("Submitted time", "submitted")],
                                   key="login", ascending=False)
        self.filter_btn = FilterButton([("Section", self.f_section), ("Category", self.f_category),
                                        ("Assessment", self.f_exam)], on_reset=self._clear_filters)
        fl.addWidget(self.f_search, 1)                      # search on the left, Sort and Filter icons to its right
        fl.addWidget(self.sort_btn)
        fl.addWidget(self.filter_btn)
        lay.addWidget(flt)

        self.table = _table(LIVE_COLUMNS, stretch=(1, 4))
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setProperty("keep_selection_on_buttons", True)       # 'Release Student' acts on the picked rows
        self.badges = BadgeDelegate(self.table)
        for col in (3, 6, 7, 8):
            self.table.setItemDelegateForColumn(col, self.badges)
        lay.addWidget(self.table, 1)
        self.status = QLabel("Connecting…")
        self.status.setObjectName("Muted")
        lay.addWidget(self.status)

        self.release_btn.clicked.connect(self._release)
        self.export_btn.clicked.connect(self._export)
        self.table.itemDoubleClicked.connect(self._open_timeline)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        for c in (self.f_section, self.f_category, self.f_exam):
            c.currentIndexChanged.connect(self.refresh)
            c.currentIndexChanged.connect(self._sync_filter_dot)
        self.f_search.textChanged.connect(self.refresh)
        self.sort_btn.sortChanged.connect(lambda: self._show_live(self._live_raw))
        return page

    # ------------------------------------------------------------- Assessments tab
    def _build_assessments(self):
        page = QWidget()
        page.setMinimumWidth(1000)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(8)
        self.a_search = make_search("Search assessment title…")
        self.a_sort = SortButton([("Title", "title"), ("Date created", "created")], key="created", ascending=False)
        self.a_category = StyledComboBox()
        self.a_category.addItem("All categories", None)
        for c in db.CATEGORIES:
            self.a_category.addItem(c, c)
        self.a_status = StyledComboBox()
        self.a_status.addItem("All statuses", None)
        self.a_status.addItem("Open (incl. re-opened)", "OPEN")
        self.a_status.addItem("Scheduled", "SCHEDULED")
        self.a_status.addItem("Closed", "CLOSED")
        self.a_filter = FilterButton([("Category", self.a_category), ("Status", self.a_status)],
                                     on_reset=self._clear_exam_filters)
        self.a_new = QPushButton("＋ New Assessment")
        bl.addWidget(self.a_search, 1)                      # search on the left, Sort and Filter icons to its right
        bl.addWidget(self.a_sort)
        bl.addWidget(self.a_filter)
        bl.addSpacing(12)
        bl.addWidget(self.a_new)
        lay.addWidget(bar)
        self.exam_table = _table(EXAM_COLUMNS, stretch=(0,), widths={1: 110, 2: 170, 3: 130, 4: 270, 5: 90, 6: 150, 7: 110})
        self.exam_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.exam_badges = BadgeDelegate(self.exam_table)
        for col in (1, 3):
            self.exam_table.setItemDelegateForColumn(col, self.exam_badges)
        self.exam_schedule = LabelledLinesDelegate(self.exam_table)           # bold "Opens:" / "Closes:"
        self.exam_table.setItemDelegateForColumn(4, self.exam_schedule)
        lay.addWidget(self.exam_table, 1)
        self.a_hint = QLabel()
        self.a_hint.setObjectName("Muted")
        lay.addWidget(self.a_hint)
        self.a_new.clicked.connect(self._new_assessment)
        self.a_search.textChanged.connect(self._show_exams)
        self.a_sort.sortChanged.connect(self._show_exams)
        for c in (self.a_category, self.a_status):
            c.currentIndexChanged.connect(self._show_exams)
        self.exam_table.itemDoubleClicked.connect(
            lambda item: self._edit_assessment(self.exam_table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole + 1)))
        return page

    # ------------------------------------------------------------- Settings tab
    def _build_settings(self):
        page = QWidget()
        page.setMinimumWidth(520)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(14)

        prof = QFrame()
        prof.setObjectName("Card")
        pl = QVBoxLayout(prof)
        pl.setContentsMargins(24, 20, 24, 20)
        pl.setSpacing(6)
        pl.addWidget(make_label("Profile", "Heading"))
        self.p_name = QLabel()
        self.p_name.setObjectName("Title")
        self.p_user = QLabel()
        self.p_user.setObjectName("Subtitle")
        pl.addWidget(self.p_name)
        pl.addWidget(self.p_user)
        row = QHBoxLayout()
        edit = secondary(QPushButton("Edit Profile"))
        pw = secondary(QPushButton("Change Password"))
        row.addWidget(edit)
        row.addWidget(pw)
        row.addStretch(1)
        pl.addSpacing(8)
        pl.addLayout(row)
        lay.addWidget(prof)

        sess = QFrame()
        sess.setObjectName("Card")
        sl = QVBoxLayout(sess)
        sl.setContentsMargins(24, 20, 24, 20)
        sl.setSpacing(6)
        sl.addWidget(make_label("Session", "Heading"))
        note = make_label("Signing out returns to the role selection screen. Students who are mid-exam are not affected.", "Subtitle")
        note.setWordWrap(True)
        sl.addWidget(note)
        self.logout_btn = QPushButton("Log Out")
        self.logout_btn.setMinimumHeight(42)
        self.logout_btn.setMaximumWidth(220)
        sl.addSpacing(8)
        sl.addWidget(self.logout_btn)
        lay.addWidget(sess)
        lay.addStretch(1)
        self._fill_profile()

        edit.clicked.connect(self._edit_profile)
        pw.clicked.connect(self._change_password)
        self.logout_btn.clicked.connect(self._logout)
        return page

    def _fill_profile(self):
        self.p_name.setText(self.teacher["full_name"])
        self.p_user.setText(self.teacher["username"])

    # ------------------------------------------------------------- filters / refresh
    def _clear_filters(self):
        """Reset the Live Monitor filter drop-downs (the search box has its own clear button)."""
        for c in (self.f_section, self.f_category, self.f_exam):
            c.blockSignals(True)
            c.setCurrentIndex(0)
            c.blockSignals(False)
        self._sync_filter_dot()
        self.refresh()

    def _clear_exam_filters(self):
        for c in (self.a_category, self.a_status):
            c.blockSignals(True)
            c.setCurrentIndex(0)
            c.blockSignals(False)
        self._show_exams()

    def _sync_filter_dot(self):
        """Put a dot on each Filter icon while one of its drop-downs is not on 'All'."""
        self.filter_btn.set_active(any(c.currentIndex() > 0 for c in (self.f_section, self.f_category, self.f_exam)))
        self.a_filter.set_active(any(c.currentIndex() > 0 for c in (self.a_category, self.a_status)))

    @staticmethod
    def _fill_combo(combo, items, all_label):
        """items: list of (label, value, tooltip). Keeps the current selection when it still exists."""
        keep = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, None)
        for label, value, tip in items:
            combo.addItem(label, value)
            combo.setItemData(combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        i = combo.findData(keep)
        combo.setCurrentIndex(i if i >= 0 else 0)
        combo.blockSignals(False)

    def refresh(self):
        """Start a background read using the current filters (skipped if one is already running)."""
        if self._task is not None or self._logging_out:
            return
        tid = self.teacher["id"]
        section, category = self.f_section.currentData(), self.f_category.currentData()
        exam_id, search = self.f_exam.currentData(), self.f_search.text()

        def fetch():
            return {"rows": db.monitor_rows(tid, section, exam_id, category, search),
                    "sections": db.sections_in_use(tid),
                    "exams": db.list_exams(tid, active_only=False, with_counts=True)}

        self._task = _FetchTask(fetch)
        self._task.signals.done.connect(self._show)
        self._task.signals.failed.connect(self._show_error)
        QThreadPool.globalInstance().start(self._task)

    def _show_error(self, msg):
        self._task = None
        self.status.setText(f"⚠ {msg}  (retrying…)")

    def _show(self, data):
        self._task = None
        self._exams = data["exams"]
        self._fill_combo(self.f_section, [(s, s, "") for s in data["sections"]], "All sections")
        self._fill_combo(self.f_exam, [(f"{x['title']}{'' if x['status'] == 'ACTIVE' else '  (closed)'}", x["id"], x["form_url"])
                                       for x in self._exams], "All assessments")
        self._sync_filter_dot()
        self._show_live(data["rows"])
        self._show_exams()
        self.status.setText(f"Live – updated {time.strftime('%H:%M:%S')}  (every {self.cfg['dashboard_refresh_ms'] / 1000:g}s)")
        self._update_buttons()

    def _show_live(self, rows):
        self._live_raw = rows
        rows = self._rows = sort_live_rows(rows, self.sort_btn.key, self.sort_btn.ascending)
        flag = int(self.cfg.get("flag_threshold", 3))
        keep = {i.data(Qt.ItemDataRole.UserRole) for i in self.table.selectedItems() if i.column() == 0}
        vbar, hbar = self.table.verticalScrollBar().value(), self.table.horizontalScrollBar().value()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            sid = QTableWidgetItem(x["student_id"])
            sid.setData(Qt.ItemDataRole.UserRole, x["id"])
            if x["status"] == "SUBMITTED" and x["submitted_time"]:
                status_text = f"SUBMITTED · {db.to_local(x['submitted_time']):%H:%M:%S}"
            else:
                status_text = "RELEASED" if x["status"] == "RELEASED_BY_TEACHER" else x["status"]
            if x["alerts"] >= flag and flag > 0:
                alert = _badge_item(f"⚑ {x['alerts']}", "FLAGGED")
            else:
                alert = QTableWidgetItem(str(x["alerts"]) if x["alerts"] else "")
            cells = [sid, QTableWidgetItem(x["full_name"].upper()), QTableWidgetItem(x["section"]),
                     _badge_item(x["category"], x["category"]), QTableWidgetItem(x["exam_title"]),
                     QTableWidgetItem(f"{db.to_local(x['login_time']):%Y-%m-%d %H:%M:%S}"),
                     _badge_item(x["lockdown"], x["lockdown"]), _badge_item(status_text, x["status"]), alert]
            for c, item in enumerate(cells):
                self.table.setItem(r, c, item)
            if x["id"] in keep:
                self._select_row(self.table, r)
        self.table.setUpdatesEnabled(True)
        self.table.verticalScrollBar().setValue(vbar)
        self.table.horizontalScrollBar().setValue(hbar)
        active = sum(1 for x in rows if x["status"] == "ACTIVE")
        done = sum(1 for x in rows if x["status"] == "SUBMITTED")
        flagged = sum(1 for x in rows if flag > 0 and x["alerts"] >= flag)
        for key, n in (("total", len(rows)), ("active", active), ("submitted", done), ("flagged", flagged)):
            self.chips[key].set_value(n)

    def _show_exams(self):
        shown = filter_exams(self._exams, self.a_search.text(), self.a_category.currentData(), self.a_status.currentData())
        self._exams_shown = shown = sort_exams(shown, self.a_sort.key, self.a_sort.ascending)
        self._sync_filter_dot()
        total = len(self._exams)
        filtering = bool(self.a_search.text().strip()) or any(c.currentIndex() > 0 for c in (self.a_category, self.a_status))
        if not total:
            self.a_hint.setText("No assessments yet. Click “＋ New Assessment” to create one.")
        elif not shown:
            self.a_hint.setText(f"No assessments match your search or filter ({total} in total).")
        else:
            count = f"Showing {len(shown)} of {total} assessments.  " if filtering else ""
            self.a_hint.setText(count + "Double-click a row to edit it or change its schedule. Padlock = close / re-open, bin = delete.")
        sig = tuple((x["id"], x["title"], x["category"], tuple(x["sections"]), x["status"], x["state"], x["label"], x["opens_at"],
                     x["closes_at"], x["students"], x["created_at"]) for x in shown)
        if sig == self._exams_sig:
            return                                   # unchanged: leave the row buttons alone
        self._exams_sig = sig
        vbar = self.exam_table.verticalScrollBar().value()
        self.exam_table.setRowCount(len(shown))
        for r, x in enumerate(shown):
            title = QTableWidgetItem(x["title"])
            title.setData(Qt.ItemDataRole.UserRole + 1, x["id"])
            cells = [title, _badge_item(x["category"], x["category"]), self._tip(QTableWidgetItem(", ".join(x["sections"]) or "All sections")),
                     _badge_item(x["label"], x["label"]), self._tip(QTableWidgetItem(self._schedule_text(x))),
                     QTableWidgetItem(str(x["students"] or 0)), QTableWidgetItem(f"{db.to_local(x['created_at']):%Y-%m-%d %H:%M}")]
            for c, item in enumerate(cells):
                self.exam_table.setItem(r, c, item)
            self.exam_table.setCellWidget(r, 7, self._action_cell(x))
            self.exam_table.setRowHeight(r, 56)
        self.exam_table.verticalScrollBar().setValue(vbar)

    @staticmethod
    def _schedule_text(x):
        """The Schedule cell: 'No schedule', or two lines such as
            Opens: Mar 8, 2026 · 4:30 PM
            Closes: Oct 11, 2026 · 5:35 PM"""
        lines = []
        if x["opens_at"] is not None:
            lines.append(f"Opens: {db.format_schedule(x['opens_at'])}")
        if x["closes_at"] is not None:
            lines.append(f"Closes: {db.format_schedule(x['closes_at'])}")
        return "\n".join(lines) or "No schedule"

    @staticmethod
    def _tip(item):
        item.setToolTip(item.text())                   # long section lists are cut off in the cell; hover shows all
        return item

    def _action_cell(self, x):
        """The Actions column (icons): Close (if open) OR Re-Open (if closed), then Delete. Double-click the row to edit."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addStretch(1)
        if x["state"] != "CLOSED":                       # open, or waiting for its opening time
            toggle = row_icon_button("close", "Close assessment")
            toggle.clicked.connect(lambda _=False, i=x["id"]: self._close_assessment(i))
        else:
            toggle = row_icon_button("reopen", "Re-Open assessment (set a new date and time, or none)")
            toggle.clicked.connect(lambda _=False, i=x["id"]: self._reopen_assessment(i))
        lay.addWidget(toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        delete = row_icon_button("delete", "Delete assessment")
        delete.clicked.connect(lambda _=False, i=x["id"]: self._delete_assessment(i))
        lay.addWidget(delete, 0, Qt.AlignmentFlag.AlignVCenter)
        return w

    def _exam_by_id(self, exam_id):
        return next((x for x in self._exams if x["id"] == exam_id), None)

    @staticmethod
    def _select_row(table, row):
        """Add a whole row to the selection (selectRow() would drop the other selected rows)."""
        table.selectionModel().select(table.model().index(row, 0), QItemSelectionModel.SelectionFlag.Select
                                      | QItemSelectionModel.SelectionFlag.Rows)

    def _selected_logins(self):
        ids = {}
        for i in self.table.selectedItems():
            if i.column() == 0:
                ids[i.data(Qt.ItemDataRole.UserRole)] = i.text()
        return ids

    def _update_buttons(self):
        logins = self._selected_logins()
        by_id = {x["id"]: x for x in self._rows}
        self.release_btn.setEnabled(any(by_id.get(i, {}).get("status") == "ACTIVE" for i in logins))
        self.export_btn.setEnabled(bool(self._rows))

    # ------------------------------------------------------------- Live Monitor actions
    def _open_timeline(self, item):
        sid = self.table.item(item.row(), 0)
        if sid is not None:
            AlertTimelineDialog(self.teacher["id"], sid.data(Qt.ItemDataRole.UserRole), self).exec()

    def _release(self):
        by_id = {x["id"]: x for x in self._rows}
        targets = [i for i in self._selected_logins() if by_id.get(i, {}).get("status") == "ACTIVE"]
        if not targets:
            return
        names = ", ".join(by_id[i]["full_name"].upper() for i in targets[:4]) + (f" and {len(targets) - 4} more" if len(targets) > 4 else "")
        if not confirm(self, "Release Student", f"Release {len(targets)} student(s)?\n\n{names}",
                       note="Their windows will unlock within a few seconds. Use this only if the student had a "
                            "technical problem or has been told to stop.", yes="Yes, Release", no="Cancel"):
            return
        try:
            n = db.release_students(targets, self.teacher["id"])
        except db.DatabaseError as e:
            warn(self, "Something Went Wrong", str(e))
            return
        self.status.setText(f"Released {n} student(s).")
        self.refresh()

    def _export(self):
        if not self._rows:
            return
        default = f"qesentry_{time.strftime('%Y%m%d_%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default, "CSV files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = csv_export.export_rows(self._rows, path)
        except OSError as e:
            warn(self, "Could Not Save", f"Could not save the file:\n{e}", note="If it is open in Excel, close it and try again.")
            return
        inform(self, "Export Complete", f"Exported {n} row(s) to:\n{path}",
               note="Only the rows currently shown (with your filters applied) were exported.")

    # ------------------------------------------------------------- Assessment actions
    def _new_assessment(self):
        dlg = AssessmentDialog(self.teacher, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            x = dlg.exam
            for_whom = ', '.join(x['sections']) or 'all sections'
            if x["state"] == "SCHEDULED":
                inform(self, f"{x['category']} Created", f"{x['category']} “{x['title']}” is scheduled for {for_whom}.",
                       note=f"Students can log in from {db.format_local(x['opens_at'])}.")
            else:
                inform(self, f"{x['category']} Created", f"{x['category']} “{x['title']}” is open for {for_whom}.",
                       note="Students can now select it when they log in.")
            self.refresh()

    def _edit_assessment(self, exam_id):
        exam = self._exam_by_id(exam_id)
        if exam is None:
            return
        if AssessmentDialog(self.teacher, self, exam).exec() == QDialog.DialogCode.Accepted:
            self._exams_sig = None
            self.refresh()

    def _close_assessment(self, exam_id):
        exam = self._exam_by_id(exam_id)
        if exam is None or not confirm(self, f"Close {exam['category']}", f"Close “{exam['title']}”?",
                                       note="No new students will be able to log in. Students already inside are not affected. "
                                            "You can re-open it later.", yes="Yes, Close", no="Cancel"):
            return
        try:
            db.close_exam(exam["id"], self.teacher["id"])
        except db.DatabaseError as e:
            warn(self, "Something Went Wrong", str(e))
        self.refresh()

    def _reopen_assessment(self, exam_id):
        exam = self._exam_by_id(exam_id)
        if exam is None:
            return
        dlg = ReopenDialog(exam, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            changed = db.reopen_exam(exam["id"], self.teacher["id"], dlg.opens_at, dlg.closes_at)
        except (ValueError, db.DatabaseError) as e:
            warn(self, "Something Went Wrong", str(e))
            return
        if not changed:
            warn(self, "Nothing Changed", "That assessment is already open, or no longer exists.")
        elif dlg.opens_at is not None and dlg.opens_at > db.utcnow():
            inform(self, f"{exam['category']} Re-Opened", f"“{exam['title']}” is scheduled again.",
                   note=f"Students can log in from {db.format_local(dlg.opens_at)}.")
        else:
            until = f" until {db.format_local(dlg.closes_at)}" if dlg.closes_at else ""
            inform(self, f"{exam['category']} Re-Opened", f"“{exam['title']}” is open again{until}.",
                   note="Students can select it in the Student Portal and log in.")
        self._exams_sig = None
        self.refresh()

    def _delete_assessment(self, exam_id):
        exam = self._exam_by_id(exam_id)
        if exam is None:
            return
        extra = f" {exam['students']} student record(s) are attached to it." if exam.get("students") else ""
        if not confirm(self, f"Delete {exam['category']}", f"Delete “{exam['title']}”?",
                       note="It disappears from every list, nobody can log in to it, and any student still locked "
                            f"inside is released.{extra}  Export a CSV first if you need the results.",
                       yes="Yes, Delete", no="Cancel"):
            return
        try:
            released = db.delete_exam(exam["id"], self.teacher["id"])
        except (ValueError, db.DatabaseError) as e:
            warn(self, "Something Went Wrong", str(e))
            return
        self.status.setText(f"Deleted “{exam['title']}”; released {released} student(s).")
        self.refresh()

    # ------------------------------------------------------------- Settings actions
    def _edit_profile(self):
        dlg = ProfileDialog(self.teacher, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.teacher["full_name"] = dlg.full_name
            self._fill_profile()
            self._set_header()
            inform(self, "Profile Updated", "Your profile has been updated.", note=f"Your name is now {dlg.full_name}.")

    def _change_password(self):
        if ChangePasswordDialog(self.teacher, self).exec() == QDialog.DialogCode.Accepted:
            inform(self, "Password Changed", "Your password has been changed.")

    def _logout(self):
        if not confirm(self, "Log Out", "Log out and return to role selection?",
                       note="Students who are mid-exam are not affected.", yes="Yes, Log Out", no="Cancel"):
            return
        self.shutdown()
        self._logging_out = True
        self.logged_out.emit()

    # ------------------------------------------------------------- lifecycle
    def shutdown(self):
        """Stop refreshing (the window may be hidden or deleted next)."""
        self._timer.stop()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
        if not self._logging_out:                # closing the window with X exits the app
            QApplication.quit()
