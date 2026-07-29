"""Auth API — register, login, current-user lookup."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.auth import authenticate_user, create_token, register_user, require_auth

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class Credentials(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(body: Credentials):
    try:
        user = register_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": create_token(user), "user": user}


@router.post("/login")
def login(body: Credentials):
    try:
        user = authenticate_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"token": create_token(user), "user": user}


@router.get("/me")
def me(user: dict = Depends(require_auth)):
    return {"user": user}
