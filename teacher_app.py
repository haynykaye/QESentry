"""Opens the Teacher Portal directly (skips the role selector):  python teacher_app.py"""
import sys

from main import main

if __name__ == "__main__":
    sys.exit(main(start="teacher"))
