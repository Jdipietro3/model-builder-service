from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)
from ..db import get_db
from ..models import Session as SessionRow
from ..models import User
from ..schemas import LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupRequest, response: Response, db: Session = Depends(get_db)):
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
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Same generic message whether the email is unknown or the password is
    # wrong — distinguishing the two would let an attacker enumerate accounts.
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

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


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
