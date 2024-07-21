from pydantic import BaseModel


class Login(BaseModel):
    userName: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenWithUserName(BaseModel):
    access_token: str
    token_type: str
    username: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    address: str | None = None
    bio: str | None = None
    phoneNumber: int | None = None


class UserInDB(User):
    hashed_password: str
