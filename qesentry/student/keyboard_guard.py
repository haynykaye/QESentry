"""Keyboard lockdown, clipboard clearing, screen-capture protection and optional Windows policies.

- KeyboardGuard      blocks shortcuts that could leave or cheat the exam (Alt+Tab, Ctrl+C, Win key, ...).
- ClipboardCleaner   empties the clipboard twice a second so nothing can be pasted in or copied out.
- protect_window()   hides the exam window from screenshots and screen recorders.
- apply_policies() / restore_policies()   optionally disable Task Manager and Lock Workstation via the registry.

Run alone for a 20-second demo:  python -m qesentry.student.keyboard_guard
WARNING: this blocks keys system-wide. Test inside a VM or keep the 20 s demo timer.
"""
import atexit
import ctypes
from ctypes import wintypes

import keyboard
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from qesentry.core import alerts
from qesentry.core import logger as log

# Every shortcut in this list is swallowed (never reaches any program) while the exam runs.
BLOCKED_HOTKEYS = [
    # window switching / task manager
    "alt+tab", "alt+shift+tab", "ctrl+alt+tab", "alt+esc", "ctrl+esc", "ctrl+shift+esc",
    # closing / tabs / windows
    "alt+f4", "ctrl+w", "ctrl+f4", "ctrl+t", "ctrl+n", "ctrl+shift+n", "ctrl+shift+t",
    # clipboard
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+insert", "shift+insert",
    # devtools / view-source / print / save / reload / fullscreen toggle
    "ctrl+shift+i", "ctrl+shift+j", "ctrl+shift+c", "ctrl+u", "ctrl+p", "ctrl+s",
    "f12", "f11", "f5", "ctrl+r", "ctrl+f5",
    # screenshots
    "print screen", "alt+print screen",
]


class KeyboardGuard(QObject):
    """Installs the global keyboard hooks. Call start() when the exam begins and stop() when it ends."""
    blocked = pyqtSignal(str)        # emitted with the hotkey name (from the keyboard thread; Qt queues it)
    exit_hotkey = pyqtSignal()       # emitted when the leave-exam shortcut is pressed

    def __init__(self, exit_hotkey="ctrl+alt+shift+q"):
        super().__init__()
        self._exit_hotkey = exit_hotkey

    def start(self):
        """Block every hotkey in BLOCKED_HOTKEYS plus the Windows keys, and register the leave-exam shortcut."""
        for hk in BLOCKED_HOTKEYS:
            try:
                # suppress=True stops the key combo from reaching other programs; we only report it.
                keyboard.add_hotkey(hk, lambda hk=hk: self._on_blocked(hk), suppress=True)
            except Exception as e:
                log.emit("HOTKEY_REGISTER_FAILED", hotkey=hk, error=str(e))
        for k in ("left windows", "right windows"):   # also kills Win+Tab, Win+D, Win+Shift+S, ...
            try:
                keyboard.hook_key(k, self._on_windows_key, suppress=True)
            except Exception as e:
                log.emit("HOTKEY_REGISTER_FAILED", hotkey=k, error=str(e))
        keyboard.add_hotkey(self._exit_hotkey, self.exit_hotkey.emit, suppress=True)
        log.emit("KEYBOARD_GUARD_STARTED")

    def _on_windows_key(self, event):
        """Same as keyboard.block_key (returns False = swallow the key) but also reports the key-down."""
        if event.event_type == "down":
            self._on_blocked("windows key")
        return False

    def _on_blocked(self, hk):
        """A blocked shortcut was pressed: tell the UI and record an itemised alert (repeats are debounced)."""
        alerts.report("KEYBOARD_VIOLATION", f"Blocked shortcut: {hk.title()}")   # first, so the strike count is up to date
        self.blocked.emit(hk)

    def stop(self):
        """Release every hook so the keyboard works normally again."""
        keyboard.unhook_all()
        log.emit("KEYBOARD_GUARD_STOPPED")


class ClipboardCleaner(QObject):
    """Empties the clipboard twice a second so nothing can be pasted in or carried out."""

    def __init__(self, interval_ms=500):
        super().__init__()
        self._t = QTimer(self)
        self._t.timeout.connect(lambda: QApplication.clipboard().clear())
        self._interval = interval_ms

    def start(self):
        self._t.start(self._interval)

    def stop(self):
        self._t.stop()


def protect_window(hwnd):
    """Hide the window from screenshots / screen recorders (Win10 2004+; older = black window).

    hwnd: the native Windows handle of the window, e.g. int(window.winId()).
    """
    fn = ctypes.windll.user32.SetWindowDisplayAffinity
    fn.argtypes = [wintypes.HWND, wintypes.DWORD]
    if not fn(hwnd, 0x11):           # WDA_EXCLUDEFROMCAPTURE: window is invisible in captures
        fn(hwnd, 0x01)               # WDA_MONITOR fallback: older Windows shows a black window instead


# ---- Optional: blunt Ctrl+Alt+Del options. Off by default (config "use_policies"). Restored on exit. ----
_POLICY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
_POLICY_VALUES = ("DisableTaskMgr", "DisableLockWorkstation")
_saved = {}                          # original registry values, so restore_policies() can put them back


def apply_policies():
    """Disable Task Manager and Lock Workstation for the current user (remembers the old values)."""
    import winreg
    k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _POLICY_KEY)
    for name in _POLICY_VALUES:
        try:
            _saved[name] = winreg.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            _saved[name] = None      # the value did not exist before; delete it again on restore
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(k)
    atexit.register(restore_policies)    # safety net: restore even if the app exits unexpectedly
    log.emit("POLICIES_APPLIED")


def restore_policies():
    """Put the registry back exactly how apply_policies() found it. Safe to call more than once."""
    import winreg
    if not _saved:
        return
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _POLICY_KEY, 0, winreg.KEY_SET_VALUE)
    for name, old in _saved.items():
        if old is None:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, old)
    winreg.CloseKey(k)
    _saved.clear()
    log.emit("POLICIES_RESTORED")


if __name__ == "__main__":
    # Demo: hooks stay active for 20 s, then everything is released.
    import sys
    app = QApplication(sys.argv)
    g = KeyboardGuard()
    g.blocked.connect(lambda k: print("blocked:", k))
    g.exit_hotkey.connect(app.quit)
    g.start()
    QTimer.singleShot(20_000, app.quit)      # safety net
    print("Hooks active for 20s. Try Alt+Tab, Win, Ctrl+C. Ctrl+Alt+Shift+Q quits.")
    app.exec()
    g.stop()
