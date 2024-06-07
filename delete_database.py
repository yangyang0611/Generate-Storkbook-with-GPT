import os
from dotenv import load_dotenv
from video_creation_script_with_auth import app, db, User, ImageFile, VideoFile, AudioFile  # Ensure to import your app, db, and User model

load_dotenv()

def delete_entry(file_path, user_id, file_type='video'):
    with app.app_context():
        if file_type == 'image':
            entry = ImageFile.query.filter_by(file_path=file_path, user_id=user_id).first()
        elif file_type == 'audio':
            entry = AudioFile.query.filter_by(file_path=file_path, user_id=user_id).first()
        elif file_type == 'video':
            entry = VideoFile.query.filter_by(file_path=file_path, user_id=user_id).first()
        else:
            print(f"Unsupported file type: {file_type}")
            return

        if entry:
            # Delete the file from the file system
            if os.path.exists(entry.file_path):
                os.remove(entry.file_path)
                print(f"Deleted file: {entry.file_path}")
            
            # Delete the entry from the database
            db.session.delete(entry)
            db.session.commit()
            print(f"Deleted entry from database: {entry.file_path}")
            
            # Verify deletion
            remaining_entry = VideoFile.query.filter_by(file_path=file_path, user_id=user_id).first()
            if remaining_entry:
                print(f"Failed to delete entry from database: {file_path}")
            else:
                print(f"Successfully deleted entry from database: {file_path}")
        else:
            print(f"No entry found for {file_type} with file path: {file_path} and user_id: {user_id}")

# Example usage:
delete_entry('video/story.mp4', 1, file_type='video')
