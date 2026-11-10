"""Manage AdenClean admin accounts.

    python create_admin.py add you@example.com      # prompts for a password
    python create_admin.py list
    python create_admin.py disable you@example.com  # blocks sign-in immediately
    python create_admin.py enable you@example.com
    python create_admin.py password you@example.com # prompts for a new password

Uses the same storage settings as the app (ADENCLEAN_STORAGE, APPWRITE_*).
"""

import getpass
import re
import sys
import uuid
from datetime import datetime, timezone

import auth
import store as storage

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")


def main(argv, store=None, password_reader=getpass.getpass, out=print):
    store = store or storage.open_store()
    command = argv[0] if argv else ""

    if command == "list":
        for admin in store.list_admins():
            state = "active" if admin["active"] == 1 else "disabled"
            out(f"{admin['email']}  {admin['role']}  {state}  since {admin['created_at']}")
        return 0

    if command in {"add", "disable", "enable", "password"} and len(argv) == 2:
        email = argv[1].strip().lower()
        if len(email) > 190 or not EMAIL_PATTERN.fullmatch(email):
            out("Enter a valid email address (190 characters or fewer).")
            return 2

        if command == "password":
            if store.get_admin_by_email(email) is None:
                out("No admin with that email.")
                return 1
            password = _read_new_password(password_reader, out)
            if password is None:
                return 2
            store.set_admin_password(email, auth.hash_password(password))
            out(f"Password changed: {email}")
            return 0

        if command == "add":
            password = _read_new_password(password_reader, out)
            if password is None:
                return 2
            try:
                store.add_admin(
                    {
                        "id": uuid.uuid4().hex,
                        "email": email,
                        "password_hash": auth.hash_password(password),
                        "role": "admin",
                        "active": 1,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except storage.Conflict:
                out("An admin with that email already exists.")
                return 1
            out(f"Admin created: {email}")
            return 0

        try:
            store.set_admin_active(email, command == "enable")
        except storage.NotFound:
            out("No admin with that email.")
            return 1
        out(f"{command.capitalize()}d: {email}")
        return 0

    out(__doc__)
    return 2


def _read_new_password(password_reader, out):
    """Asks twice; returns the password, or None after saying what was wrong."""
    password = password_reader("Password (12+ characters): ")
    problem = auth.password_problem(password)
    if problem:
        out(problem)
        return None
    if password != password_reader("Repeat password: "):
        out("The passwords did not match.")
        return None
    return password


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (RuntimeError, storage.StoreError) as error:
        print(f"Error: {error}")
        sys.exit(1)
