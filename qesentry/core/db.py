"""Backend database layer (SQLAlchemy 2.x). Every other module reaches the data only through this file.

Tables
    teachers        teacher accounts (username/email + salted PBKDF2 password hash)
    exams           one row per assessment a teacher opens (category Exam or Quiz, Google Form link, target sections)
    student_logins  one row per student per assessment: identity, login time, lockdown + submission status
    event_logs      one row per alert (focus loss, banned app, blocked URL, keyboard violation, ...)

All public functions return plain dicts / lists (never ORM objects), so results are safe to hand to Qt widgets
and to other threads. Timestamps are stored as naive UTC; use to_local() when displaying them.

To move to a REST API later, re-implement the functions in the "Repository API" sections; callers do not change.
"""
import datetime as dt
import hashlib
import hmac
import secrets
import threading

from sqlalchemy import (DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine, func, inspect, insert,
                        or_, select, text, update)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from qesentry.core.config import build_db_url
from qesentry.core.form_url import form_key, format_form_url
from qesentry.core.sections import SECTION_HINT, parse_sections, validate_sections  # noqa: F401  (parse_sections re-exported)
from qesentry.core.schedule import STATE_CLOSED, exam_state, schedule_problem, status_label
from qesentry.core.timeutil import format_local, format_schedule, to_local, to_utc, utcnow  # noqa: F401  (re-exported for the UI)

# ----------------------------------------------------------------------------- vocabularies (stored as plain strings)
STATUS_ACTIVE, STATUS_SUBMITTED = "ACTIVE", "SUBMITTED"
STATUS_RELEASED, STATUS_TERMINATED = "RELEASED_BY_TEACHER", "TERMINATED"
LOCK_LOCKED, LOCK_UNLOCKED, LOCK_OVERRIDDEN = "LOCKED", "UNLOCKED", "OVERRIDDEN"
EXAM_ACTIVE, EXAM_CLOSED, EXAM_DELETED = "ACTIVE", "CLOSED", "DELETED"
CATEGORIES = ("Exam", "Quiz")

EVENT_FOCUS, EVENT_PROCESS = "FOCUS_LOSS", "BANNED_PROCESS"
EVENT_URL, EVENT_KEYBOARD = "BLOCKED_URL", "KEYBOARD_VIOLATION"
EVENT_WINDOW, EVENT_MONITOR, EVENT_EXIT = "WINDOW_VIOLATION", "MULTI_MONITOR", "EXIT_ATTEMPT"
EVENT_DOWNLOAD = "DOWNLOAD_BLOCKED"


_now = utcnow


# ----------------------------------------------------------------------------- models
class Base(DeclarativeBase):
    pass


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)          # email or username, lower-case
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))                  # pbkdf2_sha256$iterations$salt$hash
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(10), default="Exam")        # Exam | Quiz
    form_url: Mapped[str] = mapped_column(String(1000))                      # cleaned, embeddable URL
    form_key: Mapped[str] = mapped_column(String(500), index=True)           # canonical key for link matching
    sections: Mapped[str] = mapped_column(String(500), default="")           # comma-separated, upper-case; "" = every section
    status: Mapped[str] = mapped_column(String(10), default=EXAM_ACTIVE, index=True)   # ACTIVE | CLOSED | DELETED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)    # optional schedule (naive UTC);
    closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)   # NULL = no limit on that side


