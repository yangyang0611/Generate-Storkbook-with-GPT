import os
from dotenv import load_dotenv
from video_creation_script_with_auth import app, db, User  # Ensure to import your app, db, and User model

load_dotenv()

with app.app_context():
    users = User.query.all()
    for user in users:
        print(f"User ID: {user.id}, Username: {user.username}")
