"""Per-student alert timeline (opened by double-clicking a row in the Live Monitor)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout)

from qesentry.core import db
from qesentry.ui.forms import MARGINS
from qesentry.ui.theme import APP_NAME, BADGES, BadgeDelegate, fit_window
from qesentry.teacher.form_helpers import make_label


class AlertTimelineDialog(QDialog):
    """Full timestamped alert history for one student login (opened by double-clicking a live-table row)."""

    def __init__(self, teacher_id, login_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – Alert Timeline")
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*MARGINS)
        lay.setSpacing(8)
        try:
            info, events = db.list_events(login_id, teacher_id)
        except db.DatabaseError as e:
            info, events = None, []
            lay.addWidget(make_label(str(e), "FieldError"))
        if info is None:
            lay.addWidget(make_label("This student record is not available.", "Subtitle"))
        else:
            lay.addWidget(make_label(f"{info['full_name'].upper()}  ·  {info['student_id']}", "Title"))
            lay.addWidget(make_label(f"{info['section']}  ·  {info['category']}: {info['exam_title']}  ·  {info['status'].replace('_', ' ')}", "Subtitle"))
            counts = {}
            for e in events:
                counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
            lay.addWidget(make_label("  ·  ".join(f"{k.replace('_', ' ').title()} {v}" for k, v in sorted(counts.items()))
                                 if counts else "No alerts recorded.", "Stat"))
            table = QTableWidget(len(events), 3)
            table.setHorizontalHeaderLabels(["Time", "Type", "Details"])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.setWordWrap(False)
            table.setItemDelegateForColumn(1, BadgeDelegate(table))
            hh = table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            for r, e in enumerate(events):
                table.setItem(r, 0, QTableWidgetItem(f"{db.to_local(e['timestamp']):%H:%M:%S}"))
                kind = QTableWidgetItem(e["event_type"].replace("_", " "))
                kind.setData(Qt.ItemDataRole.UserRole, e["event_type"] if e["event_type"] in BADGES else "UNLOCKED")
                table.setItem(r, 1, kind)
                table.setItem(r, 2, QTableWidgetItem(e["details"]))
            table.setMinimumHeight(220)
            lay.addWidget(table, 1)
        close = QPushButton("Close")
        close.setMinimumHeight(38)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        close.clicked.connect(self.accept)
        fit_window(self, 760, 520, min_size=(400, 300))
