from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://jnmohit29:Mohitjn123@cluster0.lfubgwo.mongodb.net/Cluster0?retryWrites=true&w=majority",
)
uri = MONGO_URI
# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi("1"))
db = client.memories
blogs_collection = db["noteDiary"]

# Send a ping to confirm a successful connection
try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
