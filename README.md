# QESentry

Secure online exams and quizzes for Google Forms, with teacher accounts, live monitoring and a database record
of every student session.

* **Students** log in (ID, name, section, exam), then sit the exam in a locked, full-screen browser.
* **Teachers** create Exams/Quizzes, watch students live, review each student's alert timeline, release a student
  remotely, and export results to CSV.
* Everything is stored in **MySQL** (SQLite works for a quick single-PC trial).

> QESentry deters casual cheating. It cannot stop a second device, a determined student, or Ctrl+Alt+Del.
> Pair it with an in-room proctor for high-stakes exams, and get your school's data-privacy approval first
> (it records names, activity and alerts).

## 0. Create your config files
`config.json` and `config.student.json` are **not** in this repository because they contain database passwords.
Create them from the example files:
1. Copy `config.example.json` and rename the copy to `config.json`.
2. Copy `config.student.example.json` and rename the copy to `config.student.json`.
3. Fill in your own database user and password (you set these in steps 3 and 6 below).

**Quick trial without MySQL:** make `config.json` contain only the line below, then skip steps 3 and 6.
```json
{ "database": { "driver": "sqlite", "path": "qesentry.db" } }
```

## 1. One-time setup (Windows, VS Code, MySQL)

1. Install **Python 3.12**, **VS Code** (+ the Python extension), **MySQL Server 8** and **MySQL Workbench**.
2. Open this folder in VS Code (**File → Open Folder**, the folder that contains `main.py`), then in the terminal:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. In **Workbench**, open `sql/01_create_database.sql`, change the password, and run it (lightning-bolt button).
4. Put the same values in **`config.json`** (`database` block: host, user, password).
5. Start the app: `python main.py` → **Teacher Portal** → **Create Teacher Account** → sign in.
   The first Teacher Portal start creates the tables automatically.
6. Back in Workbench, open `sql/02_student_user.sql`, change the password, run it, and put the same values in
   **`config.student.json`**.  *(Run it only after step 5 – the tables must exist.)*
   Use the user `qesentry_student` (the script creates it) and the password you chose.

If a password is forgotten: `python tools/teacher_admin.py reset-password --username you@school.edu`.

