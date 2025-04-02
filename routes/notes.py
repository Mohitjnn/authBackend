from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from models.model import Note, User
from typing import List, Annotated
from routes.users import get_current_active_user
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from config.config import client
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

notes_router = APIRouter()

# MongoDB connection using config
db = client.Users
notes_collection = db.notes

# S3 Configuration - Use environment variables for security
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME", "your-bucket-name")
S3_REGION = os.getenv("AWS_S3_REGION", "us-east-1")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY", "your-access-key")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY", "your-secret-key")

# KMS Configuration
KMS_KEY_ID = os.getenv("AWS_KMS_KEY_ID")

# Initialize S3 client with retry configuration
session = boto3.Session(
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# Create a config with retries
boto_config = boto3.session.Config(
    signature_version="v4", retries={"max_attempts": 3, "mode": "standard"}
)

# Initialize S3 client
s3_client = session.client("s3", config=boto_config)


async def save_encrypted_image_to_s3(image: UploadFile) -> dict:
    """Upload image to S3 with server-side encryption using KMS"""
    try:
        logger.info(f"Starting to upload image: {image.filename}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image.filename}"
        object_key = f"encrypted-images/{filename}"

        # Read file content
        content = await image.read()
        logger.info(f"Read {len(content)} bytes from image file")

        # Upload with server-side encryption using KMS
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=object_key,
            Body=content,
            ContentType=image.content_type,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY_ID,
        )
        logger.info(f"Successfully uploaded encrypted image to S3: {object_key}")

        # Create the URL
        url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{object_key}"

        return {
            "url": url,
            "key_id": KMS_KEY_ID,
        }

    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        if hasattr(e, "response") and "Error" in e.response:
            error_code = e.response["Error"].get("Code", "")
            error_message = e.response["Error"].get("Message", "")
            if error_code == "InvalidAccessKeyId":
                raise HTTPException(status_code=500, detail="Invalid AWS credentials")
            elif error_code == "AccessDenied":
                raise HTTPException(
                    status_code=500, detail="Access denied to S3 bucket or KMS key"
                )
        raise HTTPException(
            status_code=500, detail=f"Failed to upload encrypted image: {str(e)}"
        )


async def get_encrypted_image_from_s3(image_url: str):
    """Get encrypted image from S3 (decryption is handled by S3)"""
    try:
        # Extract key from URL
        key = image_url.split(".amazonaws.com/")[1]
        logger.info(f"Getting image from S3: {key}")

        # Get the object - S3 automatically decrypts it if it was encrypted with SSE-KMS
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)

        # Read data
        data = response["Body"].read()
        content_type = response.get("ContentType", "image/jpeg")
        logger.info(f"Successfully retrieved image, size: {len(data)} bytes")

        return {"data": data, "content_type": content_type}

    except ClientError as e:
        logger.error(f"Error getting from S3: {e}")
        if hasattr(e, "response") and "Error" in e.response:
            error_code = e.response["Error"].get("Code", "")
            if error_code == "NoSuchKey":
                raise HTTPException(status_code=404, detail="Image not found in S3")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve image: {str(e)}"
        )


async def delete_image_from_s3(image_url: str):
    """Delete image from S3 given its URL"""
    try:
        # Extract key from URL
        key = image_url.split(".amazonaws.com/")[1]
        logger.info(f"Deleting image from S3: {key}")

        s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
        logger.info("Image successfully deleted")
    except ClientError as e:
        logger.error(f"Error deleting from S3: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")


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
    current_user: Annotated[User, Depends(get_current_active_user)],
    title: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
    image: UploadFile | None = File(None),
):
    image_meta = None
    if image:
        image_meta = await save_encrypted_image_to_s3(image)

    # Get the next available ID
    note_id = await get_next_sequence_value()

    note = {
        "id": note_id,
        "title": title,
        "description": description,
        "date": date,
        "user_id": current_user.username,
    }

    # Add image data if provided
    if image_meta:
        note["image_url"] = image_meta["url"]
        note["image_key_id"] = image_meta["key_id"]

    result = notes_collection.insert_one(note)
    if result.inserted_id:
        return {
            "message": "Note created successfully",
            "id": note_id,
            "mongo_id": str(result.inserted_id),
            "image_url": image_meta["url"] if image_meta else None,
        }
    raise HTTPException(status_code=400, detail="Failed to create note")


@notes_router.get("/notes", response_model=List[Note])
async def get_notes(current_user: Annotated[User, Depends(get_current_active_user)]):
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


@notes_router.get("/image/{note_id}")
async def get_note_image(
    note_id: int,
    # current_user: Annotated[User, Depends(get_current_active_user)]
):
    note = notes_collection.find_one({"id": note_id, "user_id": "mohitjnn"})
    if not note or not note.get("image_url"):
        raise HTTPException(status_code=404, detail="Note or image not found")

    try:
        # Get image - S3 handles the decryption automatically
        image_data = await get_encrypted_image_from_s3(note["image_url"])

        from fastapi.responses import Response

        return Response(
            content=image_data["data"], media_type=image_data["content_type"]
        )
    except Exception as e:
        logger.error(f"Error in get_note_image: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve image: {str(e)}"
        )


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
        logger.error(f"Error in delete_note: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@notes_router.put("/notes/{note_id}")
async def update_note(
    current_user: Annotated[User, Depends(get_current_active_user)],
    note_id: int,
    image: UploadFile | None = File(None),
    title: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),
):
    try:
        # Get existing note
        existing_note = notes_collection.find_one(
            {"id": note_id, "user_id": current_user.username}
        )

        if not existing_note:
            raise HTTPException(status_code=404, detail="Note not found")

        # Process image if provided
        image_meta = None
        if image:
            # Delete old image if it exists
            if existing_note.get("image_url"):
                await delete_image_from_s3(existing_note["image_url"])

            # Upload and encrypt new image
            image_meta = await save_encrypted_image_to_s3(image)

        # Prepare update data
        update_data = {
            "title": title,
            "description": description,
            "date": date,
        }

        # Add image data if new image provided
        if image_meta:
            update_data["image_url"] = image_meta["url"]
            update_data["image_key_id"] = image_meta["key_id"]

        # Update note in MongoDB
        result = notes_collection.update_one(
            {"id": note_id, "user_id": current_user.username},
            {"$set": update_data},
        )

        if result.modified_count:
            return {"message": "Note updated successfully"}
        return {"message": "No changes detected"}

    except Exception as e:
        logger.error(f"Error in update_note: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@notes_router.get("/notes/search/{query}")
async def search_notes(
    query: str, current_user: Annotated[User, Depends(get_current_active_user)]
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
                    {"user_id": current_user.username},  # Filter by user
                    {"$or": search_conditions},  # Search conditions
                ]
            }
        )

        notes = []
        for note in cursor:
            notes.append(Note(**note))
        return notes

    except Exception as e:
        logger.error(f"Error in search_notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
