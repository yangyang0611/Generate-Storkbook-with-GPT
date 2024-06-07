import os
from dotenv import load_dotenv
from video_creation_script_with_auth import app, db, User, ImageFile, VideoFile, AudioFile  # Ensure to import your app, db, and User model

load_dotenv()

def show_all_content():
    with app.app_context():
        users = User.query.all()
        for user in users:
            print(f"User ID: {user.id}, Username: {user.username}")
            
        latest_images = {}
        latest_audios = {}
        latest_videos = {}
        
        images = ImageFile.query.all()
        for image in images:
            latest_images[image.file_path] = image
        
        audios = AudioFile.query.all()
        for audio in audios:
            latest_audios[audio.file_path] = audio
        
        videos = VideoFile.query.all()
        for video in videos:
            latest_videos[video.file_path] = video
            
        for image_path, image in latest_images.items():
            print(f"Image ID: {image.id}, FilePath: {image.file_path}, User_id: {image.user_id}")
        
        for audio_path, audio in latest_audios.items():
            print(f"Audio ID: {audio.id}, FilePath: {audio.file_path}, User_id: {audio.user_id}")
        
        for video_path, video in latest_videos.items():
            print(f"Video ID: {video.id}, FilePath: {video.file_path}, User_id: {video.user_id}")

def show_specific_user(username_to_check):
    with app.app_context():
        user = User.query.filter_by(username=username_to_check).first()
        if user:
            print(f"User ID: {user.id}, Username: {user.username}")

            latest_images = {}
            latest_audios = {}
            latest_videos = {}
            
            images = ImageFile.query.filter_by(user_id=user.id).all()
            for image in images:
                latest_images[image.file_path] = image
            
            audios = AudioFile.query.filter_by(user_id=user.id).all()
            for audio in audios:
                latest_audios[audio.file_path] = audio
            
            videos = VideoFile.query.filter_by(user_id=user.id).all()
            for video in videos:
                latest_videos[video.file_path] = video
            
            for image_path, image in latest_images.items():
                print(f"Image ID: {image.id}, FilePath: {image.file_path}, User_id: {image.user_id}")
            
            for audio_path, audio in latest_audios.items():
                print(f"Audio ID: {audio.id}, FilePath: {audio.file_path}, User_id: {audio.user_id}")
            
            for video_path, video in latest_videos.items():
                print(f"Video ID: {video.id}, FilePath: {video.file_path}, User_id: {video.user_id}")
        else:
            print(f"No user found with username: {username_to_check}")
            
if __name__ == "__main__":
    # Call the function to show all content
    # show_all_content()

    # Call the function to show specific user content
    username_to_check = "ting"  # Change this to the username you want to check
    show_specific_user(username_to_check)
