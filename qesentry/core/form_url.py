"""Google Form link validation and formatting, shared by the student and teacher apps.

- format_form_url()   validate a pasted link and return a clean, embeddable URL (adds embedded=true).
- form_key()          canonical key used to match a pasted link against a stored exam session.
- is_submission_url() True when a URL is Google's post-submit confirmation page (.../formResponse).
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params added by the Forms editor / share dialog. They are tracking noise, not form data.
# (Prefill answers use "entry.<id>" params, which are deliberately preserved.)
_TRACKING_PARAMS = {"usp", "ouid", "ts"}
_FORM_PATH = re.compile(r"^/forms/(u/\d+/)?d/")
_SUBMIT_PATH = re.compile(r"^/forms/(u/\d+/)?d/(e/)?[^/]+/formResponse/?$")


class InvalidFormUrl(ValueError):
    """Raised with a short, user-presentable message when a pasted link is not a usable form URL."""


def format_form_url(raw):
    """Validate a pasted Google Form link and return a clean, embeddable URL.

    - accepts docs.google.com/forms/... and forms.gle/... (scheme optional, http upgraded to https)
    - strips editor tracking params such as ?usp=publish-editor, and any #fragment
    - guarantees exactly one `embedded=true` parameter
    Raises InvalidFormUrl with a friendly message if the link is not acceptable.
    """
    text = (raw or "").strip().strip("\"'<>").strip()
    if not text:
        raise InvalidFormUrl("Please paste the Google Form link to continue.")
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise InvalidFormUrl("That doesn't look like a valid link.")
    if parts.scheme not in ("http", "https"):
        raise InvalidFormUrl("That doesn't look like a web link.")

    path = parts.path or "/"
    if host == "docs.google.com" and (path == "/forms" or path.startswith("/forms/")):
        if re.search(r"/edit/?$", path):
            raise InvalidFormUrl("This is the form editor link. In Google Forms, select Send → Link "
                                 "and copy that link instead.")
        if not _FORM_PATH.match(path):
            raise InvalidFormUrl("That link doesn't point to a specific Google Form.")
    elif host == "forms.gle":
        if not path.strip("/"):
            raise InvalidFormUrl("That forms.gle link is missing its form code.")
    else:
        raise InvalidFormUrl("Only Google Form links are permitted (docs.google.com/forms or forms.gle).")

    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS and k.lower() != "embedded"]
    query.append(("embedded", "true"))
    return urlunsplit(("https", host, path, urlencode(query), ""))


def form_key(url):
    """Canonical comparison key: host + path with no query, no trailing slash, lower-cased host.

    Two pasted variants of the same form (with/without ?usp=..., embedded=true, trailing slash)
    produce the same key. Raises InvalidFormUrl if `url` is not a valid form link.
    """
    parts = urlsplit(format_form_url(url))
    return f"{parts.hostname}{parts.path.rstrip('/')}"


def is_submission_url(url):
    """True if `url` is the page Google shows after a successful submit (docs.google.com/forms/.../formResponse)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.hostname or "").lower() == "docs.google.com" and bool(_SUBMIT_PATH.match(parts.path))
