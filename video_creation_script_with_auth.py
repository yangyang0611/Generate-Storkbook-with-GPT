import time
import openai
from gtts import gTTS
from PIL import Image
import os
from dotenv import load_dotenv
import requests
from io import BytesIO
from moviepy.editor import *
from flask import Flask, request, send_file, redirect, url_for, render_template, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from googletrans import Translator
import threading
import json
from werkzeug.utils import secure_filename
import pyttsx3

# Set the path to your ffmpeg binary
# os.environ["FFMPEG_BINARY"] = "C:/Program Files/ffmpeg/bin/ffmpeg.exe"

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
# login_manager.login_view = 'login'

# Set OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

progress = {'message': '', 'progress': 0}
cancel_flag = False

def update_progress(message, progress_value):
    global progress
    progress['message'] = message
    progress['progress'] = progress_value

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('videos', lazy=True))

with app.app_context():
    db.create_all()

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
            image_url = response['data'][0]['url']
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

def generate_images(scene_descriptions, image_folder):
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
    images = []
    total_scenes = len(scene_descriptions)
    for idx, description in enumerate(scene_descriptions):
        if cancel_flag:
            raise Exception("Generation cancelled")
        if description.strip():
            print(f"Generating image {idx + 1} for scene: {description}")
            update_progress(f"Generating image {idx + 1} of {total_scenes}...", 20 + int((idx + 1) / total_scenes * 40))
            image = generate_image(description)
            image_path = os.path.join(image_folder, f'image_{idx + 1}.jpg')
            image.save(image_path, format='JPEG')
            images.append(image_path)
    update_progress("All images generated.", 60)
    print(f"All images generated. Total: {len(images)}")
    return images


def translate_and_generate_audio(script, audio_folder, file_name="output.mp3"):
    update_progress("Translating script to Chinese and generating audio...", 60)
    translator = Translator()
    translated = translator.translate(script, src='en', dest='zh-cn')
    translated_script = translated.text

    if not os.path.exists(audio_folder):
        os.makedirs(audio_folder)

    audio_path = os.path.join(audio_folder, file_name)

    tts = gTTS(text=translated_script, lang='zh-cn')
    tts.save(audio_path)
    update_progress("Chinese audio generated.", 70)
    print("Translating script to Chinese and generating audio...")
    return audio_path

# Calculate lengths of scene descriptions
def calculate_scene_lengths(scene_descriptions):
    lengths = [len(desc) for desc in scene_descriptions]
    total_length = sum(lengths)
    return lengths, total_length

def split_audio(audio_file, scene_descriptions, audio_folder):
    print("Splitting audio proportionate to scene lengths...")
    update_progress("Splitting audio...", 80)
    audio_clip = AudioFileClip(audio_file)
    total_duration = audio_clip.duration
    
    lengths, total_length = calculate_scene_lengths(scene_descriptions)
    
    audio_segments = []
    start_time = 0
    for length in lengths:
        if cancel_flag:
            raise Exception("Generation cancelled")
        duration = (length / total_length) * total_duration
        end_time = start_time + duration
        segment = audio_clip.subclip(start_time, end_time)
        segment_path = os.path.join(audio_folder, f'segment_{len(audio_segments)}.mp3')
        segment.write_audiofile(segment_path)
        audio_segments.append(segment_path)
        start_time = end_time
    update_progress("Audio splitting completed.", 90)
    print("Audio splitting completed.")
    return audio_segments

def create_video(images, audio_segments, video_folder, output_file="story.mp4"):
    update_progress("Creating video...", 90)
    print("Creating video...")
    
    if not os.path.exists(video_folder):
        os.makedirs(video_folder)
        
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
    video_path = os.path.join(video_folder, output_file)
    video.write_videofile(video_path, fps=24)
    update_progress("Video created.", 100)
    print("Video created.")
    return video_path

@app.route('/generate_video', methods=['POST'])
@login_required
def generate_video():
    data = request.json
    prompt = data['prompt']
    
    global progress, cancel_flag
    progress = {'message': 'Starting video generation...', 'progress': 0}
    cancel_flag = False
    
    print(f"Current user: {current_user}")
    
    def process():
        try:
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
            video = Video(file_path=output_video_path, user_id=current_user.id)
            db.session.add(video)
            db.session.commit()
            
            update_progress("Video generation complete.", 100)
            return output_video_path
        except Exception as e:
            update_progress(f"Error: {str(e)}", 100)
            print(str(e))
    
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({'message': 'Video generation started.'})



# 將影片回傳到前端，提供下載
@app.route('/get_video/<filename>')
@login_required
def get_video(filename):
    return send_file(f'video/{filename}', as_attachment=True)

# 將影片呈現在前端網頁上
@app.route('/video')
@login_required
def video():
    user_videos = Video.query.filter_by(user_id=current_user.id).all()
    return render_template('video.html', videos=user_videos)



@app.route('/generate')
@login_required
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

@app.route('/get_generated_images')
def get_generated_images():
    images = [img for img in os.listdir('images') if img.endswith(('png', 'jpg', 'jpeg'))]
    return jsonify({'images': images})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
