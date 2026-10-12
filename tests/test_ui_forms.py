"""Headless Qt checks of the five teacher modals (QT_QPA_PLATFORM=offscreen). Skipped when PyQt6 is missing."""
import os, sys, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from qesentry.ui import theme
    from PyQt6.QtWidgets import QLineEdit
    from qesentry.teacher import account_dialogs as account, assessment_dialog as assess, auth_dialogs as auth
    HAVE = True
except ImportError:
    HAVE = False

GOOD = "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform"


@unittest.skipUnless(HAVE, "PyQt6 / SQLAlchemy not installed")
class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def focus(self, widget):
        """Give `widget` real keyboard focus (the dialog must be the active window for Qt to send focus events)."""
        window = widget.window()
        window.activateWindow()
        self.app.processEvents()
        widget.setFocus()
        self.app.processEvents()

    def test_login_flow(self):
        from unittest import mock
        exists = {"value": True}                                                  # does the typed username exist?
        patches = [mock.patch.object(auth.db, "authenticate_teacher", lambda u, p: None),
                   mock.patch.object(auth.db, "teacher_exists", lambda u: exists["value"]),
                   mock.patch.object(auth.log, "emit", lambda *a, **k: None)]
        for pt in patches:
            pt.start(); self.addCleanup(pt.stop)
        auth._fail.update(count=0, locked_until=0.0)
        self.addCleanup(lambda: auth._fail.update(count=0, locked_until=0.0))
        d = auth.TeacherLoginDialog()
        d.show()
        self.assertFalse(d.ok_btn.isEnabled())                                    # nothing typed
        self.assertEqual(d.ok_btn.cursor().shape(), Qt.CursorShape.ArrowCursor)
        self.assertFalse(d.feedback.isVisible())                                  # no guidance text at all
        self.assertTrue(hasattr(d.pw, "eye_action"))
        d.ident.setText("me")                                                     # either box activates the button
        self.assertTrue(d.ok_btn.isEnabled())
        self.assertEqual(d.ok_btn.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.assertFalse(d.feedback.isVisible())
        d.ok_btn.click()                                                          # password empty
        self.assertEqual(d.feedback.text(), "Please enter your password.")
        self.assertEqual((d.pw.property("state"), d.ident.property("state")), ("invalid", ""))
        d.ident.clear(); d.pw.setText("secret")
        self.assertFalse(d.feedback.isVisible())                                  # typing clears it
        d.ok_btn.click()                                                          # email empty
        self.assertEqual(d.feedback.text(), "Please enter your email/username and password.")
        self.assertEqual((d.ident.property("state"), d.pw.property("state")), ("invalid", "invalid"))
        self.assertEqual(d.pw.text(), "")                                         # the typed password is emptied
        d.ident.setText("me"); d.pw.setText("bad")
        d.ok_btn.click()                                                          # wrong credentials
        self.assertEqual(d.feedback.text(), "Incorrect password.")
        self.assertEqual((d.ident.property("state"), d.pw.property("state")), ("", "invalid"))   # only the password is red
        self.assertEqual((d.ident.text(), d.pw.text()), ("me", ""))               # only the password is emptied
        d.pw.setText("x")
        self.assertEqual((d.ident.property("state"), d.pw.property("state")), ("", ""))
        self.assertFalse(d.feedback.isVisible())
        exists["value"] = False                                                   # username not in the database
        d.ident.setText("ghost"); d.pw.setText("bad")
        d.ok_btn.click()
        self.assertEqual(d.feedback.text(), "Account doesn't exist. Check your email/username or create one.")
        self.assertEqual((d.ident.property("state"), d.pw.property("state")), ("invalid", "invalid"))   # both red
        self.assertEqual((d.ident.text(), d.pw.text()), ("ghost", ""))

    def test_register_flow(self):
        d = auth.RegisterTeacherDialog()
        d.show()
        self.assertFalse(d.ok_btn.isEnabled())
        self.assertEqual(d.user_f.edit.placeholderText(), "e.g., msantos@pup.edu.ph")
        for f in (d.pw_f, d.pw2_f):
            self.assertEqual(f.edit.echoMode(), QLineEdit.EchoMode.Password)
            f.edit.eye_action.trigger()
            self.assertEqual(f.edit.echoMode(), QLineEdit.EchoMode.Normal)
            f.edit.eye_action.trigger()
        d.name_f.edit.setText("M")
        self.assertTrue(d.ok_btn.isEnabled())                                     # any field activates it
        d.ok_btn.click()                                                          # others empty
        self.assertEqual(d.user_f.msg.text(), "Please enter your email or username.")
        self.assertEqual(d.pw_f.msg.text(), "Please enter your password.")
        self.assertEqual(d.pw2_f.msg.text(), "Please confirm your password.")
        self.assertEqual(d.user_f.edit.property("state"), "invalid")
        self.assertEqual(d.name_f.msg.text(), "")
        d.user_f.edit.setText("msantos@pup.edu.ph")
        self.assertEqual(d.user_f.msg.text(), "")
        self.focus(d.pw_f.edit)
        d.pw_f.edit.setText("short")
        self.assertEqual(d.pw_f.msg.text(), "")                                   # still typing: no message yet
        self.focus(d.pw2_f.edit)                                                  # moved on with < 8 characters
        self.assertEqual((d.pw_f.msg.text(), d.pw_f.edit.property("state")), ("Password must be at least 8 characters.", "invalid"))
        d.pw2_f.edit.setText("abc")
        self.assertEqual(d.pw2_f.msg.text(), "✕ Passwords do not match.")         # mismatch shows even when short
        d.pw_f.edit.setText("longenough")
        self.assertEqual(d.pw_f.msg.text(), "✓ At least 8 characters")
        self.assertEqual((d.pw2_f.msg.text(), d.pw2_f.edit.property("state")), ("✕ Passwords do not match.", "mismatch"))
        d.pw2_f.edit.setText("longenough")
        self.assertEqual((d.pw2_f.msg.text(), d.pw2_f.edit.property("state")), ("✓ Passwords match.", "match"))
        self.assertIn("#F0FDF4", theme.build_qss().split('QLineEdit[state="match"]')[2].split("}")[0])  # same green as "valid"

    def test_register_mismatch_on_click_keeps_name_and_email(self):
        d = auth.RegisterTeacherDialog()
        d.show()
        d.name_f.edit.setText("Maria Santos"); d.user_f.edit.setText("msantos@pup.edu.ph")
        d.pw_f.edit.setText("longenough"); d.pw2_f.edit.setText("different1")
        d.ok_btn.click()
        self.assertEqual((d.pw_f.edit.text(), d.pw2_f.edit.text()), ("", ""))
        self.assertEqual((d.name_f.edit.text(), d.user_f.edit.text()), ("Maria Santos", "msantos@pup.edu.ph"))
        self.assertEqual(d.pw2_f.msg.text(), "✕ Passwords do not match.")
        d.pw_f.edit.setText("1234567"); d.pw2_f.edit.setText("1234567")
        d.ok_btn.click()                                                          # too short
        self.assertEqual(d.pw_f.msg.text(), "Password must be at least 8 characters.")

    def test_change_password_flow(self):
        d = account.ChangePasswordDialog({"id": 1, "username": "u"})
        d.show()
        self.assertFalse(d.ok_btn.isEnabled())
        for f in (d.cur_f, d.new_f, d.new2_f):
            self.assertTrue(hasattr(f.edit, "eye_action"))
        self.assertEqual(d.subtitle.text(), "Enter your current password and choose a new one.")
        d.new_f.edit.setText("newpassword"); d.new2_f.edit.setText("newpass")
        self.assertTrue(d.ok_btn.isEnabled())
        self.assertEqual(d.new2_f.msg.text(), "✕ Passwords do not match")
        d.new2_f.edit.setText("newpassword")
        self.assertEqual(d.new2_f.msg.text(), "✓ Passwords match")
        d.new_f.edit.setText("weq"); d.new2_f.edit.setText("x")
        self.assertEqual(d.new_f.msg.text(), "Password must be at least 8 characters.")
        self.assertEqual(d.new2_f.msg.text(), "✕ Passwords do not match")
        d.new_f.edit.setText("newpassword"); d.new2_f.edit.setText("newpassword")
        d.ok_btn.click()                                                          # current password empty
        self.assertEqual(d.cur_f.msg.text(), "Please enter your current password.")
        self.assertEqual((d.new_f.edit.text(), d.new2_f.edit.text()), ("", ""))   # new ones are removed
        d.cur_f.edit.setText("old"); d.new_f.edit.setText("newpassword"); d.new2_f.edit.setText("other12345")
        d.ok_btn.click()
        self.assertEqual(d.new2_f.msg.text(), "✕ Passwords do not match")
        self.assertEqual((d.cur_f.edit.text(), d.new_f.edit.text()), ("old", ""))  # current stays

    def test_assessment_form_link_states(self):
        d = assess.AssessmentDialog({"id": 1})
        d.show()
        self.assertEqual(d.subtitle.text(), "Fill out the details below to publish a new assessment to the student portal.")
        e = d.url_f.edit
        self.focus(e); e.setText(GOOD)
        self.assertEqual(e.property("state"), "valid")
        self.focus(d.title_f.edit)                                                # blur -> neutral grey
        self.assertEqual(e.property("state"), "")
        self.focus(e); self.assertEqual(e.property("state"), "valid")
        e.setText("https://example.com/nope")
        self.assertEqual((e.property("state"), d.url_f.msg.text()), ("invalid", "Please enter a valid Google Forms URL."))
        self.focus(d.title_f.edit)
        self.assertEqual(e.property("state"), "invalid")                          # error outline stays after blur

    def test_assessment_sections(self):
        d = assess.AssessmentDialog({"id": 1})
        d.show()
        self.assertEqual(d.sec_f.msg.text(), "Enter target sections (e.g., BSIT 3-1, BSIT 3-1N). Leave blank to allow all sections.")
        d.title_f.edit.setText("T"); d.url_f.edit.setText(GOOD)
        d.sec_f.edit.setText("BSIT 3-1,  bsit 3-1n , BSCS 2-2")
        self.assertTrue(d.ok_btn.isEnabled())
        d.sec_f.edit.setText("BSIT3-1")
        self.assertFalse(d.ok_btn.isEnabled())
        self.assertEqual(d.sec_f.edit.property("state"), "invalid")

    def test_stylesheet_has_no_focus_ring_and_palette(self):
        qss = theme.build_qss()
        self.assertIn("outline: none", qss)
        for hexcode in ("#7A0016", "#1E293B", "#16A34A", "#DC2626", "#64748B", "#D97706", "#F0FDF4"):
            self.assertIn(hexcode, qss)


if __name__ == "__main__":
    unittest.main()
