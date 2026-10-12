"""Message prompts that share the QESentry modal layout (see forms.py): bold title, message, optional muted
note, and right-aligned buttons (outlined "No" on the left, filled "Yes" on the right).

    confirm(parent, "Delete Assessment", "Delete “Quiz 1”?", note="…", yes="Yes, Delete", no="Cancel") -> bool
    inform(parent, "Export Complete", "Exported 3 rows to …")
    warn(parent, "Could Not Save", "…")

Use these instead of QMessageBox so every prompt looks the same. In `confirm` the safe answer ("No") is the
default button, so a stray Enter or Esc never confirms a destructive action.
"""
from PyQt6.QtWidgets import QDialog

from qesentry.ui.forms import FormDialog


class PopupDialog(FormDialog):
    """Title + message (+ note) + buttons. exec() == Accepted means the primary (right-hand) button was pressed."""

    def __init__(self, parent, title, message, note="", yes="OK", no=None, danger_title=False):
        super().__init__(parent, title, message)
        if danger_title:
            self._root.itemAt(0).widget().setObjectName("FieldError")
        if note:
            n = self.make_message()
            n.setText(note)
            n.setVisible(True)
            self.body.addWidget(n)
            self.body.addSpacing(14)
        self.add_actions(yes, no, ok_slot=self.accept, safe_default=no is not None)


def confirm(parent, title, message, note="", yes="Yes", no="No"):
    """Ask a yes/no question. True only if the primary button was pressed."""
    return PopupDialog(parent, title, message, note, yes, no).exec() == QDialog.DialogCode.Accepted


def inform(parent, title, message, note="", ok="OK"):
    """Show a one-button information prompt."""
    PopupDialog(parent, title, message, note, ok).exec()


def warn(parent, title, message, note="", ok="OK"):
    """Show a one-button problem prompt (red title)."""
    PopupDialog(parent, title, message, note, ok, danger_title=True).exec()
