from fastapi import Depends, HTTPException, status, APIRouter, Request
import jwt
from jwt.exceptions import InvalidTokenError
from models.model import TokenData, User
from typing import Annotated
from utils.auth import get_user
import os
from dotenv import load_dotenv
from config.config import blogs_collection

load_dotenv(".env")

users_root = APIRouter()


def get_token_from_header(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[len("Bearer ") :]
    return token


async def get_current_user(token: Annotated[str, Depends(get_token_from_header)]):
    print("Received token:", token)  # Debug statement
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")]
        )
        print("Decoded payload:", payload)  # Debug statement
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError as e:
        print("Token error:", str(e))  # Debug statement
        raise credentials_exception
    except Exception as e:
        print("Decoding error:", str(e))  # Debug statement
        raise credentials_exception

    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@users_root.get("/users/me", response_model=User)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user


@users_root.get("/users/students")
async def get_students(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    if current_user.role != "professor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only professors can view student list",
        )

    students = list(
        blogs_collection.find({"role": "student"}, {"_id": 0, "hashed_password": 0})
    )
    return students
