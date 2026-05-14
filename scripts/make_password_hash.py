"""Generate a SMARTVOICE_USERS password hash.

Usage:
    python scripts/make_password_hash.py admin Admin
"""

from __future__ import annotations

import getpass
import sys

from smartvoice.auth import hash_password


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ").strip()
    role = sys.argv[2] if len(sys.argv) > 2 else input("Role: ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if not username or not role or not password:
        print("Username, role, and password are required.", file=sys.stderr)
        return 1
    print(f"{username}|{role}|{hash_password(password)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