> Windows **Smart App Control** / school "Application Control" policies can block PyQt6 (error: *"An Application
> Control policy has blocked this file"*). Turn Smart App Control off, or ask IT to allow the app.

## 2. Day-to-day

> **Always test with `python main.py --dev`.** Without `--dev`, the app locks the keyboard system-wide and closes other programs.

**Teacher** — `python main.py` → *Teacher Portal*
| Tab | What you do |
|-----|-------------|
| **Live Monitor** | Colour-coded counters (students / active / submitted / flagged) sit top-left; **Release Student** and **Export CSV** top-right. Filter by Section, Category, Assessment or student search. Badges show Lockdown (LOCKED / UNLOCKED / …) and Status (ACTIVE / SUBMITTED / RELEASED / TERMINATED). **FLAGGED** (⚑) appears when a student has `flag_threshold` alerts (default 3). **Double-click** a row for the full timestamped alert timeline. **Release Student** unlocks the selected students remotely. **Export CSV** saves the rows currently shown. |
| **Assessments** | **New**, then use each row's **Actions** column: **Edit**, **Close** (or **Re-Open** once closed) and **Delete**. Category is *Exam* or *Quiz*. Closing stops new logins; Re-Open makes it appear in the Student Portal again. Delete hides the assessment and releases any student still locked in it; records stay in the database. |
| **Settings** | Edit your name, change your password, **Log Out** (returns to the role selector). |

**Student** — `python main.py` → *Student Portal* (add `--dev` while testing: no keyboard hook, nothing is killed)
1. Close banned apps (Chrome, Edge, Discord, Notepad… see `denylist` in `config.py`).
2. Enter Student ID, Full Name, Section, pick the exam (or paste its link), tick the consent box, **Start Exam**.
3. The form opens full screen. Submitting it (Google's confirmation page is detected) or pressing
   *I Have Finished* unlocks the app and marks the row SUBMITTED.
4. If something goes wrong, the teacher presses **Release Student**; the app unlocks within ~10 seconds
   with no alert.

## 3. How alerts work
Every violation is one row in `event_logs`: `FOCUS_LOSS`, `BANNED_PROCESS`, `BLOCKED_URL`, `KEYBOARD_VIOLATION`,
plus `WINDOW_VIOLATION`, `MULTI_MONITOR`, `EXIT_ATTEMPT`, `DOWNLOAD_BLOCKED`. Identical alerts within one second
count once. If the server is unreachable, alerts are queued and written when it returns. The student's PC also
keeps a tamper-evident local log in `logs/`.

## 4. Security design
* **Two database profiles.** Teachers use `config.json` (full rights on the QESentry database). Students use
  `config.student.json` (restricted user: read exams, insert/update their own login row, insert alerts; **no** access
  to teacher passwords, no delete, no schema changes). The student build bundles *only* `config.student.json`,
  so teacher credentials never reach student PCs, and its Teacher Portal is switched off.
* Passwords are stored as salted PBKDF2-SHA256 (600,000 rounds). Wrong-password lockout: 3 tries, then 30 s.
* Leaving the exam early needs a teacher's **Release** (`override_mode: "release_only"`). The alternative
  `"teacher_login"` lets a teacher type credentials on the student PC, but then the student database user must be
  allowed to read teacher password hashes – not recommended.
* CSV export neutralises spreadsheet formulas (a student can't run `=…` in your Excel).
* Treat the student `.exe` as readable: its database login can only do what `sql/02_student_user.sql` grants.
  Restrict that user's host (`'10.0.5.%'` rather than `'%'`) and keep MySQL off the public internet.

## 5. Build the executables
Edit both config files first, then `build.bat` (inside the venv):
* `dist\QESentry-Student\` – give the **whole folder** to student PCs.
* `dist\QESentry-Teacher\` – teachers only.

Finish with the dress rehearsal: run `tests/bypass_checklist.md` on a spare PC/VM (not `--dev`), then a 3–5 student
low-stakes quiz.

## 6. Project layout
```
QESentry/
├── main.py                  Entry point: role selector → Student or Teacher Portal
├── teacher_app.py           Opens the Teacher Portal directly (used for the Teacher .exe)
├── config.json              Teacher database profile (never ship to student PCs)
├── config.student.json      Student database profile (restricted user)
├── config.example.json          Safe template for config.json
├── config.student.example.json  Safe template for config.student.json
├── requirements.txt, build.bat, README.md
├── qesentry/                The application code
│   ├── core/                No UI: settings, database, logging, alerts, validation rules
│   │   ├── config.py        Defaults + config files, path helpers
│   │   ├── db.py            All database access (SQLAlchemy models + functions)
│   │   ├── alerts.py        Queues alerts (strikes) and writes them to `event_logs`
│   │   ├── logger.py        Local hash-chained event log
│   │   ├── validators.py    Login / password / link rules and their messages
│   │   └── sections.py, form_url.py, csv_export.py, timeutil.py
│   ├── ui/                  Shared look & feel
│   │   ├── theme.py         One stylesheet and shared widgets for every window
│   │   └── forms.py, popups.py, role_selector.py
│   ├── teacher/             Teacher Portal screens
│   │   ├── auth_dialogs.py        Teacher login, Create Account, teacher prompt on a student PC
│   │   ├── account_dialogs.py     Edit Profile, Change Password
│   │   ├── assessment_dialog.py   New / Edit Assessment
│   │   ├── alert_timeline.py      Per-student alert timeline
│   │   ├── dashboard.py           Live Monitor | Assessments | Settings tabs
│   │   └── form_helpers.py        Shared labels and password hints
│   └── student/             Student Portal
│       ├── login_dialog.py        Student login form
│       ├── session.py             The locked-down session lifecycle
│       ├── exam_window.py         Full-screen Google Form window, navigation lock, submission detection
│       ├── keyboard_guard.py      Shortcut blocking, clipboard cleaning, screen-capture protection
│       ├── process_watchdog.py    Banned apps + focus monitor
│       └── warning_bubble.py      Yellow / red warning banner over the exam
├── sql/                     01_create_database.sql, 02_student_user.sql, 03_exam_schedule.sql
├── tools/teacher_admin.py   List teachers, create one, reset a password
├── tests/                   `python -m unittest discover -s tests`, plus bypass_checklist.md
└── logs/                    Session logs (created while the app runs)
```
Run a single module's demo with `python -m`, e.g. `python -m qesentry.student.keyboard_guard`.

**Warning banner.** While a student is in the exam, every blocked shortcut, click-away, banned app or
window violation shows a banner at the top of the screen. It is **yellow** ("Strike 1 of 3") for each attempt and
turns **red** ("Flagged") once the student reaches `flag_threshold` alerts (default 3), the same number that marks
them FLAGGED on the dashboard.

## 7. Troubleshooting
| Message | Fix |
|---------|-----|
| "Cannot reach or use the QESentry database" | Wrong host/user/password/database, MySQL not running, or missing privileges. Test the same login in Workbench. |
| `No module named 'pymysql'` / "cryptography package is required" | `pip install -r requirements.txt` with the venv active. |
| Student sees "Not available" on Teacher Portal | Intended: that build has no teacher credentials. |
| Start Exam greyed out | A banned app is running, the consent box is unticked, or the ID doesn't match `student_id_pattern`. |
| Exam list empty | No open exam; click **Refresh**. |
