-- QESentry step 1: create the database and the TEACHER account. Run in MySQL Workbench as root.
-- Replace the password. The same values go into config.json ("database" block).
CREATE DATABASE IF NOT EXISTS qesentry CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'qesentry_teacher'@'localhost' IDENTIFIED BY 'TeacherPass';
-- Use '%' (or a subnet such as '10.0.%') instead of 'localhost' if teachers connect from other PCs.
GRANT ALL PRIVILEGES ON qesentry.* TO 'qesentry_teacher'@'localhost';
FLUSH PRIVILEGES;

-- Then open the Teacher Portal once (python main.py -> Teacher Portal): it creates the tables
-- (teachers, exams, student_logins, event_logs). Run 02_student_user.sql only AFTER that.
