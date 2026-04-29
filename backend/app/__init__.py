"""
Application factory for TheSmartGuard backend.
"""
import logging
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from app.config import Config
from app.extensions import db, jwt


def _configure_logging(level: str) -> None:
    """Set up a consistent log format for the whole application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def get_video_processor(app: Flask):
    """
    Return the VideoProcessor attached to *app*.
    Raises RuntimeError if it has not been initialised yet.
    This is the single, canonical way for routes to access the processor.
    """
    vp = getattr(app, 'video_processor', None)
    if vp is None:
        raise RuntimeError('VideoProcessor is not initialised.')
    return vp


def create_app() -> Flask:
    _configure_logging(Config.LOG_LEVEL)

    if not Config._raw_secret:
        logging.getLogger(__name__).warning(
            'JWT_SECRET_KEY is not set in the environment — using insecure default. '
            'Set it in your .env file before deploying.'
        )

    app = Flask(__name__)

    # ── Config ────────────────────────────────────────────────────────
    app.config['JWT_SECRET_KEY']                = Config.JWT_SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI']       = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS

    # ── Extensions ────────────────────────────────────────────────────
    CORS(app, origins=Config.CORS_ORIGINS)
    db.init_app(app)
    jwt.init_app(app)

    # ── Routes ────────────────────────────────────────────────────────
    from app.routes import auth_bp, cameras_bp, video_bp, monitor_bp, faces_bp, robot_bp
    from app.routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(faces_bp)
    app.register_blueprint(robot_bp)
    app.register_blueprint(settings_bp)

    # ── Static / media routes ─────────────────────────────────────────
    @app.route('/')
    def index():
        return 'The Smart Guard Backend is Running!'

    @app.route('/media/<path:filename>')
    def media_files(filename):
        return send_from_directory(Config.STORAGE_ROOT, filename)

    # ── Robot controller ─────────────────────────────────────────────
    if Config.ROBOT_HOST:
        from app.robot_controller import robot_controller
        robot_controller.connect(Config.ROBOT_HOST, Config.ROBOT_PORT)

    # ── Database + VideoProcessor ─────────────────────────────────────
    # db.create_all() MUST precede VideoProcessor construction because
    # the VP queries the DB during __init__ (face loading, settings).
    with app.app_context():
        db.create_all()   # idempotent — only creates tables that don't exist
        from app.video_processor import VideoProcessor
        app.video_processor = VideoProcessor(app)

    return app
