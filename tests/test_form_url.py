import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qesentry.core.form_url import InvalidFormUrl, form_key, format_form_url, is_submission_url


class FormUrlTests(unittest.TestCase):
    A = "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform?usp=publish-editor"
    B = "docs.google.com/forms/d/e/1FAIpQLSabc/viewform/?embedded=true"

    def test_variants_share_a_key(self):
        self.assertEqual(form_key(self.A), form_key(self.B))

    def test_embedded_added_once(self):
        self.assertEqual(format_form_url(self.A).count("embedded=true"), 1)
        self.assertNotIn("usp=", format_form_url(self.A))

    def test_rejects_bad_links(self):
        for bad in ["", "https://google.com", "https://evil.com/forms/d/e/x/viewform",
                    "https://docs.google.com/forms/d/abc/edit"]:
            with self.assertRaises(InvalidFormUrl, msg=bad):
                format_form_url(bad)

    def test_submission_url(self):
        self.assertTrue(is_submission_url("https://docs.google.com/forms/d/e/ID/formResponse"))
        self.assertTrue(is_submission_url("https://docs.google.com/forms/u/0/d/e/ID/formResponse?embedded=true"))
        self.assertFalse(is_submission_url(self.A))
        self.assertFalse(is_submission_url("https://evil.com/forms/d/e/ID/formResponse"))


if __name__ == "__main__":
    unittest.main()
