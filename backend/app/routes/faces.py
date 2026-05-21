"""
Faces route — manage known face encodings.

The YOLO face detection helper now delegates to VideoProcessor.detect_faces_in_image(),
eliminating the direct coupling to video_processor.face_model.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid

import cv2
import face_recognition
import numpy as np

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.config import Config
from app.models import KnownFace, User, Detection
from app.extensions import db

logger = logging.getLogger(__name__)

faces_bp = Blueprint('faces', __name__, url_prefix='/api')


def _get_current_user() -> User | None:
    username = get_jwt_identity()
    return User.query.filter_by(username=username).first()


def _detect_face_locations(image_path: str) -> list | None:
    """
    Return face locations (face_recognition format) for *image_path*.
    Tries the VideoProcessor's YOLO model first; falls back to HOG on failure.
    """
    vp = getattr(current_app, 'video_processor', None)
    if vp is not None:
        locs = vp.detect_faces_in_image(image_path)
        if locs:
            return locs
    return None

@faces_bp.route('/faces', methods=['GET'])
@jwt_required()
def get_faces():
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    faces = KnownFace.query.filter_by(user_id=user.id).all()
    return jsonify({'success': True, 'faces': [f.to_dict() for f in faces]})


@faces_bp.route('/faces', methods=['POST'])
@jwt_required()
def add_face():
    if 'image' not in request.files or 'name' not in request.form:
        return jsonify({'success': False, 'message': 'image file and name are required'}), 400

    file = request.files['image']
    name = request.form['name'].strip()
    if not name:
        return jsonify({'success': False, 'message': 'name must not be blank'}), 400

    user = _get_current_user()

    storage_root = Config.STORAGE_ROOT
    filename = f'{uuid.uuid4()}_{file.filename}'
    save_path = os.path.join(storage_root, 'faces', filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    file.save(save_path)

    try:
        img = face_recognition.load_image_file(save_path)
        face_locs = _detect_face_locations(save_path)

        if face_locs:
            encodings = face_recognition.face_encodings(img, face_locs)
        else:
            encodings = face_recognition.face_encodings(img)

        if not encodings:
            return jsonify({'success': False, 'message': 'No face found in image'}), 400

        encoding = encodings[0]
        logger.info(f'Encoded face "{name}" (sum={np.sum(np.abs(encoding)):.4f})')

        new_face = KnownFace(
            name=name,
            encoding=encoding,
            image_path=filename,
            user_id=user.id if user else None,
        )
        db.session.add(new_face)
        db.session.commit()

        vp = getattr(current_app, 'video_processor', None)
        if vp:
            vp.reload_faces()

        return jsonify({'success': True, 'face': new_face.to_dict()}), 201

    except Exception as exc:
        db.session.rollback()
        # Clean up saved file on any error
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        logger.error(f'add_face error: {exc}')
        return jsonify({'success': False, 'message': str(exc)}), 500


@faces_bp.route('/faces/from_detection', methods=['POST'])
@jwt_required()
def add_face_from_detection():
    data = request.get_json(silent=True)
    if not data or 'detection_id' not in data or 'name' not in data:
        return jsonify({'success': False, 'message': 'detection_id and name are required'}), 400

    detection_id = data['detection_id']
    name = data['name'].strip()
    if not name:
        return jsonify({'success': False, 'message': 'name must not be blank'}), 400

    user = _get_current_user()

    detection = db.session.get(Detection, detection_id)
    if not detection:
        return jsonify({'success': False, 'message': 'Detection not found'}), 404
    if not detection.image_path:
        return jsonify({'success': False, 'message': 'No image associated with this detection'}), 400

    storage_root = Config.STORAGE_ROOT
    source_path = os.path.join(storage_root, 'detections', detection.image_path)
    if not os.path.exists(source_path):
        return jsonify({'success': False, 'message': 'Source image file missing'}), 404

    dest_filename = f'{uuid.uuid4()}_{detection.image_path}'
    dest_path = os.path.join(storage_root, 'faces', dest_filename)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(source_path, dest_path)

    try:
        img = face_recognition.load_image_file(dest_path)
        h, w = img.shape[:2]

        # Try YOLO face model for precise location first
        face_locs = _detect_face_locations(dest_path)
        if face_locs:
            encodings = face_recognition.face_encodings(img, face_locs)
        else:
            # Try dlib HOG (needs context margin — may fail on tight crops)
            encodings = face_recognition.face_encodings(img)

        # Detection images are already tight face crops saved by the pipeline.
        # If both detectors fail (no context margin), encode treating the whole
        # image as the face region — we know it contains a face.
        if not encodings:
            encodings = face_recognition.face_encodings(img, [(0, w, h, 0)])

        if not encodings:
            os.remove(dest_path)
            return jsonify({'success': False, 'message': 'No face found in the detection image'}), 400

        encoding = encodings[0]
        logger.info(f'Encoded face from detection "{name}" (size={len(encoding)})')

        new_face = KnownFace(
            name=name,
            encoding=encoding,
            image_path=dest_filename,
            user_id=user.id if user else None,
        )
        db.session.add(new_face)
        db.session.commit()

        vp = getattr(current_app, 'video_processor', None)
        if vp:
            vp.reload_faces()

        # ── Clean up similar unknown detections ───────────────────────
        deleted_count = 0
        try:
            from PIL import Image
            import imagehash
            source_hash = imagehash.phash(Image.open(source_path))
            unknown_dets = Detection.query.filter_by(label='Face: Unknown').all()
            for d in unknown_dets:
                if not d.image_path:
                    continue
                d_path = os.path.join(storage_root, 'detections', d.image_path)
                if not os.path.exists(d_path):
                    db.session.delete(d)
                    continue
                try:
                    diff = source_hash - imagehash.phash(Image.open(d_path))
                    if diff < 15:
                        os.remove(d_path)
                        db.session.delete(d)
                        deleted_count += 1
                except Exception as cmp_err:
                    logger.error(f'Hash compare error for detection {d.id}: {cmp_err}')
            db.session.commit()
        except ImportError:
            logger.warning('imagehash not installed — skipping similarity cleanup')
        except Exception as hash_err:
            logger.error(f'Hash cleanup error: {hash_err}')

        logger.info(f'Cleaned up {deleted_count} similar detection(s) for "{name}"')
        return jsonify({'success': True, 'face': new_face.to_dict(), 'cleaned_up': deleted_count}), 201

    except Exception as exc:
        db.session.rollback()
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        logger.error(f'add_face_from_detection error: {exc}')
        return jsonify({'success': False, 'message': str(exc)}), 500


@faces_bp.route('/faces/<int:face_id>', methods=['DELETE'])
@jwt_required()
def delete_face(face_id):
    user = _get_current_user()
    face = db.session.get(KnownFace, face_id)
    if not face:
        return jsonify({'success': False, 'message': 'Face not found'}), 404

    if user and face.user_id != user.id and user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        if face.image_path:
            path = os.path.join(Config.STORAGE_ROOT, 'faces', face.image_path)
            if os.path.exists(path):
                os.remove(path)

        db.session.delete(face)
        db.session.commit()

        vp = getattr(current_app, 'video_processor', None)
        if vp:
            vp.reload_faces()

        return jsonify({'success': True, 'message': 'Face deleted'})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500
