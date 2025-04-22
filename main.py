import os

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from routes.users import users_root
from routes.login import login_root
from routes.logout import logout_root
from routes.signup import signupRouter
from routes.notes import notes_router
import os

app = FastAPI()

ALLOWED_ORIGIN = os.getenv("ALLOWED_URL")
origins = [
    ALLOWED_ORIGIN,
    "http://192.168.29.147:3000"
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login_root)
app.include_router(users_root)
app.include_router(logout_root)
app.include_router(signupRouter)
app.include_router(notes_router)
