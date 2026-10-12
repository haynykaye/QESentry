import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core.sections import parse_sections, validate_sections


class SectionTests(unittest.TestCase):
    def test_accepted_formats(self):
        for ok in ("BSIT 2-3", "BSIT 1-2N", "bscs 3-1", "BSCS 1-12", "BSA 2-1", "BSIT 2-3, BSIT 1-2N"):
            self.assertEqual(validate_sections(ok)[1], [], ok)

    def test_rejected_formats(self):
        for bad in ("BSIT2-3", "BSIT 2/3", "BSIT 2-", "2-3", "BSIT 2-3N5", "B 2-3", "ABCD 2-3", "BSIT 12-3", "BSIT 0-1",
                    "BSIT 2-0", "BSIT 2-123", "BSIT 2-3 extra"):
            self.assertEqual(len(validate_sections(bad)[1]), 1, bad)

    def test_empty_means_all_sections(self):
        self.assertEqual(validate_sections(""), ([], []))
        self.assertEqual(validate_sections("  ,  "), ([], []))

    def test_flexible_whitespace_and_commas(self):
        self.assertEqual(validate_sections("BSIT 3-1, BSIT 3-1N"), (["BSIT 3-1", "BSIT 3-1N"], []))
        self.assertEqual(validate_sections("  bsit   3 - 1n ,BSCS 2-2 "), (["BSIT 3-1N", "BSCS 2-2"], []))
        self.assertEqual(validate_sections("BSCS 2-2")[1], [])

    def test_cleaning(self):
        self.assertEqual(parse_sections("bsit  2-3 ,BSIT 2-3; bsit 1-2n"), ["BSIT 2-3", "BSIT 1-2N"])


if __name__ == "__main__":
    unittest.main()
