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
db = client.memories
notes_collection = db.noteDiary

# S3 Configuration - Use environment variables for security
S3_BUCKET = os.getenv("MY_AWS_S3_BUCKET_NAME", "your-bucket-name")
S3_REGION = os.getenv("MY_AWS_S3_REGION", "us-east-1")
MY_AWS_ACCESS_KEY = os.getenv("MY_AWS_ACCESS_KEY", "your-access-key")
MY_AWS_SECRET_KEY = os.getenv("MY_AWS_SECRET_KEY", "your-secret-key")

# Initialize S3 client with retry configuration
session = boto3.Session(
    region_name=S3_REGION,
    aws_access_key_id=MY_AWS_ACCESS_KEY,
    aws_secret_access_key=MY_AWS_SECRET_KEY,
)

# Create a config with retries
boto_config = boto3.session.Config(
    signature_version="v4", retries={"max_attempts": 3, "mode": "standard"}
)

# Initialize S3 client
s3_client = session.client("s3", config=boto_config)


async def save_file_to_s3(file: UploadFile, file_type: str) -> dict:
    """Upload file to S3"""
    try:
        logger.info(f"Starting to upload {file_type}: {file.filename}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        object_key = f"{filename}"

        # Read file content
        content = await file.read()
        logger.info(f"Read {len(content)} bytes from {file_type} file")

        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=object_key,
            Body=content,
            ContentType=file.content_type,
        )
        logger.info(f"Successfully uploaded {file_type} to S3: {object_key}")

        # Create the URL
        url = f"https://d2ljorwegx33x7.cloudfront.net/{object_key}"

        return {
            "url": url,
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
                    status_code=500, detail="Access denied to S3 bucket"
                )
        raise HTTPException(
            status_code=500, detail=f"Failed to upload {file_type}: {str(e)}"
        )


async def get_file_from_s3(file_url: str):
    """Get file from S3"""
    try:
        from urllib.parse import unquote, unquote_plus
        
        # Handle both CloudFront and S3 URLs
        if "cloudfront.net" in file_url:
            # CloudFront URL format: https://d2ljorwegx33x7.cloudfront.net/filename
            key = file_url.split("cloudfront.net/")[1]
        elif ".amazonaws.com/" in file_url:
            # S3 URL format: https://bucket.s3.region.amazonaws.com/filename
            key = file_url.split(".amazonaws.com/")[1]
        else:
            # Assume it's just the key/filename
            key = file_url
        
        # Try different variations of the key
        keys_to_try = [
            key,  # Original key
            unquote_plus(key),  # + to space
            unquote(key),  # Regular decode
            key.replace('+', ' '),  # Manual + to space replacement
        ]
        
        # Remove duplicates while preserving order
        unique_keys = []
        for k in keys_to_try:
            if k not in unique_keys:
                unique_keys.append(k)
        
        # Try each key until one works
        for attempt_key in unique_keys:
            try:
                response = s3_client.get_object(Bucket=S3_BUCKET, Key=attempt_key)
                
                # Read data
                data = response["Body"].read()
                content_type = response.get("ContentType", "application/octet-stream")
                
                return {"data": data, "content_type": content_type}
                
            except ClientError as e:
                if e.response["Error"].get("Code") == "NoSuchKey":
                    continue
                else:
                    # Different error, re-raise
                    raise
        
        # If we get here, none of the keys worked
        raise HTTPException(status_code=404, detail=f"File not found with any key variation")

    except IndexError as e:
        logger.error(f"Error parsing URL '{file_url}': {e}")
        raise HTTPException(status_code=400, detail=f"Invalid file URL format: {file_url}")
    except ClientError as e:
        logger.error(f"Error getting from S3: {e}")
        if hasattr(e, "response") and "Error" in e.response:
            error_code = e.response["Error"].get("Code", "")
            if error_code == "NoSuchKey":
                raise HTTPException(status_code=404, detail=f"File not found in S3")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve file: {str(e)}"
        )


async def delete_file_from_s3(file_url: str):
    """Delete file from S3 given its URL"""
    try:
        from urllib.parse import unquote
        
        logger.info(f"Deleting file with URL: {file_url}")
        
        # Handle both CloudFront and S3 URLs
        if "cloudfront.net" in file_url:
            # CloudFront URL format: https://d2ljorwegx33x7.cloudfront.net/filename
            key = file_url.split("cloudfront.net/")[1]
        elif ".amazonaws.com/" in file_url:
            # S3 URL format: https://bucket.s3.region.amazonaws.com/filename
            key = file_url.split(".amazonaws.com/")[1]
        else:
            # Assume it's just the key/filename
            key = file_url
        
        # URL decode the key to handle spaces and special characters
        decoded_key = unquote(key)
        logger.info(f"Deleting file from S3: {decoded_key}")

        s3_client.delete_object(Bucket=S3_BUCKET, Key=decoded_key)
        logger.info("File successfully deleted")
    except IndexError as e:
        logger.error(f"Error parsing URL for deletion '{file_url}': {e}")
        raise HTTPException(status_code=400, detail=f"Invalid file URL format: {file_url}")
    except ClientError as e:
        logger.error(f"Error deleting from S3: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


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
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
):
    image_meta = None
    audio_meta = None
    video_meta = None

    # Process image if provided
    if image:
        image_meta = await save_file_to_s3(image, "images")

    # Process audio if provided
    if audio:
        audio_meta = await save_file_to_s3(audio, "audio")

    # Process video if provided
    if video:
        video_meta = await save_file_to_s3(video, "videos")

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

    # Add audio data if provided
    if audio_meta:
        note["audio_url"] = audio_meta["url"]

    # Add video data if provided
    if video_meta:
        note["video_url"] = video_meta["url"]

    result = notes_collection.insert_one(note)
    if result.inserted_id:
        return {
            "message": "Note created successfully",
            "id": note_id,
            "mongo_id": str(result.inserted_id),
            "image_url": image_meta["url"] if image_meta else None,
            "audio_url": audio_meta["url"] if audio_meta else None,
            "video_url": video_meta["url"] if video_meta else None,
        }
    raise HTTPException(status_code=400, detail="Failed to create note")


