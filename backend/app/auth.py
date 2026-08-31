"""Session-cookie auth and per-resource ownership checks.

Zero new dependencies on purpose: this machine has Windows Smart App Control
enabled, which has already blocked native wheels (xgboost's .dll among them).
A native password-hashing package (bcrypt/argon2) risks the same fate, so
password hashing here is stdlib-only (hashlib.scrypt + secrets + hmac).
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import COOKIE_SECURE, SESSION_TTL_DAYS
from .db import get_db
from .models import ApiKey, Dataset, Deployment, Prediction, Project, Run
from .models import Session as SessionRow
from .models import User

COOKIE_NAME = "mb_session"

_SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT_PARAMS)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    """Never raises: a malformed stored hash (wrong scheme, corrupt hex, etc.)
    is just treated as "doesn't match" rather than a 500."""
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT_PARAMS)
    return hmac.compare_digest(candidate, expected)


def create_session(db: Session, user: User) -> SessionRow:
    session = SessionRow(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=_now() + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    return session


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite="lax", secure=COOKIE_SECURE)


def optional_current_user(request: Request, db: Session) -> User | None:
    """Plain function (not a Depends target) so callers that must avoid a
    request-scoped db session — e.g. the SSE routes, which outlive it — can
    call it themselves inside their own short-lived session."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = db.get(SessionRow, token)
    if not session:
        return None
    # SQLite's generic DateTime column drops tzinfo on round-trip (a fresh
    # fetch comes back naive even though _now() below is tz-aware and that's
    # what we wrote at creation time) — strip tzinfo on both sides so the
    # comparison is apples-to-apples regardless of whether this row just came
    # off this same Session's identity map or a genuine fetch.
    if session.expires_at.replace(tzinfo=None) < _now().replace(tzinfo=None):
        # Sweep the stale row now; there's no cron in this prototype to do it later.
        db.delete(session)
        db.commit()
        return None
    return db.get(User, session.user_id)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = optional_current_user(request, db)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


def owned_project(
    project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        # 404, not 403: a 403 would confirm that a project with this id exists
        # but belongs to someone else. Treat "not yours" the same as "absent".
        raise HTTPException(404, "Project not found")
    return project


def owned_run(
    run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Run:
    run = db.get(Run, run_id)
    project = db.get(Project, run.project_id) if run is not None else None
    if run is None or project is None or project.user_id != user.id:
        # See owned_project: 404 rather than 403 so we don't leak existence.
        raise HTTPException(404, "Run not found")
    return run


def owned_dataset(
    dataset_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    project = db.get(Project, dataset.project_id) if dataset is not None else None
    if dataset is None or project is None or project.user_id != user.id:
        # See owned_project: 404 rather than 403 so we don't leak existence.
        raise HTTPException(404, "Dataset not found")
    return dataset


def owned_deployment(
    deployment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    project = db.get(Project, deployment.project_id) if deployment is not None else None
    if deployment is None or project is None or project.user_id != user.id:
        # See owned_project: 404 rather than 403 so we don't leak existence.
        raise HTTPException(404, "Deployment not found")
    return deployment


def owned_prediction(
    prediction_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Prediction:
    prediction = db.get(Prediction, prediction_id)
    project = db.get(Project, prediction.project_id) if prediction is not None else None
    if prediction is None or project is None or project.user_id != user.id:
        # See owned_project: 404 rather than 403 so we don't leak existence.
        raise HTTPException(404, "Prediction not found")
    return prediction
