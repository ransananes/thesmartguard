from flask import Flask
from flask_cors import CORS
from flask_cors import CORS
from .extensions import db, jwt
from .routes import auth_bp, cameras_bp, video_bp, monitor_bp, faces_bp
from .routes.settings import settings_bp
from .models import Camera
from .video_processor import VideoProcessor
import os

def create_app():
    app = Flask(__name__)
    CORS(app)

    # Database Config
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'smartguard.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['JWT_SECRET_KEY'] = 'super-secret-key-change-this-in-prod' # Change this!
    
    db.init_app(app)
    jwt.init_app(app)

    @app.route('/')
    def index():
        return "The Smart Guard Backend is Running!"
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(faces_bp)
    
    app.register_blueprint(settings_bp)
    
    # Initialize video processor and start existing cameras
    with app.app_context():
        try:
            # Check if we have cameras and start processing
            # We need to import models here to avoid circular imports if possible or just use db

            
            # Attaching to app instance so it persists
            app.video_processor = VideoProcessor(app)
            
            cameras = Camera.query.filter_by(status='online').all()
            if cameras:
                print(f"Found {len(cameras)} online cameras. Starting processors...")
                for cam in cameras:
                    # For this demo, we only support one active stream/processor efficiently
                    # but let's try to start the first one or all if threaded properly.
                    # VideoProcessor class as written supports ONE camera at a time (single self.camera_id).
                    # So let's just start the first online one.
                    print(f"Starting processor for camera: {cam.name}")
                    app.video_processor.start_processing(cam.id, cam.stream_url)
                    break # Only one for now
        except Exception as e:
            print(f"Error initializing video processor: {e}")

    return app
