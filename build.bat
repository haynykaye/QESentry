@echo off
REM Builds the two QESentry editions. Run from this folder, inside the venv (Python 3.10-3.12).
REM
REM   QESentry-Student  bundles ONLY config.student.json (restricted DB user). Its Teacher Portal is switched off.
REM   QESentry-Teacher  bundles ONLY config.json (full DB user) and opens straight into the Teacher Portal.
REM
REM Edit config.student.json / config.json first (host, password). Never ship config.json to student PCs.
pip install -r requirements.txt || exit /b 1

pyinstaller --noconfirm --clean --onedir --windowed --name QESentry-Student ^
  --icon assets\qesentry.ico --add-data "assets;assets" ^
  --add-data "config.student.json;." ^
  --hidden-import pymysql --hidden-import cryptography main.py || exit /b 1

pyinstaller --noconfirm --clean --onedir --windowed --name QESentry-Teacher ^
  --icon assets\qesentry.ico --add-data "assets;assets" ^
  --add-data "config.json;." ^
  --hidden-import pymysql --hidden-import cryptography teacher_app.py || exit /b 1

echo.
echo Done:
echo   dist\QESentry-Student\QESentry-Student.exe   (give the whole folder to students)
echo   dist\QESentry-Teacher\QESentry-Teacher.exe   (teachers only)
