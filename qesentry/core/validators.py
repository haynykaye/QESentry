"""Pure-Python form rules and microcopy (no Qt), so every message can be unit-tested.

Each helper returns (text, kind) or (text, kind, field_state) where
    kind        "" | "hint" | "warn" | "error" | "ok"   -> label colour (see theme.set_feedback)
    field_state ""  | "valid" | "match" | "mismatch" | "invalid"   -> input border (see theme.set_state)
"""
from qesentry.core.form_url import InvalidFormUrl, format_form_url

MIN_PASSWORD = 8

LOGIN_NEED_PASSWORD = "Please enter your password."
LOGIN_NEED_USER = "Please enter your email/username and password."
LOGIN_BAD_CREDENTIALS = "Incorrect password."
LOGIN_NO_ACCOUNT = "Account doesn't exist. Check your email/username or create one."

LENGTH_OK = "✓ At least 8 characters"
TOO_SHORT = "Password must be at least 8 characters."
MISMATCH = "✕ Passwords do not match."
MATCH = "✓ Passwords match."
BAD_FORM_URL = "Please enter a valid Google Forms URL."
SECTIONS_HELP = "Enter target sections (e.g., BSIT 3-1, BSIT 3-1N). Leave blank to allow all sections."


def login_submit_problem(identifier, password):
    """Checked only when Sign In is clicked. Returns None when both boxes have text, otherwise
    (message, boxes_to_mark_red) where boxes are 'ident' and/or 'pw'. A typed password is emptied together
    with a missing email, so the caller clears it when 'ident' is in the result."""
    has_user, has_pw = bool(identifier.strip()), bool(password)
    if has_user and has_pw:
        return None
    if has_user:
        return LOGIN_NEED_PASSWORD, ("pw",)
    return LOGIN_NEED_USER, ("ident", "pw")


def length_hint(password):
    """Green tick once the password reaches 8 characters; nothing before that (no intermediate red states)."""
    return (LENGTH_OK, "ok") if len(password) >= MIN_PASSWORD else ("", "")


def match_hint(password, confirm, match_text=MATCH, mismatch_text=MISMATCH):
    """Live feedback for a 'confirm password' box: (text, kind, field_state). Silent while it is empty.
    A mismatch is always reported; a match only counts once the password has 8+ characters."""
    if not confirm:
        return "", "", ""
    if confirm != password:
        return mismatch_text, "error", "mismatch"
    if len(password) >= MIN_PASSWORD:
        return match_text, "ok", "match"
    return "", "", ""


def form_url_check(text):
    """(valid, message). Empty text is neutral (no message). Any invalid link gets the same plain message."""
    if not text.strip():
        return False, ""
    try:
        format_form_url(text)
        return True, ""
    except InvalidFormUrl:
        return False, BAD_FORM_URL
