import csv, datetime as dt, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core import csv_export


def row(**kw):
    base = dict(student_id="2022-01234-MN-0", full_name="Juan", section="BSCS 3-1", category="Quiz",
                exam_title="Quiz 1", status="SUBMITTED", lockdown="UNLOCKED", alerts=2,
                login_time=dt.datetime(2026, 1, 1, 1, 0, 0), ended_time=dt.datetime(2026, 1, 1, 1, 30, 0))
    base.update(kw)
    return base


class CsvTests(unittest.TestCase):
    def test_formula_injection_is_neutralised(self):
        for evil in ("=HYPERLINK(\"http://x\")", "+1+1", "-2", "@SUM(A1)"):
            self.assertTrue(csv_export.csv_safe(evil).startswith("'"))
        self.assertEqual(csv_export.csv_safe("Juan"), "Juan")

    def test_export_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.csv")
            n = csv_export.export_rows([row(), row(full_name="=cmd", status="RELEASED_BY_TEACHER", ended_time=None)], path)
            self.assertEqual(n, 2)
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0], csv_export.HEADERS)
        self.assertEqual(rows[1][1], "JUAN")
        self.assertEqual(rows[2][1], "'=CMD")
        self.assertEqual(rows[2][5], "RELEASED")
        self.assertEqual(rows[2][9], "")


if __name__ == "__main__":
    unittest.main()
