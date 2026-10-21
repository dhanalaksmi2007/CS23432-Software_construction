"""Create a real account (for example the first admin).

Usage:  python create_user.py USERNAME "Full Name" admin
The password is typed in a hidden prompt, never stored in a file or on the command line.
"""
import argparse
import getpass
import os
import re
import sqlite3
import sys

from werkzeug.security import generate_password_hash

import database
from app import BASE_DIR

DB_PATH = os.environ.get("DATABASE", os.path.join(BASE_DIR, "instance", "canteen.db"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("name")
    parser.add_argument("role", choices=["student", "staff", "admin"])
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
        sys.exit("Username must be 3-30 letters, numbers or underscores.")
    password = getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8 or password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 8 characters.")
    database.init_db(DB_PATH)
    conn = database.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO users (username, name, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, args.name.strip(), generate_password_hash(password), args.role),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        sys.exit("That username already exists.")
    finally:
        conn.close()
    print(f"Created {args.role} account '{username}'.")


if __name__ == "__main__":
    main()
