"""Background monitors that watch what else is running on the computer.

- ProcessWatchdog   scans running programs against the denylist and kills (or just flags) banned ones.
- FocusMonitor      notices when another window takes focus, logs it, and pulls focus back to the exam.

Run alone for a 30-second demo (flag-only, safe):  python -m qesentry.student.process_watchdog
"""
import ctypes
import os
import time
from ctypes import wintypes

import psutil
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from qesentry.core import alerts
from qesentry.core import logger as log
from qesentry.core.config import friendly_app_name


class ProcessWatchdog(QObject):
    """Checks running processes every few seconds against the banned-app list."""
    violation = pyqtSignal(str, str)         # (app name, "killed" | "flagged" | "kill_failed")

    def __init__(self, denylist, mode="kill", interval_ms=2000):
        super().__init__()
        self.denylist = {n.lower() for n in denylist}   # lower-case set for fast, case-insensitive matching
        self.mode = mode                                # "kill" closes banned apps, "flag" only logs them
        self._own = os.getpid()                         # never match ourselves
        self._seen = set()                              # pids already reported (avoid log spam)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._interval = interval_ms

    def _matches(self):
        """All running processes (other than this app) whose name is on the denylist."""
        out = []
        for p in psutil.process_iter(["pid", "name"]):
            if p.info["pid"] != self._own and (p.info["name"] or "").lower() in self.denylist:
                out.append(p)
        return out

    def scan_once(self):
        """Readable names of banned apps currently running (e.g. "Google Chrome"). Used by the pre-flight screen."""
        return sorted({friendly_app_name(p.info["name"]) for p in self._matches()})

    def _tick(self):
        """Runs on every timer interval: kill or flag each banned process and log it once."""
        for p in self._matches():
            exe = (p.info["name"] or "").lower()
            name = friendly_app_name(exe)
            action = "flagged"
            if self.mode == "kill":
                try:
                    p.kill()
                    action = "killed"
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    action = "kill_failed"
            if p.info["pid"] not in self._seen:         # report each process only the first time
                self._seen.add(p.info["pid"])
                log.emit("PROC_VIOLATION", name=name, exe=exe, pid=p.info["pid"], action=action)
                alerts.report("BANNED_PROCESS", f"Banned app launched: {exe} ({name}) – {action}")
                self.violation.emit(name, action)

    def start(self):
        self._timer.start(self._interval)

    def stop(self):
        self._timer.stop()


# ----------------------------- focus-loss detector -----------------------------
# Windows API access (only available on Windows; _user32 stays None elsewhere).
_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
if _user32:
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def foreground_info():
    """(pid, window title) of whatever window currently has focus. pid 0 = none (e.g. lock screen)."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return 0, ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return pid.value, buf.value


class FocusMonitor(QObject):
    """Checks several times a second whether the exam window still has focus."""
    focus_lost = pyqtSignal()
    focus_regained = pyqtSignal(float)       # seconds spent away

    def __init__(self, window, interval_ms=300):
        super().__init__()
        self.window = window                 # the exam window to pull back to the front
        self._own = os.getpid()
        self._away_since = None              # None = exam window has focus; otherwise the time focus was lost
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._interval = interval_ms

    def _tick(self):
        pid, title = foreground_info()
        if pid != self._own:                 # some other program is in front
            if self._away_since is None:     # first tick after losing focus: log it once
                self._away_since = time.monotonic()
                try:
                    exe = psutil.Process(pid).name() if pid else "none"
                except psutil.Error:
                    exe = "unknown"
                app = friendly_app_name(exe) if exe not in ("none", "unknown") else exe
                log.emit("FOCUS_LOST", app=app, exe=exe, title=title)
                alerts.report("FOCUS_LOSS", f"Window lost focus to {app}" + (f" – “{title[:100]}”" if title else ""))
                self.focus_lost.emit()
            self.window.raise_()             # drag focus back every tick
            self.window.activateWindow()
        elif self._away_since is not None:   # focus is back: log how long it was gone
            secs = round(time.monotonic() - self._away_since, 1)
            self._away_since = None
            log.emit("FOCUS_REGAINED", seconds_away=secs)
            self.focus_regained.emit(secs)

    def start(self):
        self._timer.start(self._interval)

    def stop(self):
        self._timer.stop()


if __name__ == "__main__":
    # Demo: print banned apps running right now, then watch for 30 s in flag-only mode.
    import sys
    from PyQt6.QtWidgets import QApplication
    from qesentry.core.config import DEFAULTS
    app = QApplication(sys.argv)
    w = ProcessWatchdog(DEFAULTS["denylist"], mode="flag")
    print("Banned apps running right now:", w.scan_once())
    w.start()
    QTimer.singleShot(30_000, app.quit)
    app.exec()
