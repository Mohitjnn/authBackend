from fastapi import APIRouter, Response

logout_root = APIRouter()


@logout_root.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/", domain=None)
    return {"message": "logout successful"}
