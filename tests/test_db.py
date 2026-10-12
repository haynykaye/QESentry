"""Database-layer tests on a throw-away SQLite file. Needs SQLAlchemy (pip install -r requirements.txt)."""
import datetime as dt
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from qesentry.core import db
    HAVE = True
except ImportError:
    HAVE = False

FORM = "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform"


@unittest.skipUnless(HAVE, "SQLAlchemy not installed")
class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cfg = {"database": {"url": "sqlite:///" + os.path.join(cls.tmp.name, "t.db").replace("\\", "/"), "connect_timeout": 5}}
        db.connect(cfg)
        db.init_db()
        cls.t = db.register_teacher("Maria Santos", "MSantos@School.edu", "correct horse")
        cls.other = db.register_teacher("Other Teacher", "other@school.edu", "another password")

    @classmethod
    def tearDownClass(cls):
        db._state["engine"].dispose()
        cls.tmp.cleanup()

    def mk(self, title="Quiz 1", category="Quiz", sections="bscs 3-1"):
        return db.create_exam(self.t["id"], title, category, FORM, sections)

    def test_auth(self):
        self.assertIsNotNone(db.authenticate_teacher("msantos@school.edu", "correct horse"))
        self.assertIsNone(db.authenticate_teacher("msantos@school.edu", "wrong"))
        self.assertIsNone(db.authenticate_teacher("nobody@school.edu", "correct horse"))
        with self.assertRaises(ValueError):
            db.register_teacher("Dup", "msantos@school.edu", "password123")
        with self.assertRaises(ValueError):
            db.register_teacher("Short Pw", "short@school.edu", "abc")

    def test_profile_and_password(self):
        self.assertEqual(db.update_teacher_name(self.other["id"], "Other  Person"), "Other Person")
        with self.assertRaises(ValueError):
            db.change_password(self.other["id"], "bad current", "newpassword1")
        db.change_password(self.other["id"], "another password", "newpassword1")
        self.assertIsNotNone(db.authenticate_teacher("other@school.edu", "newpassword1"))

    def test_wrong_current_password_is_distinguishable(self):
        with self.assertRaises(db.WrongPassword):
            db.change_password(self.t["id"], "not my password", "brand new pass")
        with self.assertRaises(ValueError) as ctx:                                       # too short, but current is right
            db.change_password(self.t["id"], "correct horse", "short")
        self.assertNotIsInstance(ctx.exception, db.WrongPassword)

    def test_section_format_enforced(self):
        with self.assertRaises(ValueError):
            db.create_exam(self.t["id"], "Bad", "Exam", FORM, "BSIT2-3")
        ex = self.mk("Fmt", "Exam", "bsit 1-2n")
        self.assertEqual(ex["sections"], ["BSIT 1-2N"])
        with self.assertRaises(ValueError):
            db.update_exam(ex["id"], self.t["id"], "Fmt", "Exam", FORM, "nonsense")

    def test_reopen(self):
        ex = self.mk("Reopen me")
        self.assertTrue(db.close_exam(ex["id"], self.t["id"]))
        self.assertNotIn(ex["id"], [e["id"] for e in db.list_exams(active_only=True)])
        self.assertFalse(db.reopen_exam(ex["id"], self.other["id"]))                    # only the owner
        self.assertTrue(db.reopen_exam(ex["id"], self.t["id"]))
        self.assertIn(ex["id"], [e["id"] for e in db.list_exams(active_only=True)])
        self.assertFalse(db.reopen_exam(ex["id"], self.t["id"]))                        # already open

    # ---- open / close schedule
    def _sched(self, title, opens=None, closes=None):
        return db.create_exam(self.t["id"], title, "Quiz", FORM, "", opens, closes)

    def _ids(self, **kw):
        return [e["id"] for e in db.list_exams(**kw)]

    def test_schedule_gates_students(self):
        now, hour = db.utcnow(), dt.timedelta(hours=1)
        later = self._sched("Opens later", opens=now + hour, closes=now + 2 * hour)
        self.assertEqual(later["state"], "SCHEDULED")
        self.assertNotIn(later["id"], self._ids(active_only=True))               # hidden from students...
        self.assertIn(later["id"], self._ids(teacher_id=self.t["id"], active_only=False))   # ...but the teacher still sees it
        with self.assertRaises(db.LoginRejected) as ctx:
            db.register_student_login("2022-00001-MN-0", "Ana Cruz", "BSIT 2-2N", later["id"])
        self.assertIn("opens on", str(ctx.exception))
        live = self._sched("Open now", opens=now - hour, closes=now + hour)
        self.assertEqual(live["state"], "OPEN")
        self.assertIn(live["id"], self._ids(active_only=True))
        self.assertTrue(db.register_student_login("2022-00001-MN-0", "Ana Cruz", "BSIT 2-2N", live["id"])["login_id"])

    def test_due_assessment_closes_itself_and_can_be_reopened(self):
        now, hour = db.utcnow(), dt.timedelta(hours=1)
        ex = self._sched("Due soon", closes=now + hour)
        due = db.update_exam(ex["id"], self.t["id"], "Due soon", "Quiz", FORM, "", None, now - hour)   # time passes
        self.assertEqual((due["state"], due["status"]), ("CLOSED", "ACTIVE"))      # nobody pressed Close
        self.assertNotIn(ex["id"], self._ids(active_only=True))
        with self.assertRaises(db.LoginRejected) as ctx:
            db.register_student_login("2022-00002-MN-0", "Ben Lim", "BSIT 2-2N", ex["id"])
        self.assertIn("closed on", str(ctx.exception))
        self.assertFalse(db.reopen_exam(ex["id"], self.other["id"]))                # only the owner
        self.assertTrue(db.reopen_exam(ex["id"], self.t["id"]))                     # re-open with no schedule
        row = next(e for e in db.list_exams(self.t["id"], active_only=False) if e["id"] == ex["id"])
        self.assertEqual(row["state"], "OPEN")
        self.assertEqual(row["label"], "RE-OPENED")                                # was closed once, open again now
        self.assertIsNone(row["closes_at"])
        self.assertIn(ex["id"], self._ids(active_only=True))

    def test_reopen_with_a_new_schedule(self):
        now, hour = db.utcnow(), dt.timedelta(hours=1)
        ex = self._sched("Reschedule me")
        self.assertTrue(db.close_exam(ex["id"], self.t["id"]))
        self.assertTrue(db.reopen_exam(ex["id"], self.t["id"], now + hour, now + 2 * hour))
        row = next(e for e in db.list_exams(self.t["id"], active_only=False) if e["id"] == ex["id"])
        self.assertEqual((row["state"], row["label"]), ("SCHEDULED", "SCHEDULED"))   # not open yet -> SCHEDULED

    def test_never_closed_assessment_is_not_labelled_reopened(self):
        fresh = self.mk("Fresh one")
        self.assertEqual(fresh["label"], "OPEN")
        later = self._sched("Opens later", opens=db.utcnow() + dt.timedelta(hours=1))
        self.assertEqual(later["label"], "SCHEDULED")

    def test_schedule_validation(self):
        now, hour = db.utcnow(), dt.timedelta(hours=1)
        with self.assertRaises(ValueError):
            self._sched("Closes in the past", closes=now - hour)
        with self.assertRaises(ValueError):
            self._sched("Closes before it opens", opens=now + 2 * hour, closes=now + hour)
        ex = self.mk("Needs a future time")
        db.close_exam(ex["id"], self.t["id"])
        with self.assertRaises(ValueError):
            db.reopen_exam(ex["id"], self.t["id"], None, now - hour)

    def test_edit_keeps_schedule_unless_changed(self):
        now, hour = db.utcnow(), dt.timedelta(hours=1)
        ex = self._sched("Keep my times", opens=now + hour, closes=now + 2 * hour)
        kept = db.update_exam(ex["id"], self.t["id"], "Renamed", "Quiz", FORM, "")
        self.assertEqual(kept["closes_at"].replace(microsecond=0), ex["closes_at"].replace(microsecond=0))
        self.assertEqual(kept["state"], "SCHEDULED")
        cleared = db.update_exam(ex["id"], self.t["id"], "Renamed", "Quiz", FORM, "", None, None)
        self.assertIsNone(cleared["opens_at"])
        self.assertEqual(cleared["state"], "OPEN")

    def test_names_saved_uppercase(self):
        ex = self.mk("Names", "Exam", "")
        db.register_student_login("2022-00009-MN-0", "juan  a. dela cruz", "X 1-1", ex["id"])
        row = db.monitor_rows(self.t["id"], exam_id=ex["id"])[0]
        self.assertEqual(row["full_name"], "JUAN A. DELA CRUZ")

    def test_login_flow_and_alerts(self):
        ex = self.mk("Flow")
        with self.assertRaises(db.LoginRejected):
            db.register_student_login("2022-00001-MN-0", "Ana", "BSIT 1-1", ex["id"])       # wrong section
        r = db.register_student_login("2022-00001-MN-0", "Ana Cruz", "bscs 3-1", ex["id"])
        lid = r["login_id"]
        db.add_events(lid, [("FOCUS_LOSS", "Window lost focus to Discord", db.utcnow()),
                            ("BANNED_PROCESS", "Banned app launched: discord.exe", db.utcnow())])
        rows = [x for x in db.monitor_rows(self.t["id"], exam_id=ex["id"])]
        self.assertEqual(rows[0]["alerts"], 2)
        self.assertEqual(rows[0]["category"], "Quiz")
        info, evs = db.list_events(lid, self.t["id"])
        self.assertEqual([e["event_type"] for e in evs], ["FOCUS_LOSS", "BANNED_PROCESS"])
        self.assertEqual(db.list_events(lid, self.other["id"]), (None, []))               # not another teacher's
        self.assertEqual(db.heartbeat(lid), "ACTIVE")
        self.assertTrue(db.mark_submitted(lid, "form_redirect"))
        self.assertFalse(db.mark_submitted(lid, "form_redirect"))                        # idempotent
        with self.assertRaises(db.LoginRejected):
            db.register_student_login("2022-00001-MN-0", "Ana Cruz", "BSCS 3-1", ex["id"])  # already submitted

    def test_release(self):
        ex = self.mk("Release")
        lid = db.register_student_login("2022-00002-MN-0", "Ben", "BSCS 3-1", ex["id"])["login_id"]
        self.assertEqual(db.release_students([lid], self.other["id"]), 0)                # not the owner
        self.assertEqual(db.release_students([lid], self.t["id"]), 1)
        self.assertEqual(db.heartbeat(lid), db.STATUS_RELEASED)
        db.mark_release_acked(lid)
        row = [x for x in db.monitor_rows(self.t["id"], exam_id=ex["id"])][0]
        self.assertEqual((row["status"], row["lockdown"]), ("RELEASED_BY_TEACHER", "UNLOCKED"))

    def test_edit_close_delete(self):
        ex = self.mk("Edit me", "Exam")
        new = db.update_exam(ex["id"], self.t["id"], "Edited", "Quiz", FORM, "BSCS 3-2")
        self.assertEqual((new["title"], new["category"], new["sections"]), ("Edited", "Quiz", ["BSCS 3-2"]))
        with self.assertRaises(ValueError):
            db.update_exam(ex["id"], self.other["id"], "Hijack", "Exam", FORM, "")
        lid = db.register_student_login("2022-00003-MN-0", "Cy", "BSCS 3-2", ex["id"])["login_id"]
        self.assertTrue(db.close_exam(ex["id"], self.t["id"]))
        self.assertNotIn(ex["id"], [e["id"] for e in db.list_exams(active_only=True)])
        self.assertEqual(db.delete_exam(ex["id"], self.t["id"]), 1)                        # releases the active student
        self.assertEqual(db.heartbeat(lid), db.STATUS_RELEASED)
        self.assertNotIn(ex["id"], [e["id"] for e in db.list_exams(self.t["id"], active_only=False)])
        self.assertEqual([x for x in db.monitor_rows(self.t["id"], exam_id=ex["id"])], [])

    def test_filters(self):
        ex = self.mk("Filters", "Exam", "")
        db.register_student_login("2022-00004-MN-0", "Dee 100%", "BSCS 9-9", ex["id"])
        self.assertEqual(len(db.monitor_rows(self.t["id"], search="100%", exam_id=ex["id"])), 1)
        self.assertEqual(len(db.monitor_rows(self.t["id"], search="zzz", exam_id=ex["id"])), 0)
        self.assertEqual(len(db.monitor_rows(self.t["id"], category="Quiz", exam_id=ex["id"])), 0)
        self.assertEqual(len(db.monitor_rows(self.t["id"], section="bscs 9-9", exam_id=ex["id"])), 1)


@unittest.skipUnless(HAVE, "SQLAlchemy not installed")
class MigrationTests(unittest.TestCase):
    def test_old_exams_table_gets_the_schedule_columns(self):
        from sqlalchemy import inspect, text
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"database": {"url": "sqlite:///" + os.path.join(tmp, "old.db").replace("\\", "/"), "connect_timeout": 5}}
            db.connect(cfg)
            with db._state["engine"].begin() as c:             # the exams table as it was before the schedule feature
                c.execute(text("CREATE TABLE exams (id INTEGER PRIMARY KEY, teacher_id INTEGER, title VARCHAR(200), "
                               "category VARCHAR(10), form_url VARCHAR(1000), form_key VARCHAR(500), "
                               "sections VARCHAR(500), status VARCHAR(10), created_at DATETIME, closed_at DATETIME)"))
            db.init_db()
            cols = {c["name"] for c in inspect(db._state["engine"]).get_columns("exams")}
            db._state["engine"].dispose()
        self.assertTrue({"opens_at", "closes_at"} <= cols)


if __name__ == "__main__":
    unittest.main()