@notes_router.get("/debug/s3-files")
async def debug_s3_files(current_user: Annotated[User, Depends(get_current_active_user)]):
    """Debug endpoint to list files in S3 bucket"""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, MaxKeys=50)
        
        if 'Contents' not in response:
            return {"message": "No files found in S3 bucket", "bucket": S3_BUCKET}
        
        files = []
        for obj in response['Contents']:
            files.append({
                "key": obj['Key'],
                "size": obj['Size'],
                "last_modified": obj['LastModified'].isoformat(),
                "cloudfront_url": f"https://d2ljorwegx33x7.cloudfront.net/{obj['Key']}"
            })
        
        return {
            "bucket": S3_BUCKET,
            "total_files": len(files),
            "files": files
        }
    except Exception as e:
        logger.error(f"Error listing S3 files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@notes_router.get("/debug/notes")
async def debug_notes(current_user: Annotated[User, Depends(get_current_active_user)]):
    """Debug endpoint to see note structure and URLs"""
    try:
        notes = []
        cursor = notes_collection.find({"user_id": current_user.username})
        for note in cursor:
            debug_note = {
                "id": note.get("id"),
                "title": note.get("title"),
                "has_image": bool(note.get("image_url")),
                "image_url": note.get("image_url"),
                "has_audio": bool(note.get("audio_url")),
                "audio_url": note.get("audio_url"),
                "has_video": bool(note.get("video_url")),
                "video_url": note.get("video_url"),
            }
            notes.append(debug_note)
        return {"user": current_user.username, "notes": notes}
    except Exception as e:
        logger.error(f"Error in debug_notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        note = notes_collection.find_one({"id": note_id, "user_id": current_user.username})
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        if not note.get("image_url"):
            raise HTTPException(status_code=404, detail="Note has no image")

        logger.info(f"Attempting to get image for note {note_id} with URL: {note.get('image_url')}")
        
        # Get image
        image_data = await get_file_from_s3(note["image_url"])

        from fastapi.responses import Response

        return Response(
            content=image_data["data"], media_type=image_data["content_type"]
        )
    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper status codes)
        raise
    except Exception as e:
        logger.error(f"Error in get_note_image for note {note_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve image: {str(e)}"
        )


@notes_router.get("/audio/{note_id}")
async def get_note_audio(
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    note = notes_collection.find_one({"id": note_id, "user_id": current_user.username})
    if not note or not note.get("audio_url"):
        raise HTTPException(status_code=404, detail="Note or audio not found")

    try:
        # Get audio
        audio_data = await get_file_from_s3(note["audio_url"])

        from fastapi.responses import Response

        return Response(
            content=audio_data["data"], media_type=audio_data["content_type"]
        )
    except Exception as e:
        logger.error(f"Error in get_note_audio: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve audio: {str(e)}"
        )


@notes_router.get("/video/{note_id}")
async def get_note_video(
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    note = notes_collection.find_one({"id": note_id, "user_id": current_user.username})
    if not note or not note.get("video_url"):
        raise HTTPException(status_code=404, detail="Note or video not found")

    try:
        # Get video
        video_data = await get_file_from_s3(note["video_url"])

        from fastapi.responses import Response

        return Response(
            content=video_data["data"], media_type=video_data["content_type"]
        )
    except Exception as e:
        logger.error(f"Error in get_note_video: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve video: {str(e)}"
        )


@notes_router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        # Find note first to get file URLs if they exist
        note = notes_collection.find_one(
            {"id": note_id, "user_id": current_user.username}
        )

        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        # Delete image from S3 if exists
        if note.get("image_url"):
            await delete_file_from_s3(note["image_url"])

        # Delete audio from S3 if exists
        if note.get("audio_url"):
            await delete_file_from_s3(note["audio_url"])

        # Delete video from S3 if exists
        if note.get("video_url"):
            await delete_file_from_s3(note["video_url"])

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
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
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
                await delete_file_from_s3(existing_note["image_url"])

            # Upload new image
            image_meta = await save_file_to_s3(image, "images")

        # Process audio if provided
        audio_meta = None
        if audio:
            # Delete old audio if it exists
            if existing_note.get("audio_url"):
                await delete_file_from_s3(existing_note["audio_url"])

            # Upload new audio
            audio_meta = await save_file_to_s3(audio, "audio")

        # Process video if provided
        video_meta = None
        if video:
            # Delete old video if it exists
            if existing_note.get("video_url"):
                await delete_file_from_s3(existing_note["video_url"])

            # Upload new video
            video_meta = await save_file_to_s3(video, "videos")

        # Prepare update data
        update_data = {
            "title": title,
            "description": description,
            "date": date,
        }

        # Add image data if new image provided
        if image_meta:
            update_data["image_url"] = image_meta["url"]

        # Add audio data if new audio provided
        if audio_meta:
            update_data["audio_url"] = audio_meta["url"]

        # Add video data if new video provided
        if video_meta:
            update_data["video_url"] = video_meta["url"]

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
