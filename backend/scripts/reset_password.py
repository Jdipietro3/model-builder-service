"""Operator CLI to reset a user's password.

WHY THIS EXISTS: there is no self-serve password reset, because that needs mail
infrastructure this prototype doesn't have. Without something like this a
forgotten password is permanent lockout — the account and every project, model
and deployment under it become unreachable. This is the stopgap.

It deliberately bypasses knowing the current password. That is safe only because
running it already requires shell access to the machine and write access to the
database, which is strictly more privilege than the account itself grants.

    venv\\Scripts\\python.exe backend\\scripts\\reset_password.py --list
    venv\\Scripts\\python.exe backend\\scripts\\reset_password.py user@example.com
    venv\\Scripts\\python.exe backend\\scripts\\reset_password.py user@example.com --generate

Everything security-relevant is imported from app.auth rather than reimplemented,
so if the hashing scheme or session rules change this script follows without
anyone remembering to update it.
"""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

# backend/ on the path so `app.*` resolves however this is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.auth import (  # noqa: E402
    clear_login_attempts,
    delete_user_sessions,
    hash_password,
)
from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402

MIN_PASSWORD_LENGTH = 8  # matches SignupRequest / ChangePasswordRequest


def list_users(db) -> int:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    if not users:
        print("No accounts exist yet.")
        return 0
    print(f"{len(users)} account(s):")
    for u in users:
        print(f"  {u.email:<40} created {u.created_at:%Y-%m-%d}")
    return 0


def prompt_for_password() -> str | None:
    """Read the new password twice without echoing it.

    Not accepted as a command-line argument on purpose: an argument lands in
    shell history and in the process list, where any other user on the box can
    read it. Use --generate for non-interactive use.
    """
    first = getpass.getpass("New password (not echoed): ")
    if len(first) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return None
    if first != getpass.getpass("Confirm new password: "):
        print("Passwords did not match.", file=sys.stderr)
        return None
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a Model Builder account password.")
    parser.add_argument("email", nargs="?", help="Account to reset.")
    parser.add_argument("--list", action="store_true", help="List accounts and exit.")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate a strong random password and print it once, instead of prompting.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.list:
            return list_users(db)

        if not args.email:
            parser.print_usage(sys.stderr)
            print("\nGive an email, or --list to see the accounts.", file=sys.stderr)
            return 2

        email = args.email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            # Enumeration isn't a concern here — the operator can already read
            # the users table — so say plainly what went wrong.
            print(f"No account with email {email!r}. Try --list.", file=sys.stderr)
            return 1

        if args.generate:
            new_password = secrets.token_urlsafe(18)
        else:
            new_password = prompt_for_password()
            if new_password is None:
                return 1

        user.password_hash = hash_password(new_password)
        db.commit()

        # Same reasoning as the in-app password change: a reset is how someone
        # responds to losing control of an account, so every existing session
        # has to die with it. Unlike the in-app flow there is no session here to
        # preserve, so all of them go.
        delete_user_sessions(db, user.id)

        # Without this the operator resets the password and the user still can't
        # log in, because the failed attempts that led them to ask for a reset
        # are exactly what has them rate limited. Easy to miss, and it makes the
        # tool look broken.
        clear_login_attempts(db, email)

        print(f"Password reset for {email}.")
        print("All existing sessions for this account were signed out.")
        if args.generate:
            print(f"\n  New password: {new_password}\n")
            print("Shown once. Give it to the user over a channel you trust, and")
            print("have them change it from the account page after signing in.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
