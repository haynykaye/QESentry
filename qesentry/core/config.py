"""Configuration and path helpers, shared by every other module.

- DEFAULTS holds the built-in settings. Anything set in config.json / config.student.json overrides them.
- load_config(role) builds the settings for the "teacher" or "student" runtime (separate database profiles).
- available_roles() says which portals this build/install has credentials for.
- friendly_app_name() turns an executable name into a readable app name for dialogs and logs.
- app_dir() / resource_path() find files correctly both when running from source and when
  running as the packaged .exe.
"""
import json
import os
import sys

# Built-in default settings. config.json is merged on top of these in load_config().
DEFAULTS = {
    "exam_url": "",                 # filled in at runtime from the exam the student selects
    "student_field": "",            # e.g. "entry.123456" -> the student ID is pre-filled into that form question
    "exit_hotkey": "ctrl+alt+shift+q",   # shortcut a student/teacher presses to try to leave the exam
    # What leaving early does on a student PC:
    #   "release_only"  -> nothing local; the teacher must press "Release Student" on the dashboard (recommended:
    #                      the student app then never needs to read teacher password hashes)
    #   "teacher_login" -> a teacher types email + password on that PC (needs a student DB user that can read teachers)
    "override_mode": "release_only",
    "process_mode": "kill",         # "kill" = close banned apps, "flag" = only log them
    "use_policies": False,          # registry: disable Task Manager / Lock. KEEP FALSE on dev machines.
    # The exam window may only navigate to addresses starting with one of these.
    "allowed_prefixes": [
        "https://docs.google.com/",
        "https://forms.gle/",
        "https://accounts.google.com/",
    ],
    # --- backend database ---
    # Either give a full SQLAlchemy "url", or fill in the parts and the URL is built for you.
    # driver: "sqlite" (path) | "postgresql" / "mysql" (host, port, name, user, password).
    # The password can be supplied through the QESENTRY_DB_PASSWORD environment variable instead of the file.
    "database": {
        "url": "",
        "driver": "sqlite",
        "path": "qesentry.db",       # sqlite only; relative paths resolve next to the app. Use a shared path for multi-PC use.
        "host": "", "port": 0, "name": "", "user": "", "password": "",
        "connect_timeout": 5,        # seconds; keeps the UI from hanging when the server is unreachable
    },
    # --- system settings ---
    "student_id_pattern": r"^\d{4}-\d{5}-MN-\d{1}$",   # regex a student ID must match (default: PUP format)
    "student_id_example": "2022-01234-MN-0",
    "dashboard_refresh_ms": 3000,    # how often the teacher dashboard re-reads the database
    "heartbeat_seconds": 10,         # how often a locked-down student client reports in
    "auto_detect_submission": True,  # treat Google's /formResponse confirmation page as a submission
    "submit_grace_ms": 2500,         # show the form's confirmation page this long before unlocking
    "flag_threshold": 3,             # a student with this many alerts or more is shown as FLAGGED
    "teacher_registration_code": "", # if set, creating a teacher account also requires this code
    "user_agent": "",               # empty = built-in modern desktop Chrome UA (see exam_window.py)
    # Programs that must not run during the exam (lower-case executable names).
    "denylist": [
        "discord.exe", "msedge.exe", "firefox.exe", "brave.exe",
        "notepad.exe", "chatgpt.exe", "obs64.exe", "obs32.exe", "teamviewer.exe", "anydesk.exe",
        "telegram.exe", "whatsapp.exe", "snippingtool.exe", "screenclippinghost.exe", "taskmgr.exe",
    ],
}


# Human-readable names for the executables we watch (used in dialogs and logs).
APP_DISPLAY_NAMES = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "brave.exe": "Brave Browser",
    "opera.exe": "Opera Browser",
    "opera_gx.exe": "Opera GX Browser",
    "discord.exe": "Discord",
    "notepad.exe": "Notepad",
    "chatgpt.exe": "ChatGPT",
    "obs64.exe": "OBS Studio",
    "obs32.exe": "OBS Studio",
    "teamviewer.exe": "TeamViewer",
    "anydesk.exe": "AnyDesk",
    "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp",
    "snippingtool.exe": "Snipping Tool",
    "screenclippinghost.exe": "Snipping Tool",
    "taskmgr.exe": "Task Manager",
    "code.exe": "Visual Studio Code",
    "python.exe": "Python",
    "pythonw.exe": "Python",
    "explorer.exe": "File Explorer",
}


def friendly_app_name(exe_name):
    """'chrome.exe' -> 'Google Chrome'. Unknown executables become e.g. 'my_tool.exe' -> 'My Tool'."""
    key = (exe_name or "").strip().lower()
    if key in APP_DISPLAY_NAMES:
        return APP_DISPLAY_NAMES[key]
    base = key[:-4] if key.endswith(".exe") else key
    return base.replace("_", " ").replace("-", " ").title() or "Unknown Application"


# Project folder (holds config.json, logs/, ...): qesentry/core/config.py -> three levels up.
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def app_dir():
    """Folder next to the .exe when frozen, else next to the source. Logs are written here."""
    if getattr(sys, "frozen", False):          # True when running as the PyInstaller .exe
        return os.path.dirname(sys.executable)
    return _PROJECT_DIR


def resource_path(name):
    """Full path to a bundled file (such as config.json), inside the .exe bundle or next to the source."""
    base = getattr(sys, "_MEIPASS", _PROJECT_DIR)
    return os.path.join(base, name)


def _read_json(name):
    """Contents of a bundled/side-by-side JSON file, or {} if it does not exist."""
    path = resource_path(name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_config(role="teacher"):
    """Merge DEFAULTS <- config.json <- (student role only) config.student.json.

    Two connection profiles, one per role:
      teacher  config.json           database user with full rights  (ship only with the teacher app)
      student  config.student.json   restricted database user        (ship only with the student app)
    The student build bundles ONLY config.student.json, so teacher credentials never reach student PCs.
    "database" is merged key by key.
    """
    user = _read_json("config.json")
    if role == "student":
        extra = _read_json("config.student.json")
        user = {**user, **extra, "database": {**user.get("database", {}), **extra.get("database", {})}}
    cfg = {**DEFAULTS, **user}
    cfg["database"] = {**DEFAULTS["database"], **user.get("database", {})}
    return cfg


def available_roles():
    """Which portals have credentials in this install: {"student", "teacher"} subset.

    teacher -> config.json is present.  student -> config.student.json (or, for development, config.json).
    The student build ships only config.student.json, so its Teacher Portal is switched off.
    """
    roles = set()
    if os.path.exists(resource_path("config.json")):
        roles |= {"teacher", "student"}
    if os.path.exists(resource_path("config.student.json")):
        roles.add("student")
    return roles


def build_db_url(cfg):
    """SQLAlchemy URL from cfg["database"]. An explicit "url" wins; otherwise it is assembled from the parts."""
    from urllib.parse import quote_plus
    d = cfg["database"]
    if d.get("url"):
        return d["url"]
    driver = (d.get("driver") or "sqlite").lower()
    if driver == "sqlite":
        path = d.get("path") or "qesentry.db"
        if not os.path.isabs(path):
            path = os.path.join(app_dir(), path)
        return "sqlite:///" + path.replace("\\", "/")
    password = os.environ.get("QESENTRY_DB_PASSWORD") or d.get("password", "")
    auth = quote_plus(d.get("user", "")) + (":" + quote_plus(password) if password else "")
    port = f":{d['port']}" if d.get("port") else ""
    return f"{driver}://{auth}@{d.get('host', '')}{port}/{d.get('name', '')}"
