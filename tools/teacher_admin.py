"""Administrator helper for teacher accounts (run from the project folder, with the venv active).

    python tools/teacher_admin.py list
    python tools/teacher_admin.py create --name "Maria Santos" --username msantos@school.edu
    python tools/teacher_admin.py reset-password --username msantos@school.edu

Teachers can also create their own account in the Teacher Portal; use this tool when someone forgets their
password (there is no self-service reset) or to bootstrap the first account. Uses config.json (teacher profile).
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from qesentry.core import db                                   # noqa: E402
from qesentry.core.config import load_config              # noqa: E402


def _password():
    pw = getpass.getpass("New password: ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return pw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--username", required=True)
    r = sub.add_parser("reset-password")
    r.add_argument("--username", required=True)
    args = ap.parse_args()
    try:
        db.connect(load_config("teacher"))
        db.init_db()
        if args.cmd == "list":
            for t in db.list_teachers():
                print(f"#{t['id']:<3} {t['username']:<35} {t['full_name']}{'' if t['is_active'] else '  (disabled)'}")
        elif args.cmd == "create":
            t = db.register_teacher(args.name, args.username, _password())
            print(f"Created teacher #{t['id']}: {t['full_name']} <{t['username']}>")
        else:
            print("Password updated." if db.admin_set_password(args.username, _password()) else "No such user.")
    except (ValueError, db.DatabaseError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
