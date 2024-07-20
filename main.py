from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from routes.users import users_root
from routes.login import login_root

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login_root)
app.include_router(users_root)
