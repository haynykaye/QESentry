import os, sys, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core.listing import filter_exams, sort_exams, sort_live_rows


def row(sid, name, login, submitted=None):
    return {"student_id": sid, "full_name": name, "login_time": login, "submitted_time": submitted}


def exam(i, title, category, state, created):
    return {"id": i, "title": title, "category": category, "state": state, "created_at": created}


class LiveSortTests(unittest.TestCase):
    rows = [row("2", "Carla", datetime(2026, 1, 1, 9, 5), datetime(2026, 1, 1, 10, 0)),
            row("1", "bea", datetime(2026, 1, 1, 9, 0)),
            row("3", "Anna", datetime(2026, 1, 1, 9, 10), datetime(2026, 1, 1, 9, 40))]

    def ids(self, **kw):
        return [r["student_id"] for r in sort_live_rows(self.rows, **kw)]

    def test_name_ignores_case(self):
        self.assertEqual(self.ids(key="name", ascending=True), ["3", "1", "2"])
        self.assertEqual(self.ids(key="name", ascending=False), ["2", "1", "3"])

    def test_login_time(self):
        self.assertEqual(self.ids(key="login", ascending=True), ["1", "2", "3"])
        self.assertEqual(self.ids(key="login", ascending=False), ["3", "2", "1"])

    def test_submitted_time_keeps_unsubmitted_last(self):
        self.assertEqual(self.ids(key="submitted", ascending=True), ["3", "2", "1"])
        self.assertEqual(self.ids(key="submitted", ascending=False), ["2", "3", "1"])

    def test_input_not_mutated(self):
        before = list(self.rows)
        sort_live_rows(self.rows, key="name")
        self.assertEqual(self.rows, before)


class ExamTests(unittest.TestCase):
    exams = [exam(1, "Midterm Exam", "Exam", "OPEN", datetime(2026, 1, 1)),
             exam(2, "quiz 1", "Quiz", "CLOSED", datetime(2026, 1, 3)),
             exam(3, "Final Exam", "Exam", "CLOSED", datetime(2026, 1, 2)),
             exam(4, "Quiz 2", "Quiz", "OPEN", datetime(2026, 1, 4)),
             exam(5, "Quiz 3", "Quiz", "SCHEDULED", datetime(2026, 1, 5))]

    def titles(self, items):
        return [x["title"] for x in items]

    def test_search_is_case_insensitive_substring(self):
        self.assertEqual(self.titles(filter_exams(self.exams, "QUIZ")), ["quiz 1", "Quiz 2", "Quiz 3"])
        self.assertEqual(self.titles(filter_exams(self.exams, "  term ")), ["Midterm Exam"])
        self.assertEqual(len(filter_exams(self.exams, "")), 5)

    def test_category_and_status_combine(self):
        self.assertEqual(self.titles(filter_exams(self.exams, category="Exam")), ["Midterm Exam", "Final Exam"])
        self.assertEqual(self.titles(filter_exams(self.exams, status="CLOSED")), ["quiz 1", "Final Exam"])
        self.assertEqual(self.titles(filter_exams(self.exams, category="Quiz", status="OPEN")), ["Quiz 2"])
        self.assertEqual(self.titles(filter_exams(self.exams, status="SCHEDULED")), ["Quiz 3"])
        self.assertEqual(filter_exams(self.exams, "final", category="Quiz"), [])

    def test_sort_title(self):
        self.assertEqual(self.titles(sort_exams(self.exams, "title", True)), ["Final Exam", "Midterm Exam", "quiz 1", "Quiz 2", "Quiz 3"])
        self.assertEqual(self.titles(sort_exams(self.exams, "title", False)), ["Quiz 3", "Quiz 2", "quiz 1", "Midterm Exam", "Final Exam"])

    def test_sort_created(self):
        self.assertEqual([x["id"] for x in sort_exams(self.exams, "created", False)], [5, 4, 2, 3, 1])
        self.assertEqual([x["id"] for x in sort_exams(self.exams, "created", True)], [1, 3, 2, 4, 5])


if __name__ == "__main__":
    unittest.main()
