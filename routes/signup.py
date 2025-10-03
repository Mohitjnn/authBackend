from fastapi import APIRouter, HTTPException
from config.config import blogs_collection
from utils.auth import get_password_hash
from models.model import signupUser
from pydantic import BaseModel

signupRouter = APIRouter()


class HashPasswordRequest(BaseModel):
    password: str


@signupRouter.post("/hash-password")
async def hash_password(request: HashPasswordRequest):
    """Generate a hashed version of the provided password"""
    try:
        hashed = get_password_hash(request.password)
        return {
            "original_password": request.password,
            "hashed_password": hashed,
            "message": "Password hashed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error hashing password: {str(e)}")


@signupRouter.post("/signup")
async def sign_up(user: signupUser):
    user_dict = user.dict()
    print(user_dict)
    print("Received data:", user_dict)  # Debug log
    if not user.hashed_password:
        raise HTTPException(status_code=400, detail="Password is required")

    existing_user = blogs_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict["hashed_password"] = get_password_hash(user.hashed_password)
    blogs_collection.insert_one(user_dict)
    return {"success": True, "message": "User created successfully"}
