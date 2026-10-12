"""Section names: parsing and the one accepted format (pure Python, easy to test).

An accepted section looks like  BSIT 2-3,  BSIT 1-12  or  BSIT 1-2N :
    "BS" + 1-6 course letters (BSIT, BSCS, BSA, BSCPE ...), a space, the year level (one digit, 1-9),
    a dash, the section number (1 or 2 digits, no leading zero), and an optional trailing letter.
"""
import re

SECTION_RE = re.compile(r"^BS[A-Z]{1,6} [1-9]-[1-9]\d?[A-Z]?$")
SECTION_HINT = "Use a format like BSIT 3-1 or BSIT 3-1N, separated by commas."


def parse_sections(text):
    """'bscs 1-1, BSCS 1-2;bscs 1-1' -> ['BSCS 1-1', 'BSCS 1-2'] (upper-cased, de-duplicated, order kept)."""
    out = []
    for part in (text or "").replace(";", ",").replace("\n", ",").split(","):
        part = re.sub(r"\s*-\s*", "-", " ".join(part.split())).upper()      # "bsit  3 - 1n" -> "BSIT 3-1N"
        if part and part not in out:
            out.append(part)
    return out


def validate_sections(text):
    """Return (sections, invalid): the cleaned list and the entries that do not match the accepted format.
    Empty text is valid and means 'every section'."""
    sections = parse_sections(text)
    return sections, [s for s in sections if not SECTION_RE.match(s)]
