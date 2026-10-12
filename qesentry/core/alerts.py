"""Itemised alert logging: every violation becomes one timestamped row in the `event_logs` table.

    alerts.start(login_id)                       once, when the student's session begins
    alerts.report(event_type, "what happened")   from anywhere, any thread (keyboard hook, watchdog, web view)
    alerts.stop()                                at shutdown: flushes whatever is still queued

report() never blocks and never raises: events go into a queue and a background thread writes them to the
database in small batches. If the server is unreachable the events are kept and retried, so a network blip
does not lose them (up to a cap). The detailed local log (logger.py) is unaffected and remains the backup.
"""
import queue
import threading
import time

from qesentry.core import db
from qesentry.core import logger as log
from qesentry.core.timeutil import utcnow

_DEBOUNCE_SECONDS = 1.0          # identical (type, details) within this window count once (key auto-repeat)
_MAX_PENDING = 500               # cap on events held while the database is unreachable

_q = queue.Queue(maxsize=2000)
_stop = threading.Event()
_state = {"login_id": None, "thread": None, "count": 0}      # count = strikes this session
_last = {}


def start(login_id):
    """Begin recording alerts for this student login."""
    _state["login_id"] = login_id
    _state["count"] = 0
    _stop.clear()
    t = threading.Thread(target=_run, name="qesentry-alerts", daemon=True)
    _state["thread"] = t
    t.start()


def report(event_type, details=""):
    """Record one alert (non-blocking). Ignored before start() so demos and tests need no database."""
    if _state["login_id"] is None or _stop.is_set():
        return
    key = (event_type, details)
    now = time.monotonic()
    if now - _last.get(key, -10.0) < _DEBOUNCE_SECONDS:
        return
    _last[key] = now
    _state["count"] += 1                         # one strike per distinct (non-repeated) alert
    try:
        _q.put_nowait((event_type, details, utcnow()))
    except queue.Full:
        pass


def session_count():
    """How many alerts (strikes) this student has caused so far in this session."""
    return _state["count"]


def stop(timeout=4.0):
    """Flush queued alerts (best effort, up to `timeout` seconds) and stop the writer."""
    _stop.set()
    t = _state["thread"]
    if t is not None:
        t.join(timeout)


def _drain(pending):
    try:
        while len(pending) < _MAX_PENDING:
            pending.append(_q.get_nowait())
    except queue.Empty:
        pass


def _run():
    pending = []
    warned = False
    while True:
        stopping = _stop.is_set()
        if not pending:
            try:
                pending.append(_q.get(timeout=0 if stopping else 1.0))
            except queue.Empty:
                if stopping:
                    return
                continue
        _drain(pending)
        try:
            db.add_events(_state["login_id"], pending)
            pending = []
            warned = False
        except db.DatabaseError:
            if not warned:
                warned = True
                log.emit("ALERT_WRITE_FAILED", queued=len(pending))
            if stopping:
                return                       # give up: the local log still has the details
            _stop.wait(2.0)
