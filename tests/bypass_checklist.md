# QESentry – hardware lockdown test sheet

Run on a **spare Windows PC or a VM**, with the real student build (`QESentry-Student.exe`) or
`python main.py` **without `--dev`**. Never run non-`--dev` on your main work PC: the keyboard lock is system-wide.
Prepare: one open Exam/Quiz created in the Teacher Portal, the teacher dashboard open on another PC.
Mark each row PASS / FAIL and note what you saw. Logs: `logs\session_*.jsonl` next to the exe.

## A. Role selector and login
| # | Test | Expected | Result |
|---|------|----------|--------|
| 1 | Launch the student build | Role selector shows; **Teacher Portal is greyed out** ("not available on student devices") | |
| 2 | Student Portal → "← Back" (top of the form) | Returns to the role selector | |
| 3 | Small screen / 125–150% scaling | Student login fits; form scrolls; **Start Exam always visible** | |
| 4 | Wrong section / unknown link | Rejected with a clear message, no row created | |
| 5 | Open Chrome/Discord before login | Start Exam disabled, app named in the red box | |

## B. Lockdown (every row should also appear in the alert timeline)
| # | Test | Expected alert | Result |
|---|------|----------------|--------|
| 6 | Alt+Tab, Win key, Ctrl+Esc, Alt+Esc | Nothing happens; `KEYBOARD_VIOLATION` "Blocked shortcut" | |
| 6a | Same keys, plus Alt+F4, Ctrl+C / Ctrl+V, Print Screen | A **yellow** banner floats at the top of the exam for ~4.5 s showing "Strike 1 of 3", "Strike 2 of 3" (never takes focus, fades by itself); repeated presses just refresh it | |
| 6b | Keep going until the 3rd alert | The banner turns **red** ("Flagged"); the student shows FLAGGED on the dashboard | |
| 6c | Click another window / open a banned app | Same banner: "You left the exam window…" / "<App> is not allowed… It was closed." | |
| 6d | Submit the exam | No banner on the completion screen | |
| 7 | Ctrl+C / V / P / S / U, F12, PrintScreen, Win+Shift+S | Blocked; clipboard stays empty | |
| 8 | Ctrl+Alt+Del → Task Manager | Note: **cannot be blocked by the app** (needs the policy setting `use_policies`); record the result | |
| 9 | Start Chrome / Discord / Notepad during the exam | Closed within ~2 s; `BANNED_PROCESS` | |
| 10 | Click another window / notification | Focus snaps back; `FOCUS_LOSS` with window title | |
| 11 | Try Minimize / un-fullscreen | Snaps back; `WINDOW_VIOLATION` | |
| 12 | Click a link leaving Google Forms | Blocked; `BLOCKED_URL` | |
| 13 | Right-click → Save / drag a file out | Nothing saved | |
| 14 | Plug in a 2nd monitor before start | `MULTI_MONITOR` alert recorded | |
| 15 | Screen-share / screenshot tool | Exam window appears black | |

## C. Leaving and finishing
| # | Test | Expected | Result |
|---|------|----------|--------|
| 16 | Alt+F4 | Message "only your teacher can end this session"; `EXIT_ATTEMPT` alert | |
| 17 | Teacher presses **Release Student** | Student unlocks within ~10 s, "Session Ended by Your Teacher" screen, status RELEASED, **no exit alert** | |
| 18 | Submit the Google Form | `FORM_SUBMISSION_DETECTED`, unlocks after ~2.5 s, row SUBMITTED with end time | |
| 19 | "I Have Finished" button → Yes | Same as 18 (source `student_confirmed`) | |
| 20 | Submit with the network unplugged | Unlocks anyway; submission saved after reconnect (retries every 5 s) | |
| 21 | Teacher **Deletes** the assessment mid-exam | Active students unlock (released) | |

## D. Teacher Portal
| # | Test | Expected | Result |
|---|------|----------|--------|
| 23 | Create account, log in, wrong password ×3 | Account works; 30 s lockout after 3 misses | |
| 24 | Edit profile name / change password | Header updates; new password works, old one doesn't | |
| 25 | Create, edit (title/category/link/section), **Close then Re-Open**, delete an assessment from the Actions column | Each reflected in the table and the student list; a closed one disappears from the Student Portal and returns on Re-Open | |
| 26 | Double-click a student row | Timeline modal lists each alert with time and details | |
| 27 | Filters: section, category, assessment, search | Table narrows; "Clear" resets | |
| 28 | Export CSV with filters on, open in Excel | Only visible rows; a student named `=1+1` shows as text | |
| 29 | Log Out | Back at the role selector; Teacher Portal asks for login again | |
| 30 | Shrink the dashboard window | Scroll bars appear; nothing is cut off | |

## E. Security check before the real exam
| # | Test | Expected | Result |
|---|------|----------|--------|
| 31 | `SHOW GRANTS FOR 'qesentry_student'@'%';` | Matches `sql/02_student_user.sql` – nothing broader | |
| 32 | Student build folder contains **no** `config.json` | Only `config.student.json` | |
| 33 | Log in to MySQL with the student account and run `SELECT * FROM teachers;` | **Denied** | |
