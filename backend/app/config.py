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
    # Minimum person confidence required to trigger face detection pipeline
    PERSON_CONF_THRESHOLD: float = float(os.environ.get('PERSON_CONF_THRESHOLD', '0.55'))
    # Face-model confidence threshold
    FACE_CONF_THRESHOLD: float = float(os.environ.get('FACE_CONF_THRESHOLD', '0.65'))
    # Face recognition distance tolerance (lower = stricter)
    FACE_TOLERANCE: float = float(os.environ.get('FACE_TOLERANCE', '0.55'))
    # JPEG quality used when encoding frames for the live stream (1-100)
    STREAM_JPEG_QUALITY: int = int(os.environ.get('STREAM_JPEG_QUALITY', '70'))
    # Default FPS to use if the stream doesn't report one (or for files)
    DEFAULT_FPS: float = float(os.environ.get('DEFAULT_FPS', '30.0'))
    # Max frames to buffer in the capture→processing queue
    FRAME_QUEUE_SIZE: int = int(os.environ.get('FRAME_QUEUE_SIZE', '2'))
    # Max detections to buffer before writing to DB
    DETECTION_QUEUE_SIZE: int = int(os.environ.get('DETECTION_QUEUE_SIZE', '100'))
    # Worker threads for face encoding executor
    FACE_EXECUTOR_WORKERS: int = int(os.environ.get('FACE_EXECUTOR_WORKERS', '1'))
    # Run full YOLO tracking every N frames; raw frame is passed through on skipped frames
    YOLO_PROCESS_EVERY_N_FRAMES: int = int(os.environ.get('YOLO_PROCESS_EVERY_N_FRAMES', '2'))
    # Target FPS for the MJPEG video_feed stream sent to the browser
    STREAM_TARGET_FPS: int = int(os.environ.get('STREAM_TARGET_FPS', '25'))

    # ------------------------------------------------------------------ #
    # Robot (ESP32-CAM WiFi TCP)
    # ------------------------------------------------------------------ #
    # IP address printed by the ESP32 on boot — set in .env as ROBOT_HOST
    ROBOT_HOST: str = os.environ.get('ROBOT_HOST', '192.168.1.64')
    ROBOT_PORT: int = int(os.environ.get('ROBOT_PORT', '3000'))
    ROBOT_COMMAND_INTERVAL: float = float(
        os.environ.get('ROBOT_COMMAND_INTERVAL', '0.2')
    )
    # Port the ESP32-CAM camera HTTP server listens on (default 81)
    ROBOT_CAMERA_PORT: int = int(os.environ.get('ROBOT_CAMERA_PORT', '81'))
    # Seconds the robot will rotate scanning for a target after returning home
    INTERCEPT_SCAN_TIMEOUT: float = float(os.environ.get('INTERCEPT_SCAN_TIMEOUT', '30.0'))
    # Seconds the main camera must fail to identify a person before the robot engages
    ROBOT_ENGAGE_DELAY: float = float(os.environ.get('ROBOT_ENGAGE_DELAY', '2.5'))
    # Seconds a confirmed Unknown person must persist before a notification is sent
    UNKNOWN_NOTIFY_DELAY: float = float(os.environ.get('UNKNOWN_NOTIFY_DELAY', '5.0'))
    # Minimum move duration (ms) worth logging for dead-reckoning
    MOVE_LOG_MIN_MS: int = int(os.environ.get('MOVE_LOG_MIN_MS', '50'))
    # Duration (ms) of the 180° spin at the start of return-to-home
    # Calibrate on your robot: increase if it undershoots, decrease if it overshoots
    SPIN_180_MS: int = int(os.environ.get('SPIN_180_MS', '1600'))
    # Duration (ms) the robot steers to clear one obstacle during return
    OBSTACLE_AVOID_STEER_MS: int = int(os.environ.get('OBSTACLE_AVOID_STEER_MS', '400'))

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'INFO')
