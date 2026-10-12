import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core.validators import form_url_check, length_hint, login_submit_problem, match_hint


class ValidatorTests(unittest.TestCase):
    def test_login_submit_problem(self):
        self.assertIsNone(login_submit_problem("a", "b"))
        self.assertEqual(login_submit_problem("a", ""), ("Please enter your password.", ("pw",)))
        self.assertEqual(login_submit_problem("", "x"), ("Please enter your email/username and password.", ("ident", "pw")))
        self.assertEqual(login_submit_problem("  ", "x")[1], ("ident", "pw"))
        self.assertEqual(login_submit_problem("", "")[1], ("ident", "pw"))

    def test_length_hint_has_no_intermediate_failure(self):
        for n in range(0, 8):
            self.assertEqual(length_hint("x" * n), ("", ""))
        self.assertEqual(length_hint("x" * 8), ("✓ At least 8 characters", "ok"))

    def test_match_hint(self):
        self.assertEqual(match_hint("abcdefgh", ""), ("", "", ""))
        self.assertEqual(match_hint("abcdefgh", "abc"), ("✕ Passwords do not match.", "error", "mismatch"))
        self.assertEqual(match_hint("abc", "ab")[2], "mismatch")                 # mismatch is reported even when short
        self.assertEqual(match_hint("abcdefgh", "abcdefgh"), ("✓ Passwords match.", "ok", "match"))
        self.assertEqual(match_hint("abc", "abc"), ("", "", ""))                 # a match only counts at 8+ characters
        self.assertEqual(match_hint("abcdefgh", "abcdefgh", "✓ Passwords match", "x")[0], "✓ Passwords match")

    def test_form_url(self):
        self.assertEqual(form_url_check(""), (False, ""))
        self.assertEqual(form_url_check("https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform"), (True, ""))
        self.assertEqual(form_url_check("docs.google.com/forms/d/e/abc/viewform"), (True, ""))
        self.assertEqual(form_url_check("https://example.com/x"), (False, "Please enter a valid Google Forms URL."))
        self.assertEqual(form_url_check("nonsense"), (False, "Please enter a valid Google Forms URL."))


if __name__ == "__main__":
    unittest.main()
