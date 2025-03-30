from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from models.model import Note, User
from typing import List, Annotated
from routes.users import get_current_active_user
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from config.config import client

notes_router = APIRouter()

# MongoDB connection using config
db = client.Users
notes_collection = db.notes

# S3 Configuration - Use environment variables for security
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME", "your-bucket-name")
S3_REGION = os.getenv("AWS_S3_REGION", "us-east-1")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY", "your-access-key")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY", "your-secret-key")

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)


async def save_image_to_s3(image: UploadFile) -> str:
    """Upload image to S3 and return the URL"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image.filename}"

        # Read file content
        content = await image.read()

        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"images/{filename}",
            Body=content,
            ContentType=image.content_type,
            ACL="public-read",  # Makes the file publicly accessible
        )

        # Create the URL
        # For free tier, use the standard S3 URL format
        url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/images/{filename}"
        return url

    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")


async def delete_image_from_s3(image_url: str):
    """Delete image from S3 given its URL"""
    try:
        # Extract key from URL
        key = image_url.split(".amazonaws.com/")[1]
        s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as e:
        print(f"Error deleting from S3: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete image")


async def get_next_sequence_value() -> int:
    """Get next sequence value for note ID"""
    # Find the document with the highest id
    highest_note = notes_collection.find_one(
        {}, sort=[("id", -1)]  # Sort by id in descending order
    )

    # If no notes exist, start with 1, else increment the highest id
    return 1 if not highest_note else highest_note.get("id", 0) + 1


@notes_router.post("/notes")
async def create_note(
    title: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
    image: UploadFile | None = File(None),
):
    image_url = None
    if image:
        image_url = await save_image_to_s3(image)

    # Get the next available ID
    note_id = await get_next_sequence_value()

    note = {
        "id": note_id,  # Add the auto-incrementing ID
        "title": title,
        "description": description,
        "date": date,
        "image_url": image_url,
        "user_id": "mohitjnn",  # Replace with actual user ID later
    }

    result = notes_collection.insert_one(note)
    if result.inserted_id:
        return {
            "message": "Note created successfully",
            "id": note_id,  # Return the numeric ID
            "mongo_id": str(result.inserted_id),
            "image_url": image_url,
        }
    raise HTTPException(status_code=400, detail="Failed to create note")


@notes_router.get("/notes", response_model=List[Note])
async def get_notes(current_user: Annotated[User, Depends(get_current_active_user)]):
    # async def get_notes():
    notes = []
    cursor = notes_collection.find({"user_id": current_user.username})
    for note in cursor:
        notes.append(Note(**note))
    return notes


@notes_router.get("/notes/{note_id}")
async def get_note(
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    note = notes_collection.find_one({"id": note_id, "user_id": current_user.username})
    if note:
        return note
    raise HTTPException(status_code=404, detail="Note not found")


@notes_router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        # Find note first to get image URL if exists
        note = notes_collection.find_one(
            {"id": note_id, "user_id": current_user.username}
        )

        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        # Delete image from S3 if exists
        if note.get("image_url"):
            await delete_image_from_s3(note["image_url"])

        # Delete note from MongoDB
        result = notes_collection.delete_one(
            {"id": note_id, "user_id": current_user.username}
        )

        if result.deleted_count:
            return {"message": "Note deleted successfully"}
        raise HTTPException(status_code=404, detail="Note not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@notes_router.put("/notes/{note_id}")
async def update_note(
    current_user: Annotated[User, Depends(get_current_active_user)],
    note_id: int,
    title: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
):
    try:
        # Update note in MongoDB
        result = notes_collection.update_one(
            {"id": note_id, "user_id": current_user.username},
            {"$set": {"title": title, "description": description, "date": date}},
        )

        if result.modified_count:
            return {"message": "Note updated successfully"}
        raise HTTPException(status_code=404, detail="Note not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@notes_router.get("/notes/search/{query}")
async def search_notes(
    current_user: Annotated[User, Depends(get_current_active_user)], query: str
):
    try:
        # Create a case-insensitive regex pattern
        search_pattern = {"$regex": query, "$options": "i"}

        # Search in title, description, and id (if query is a number)
        search_conditions = [
            {"title": search_pattern},
            {"description": search_pattern},
        ]

        # If query can be converted to int, also search by id
        try:
            note_id = int(query)
            search_conditions.append({"id": note_id})
        except ValueError:
            pass

        # Find notes matching any of the conditions
        cursor = notes_collection.find(
            {
                "$and": [
                    {"user_id": "mohitjnn"},  # Filter by user
                    {"$or": search_conditions},  # Search conditions
                ]
            }
        )

        notes = []
        for note in cursor:
            notes.append(Note(**note))
        return notes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
