"""Open / close schedule rules for assessments (pure Python, no Qt or database imports, so they are easy to test).

An assessment has a manual flag (status ACTIVE or CLOSED, set with the Close / Re-Open icons) and an optional
schedule (opens_at, closes_at; naive UTC like every other timestamp). Its effective state is worked out on the fly:

    OPEN        status ACTIVE, and the opening time (if any) has passed, and the closing time (if any) has not
    SCHEDULED   status ACTIVE, but the opening time is still in the future  -> students cannot log in yet
    CLOSED      closed by the teacher, OR the closing time has passed (it "closes itself" - no background job)
"""

STATE_OPEN, STATE_SCHEDULED, STATE_CLOSED = "OPEN", "SCHEDULED", "CLOSED"
LABEL_REOPENED = "RE-OPENED"


def exam_state(status, opens_at, closes_at, now):
    """Effective state (OPEN / SCHEDULED / CLOSED) of an assessment at time `now`."""
    if status != "ACTIVE":
        return STATE_CLOSED
    if closes_at is not None and now >= closes_at:
        return STATE_CLOSED
    if opens_at is not None and now < opens_at:
        return STATE_SCHEDULED
    return STATE_OPEN


def schedule_problem(opens_at, closes_at, now, closing_must_be_future=True):
    """Why this schedule cannot be saved (a sentence for the teacher), or '' if it is fine."""
    if opens_at is not None and closes_at is not None and closes_at <= opens_at:
        return "The closing time must be after the opening time."
    if closing_must_be_future and closes_at is not None and closes_at <= now:
        return "The closing time has already passed. Pick a later date or time."
    return ""


def status_label(state, reopened):
    """The word shown in the Status column. It is the effective state, except that an assessment which the teacher
    re-opened and which is open right now reads RE-OPENED. One that is still waiting for its opening time stays
    SCHEDULED, and a closed one stays CLOSED."""
    return LABEL_REOPENED if state == STATE_OPEN and reopened else state
