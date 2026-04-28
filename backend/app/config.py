"""
Centralized application configuration.
All tunable constants and secrets live here; sensitive values are read from
environment variables so they are never hard-coded.
"""
import os
from dotenv import load_dotenv

# Load .env from the backend root (parent of the app/ package)
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(_backend_dir, '.env'))


class Config:
    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #
    _raw_secret = os.environ.get('JWT_SECRET_KEY', '')
    JWT_SECRET_KEY: str = _raw_secret or 'CHANGE_ME_IN_DOT_ENV'

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    _basedir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(_basedir, 'smartguard.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #
    # Root of on-disk media storage (detections/, faces/ sub-folders)
    STORAGE_ROOT: str = os.environ.get(
        'STORAGE_ROOT',
        os.path.join(_backend_dir, 'storage')
    )

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    CORS_ORIGINS: str = os.environ.get('CORS_ORIGINS', '*')

    # ------------------------------------------------------------------ #
    # Video processing
    # ------------------------------------------------------------------ #
    # Seconds between repeated alerts for the same object/track
    ALERT_COOLDOWN: float = float(os.environ.get('ALERT_COOLDOWN', '5.0'))
    # Seconds an unknown face must remain unseen before re-identifying
    UNKNOWN_FACE_RECHECK_INTERVAL: float = float(
        os.environ.get('UNKNOWN_FACE_RECHECK_INTERVAL', '2.0')
    )
    # Seconds a track must be absent before being evicted from memory
    STALE_TRACK_TTL: float = float(os.environ.get('STALE_TRACK_TTL', '10.0'))
    # YOLO detection confidence threshold
    YOLO_CONF_THRESHOLD: float = float(os.environ.get('YOLO_CONF_THRESHOLD', '0.4'))
    # Face-model confidence threshold
    FACE_CONF_THRESHOLD: float = float(os.environ.get('FACE_CONF_THRESHOLD', '0.5'))
    # Face recognition distance tolerance (lower = stricter)
    FACE_TOLERANCE: float = float(os.environ.get('FACE_TOLERANCE', '0.55'))
    # JPEG quality used when encoding frames for the live stream (1-100)
    STREAM_JPEG_QUALITY: int = int(os.environ.get('STREAM_JPEG_QUALITY', '70'))
    # Max frames to buffer in the capture→processing queue
    FRAME_QUEUE_SIZE: int = int(os.environ.get('FRAME_QUEUE_SIZE', '2'))
    # Max detections to buffer before writing to DB
    DETECTION_QUEUE_SIZE: int = int(os.environ.get('DETECTION_QUEUE_SIZE', '100'))
    # Worker threads for face encoding executor
    FACE_EXECUTOR_WORKERS: int = int(os.environ.get('FACE_EXECUTOR_WORKERS', '2'))

    # ------------------------------------------------------------------ #
    # Robot
    # ------------------------------------------------------------------ #
    ROBOT_COMMAND_INTERVAL: float = float(
        os.environ.get('ROBOT_COMMAND_INTERVAL', '0.2')
    )

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'INFO')
