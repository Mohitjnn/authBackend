from fastapi import APIRouter
from datetime import timedelta
from typing import Annotated
from fastapi import Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from utils.auth import authenticate_user, create_access_token
from models.model import Token, Login
import os
from dotenv import load_dotenv

load_dotenv(".env")

login_root = APIRouter()


@login_root.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response
):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
    )
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return Token(access_token=access_token, token_type="bearer")


@login_root.post("/signIn", response_model=Token)
async def login_for_access_token(form_data: Login, response: Response):
    user = authenticate_user(form_data.userName, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
    )
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return Token(access_token=access_token, token_type="bearer")
