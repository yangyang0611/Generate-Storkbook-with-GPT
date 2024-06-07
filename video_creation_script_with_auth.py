import time
import openai
from gtts import gTTS
from PIL import Image
import os
from dotenv import load_dotenv
import requests
from io import BytesIO
from moviepy.editor import *
from flask import Flask, request, send_file, redirect, url_for, render_template, flash, Response, jsonify, make_response, copy_current_request_context, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from googletrans import Translator
import threading
import json
from werkzeug.utils import secure_filename
import pyttsx3
import traceback
from functools import wraps

# Set the path to your ffmpeg binary
# os.environ["FFMPEG_BINARY"] = "C:/Program Files/ffmpeg/bin/ffmpeg.exe"

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SESSION_TYPE'] = 'filesystem'

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Set OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

progress = {'message': '', 'progress': 0}
cancel_flag = False

def update_progress(message, progress_value):
    global progress
    progress['message'] = message
    progress['progress'] = progress_value

db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    
class ImageFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('images', lazy=True))

class AudioFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('audios', lazy=True))

class VideoFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('videos', lazy=True))

# create database tables
with app.app_context():
    db.create_all()

def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
    return no_cache

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('generate'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            flash('Username already exists. Please choose a different username.', 'danger')
            return redirect(url_for('register'))
        
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/generate_video_progress')
def generate_video_progress():
    def progress_stream():
        global progress
        while progress['progress'] < 100:
            time.sleep(1)
            yield f"data: {json.dumps(progress)}\n\n"
        yield f"data: {json.dumps(progress)}\n\n"
    return Response(progress_stream(), content_type='text/event-stream')

@app.route('/cancel_generation', methods=['POST'])
@login_required
def cancel_generation():
    global cancel_flag
    cancel_flag = True
    return jsonify({'message': 'Video generation cancelled.'})

def generate_script_and_scene(prompt, script_file_path="generated_script.txt"):
    print("Generating script and scene descriptions...")
    update_progress("Generating script and scene descriptions...", 10)
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    script_and_scene = response['choices'][0]['message']['content'].strip()
    update_progress("Script and scene descriptions generated.", 20)
    print("Script and scene descriptions generated.")
    
    with open(script_file_path, "w", encoding="utf-8") as script_file:
        script_file.write(script_and_scene)
    
    return script_and_scene

def generate_image(prompt, retries=5):
    for i in range(retries):
        if cancel_flag:
            raise Exception("Generation cancelled")
        try:
            response = openai.Image.create(
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            print(f"OpenAI response: {response}")  # Debug print
            if 'data' not in response or not response['data']:
                raise Exception("No data in response")

            image_url = response['data'][0].get('url', None)
            if not image_url:
                raise Exception("No URL in data")

            image_response = requests.get(image_url)
            image = Image.open(BytesIO(image_response.content))
            time.sleep(5)
            print("Image generated.")
            return image
        except openai.error.APIError as e:
            print(f"Error generating image: {e}")
            if i < retries - 1:
                print("Retrying...")
                time.sleep(2)
            else:
                raise e
        except Exception as e:
            print(f"General error: {e}")
            traceback.print_exc()
            if i < retries - 1:
                print("Retrying...")
                time.sleep(2)
            else:
                raise e

def generate_images(scene_descriptions, image_folder):
    user_image_folder = os.path.join(image_folder, str(current_user.id))
    if not os.path.exists(user_image_folder):
        os.makedirs(user_image_folder)
        
    images = []
    total_scenes = len(scene_descriptions)
    for idx, description in enumerate(scene_descriptions):
        if cancel_flag:
            raise Exception("Generation cancelled")
        if description.strip():
            print(f"Generating image {idx + 1} for scene: {description}")
            update_progress(f"Generating image {idx + 1} of {total_scenes}...", 20 + int((idx + 1) / total_scenes * 40))
            try:
                image = generate_image(description)
                if image is None:
                    raise Exception("Generated image is None")
                image_path = os.path.join(user_image_folder, f'image_{idx + 1}.jpg')
                print(f"Saving image to: {image_path}")
                image.save(image_path, format='JPEG')
                
                 # Save image path to database
                db_image = ImageFile(file_path=image_path, user_id=current_user.id)
                db.session.add(db_image)
                db.session.commit()
                
                images.append(image_path)
            except Exception as e:
                print(f"Error generating or saving image: {e}")
                raise e
    update_progress("All images generated.", 60)
    print(f"All images generated. Total: {len(images)}")
    return images


def translate_and_generate_audio(script, audio_folder, file_name="output.mp3"):
    user_audio_folder = os.path.join(audio_folder, str(current_user.id))
    if not os.path.exists(user_audio_folder):
        os.makedirs(user_audio_folder)
    
    update_progress("Translating script to Chinese and generating audio...", 60)
    
    # Use deep-translator for translation
    translator = GoogleTranslator(source='en', target='zh-cn')
    translated_script = translator.translate(script)
    
    audio_path = os.path.join(user_audio_folder, file_name)

    tts = gTTS(text=translated_script, lang='zh-cn')
    tts.save(audio_path)
    
    # Save combined audio path to database
    db_audio = AudioFile(file_path=audio_path, user_id=current_user.id)
    db.session.add(db_audio)
    db.session.commit()
    
    update_progress("Chinese audio generated.", 70)
    print("Translating script to Chinese and generating audio...")
    return audio_path


# Calculate lengths of scene descriptions
def calculate_scene_lengths(scene_descriptions):
    lengths = [len(desc) for desc in scene_descriptions]
    total_length = sum(lengths)
    return lengths, total_length

def split_audio(audio_file, scene_descriptions, audio_folder):
    user_audio_folder = os.path.join(audio_folder, str(current_user.id))
    if not os.path.exists(user_audio_folder):
        os.makedirs(user_audio_folder)

    print("Splitting audio proportionate to scene lengths...")
    update_progress("Splitting audio...", 80)
    audio_clip = AudioFileClip(audio_file)
    total_duration = audio_clip.duration
    
    lengths, total_length = calculate_scene_lengths(scene_descriptions)
    
    audio_segments = []
    start_time = 0
    for segment_id, length in enumerate(lengths):
        if cancel_flag:
            raise Exception("Generation cancelled")
        duration = (length / total_length) * total_duration
        end_time = start_time + duration
        try:
            segment = audio_clip.subclip(start_time, end_time)
            segment_path = os.path.join(user_audio_folder, f'segment_{segment_id}.mp3')
            segment.write_audiofile(segment_path)
            
            # Save audio segment path to database
            db_audio_segment = AudioFile(file_path=segment_path, user_id=current_user.id)
            db.session.add(db_audio_segment)
            db.session.commit()
            
            audio_segments.append(segment_path)
            start_time = end_time
        except Exception as e:
            print(f"Error splitting audio: {e}")
            traceback.print_exc()
            raise e
    update_progress("Audio splitting completed.", 90)
    print("Audio splitting completed.")
    return audio_segments

def create_video(images, audio_segments, video_folder, output_file="story.mp4"):
    user_video_folder = os.path.join(video_folder, str(current_user.id))
    if not os.path.exists(user_video_folder):
        os.makedirs(user_video_folder)

    update_progress("Creating video...", 90)
    print("Creating video...")
    
    clips = []
    crossfade_duration = 0.5  # Crossfade duration in seconds
    for image_path, audio_segment in zip(images, audio_segments):
        if cancel_flag:
            raise Exception("Generation cancelled")
        img_clip = ImageClip(image_path).set_duration(AudioFileClip(audio_segment).duration)
        audio_clip = AudioFileClip(audio_segment)
        img_clip = img_clip.set_audio(audio_clip)
        clips.append(img_clip.crossfadein(crossfade_duration))
        
    video = concatenate_videoclips(clips, method="compose", padding=-crossfade_duration)
    video_path = os.path.join(user_video_folder, output_file)
    video.write_videofile(video_path, fps=24)
    
    # Save video path to database
    db_video = VideoFile(file_path=video_path, user_id=current_user.id)
    db.session.add(db_video)
    db.session.commit()
    
    update_progress("Video created.", 100)
    print("Video created.")
    return video_path

@app.route('/generate_video', methods=['POST'])
@login_required
@nocache
def generate_video():
    data = request.json
    prompt = data['prompt']
    
    global progress, cancel_flag
    progress = {'message': 'Starting video generation...', 'progress': 0}
    cancel_flag = False
    
    print(f"Current user: {current_user}")
    
    @copy_current_request_context
    def process():
        try:
            # Ensure the user is authenticated
            if not current_user or current_user.is_anonymous:
                raise Exception("User not authenticated")
            
            # Generate script and scene description
            script_file_path = "generated_script.txt"
            script_and_scene = generate_script_and_scene(prompt, script_file_path)
            scene_descriptions = script_and_scene.split('\n')
            scene_descriptions = [desc for desc in scene_descriptions if desc.strip()]
            
            # Generate images
            image_folder = 'images'
            images = generate_images(scene_descriptions, image_folder)
            
            # Translate to Chinese and generate Chinese audio
            audio_folder = 'audio'
            audio_file = translate_and_generate_audio(script_and_scene, audio_folder)
            
            # Split audio into segments
            audio_segments = split_audio(audio_file, scene_descriptions, audio_folder)
            
            # Create video
            video_folder = 'video'
            output_video_path = create_video(images, audio_segments, video_folder)
            
            # Save video details to database
            video = VideoFile(file_path=output_video_path, user_id=current_user.id)
            db.session.add(video)
            db.session.commit()
            
            update_progress("Video generation complete.", 100)
            return output_video_path
        except Exception as e:
            update_progress(f"Error: {str(e)}", 100)
            print(str(e))
            traceback.print_exc()
    
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({'message': 'Video generation started.'})



# 將影片回傳到前端，提供下載
@app.route('/get_video/<filename>')
@login_required
def get_video(filename):
    return send_file(f'video/{filename}', as_attachment=True)

from flask import send_from_directory

@app.route('/images/<int:user_id>/<path:filename>')
@login_required
def get_user_image(user_id, filename):
    if user_id != current_user.id:
        return "Unauthorized", 403
    user_image_folder = os.path.join('images', str(user_id))
    return send_from_directory(user_image_folder, filename)

@app.route('/my_images')
@login_required
@nocache
def my_images():
    user_images = ImageFile.query.filter_by(user_id=current_user.id).all()
    return render_template('my_images.html', images=user_images)


@app.route('/my_videos')
@login_required
@nocache
def my_videos():
    user_videos = VideoFile.query.filter_by(user_id=current_user.id).all()
    return render_template('videos.html', videos=user_videos)

@app.route('/generate')
@login_required
@nocache
def generate():
    return render_template('generate.html')

@app.route('/generate2')
def generate2():
    return render_template('generate2.html')

@app.route('/textbox')
def textbox():
    return render_template('textbox.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
