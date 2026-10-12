"""Teacher account dialogs: Edit Profile and Change Password."""

from qesentry.core import db
from qesentry.ui.forms import FormDialog
from qesentry.ui.theme import set_state
from qesentry.teacher.form_helpers import password_hints, reject_new_passwords


class ProfileDialog(FormDialog):
    """Edit the teacher's own profile (full name). Save Changes stays grey until the name actually changes.
    On success: .full_name."""

    def __init__(self, teacher, parent=None):
        super().__init__(parent, "Edit Profile", "Update your account information below.")
        self.teacher, self.full_name = teacher, None
        self._original = " ".join(teacher["full_name"].split())
        self.name_f = self.add_field("Full Name")
        self.name_f.edit.setText(teacher["full_name"])
        self.user_f = self.add_field("Email / Username")
        self.user_f.edit.setText(teacher["username"])
        self.user_f.edit.setEnabled(False)
        self.err = self.add_message()
        self.ok_btn = self.add_actions("Save Changes", ok_slot=self._save)
        self.name_f.edit.textChanged.connect(self._changed)
        self._changed()
        self.name_f.edit.setFocus()

    def _changed(self):
        new = " ".join(self.name_f.edit.text().split())
        self.ok_btn.setEnabled(len(new) >= 3 and new != self._original)
        if self.err.isVisible():
            self.say(self.err, "", "")

    def _save(self):
        try:
            self.full_name = db.update_teacher_name(self.teacher["id"], self.name_f.edit.text())
        except (ValueError, db.DatabaseError) as e:
            self.say(self.err, str(e), "error")
            return
        self.accept()


class ChangePasswordDialog(FormDialog):
    """Change the teacher's password. The button stays grey until the current password is typed and the new one is 8+ characters and confirmed.

    Wrong current password  -> that box turns red and ALL three boxes are emptied.
    New passwords not matching / too weak -> the new + confirm boxes turn red and are emptied;
                                             the current password stays typed.
    """

    def __init__(self, teacher, parent=None):
        super().__init__(parent, "Change Password", "Enter your current password and choose a new one.")
        self.teacher = teacher
        self.cur_f = self.add_field("Current Password", "Enter your current password", password=True)
        self.new_f = self.add_field("New Password", "At least 8 characters", password=True)
        self.new2_f = self.add_field("Confirm New Password", "Re-enter your new password", password=True)
        self.ok_btn = self.add_actions("Change Password", ok_slot=self._save)
        self.ok_btn.setEnabled(False)
        self.cur_f.edit.textChanged.connect(self._cur_changed)
        self.new_f.edit.textChanged.connect(self._new_changed)
        self.new2_f.edit.textChanged.connect(self._new_changed)
        self.new_f.edit.blurred.connect(self._new_changed)
        self.cur_f.edit.setFocus()

    def _enable(self):
        """Active as soon as anything is typed; the checks run when the button is clicked."""
        self.ok_btn.setEnabled(any(f.edit.text() for f in (self.cur_f, self.new_f, self.new2_f)))

    def _cur_changed(self):
        set_state(self.cur_f.edit, "")
        self.say(self.cur_f.msg, "", "")
        self._enable()

    def _new_changed(self):
        password_hints(self, self.new_f, self.new2_f, "✓ Passwords match", "✕ Passwords do not match")
        self._enable()

    def _flag(self, flag, clear, field, message):
        """Empty the `clear` boxes first (clearing resets the live hints), then mark `flag` red and explain under `field`."""
        for f in clear:
            f.edit.clear()
        for f in flag:
            set_state(f.edit, "invalid")
        self.say(field.msg, message, "error")
        flag[0].edit.setFocus()

    def _save(self):
        new = self.new_f.edit.text()
        missing = [(f, m) for f, m in ((self.cur_f, "Please enter your current password."),
                                       (self.new_f, "Please enter your new password."),
                                       (self.new2_f, "Please confirm your new password.")) if not f.edit.text()]
        if missing:
            if not self.cur_f.edit.text():                     # the new passwords are retyped together with it
                self.new_f.edit.clear(); self.new2_f.edit.clear()
            for f, m in missing:
                self.flag(f, m)
            missing[0][0].edit.setFocus()
            return
        if not reject_new_passwords(self, self.new_f, self.new2_f, "✕ Passwords do not match"):
            return
        try:
            db.change_password(self.teacher["id"], self.cur_f.edit.text(), new)
        except db.WrongPassword:
            self._flag((self.cur_f,), (self.cur_f, self.new_f, self.new2_f), self.cur_f, "Current password is incorrect.")
            return
        except ValueError as e:                                  # e.g. shorter than 8 characters
            self._flag((self.new_f, self.new2_f), (self.new_f, self.new2_f), self.new_f, str(e))
            return
        except db.DatabaseError as e:
            self.say(self.cur_f.msg, str(e), "error")
            return
        self.accept()
