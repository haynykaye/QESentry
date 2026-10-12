"""Headless checks of the floating warning bubble (QT_QPA_PLATFORM=offscreen)."""
import os, sys, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QWidget
    from qesentry.ui import theme
    from qesentry.student import warning_bubble as wb
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "PyQt6 not installed")
class BubbleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def test_key_messages(self):
        self.assertIn("Switching", wb.key_warning("alt+tab"))
        self.assertIn("Switching", wb.key_warning("windows key"))
        self.assertIn("Closing", wb.key_warning("alt+f4"))
        self.assertIn("Copy and paste", wb.key_warning("ctrl+c"))
        self.assertIn("Screenshots", wb.key_warning("print screen"))
        self.assertEqual(wb.key_warning("f12"), "The F12 shortcut is disabled during the exam.")

    def test_levels_and_texts(self):
        self.assertEqual(wb.banner_level(1, 3), "warning")
        self.assertEqual(wb.banner_level(2, 3), "warning")
        self.assertEqual(wb.banner_level(3, 3), "error")             # reaching the flag threshold = red
        self.assertEqual(wb.banner_level(7, 3), "error")
        self.assertEqual(wb.banner_texts("Msg.", 2, 3), ("Msg.", "Strike 2 of 3"))
        self.assertEqual(wb.banner_texts("Msg.", 0, 3)[1], "Warning")
        main, tag = wb.banner_texts("Msg.", 3, 3)
        self.assertEqual(tag, "Flagged")
        self.assertTrue(main.startswith("You have been flagged") and main.endswith("Msg."))

    def test_bubble_colours_focus_and_hides(self):
        host = QWidget(); host.show()
        b = wb.WarningBubble(host)
        for f in (Qt.WindowType.WindowStaysOnTopHint, Qt.WindowType.WindowDoesNotAcceptFocus,
                  Qt.WindowType.WindowTransparentForInput):
            self.assertTrue(b.windowFlags() & f)
        self.assertFalse(b.isVisible())
        b.show_message("Switching to other apps or windows is not allowed.", 1, 3)
        self.assertTrue(b.isVisible())
        self.assertEqual((b.level, b.strike.text()), ("warning", "Strike 1 of 3"))
        self.assertIn(wb.WARNING_COLOR, b.frame.styleSheet())          # yellow
        b.show_message("Copy and paste are disabled during the exam.", 3, 3)   # refreshes the same banner, now red
        self.assertEqual((b.level, b.strike.text()), ("error", "Flagged"))
        self.assertIn(wb.ERROR_COLOR, b.frame.styleSheet())
        b.dismiss()
        self.assertFalse(b.isVisible())

    def test_strike_counter(self):
        from qesentry.core import alerts
        alerts._state["login_id"] = 1                                # pretend a session started (no DB writer thread)
        alerts._state["count"] = 0
        try:
            alerts.report("KEYBOARD_VIOLATION", "Blocked shortcut: Alt+Tab")
            alerts.report("KEYBOARD_VIOLATION", "Blocked shortcut: Alt+Tab")   # key auto-repeat: debounced, one strike
            alerts.report("FOCUS_LOSS", "Window lost focus to X")
            self.assertEqual(alerts.session_count(), 2)
        finally:
            alerts._state["login_id"] = None
            alerts._last.clear()
            while not alerts._q.empty():
                alerts._q.get_nowait()

    def test_auto_hide(self):
        b = wb.WarningBubble(QWidget())
        wb.SHOW_MS, wb.FADE_MS = 30, 10
        b.show_message("x")
        for _ in range(60):
            self.app.processEvents(); __import__("time").sleep(0.01)
        self.assertFalse(b.isVisible())


if __name__ == "__main__":
    unittest.main()
