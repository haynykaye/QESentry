import os, sys, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core.schedule import exam_state, schedule_problem, status_label
from qesentry.core.timeutil import format_local, format_schedule, to_local, to_utc

NOW = datetime(2026, 10, 12, 9, 0)
H = timedelta(hours=1)


class StateTests(unittest.TestCase):
    def test_no_schedule_follows_the_manual_flag(self):
        self.assertEqual(exam_state("ACTIVE", None, None, NOW), "OPEN")
        self.assertEqual(exam_state("CLOSED", None, None, NOW), "CLOSED")

    def test_before_opening_time_is_scheduled(self):
        self.assertEqual(exam_state("ACTIVE", NOW + H, None, NOW), "SCHEDULED")
        self.assertEqual(exam_state("ACTIVE", NOW + H, NOW + 2 * H, NOW), "SCHEDULED")

    def test_exactly_at_opening_time_is_open(self):
        self.assertEqual(exam_state("ACTIVE", NOW, NOW + H, NOW), "OPEN")

    def test_closes_itself_at_the_closing_time(self):
        self.assertEqual(exam_state("ACTIVE", None, NOW + H, NOW), "OPEN")
        self.assertEqual(exam_state("ACTIVE", None, NOW, NOW), "CLOSED")          # the closing moment itself is closed
        self.assertEqual(exam_state("ACTIVE", NOW - 2 * H, NOW - H, NOW), "CLOSED")

    def test_manual_close_beats_the_schedule(self):
        self.assertEqual(exam_state("CLOSED", NOW - H, NOW + H, NOW), "CLOSED")
        self.assertEqual(exam_state("CLOSED", NOW + H, None, NOW), "CLOSED")


class ProblemTests(unittest.TestCase):
    def test_valid_schedules(self):
        self.assertEqual(schedule_problem(None, None, NOW), "")
        self.assertEqual(schedule_problem(NOW, NOW + H, NOW), "")
        self.assertEqual(schedule_problem(None, NOW + H, NOW), "")
        self.assertEqual(schedule_problem(NOW + H, None, NOW), "")

    def test_closing_must_follow_opening(self):
        self.assertIn("after the opening", schedule_problem(NOW + H, NOW + H, NOW))
        self.assertIn("after the opening", schedule_problem(NOW + 2 * H, NOW + H, NOW))

    def test_closing_in_the_past(self):
        self.assertIn("already passed", schedule_problem(None, NOW - H, NOW))
        self.assertIn("already passed", schedule_problem(None, NOW, NOW))
        self.assertEqual(schedule_problem(None, NOW - H, NOW, closing_must_be_future=False), "")   # editing a due one


class TimeTests(unittest.TestCase):
    def test_local_to_utc_round_trip(self):
        local = datetime(2026, 10, 12, 14, 30)
        self.assertEqual(to_local(to_utc(local)), local)
        self.assertIsNone(to_utc(None))

    def test_format_schedule(self):
        self.assertEqual(format_schedule(None), "")
        self.assertEqual(format_schedule(to_utc(datetime(2026, 3, 8, 16, 30))), "Mar 8, 2026 · 4:30 PM")
        self.assertEqual(format_schedule(to_utc(datetime(2026, 10, 11, 0, 5))), "Oct 11, 2026 · 12:05 AM")

    def test_status_label(self):
        self.assertEqual(status_label("OPEN", True), "RE-OPENED")
        self.assertEqual(status_label("OPEN", False), "OPEN")
        self.assertEqual(status_label("SCHEDULED", True), "SCHEDULED")     # waiting for its time: still SCHEDULED
        self.assertEqual(status_label("CLOSED", True), "CLOSED")

    def test_format_local(self):
        self.assertEqual(format_local(None), "")
        self.assertEqual(format_local(to_utc(datetime(2026, 10, 12, 8, 5))), "Oct 12, 2026 8:05 AM")
        self.assertEqual(format_local(to_utc(datetime(2026, 10, 12, 0, 0))), "Oct 12, 2026 12:00 AM")
        self.assertEqual(format_local(to_utc(datetime(2026, 10, 12, 13, 45))), "Oct 12, 2026 1:45 PM")


if __name__ == "__main__":
    unittest.main()
