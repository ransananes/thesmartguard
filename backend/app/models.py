"""
SQLAlchemy models for TheSmartGuard backend.

Design notes:
- All date-times are stored as UTC and serialised as ISO-8601 strings.
- DB indexes are placed on every column that appears in a WHERE / ORDER BY
  clause so that history/stats queries stay fast as the table grows.
- `pytz` is no longer used here; timezone-aware UTC datetimes come from
  `datetime.timezone.utc` (stdlib, zero extra dependency).
"""
from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'user'

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(256))
    role: str = db.Column(db.String(20), default='user')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
        }


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

class Camera(db.Model):
    __tablename__ = 'camera'

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(100), nullable=False)
    location: str = db.Column(db.String(100))
    ip_address: str = db.Column(db.String(50), nullable=True)
    port: int = db.Column(db.Integer, nullable=True)
    stream_url: str = db.Column(db.String(500), nullable=False)
    status: str = db.Column(db.String(20), default='online')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'ip_address': self.ip_address,
            'port': self.port,
            'streamUrl': self.stream_url,
            'status': self.status,
        }


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class Detection(db.Model):
    __tablename__ = 'detection'

    id: int = db.Column(db.Integer, primary_key=True)
    camera_id: int = db.Column(
        db.Integer,
        db.ForeignKey('camera.id'),
        nullable=False,
        index=True,                   # ← speeds up camera-specific queries
    )
    label: str = db.Column(db.String(50), nullable=False, index=True)   # ← filter by label
    confidence: float = db.Column(db.Float, nullable=False)
    image_path: str = db.Column(db.String(255), nullable=True)
    timestamp: datetime.datetime = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,                   # ← ORDER BY timestamp DESC
    )

    camera = db.relationship('Camera', backref=db.backref('detections', lazy=True))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'label': self.label,
            'confidence': self.confidence,
            'image_path': f'/media/detections/{self.image_path}' if self.image_path else None,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# KnownFace
# ---------------------------------------------------------------------------

class KnownFace(db.Model):
    __tablename__ = 'known_face'

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(100), nullable=False)
    encoding = db.Column(db.PickleType, nullable=False)
    image_path: str = db.Column(db.String(255), nullable=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at: datetime.datetime = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'image_url': f'/media/faces/{self.image_path}' if self.image_path else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# NotificationSetting
# ---------------------------------------------------------------------------

class NotificationSetting(db.Model):
    __tablename__ = 'notification_setting'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    label: str = db.Column(db.String(50), nullable=False)
    enabled: bool = db.Column(db.Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            'label': self.label,
            'enabled': self.enabled,
        }
