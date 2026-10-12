"""Event log for each exam session.

Usage from any module:
    from qesentry.core import logger as log
    log.emit("EVENT_TYPE", key=value)

Each session writes one file, logs/session_<date>_<time>.jsonl (one JSON record per line).
Records are hash-chained: every record stores the hash of the one before it, so editing or
deleting a line breaks the chain and verify() can detect it. All writes are thread-safe.
"""
import datetime as dt
import hashlib
import json
import os
import threading

from qesentry.core.config import app_dir

_ZERO = "0" * 64                  # "previous hash" of the very first record
_lock = threading.Lock()          # the keyboard hook runs on another thread, so writes must be serialized
_state = {"path": None, "seq": 0, "prev": _ZERO, "student": ""}
_listeners = []                   # callables fn(event_type, detail_dict), e.g. the violation counter in main.py


def add_listener(fn):
    """Call fn(event_type, detail) after every emitted event (exceptions in fn are swallowed)."""
    _listeners.append(fn)


def start_session(student_id):
    """Create a new log file for this student and write the SESSION_START record."""
    d = os.path.join(app_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    _state.update(path=os.path.join(d, f"session_{stamp}.jsonl"), seq=0, prev=_ZERO, student=student_id)
    emit("SESSION_START")


def _digest(rec):
    """SHA-256 of a record's contents (excluding its own 'hash' field)."""
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def emit(event_type, **detail):
    """Append one event to the log (and print it to the console).

    event_type: short name such as "FOCUS_LOST"; detail: any extra key=value facts about the event.
    """
    with _lock:
        rec = {
            "seq": _state["seq"],                                  # running number, starts at 0
            "ts": dt.datetime.now().isoformat(timespec="milliseconds"),
            "student": _state["student"],
            "type": event_type,
            "detail": detail,
            "prev": _state["prev"],                                # hash of the previous record (the chain link)
        }
        rec["hash"] = _digest(rec)
        _state["seq"] += 1
        _state["prev"] = rec["hash"]
        line = json.dumps(rec, ensure_ascii=False, default=str)
        print(line)
        if _state["path"]:                                         # before start_session(), only print
            with open(_state["path"], "a", encoding="utf-8") as f:
                f.write(line + "\n")
    for fn in list(_listeners):                                    # outside the lock: listeners may log too
        try:
            fn(event_type, detail)
        except Exception:
            pass


def verify(path):
    """Check a log file's hash chain.

    Returns (True, None) if the chain is intact, else (False, index_of_first_bad_line).
    """
    prev = _ZERO
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f):
            rec = json.loads(line)
            if rec["prev"] != prev or rec["hash"] != _digest(rec):
                return False, n
            prev = rec["hash"]
    return True, None
