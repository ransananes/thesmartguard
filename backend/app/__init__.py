from flask import Flask, send_from_directory
from flask_cors import CORS
import os
from app.extensions import db, jwt
from app.routes import auth_bp, cameras_bp, video_bp, monitor_bp, faces_bp
from app.routes.settings import settings_bp
from app.models import Camera
from app.video_processor import VideoProcessor

def create_app():
    app = Flask(__name__)
    CORS(app)

    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'smartguard.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['JWT_SECRET_KEY'] = 'super-secret-key-change-this-in-prod'
    
    db.init_app(app)
    jwt.init_app(app)

    @app.route('/')
    def index():
        return "The Smart Guard Backend is Running!"

    @app.route('/media/<path:filename>')
    def media_files(filename):
        storage_path = os.path.join(os.path.dirname(app.root_path), 'storage')
        return send_from_directory(storage_path, filename)
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(faces_bp)
    
    app.register_blueprint(settings_bp)
    
    
    with app.app_context():
        app.video_processor = VideoProcessor(app)


    return app

