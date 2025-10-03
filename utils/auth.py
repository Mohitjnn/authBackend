from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException
import os
from dotenv import load_dotenv
from config.config import blogs_collection
from models.model import UserInDB

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"  # Explicitly set algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password):
    """Hash a password"""
    try:
        # Simple truncation to 72 characters (not bytes) to be safe
        if len(password) > 72:
            password = password[:72]
        
        return pwd_context.hash(password)
    except Exception as e:
        print(f"Password hashing error: {e}")
        print(f"Password length: {len(password)} chars")
        # Try with even shorter password
        try:
            short_password = password[:50]
            return pwd_context.hash(short_password)
        except Exception as e2:
            print(f"Second attempt failed: {e2}")
            raise HTTPException(status_code=500, detail=f"Unable to hash password: {str(e)}")


def verify_password(plain_password, hashed_password):
    """Verify a password against a hash"""
    try:
        # Simple truncation to 72 characters to match hashing
        if len(plain_password) > 72:
            plain_password = plain_password[:72]
            
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"Password verification error: {e}")
        # Try with shorter password
        try:
            short_password = plain_password[:50]
            return pwd_context.verify(short_password, hashed_password)
        except Exception as e2:
            print(f"Second verification attempt failed: {e2}")
            return False


def get_user(username: str):
    user_dict = blogs_collection.find_one({"username": username})
    if user_dict:
        return UserInDB(**user_dict)
    return None


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    # Explicitly specify algorithm
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str):
    try:
        # Explicitly specify algorithm
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
