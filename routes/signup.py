from fastapi import APIRouter, HTTPException
from config.config import blogs_collection
from utils.auth import get_password_hash
from models.model import signupUser

signupRouter = APIRouter()


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
