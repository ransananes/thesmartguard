import os
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Detection, Camera, User, NotificationSetting
from app.extensions import db
from app.config import Config

monitor_bp = Blueprint('monitor', __name__, url_prefix='/api')


def _get_enabled_labels(user: User, fallback: list[str]) -> list[str]:
    """Return the list of enabled detection labels for *user*."""
    settings = NotificationSetting.query.filter_by(user_id=user.id, enabled=True).all()
    if not settings:
        return fallback
    return [s.label for s in settings]


@monitor_bp.route('/detections', methods=['POST'])
@jwt_required()
def add_detection():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Request body must be JSON'}), 400

    camera_id = data.get('camera_id')
    label = data.get('label')
    confidence = data.get('confidence')

    if not camera_id or not label or confidence is None:
        return jsonify({'success': False, 'message': 'camera_id, label, and confidence are required'}), 400

    new_detection = Detection(camera_id=camera_id, label=label, confidence=confidence)
    try:
        db.session.add(new_detection)
        db.session.commit()
        return jsonify({'success': True, 'detection': new_detection.to_dict()}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500


@monitor_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    total_detections = Detection.query.count()
    active_cameras = Camera.query.filter_by(status='online').count()

    alerts_count = 0
    if user:
        enabled_labels = _get_enabled_labels(user, ['person', 'Face: Unknown'])
        alerts_count = Detection.query.filter(Detection.label.in_(enabled_labels)).count()

    return jsonify({
        'success': True,
        'stats': {
            'active_cameras': active_cameras,
            'detections': total_detections,
            'alerts': alerts_count,
            'security_level': 'High',
        },
    })


@monitor_bp.route('/detections/history', methods=['GET'])
@jwt_required()
def get_history():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    enabled_labels = [
        l for l in _get_enabled_labels(
            user, ['person', 'Face: Unknown', 'car']
        )
        if l != 'Face: Known'
    ]

    pagination = (
        Detection.query
        .filter(Detection.label.in_(enabled_labels))
        .order_by(Detection.timestamp.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        'success': True,
        'history': [d.to_dict() for d in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
    })


@monitor_bp.route('/detections/clear', methods=['POST'])
@jwt_required()
def clear_detections():
    """Delete all detection records and their on-disk images. Known faces are untouched."""
    try:
        detections = Detection.query.all()
        deleted_files = 0
        for det in detections:
            if det.image_path:
                fpath = os.path.join(Config.STORAGE_ROOT, 'detections', det.image_path)
                try:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                        deleted_files += 1
                except OSError:
                    pass

        count = Detection.query.delete()
        db.session.commit()

        # Reset in-memory alert cooldown so fresh detections fire immediately
        vp = getattr(current_app, 'video_processor', None)
        if vp:
            vp._last_detection_alert.clear()
            vp.track_names.clear()
            vp._recent_alerted_encodings.clear()

        return jsonify({'success': True, 'deleted_records': count, 'deleted_files': deleted_files})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500
