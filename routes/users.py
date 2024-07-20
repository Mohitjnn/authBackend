from fastapi import Depends, HTTPException, status, APIRouter
import jwt
from jwt.exceptions import InvalidTokenError
from models.model import TokenData, User
from typing import Annotated
from utils.authcookie import OAuth2PasswordBearerWithCookie
from utils.auth import get_user
import os
from dotenv import load_dotenv

load_dotenv(".env")

oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="/token")

users_root = APIRouter()


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


@users_root.get("/users/me")
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@users_root.get("/users/me/items/")
async def read_own_items(current_user: Annotated[User, Depends(get_current_user)]):
    return [{"item_id": "Foo", "owner": current_user.username}]
