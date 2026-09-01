from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (
    COOKIE_NAME,
    _DUMMY_HASH,
    clear_login_attempts,
    clear_session_cookie,
    client_ip,
    create_session,
    current_user,
    delete_user_sessions,
    hash_password,
    ip_blocked,
    login_blocked,
    record_failed_login,
    set_session_cookie,
    verify_password,
)
from ..db import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas import ChangePasswordRequest, LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every rejected login. See login() for why it is also important
# that the *timing* of each rejection matches.
_BAD_CREDENTIALS = "Invalid email or password"
_TOO_MANY = "Too many login attempts. Try again later."


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(
    body: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)
):
    # Signup is open, which makes it a free account faucet without a per-ip cap.
    # It shares the failed-login counter deliberately: someone brute-forcing
    # logins should not get a clean budget for creating accounts as well.
    if ip_blocked(db, client_ip(request)):
        raise HTTPException(429, _TOO_MANY)

    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(409, "An account with this email already exists")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()

    session = create_session(db, user)
    set_session_cookie(response, session.token)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
):
    email = body.email.strip().lower()
    ip = client_ip(request)

    # Checked before any lookup, and phrased identically regardless of whether
    # the account exists — a 429 that only fired for real accounts would just
    # move enumeration from the timing channel to the status code.
    if login_blocked(db, email, ip):
        raise HTTPException(429, _TOO_MANY)

    user = db.scalar(select(User).where(User.email == email))

    # Always run exactly one scrypt verification, against a dummy hash when the
    # email is unknown. Writing this as `not user or not verify_password(...)`
    # short-circuits, so an unknown email skips the hash entirely and returns
    # measurably faster (334ms vs 215ms as measured) — which enumerates accounts
    # by stopwatch no matter how generic the message below is.
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)

    if not user or not password_ok:
        record_failed_login(db, email, ip)
        raise HTTPException(401, _BAD_CREDENTIALS)

    clear_login_attempts(db, email)
    session = create_session(db, user)
    set_session_cookie(response, session.token)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = db.get(SessionRow, token)
        if session:
            db.delete(session)
            db.commit()
    clear_session_cookie(response)


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    delete_user_sessions(db, user.id)
    clear_session_cookie(response)


@router.post("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    db.commit()

    # Changing a password is how someone responds to believing they are
    # compromised, so it has to end every other session — otherwise an attacker
    # already holding a cookie keeps their access. The current session is
    # re-issued rather than kept, so the old token dies too and the safe action
    # does not sign the user out of the tab they are standing in.
    delete_user_sessions(db, user.id)
    session = create_session(db, user)
    set_session_cookie(response, session.token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