class StudentLogin(Base):
    __tablename__ = "student_logins"
    __table_args__ = (UniqueConstraint("student_id", "exam_id", name="uq_student_exam"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(40), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    section: Mapped[str] = mapped_column(String(40), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    login_time: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    status: Mapped[str] = mapped_column(String(24), default=STATUS_ACTIVE)   # ACTIVE | SUBMITTED | RELEASED_BY_TEACHER | TERMINATED
    lockdown_status: Mapped[str] = mapped_column(String(12), default=LOCK_LOCKED)   # LOCKED | UNLOCKED | OVERRIDDEN
    submitted_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    ended_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)   # submitted, released or terminated
    submit_source: Mapped[str | None] = mapped_column(String(24), nullable=True)      # form_redirect | student_confirmed
    last_heartbeat: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class EventLog(Base):
    __tablename__ = "event_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_login_id: Mapped[int] = mapped_column(ForeignKey("student_logins.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(String(500), default="")
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


# ----------------------------------------------------------------------------- connection
class DatabaseError(Exception):
    """Any backend failure (unreachable server, missing tables, ...), with a message safe to show to a user."""


class WrongPassword(ValueError):
    """The 'current password' typed when changing a password was incorrect."""


class LoginRejected(Exception):
    """A student login that the rules refuse (wrong section, exam closed, already submitted, ...)."""


_lock = threading.Lock()
_state = {"engine": None, "Session": None, "url": None}


def connect(cfg):
    """Create (once per URL) the shared engine from cfg. Safe to call repeatedly and from any thread."""
    url = build_db_url(cfg)
    with _lock:
        if _state["engine"] is not None and _state["url"] == url:
            return
        if _state["engine"] is not None:
            _state["engine"].dispose()
        timeout = int(cfg["database"].get("connect_timeout", 5))
        args = {"timeout": timeout, "check_same_thread": False} if url.startswith("sqlite") \
            else {"connect_timeout": timeout}
        engine = create_engine(url, connect_args=args, pool_pre_ping=True)
        _state.update(engine=engine, Session=sessionmaker(engine, expire_on_commit=False), url=url)


def init_db():
    """Create any missing tables. Used by the Teacher Portal only; the student app never alters the schema."""
    _require()
    try:
        Base.metadata.create_all(_state["engine"])
        _add_missing_columns(_state["engine"])
    except SQLAlchemyError as e:
        raise DatabaseError("Could not set up the QESentry tables. Check the database user's permissions.") from e


def _add_missing_columns(engine):
    """Databases created before the schedule feature lack exams.opens_at / closes_at: add them (one-time, harmless)."""
    have = {c["name"] for c in inspect(engine).get_columns("exams")}
    with engine.begin() as conn:
        for name in ("opens_at", "closes_at"):
            if name not in have:
                conn.execute(text(f"ALTER TABLE exams ADD COLUMN {name} DATETIME NULL"))


def _require():
    if _state["engine"] is None:
        raise DatabaseError("Database is not configured.")


class _Tx:
    """Context manager: a session that commits on success and turns SQLAlchemy errors into DatabaseError."""

    def __enter__(self):
        _require()
        self.s = _state["Session"]()
        return self.s

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.s.commit()
            else:
                self.s.rollback()
        except SQLAlchemyError as e:                       # the commit itself failed
            self.s.close()
            raise DatabaseError("Cannot reach or use the QESentry database. Check your connection and try again.") from e
        finally:
            self.s.close()
        if isinstance(exc, SQLAlchemyError):
            raise DatabaseError("Cannot reach or use the QESentry database. Check your connection and try again.") from exc
        return False


def check_connection():
    """Raise DatabaseError unless the database answers AND has the QESentry tables."""
    with _Tx() as s:
        s.execute(select(func.count()).select_from(Exam))


# ----------------------------------------------------------------------------- passwords
_ITER = 600_000          # PBKDF2-SHA256 work factor (stored in each hash, so it can be raised later)


def hash_password(password, iterations=_ITER, salt=None):
    """'pbkdf2_sha256$<iterations>$<salt>$<hash>' (salt and hash in hex)."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password, stored):
    """Constant-time check of `password` against a hash made by hash_password()."""
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        probe = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(probe, digest)


_DUMMY_HASH = hash_password("not-a-real-password")      # verified against when the user does not exist (timing)


def _check_new_password(password, username=""):
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    if username and password.lower() == username.lower():
        raise ValueError("Password must not be the same as the username.")


# ----------------------------------------------------------------------------- helpers
def _exam_dict(r, teacher_name=None, students=None):
    state = exam_state(r.status, r.opens_at, r.closes_at, _now())
    reopened = r.status == EXAM_ACTIVE and r.closed_at is not None      # closed once, then re-opened (see reopen_exam)
    return {"id": r.id, "teacher_id": r.teacher_id, "title": r.title, "category": r.category,
            "form_url": r.form_url, "sections": parse_sections(r.sections), "status": r.status,
            "created_at": r.created_at, "closed_at": r.closed_at, "teacher_name": teacher_name,
            "students": students, "opens_at": r.opens_at, "closes_at": r.closes_at,
            "state": state,
            "label": status_label(state, reopened)}   # state: OPEN | SCHEDULED | CLOSED; label adds RE-OPENED


def _clean_sections(text):
    """Cleaned section list, or ValueError naming the entries that are not in the BSIT 2-3 / BSIT 1-2N format."""
    sections, bad = validate_sections(text)
    if bad:
        raise ValueError(f"Invalid section: {', '.join(bad)}. {SECTION_HINT}")
    return sections


def _clean_category(category):
    if category not in CATEGORIES:
        raise ValueError("Category must be Exam or Quiz.")
    return category


# ----------------------------------------------------------------------------- Repository API: teachers
def register_teacher(full_name, username, password):
    """Create a teacher account. Raises ValueError (presentable message) for bad or duplicate input."""
    full_name = " ".join((full_name or "").split())
    username = (username or "").strip().lower()
    if len(full_name) < 3:
        raise ValueError("Please enter your full name.")
    if len(username) < 3 or any(c.isspace() for c in username):
        raise ValueError("Username / email must be at least 3 characters with no spaces.")
    _check_new_password(password, username)
    with _Tx() as s:
        if s.scalar(select(Teacher.id).where(Teacher.username == username)):
            raise ValueError("That username / email is already registered.")
        t = Teacher(username=username, full_name=full_name, password_hash=hash_password(password))
        s.add(t)
        try:
            s.flush()
        except IntegrityError:
            raise ValueError("That username / email is already registered.")
        return {"id": t.id, "username": t.username, "full_name": t.full_name}


def authenticate_teacher(username, password):
    """Check username/email + password. Returns {id, username, full_name} or None.
    'No such user' and 'wrong password' look identical (a hash is always computed)."""
    ident = (username or "").strip().lower()
    with _Tx() as s:
        t = s.scalar(select(Teacher).where(Teacher.username == ident, Teacher.is_active == 1))
        ok = verify_password(password or "", t.password_hash if t else _DUMMY_HASH)
        if t and ok:
            return {"id": t.id, "username": t.username, "full_name": t.full_name}
    return None


def teacher_exists(username):
    """True if a teacher account with this username/email exists (used only to pick the login error message)."""
    ident = (username or "").strip().lower()
    with _Tx() as s:
        return s.scalar(select(Teacher.id).where(Teacher.username == ident)) is not None


def update_teacher_name(teacher_id, full_name):
    """Change a teacher's display name. Returns the cleaned name."""
    full_name = " ".join((full_name or "").split())
    if len(full_name) < 3:
        raise ValueError("Please enter your full name.")
    with _Tx() as s:
        s.execute(update(Teacher).where(Teacher.id == teacher_id).values(full_name=full_name))
    return full_name


def change_password(teacher_id, current, new):
    """Change a teacher's password after verifying the current one. Raises ValueError with a presentable message."""
    with _Tx() as s:
        t = s.get(Teacher, teacher_id)
        if t is None or not verify_password(current or "", t.password_hash):
            raise WrongPassword("Current password is incorrect.")
        _check_new_password(new, t.username)
        t.password_hash = hash_password(new)


def admin_set_password(username, new):
    """Reset a password without the old one (used only by tools/teacher_admin.py). Returns True if the user exists."""
    _check_new_password(new)
    with _Tx() as s:
        res = s.execute(update(Teacher).where(Teacher.username == username.strip().lower())
                        .values(password_hash=hash_password(new)))
        return res.rowcount > 0


def list_teachers():
    """All teacher accounts (no password data) - for tools/teacher_admin.py."""
    with _Tx() as s:
        return [{"id": t.id, "username": t.username, "full_name": t.full_name, "is_active": bool(t.is_active)}
                for t in s.scalars(select(Teacher).order_by(Teacher.id))]


# ----------------------------------------------------------------------------- Repository API: exams
_KEEP = object()                                    # "leave the schedule as it is" marker for update_exam


def _check_schedule(opens_at, closes_at, closing_must_be_future):
    problem = schedule_problem(opens_at, closes_at, _now(), closing_must_be_future)
    if problem:
        raise ValueError(problem)


def create_exam(teacher_id, title, category, form_url, sections_text, opens_at=None, closes_at=None):
    """Publish an assessment. opens_at / closes_at (naive UTC, both optional) schedule when students can log in.
    Validates/cleans the link; raises InvalidFormUrl or ValueError with a presentable message."""
    title = " ".join((title or "").split())
    if not title:
        raise ValueError("Please enter a title.")
    category = _clean_category(category)
    clean = format_form_url(form_url)               # may raise InvalidFormUrl
    sections = _clean_sections(sections_text)
    _check_schedule(opens_at, closes_at, True)
    with _Tx() as s:
        row = Exam(teacher_id=teacher_id, title=title, category=category, form_url=clean, form_key=form_key(clean),
                   sections=", ".join(sections), opens_at=opens_at, closes_at=closes_at)
        s.add(row)
        s.flush()
        return _exam_dict(row)


def update_exam(exam_id, teacher_id, title, category, form_url, sections_text, opens_at=_KEEP, closes_at=_KEEP):
    """Edit an assessment's title, category, link, target sections and (optionally) schedule (owner only, not once
    deleted). Students who already logged in keep what they loaded; the change applies to new logins.
    Leave opens_at / closes_at out to keep the schedule as it is; pass None to remove that side of it."""
    title = " ".join((title or "").split())
    if not title:
        raise ValueError("Please enter a title.")
    category = _clean_category(category)
    clean = format_form_url(form_url)
    sections = _clean_sections(sections_text)
    values = dict(title=title, category=category, form_url=clean, form_key=form_key(clean), sections=", ".join(sections))
    if opens_at is not _KEEP or closes_at is not _KEEP:
        _check_schedule(None if opens_at is _KEEP else opens_at, None if closes_at is _KEEP else closes_at, False)
        if opens_at is not _KEEP:
            values["opens_at"] = opens_at
        if closes_at is not _KEEP:
            values["closes_at"] = closes_at
    with _Tx() as s:
        res = s.execute(update(Exam).where(Exam.id == exam_id, Exam.teacher_id == teacher_id, Exam.status != EXAM_DELETED)
                        .values(**values))
        if res.rowcount == 0:
            raise ValueError("That assessment no longer exists.")
        return _exam_dict(s.get(Exam, exam_id))


def close_exam(exam_id, teacher_id):
    """Stop new logins to an assessment (owner only). Students inside are not affected. True if it changed."""
    with _Tx() as s:
        res = s.execute(update(Exam).where(Exam.id == exam_id, Exam.teacher_id == teacher_id, Exam.status == EXAM_ACTIVE)
                        .values(status=EXAM_CLOSED, closed_at=_now()))
        return res.rowcount > 0


def reopen_exam(exam_id, teacher_id, opens_at=None, closes_at=None):
    """Open a closed assessment again (owner only) - closed by the teacher or past its closing time. The schedule
    is replaced by opens_at / closes_at (naive UTC); leave both out to re-open with no schedule at all.
    True if it changed (False if it was not closed, or is not this teacher's)."""
    _check_schedule(opens_at, closes_at, True)
    with _Tx() as s:
        row = s.get(Exam, exam_id)
        if row is None or row.teacher_id != teacher_id or row.status == EXAM_DELETED:
            return False
        if exam_state(row.status, row.opens_at, row.closes_at, _now()) != STATE_CLOSED:
            return False
        closed_when = row.closed_at or row.closes_at or _now()      # keep a closed_at: it is what marks "re-opened"
        row.status, row.closed_at, row.opens_at, row.closes_at = EXAM_ACTIVE, closed_when, opens_at, closes_at
        return True


def delete_exam(exam_id, teacher_id):
    """Soft-delete an assessment (owner only): it disappears from every list and nobody can log in again.
    Students still ACTIVE in it are released so their locked apps unlock. Records stay in the database.
    Returns the number of students released."""
    with _Tx() as s:
        res = s.execute(update(Exam).where(Exam.id == exam_id, Exam.teacher_id == teacher_id, Exam.status != EXAM_DELETED)
                        .values(status=EXAM_DELETED, closed_at=_now()))
        if res.rowcount == 0:
            raise ValueError("That assessment no longer exists.")
        rel = s.execute(update(StudentLogin).where(StudentLogin.exam_id == exam_id, StudentLogin.status == STATUS_ACTIVE)
                        .values(status=STATUS_RELEASED))
        return rel.rowcount


def _open_now(now):
    """SQL condition: status ACTIVE, opening time reached (or none), closing time not reached (or none)."""
    return (Exam.status == EXAM_ACTIVE,
            or_(Exam.opens_at.is_(None), Exam.opens_at <= now),
            or_(Exam.closes_at.is_(None), Exam.closes_at > now))


def list_exams(teacher_id=None, active_only=True, with_counts=False):
    """Non-deleted assessments, newest first. teacher_id=None -> everyone's (the student app uses this).
    active_only=True keeps only those students can log in to right now. with_counts=True adds 'students'."""
    q = select(Exam, Teacher.full_name).join(Teacher, Teacher.id == Exam.teacher_id).where(Exam.status != EXAM_DELETED)
    if teacher_id is not None:
        q = q.where(Exam.teacher_id == teacher_id)
    if active_only:                                  # "open for students right now": not closed, inside its schedule
        q = q.where(*_open_now(_now()))
    with _Tx() as s:
        rows = list(s.execute(q.order_by(Exam.created_at.desc())))
        counts = {}
        if with_counts and rows:
            counts = dict(s.execute(select(StudentLogin.exam_id, func.count(StudentLogin.id))
                                    .where(StudentLogin.exam_id.in_([r.id for r, _ in rows]))
                                    .group_by(StudentLogin.exam_id)).all())
        return [_exam_dict(r, name, counts.get(r.id, 0) if with_counts else None) for r, name in rows]


def find_exam_by_link(link, section):
    """Newest ACTIVE assessment whose form matches `link` and whose target sections include `section`.
    Returns a dict or None. Raises InvalidFormUrl for a bad link."""
    key = form_key(link)
    sec = " ".join((section or "").split()).upper()
    with _Tx() as s:
        rows = s.scalars(select(Exam).where(Exam.form_key == key, *_open_now(_now()))
                         .order_by(Exam.created_at.desc())).all()
        for r in rows:
            allowed = parse_sections(r.sections)
            if not allowed or sec in allowed:
                return _exam_dict(r)
    return None


# ----------------------------------------------------------------------------- Repository API: student logins
def register_student_login(student_id, full_name, section, exam_id):
    """Log a student into an assessment with status ACTIVE. Returns {login_id, resumed, exam}.

    Rules: the assessment must be ACTIVE; the section must be one of its targets (if it has any); a student who
    already SUBMITTED cannot re-enter; a student with an existing row (app crashed / was released) resumes that
    row instead of creating a duplicate.
    """
    section = " ".join((section or "").split()).upper()
    with _Tx() as s:
        ex = s.get(Exam, exam_id)
        if ex is None or ex.status != EXAM_ACTIVE:
            raise LoginRejected("That assessment is not open. Ask your teacher.")
        now = _now()
        if ex.opens_at is not None and now < ex.opens_at:
            raise LoginRejected(f"This assessment opens on {format_local(ex.opens_at)}. Please come back then.")
        if ex.closes_at is not None and now >= ex.closes_at:
            raise LoginRejected(f"This assessment closed on {format_local(ex.closes_at)}. Ask your teacher.")
        allowed = parse_sections(ex.sections)
        if allowed and section not in allowed:
            raise LoginRejected(f"Section {section} is not assigned to this assessment (allowed: {', '.join(allowed)}).")
        row = s.scalar(select(StudentLogin).where(StudentLogin.student_id == student_id, StudentLogin.exam_id == exam_id))
        resumed = row is not None
        if row is not None:
            if row.status == STATUS_SUBMITTED:
                raise LoginRejected("You have already submitted this assessment.")
            row.status, row.lockdown_status, row.ended_time = STATUS_ACTIVE, LOCK_LOCKED, None
            row.full_name, row.section, row.last_heartbeat = " ".join(full_name.split()).upper(), section, _now()
        else:
            row = StudentLogin(student_id=student_id, full_name=" ".join(full_name.split()).upper(), section=section,
                               exam_id=exam_id, status=STATUS_ACTIVE, lockdown_status=LOCK_LOCKED,
                               last_heartbeat=_now())
            s.add(row)
        try:
            s.flush()
        except IntegrityError:
            raise LoginRejected("Your login is already being processed. Please try again.")
        return {"login_id": row.id, "resumed": resumed, "exam": _exam_dict(ex)}


def heartbeat(login_id):
    """Called every few seconds by a locked-down client: proves it is alive. Returns the row's current status,
    so the client learns about a teacher release (RELEASED_BY_TEACHER) without a second query."""
    with _Tx() as s:
        s.execute(update(StudentLogin).where(StudentLogin.id == login_id, StudentLogin.status == STATUS_ACTIVE)
                  .values(last_heartbeat=_now()))
        return s.scalar(select(StudentLogin.status).where(StudentLogin.id == login_id))


def mark_submitted(login_id, source):
    """Student finished: status SUBMITTED, lockdown UNLOCKED. Idempotent. True if this call changed it."""
    now = _now()
    with _Tx() as s:
        res = s.execute(update(StudentLogin).where(StudentLogin.id == login_id, StudentLogin.status != STATUS_SUBMITTED)
                        .values(status=STATUS_SUBMITTED, lockdown_status=LOCK_UNLOCKED, submitted_time=now,
                                ended_time=now, submit_source=source, last_heartbeat=now))
        return res.rowcount > 0


def mark_release_acked(login_id):
    """The student app saw RELEASED_BY_TEACHER and unlocked: lockdown UNLOCKED, end time recorded."""
    now = _now()
    with _Tx() as s:
        s.execute(update(StudentLogin).where(StudentLogin.id == login_id, StudentLogin.status == STATUS_RELEASED)
                  .values(lockdown_status=LOCK_UNLOCKED, ended_time=now, last_heartbeat=now))


def mark_overridden(login_id):
    """A teacher ended the lockdown on the student's PC before submission: TERMINATED / OVERRIDDEN."""
    now = _now()
    with _Tx() as s:
        s.execute(update(StudentLogin).where(StudentLogin.id == login_id, StudentLogin.status == STATUS_ACTIVE)
                  .values(status=STATUS_TERMINATED, lockdown_status=LOCK_OVERRIDDEN, ended_time=now, last_heartbeat=now))


def release_students(login_ids, teacher_id):
    """Teacher remote release: ACTIVE students in this teacher's assessments become RELEASED_BY_TEACHER.
    Their apps notice on the next heartbeat and unlock. Returns how many were released."""
    if not login_ids:
        return 0
    with _Tx() as s:
        mine = select(Exam.id).where(Exam.teacher_id == teacher_id)
        res = s.execute(update(StudentLogin).where(StudentLogin.id.in_(list(login_ids)), StudentLogin.status == STATUS_ACTIVE,
                                                   StudentLogin.exam_id.in_(mine))
                        .values(status=STATUS_RELEASED), execution_options={"synchronize_session": False})
        return res.rowcount


# ----------------------------------------------------------------------------- Repository API: monitoring
def monitor_rows(teacher_id=None, section=None, exam_id=None, category=None, search=None):
    """Rows for the live teacher table, newest login first, with optional filters.

    'lockdown' in each row is LOCKED, UNLOCKED or OVERRIDDEN.
    'alerts' is the number of event_logs rows for that login.
    """
    alerts = (select(func.count(EventLog.id)).where(EventLog.student_login_id == StudentLogin.id).scalar_subquery())
    q = (select(StudentLogin, Exam.title, Exam.category, alerts.label("alerts"))
         .join(Exam, Exam.id == StudentLogin.exam_id).where(Exam.status != EXAM_DELETED))
    if teacher_id is not None:
        q = q.where(Exam.teacher_id == teacher_id)
    if section:
        q = q.where(StudentLogin.section == section.upper())
    if exam_id:
        q = q.where(StudentLogin.exam_id == exam_id)
    if category:
        q = q.where(Exam.category == category)
    if search and search.strip():
        esc = search.strip().replace("/", "//").replace("%", "/%").replace("_", "/_")
        pat = f"%{esc}%"
        q = q.where(or_(StudentLogin.student_id.ilike(pat, escape="/"), StudentLogin.full_name.ilike(pat, escape="/")))
    out = []
    with _Tx() as s:
        for r, title, cat, n in s.execute(q.order_by(StudentLogin.login_time.desc())):
            lock = r.lockdown_status
            out.append({"id": r.id, "student_id": r.student_id, "full_name": r.full_name, "section": r.section,
                        "exam_title": title, "category": cat, "exam_id": r.exam_id, "login_time": r.login_time,
                        "lockdown": lock, "status": r.status, "submitted_time": r.submitted_time,
                        "ended_time": r.ended_time, "alerts": int(n or 0)})
    return out


def sections_in_use(teacher_id=None):
    """Distinct sections seen in logins and in assessment targets, sorted (feeds the dashboard's Section filter)."""
    found = set()
    with _Tx() as s:
        q = select(StudentLogin.section).join(Exam, Exam.id == StudentLogin.exam_id).where(Exam.status != EXAM_DELETED)
        q2 = select(Exam.sections).where(Exam.status != EXAM_DELETED)
        if teacher_id is not None:
            q, q2 = q.where(Exam.teacher_id == teacher_id), q2.where(Exam.teacher_id == teacher_id)
        found.update(x for x in s.scalars(q.distinct()) if x)
        for text in s.scalars(q2):
            found.update(parse_sections(text))
    return sorted(found)


# ----------------------------------------------------------------------------- Repository API: alerts
def add_events(login_id, events):
    """Insert alert rows. events: list of (event_type, details, timestamp_utc_naive). One round trip."""
    if not events:
        return
    with _Tx() as s:
        s.execute(insert(EventLog), [{"student_login_id": login_id, "event_type": t[:32], "details": (d or "")[:500],
                                      "timestamp": ts} for t, d, ts in events])


def list_events(login_id, teacher_id):
    """(student_info, events) for one login, oldest event first - only if the login belongs to this teacher.
    Returns (None, []) otherwise."""
    with _Tx() as s:
        row = s.execute(select(StudentLogin, Exam.title, Exam.category).join(Exam, Exam.id == StudentLogin.exam_id)
                        .where(StudentLogin.id == login_id, Exam.teacher_id == teacher_id)).first()
        if row is None:
            return None, []
        r, title, cat = row
        info = {"id": r.id, "student_id": r.student_id, "full_name": r.full_name, "section": r.section,
                "exam_title": title, "category": cat, "status": r.status}
        evs = [{"id": e.id, "event_type": e.event_type, "details": e.details, "timestamp": e.timestamp}
               for e in s.scalars(select(EventLog).where(EventLog.student_login_id == login_id)
                                  .order_by(EventLog.timestamp, EventLog.id))]
        return info, evs
