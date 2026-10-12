"""Small helpers shared by the teacher dialogs: form labels and the live password hints / click-time checks."""

from PyQt6.QtWidgets import QLabel

from qesentry.core.validators import MATCH, MIN_PASSWORD, MISMATCH, TOO_SHORT, length_hint, match_hint
from qesentry.ui.theme import set_state


# ----------------------------------------------------------------------------- small helpers
def make_label(text, name="FieldLabel"):
    lab = QLabel(text)
    lab.setObjectName(name)
    return lab


def password_hints(dialog, new_f, confirm_f, match_text=MATCH, mismatch_text=MISMATCH):
    """Live feedback under a 'new password' + 'confirm' pair (shown before any button is clicked).
    New password: green '✓ At least 8 characters' at 8+; a red 'Password must be at least 8 characters.' once the
    user has left the box (or started the confirm box) with fewer; nothing while still typing it.
    Confirm: red '✕ ... do not match' whenever it differs; green '✓ ... match' only when equal and 8+ characters.
    Both green boxes share one style. Returns (long_enough, match)."""
    new, confirm = new_f.edit.text(), confirm_f.edit.text()
    long_enough = len(new) >= MIN_PASSWORD
    text, kind = length_hint(new)
    state = "valid" if long_enough else ""
    if new and not long_enough and (confirm or not new_f.edit.hasFocus()):
        text, kind, state = TOO_SHORT, "error", "invalid"
    set_state(new_f.edit, state)
    dialog.say(new_f.msg, text, kind)
    text, kind, state = match_hint(new, confirm, match_text, mismatch_text)
    set_state(confirm_f.edit, state)
    dialog.say(confirm_f.msg, text, kind)
    return long_enough, state == "match"


def reject_new_passwords(dialog, new_f, confirm_f, mismatch_text):
    """Click-time check of a new-password pair. Returns True if it is fine. Otherwise explains the problem,
    empties both boxes so the user types them again, and returns False."""
    new, confirm = new_f.edit.text(), confirm_f.edit.text()
    if len(new) < MIN_PASSWORD:
        new_f.edit.clear(); confirm_f.edit.clear()
        dialog.flag(new_f, TOO_SHORT)
        new_f.edit.setFocus()
        return False
    if new != confirm:
        new_f.edit.clear(); confirm_f.edit.clear()
        set_state(new_f.edit, "mismatch"); set_state(confirm_f.edit, "mismatch")
        dialog.say(confirm_f.msg, mismatch_text, "error")
        new_f.edit.setFocus()
        return False
    return True
