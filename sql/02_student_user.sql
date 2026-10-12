-- QESentry step 2: the RESTRICTED account the student app uses. Run in MySQL Workbench as root,
-- AFTER the Teacher Portal has created the tables (MySQL refuses grants on tables that do not exist yet).
--
-- Replace the password; put the same value in config.student.json.
-- Replace '%' with the exact host/subnet of your student PCs where you can (e.g. '10.0.5.%').
CREATE USER IF NOT EXISTS 'qesentry_student'@'%' IDENTIFIED BY 'StudentPass';

-- Read the list of open exams (and their teacher's NAME only - never the password column).
GRANT SELECT ON qesentry.exams TO 'qesentry_student'@'%';
GRANT SELECT (id, full_name) ON qesentry.teachers TO 'qesentry_student'@'%';

-- Log in, send heartbeats, report submission, notice a teacher release.
GRANT SELECT, INSERT, UPDATE ON qesentry.student_logins TO 'qesentry_student'@'%';

-- Write alerts. INSERT only: a student client can add events but cannot read, change or delete them.
GRANT INSERT ON qesentry.event_logs TO 'qesentry_student'@'%';

FLUSH PRIVILEGES;

-- Not granted on purpose: DELETE anywhere, any access to teachers.username / password_hash,
-- changes to exams, and any DDL (CREATE / ALTER / DROP).
--
-- Check:  SHOW GRANTS FOR 'qesentry_student'@'%';
