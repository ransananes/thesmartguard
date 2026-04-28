from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Detection, Camera, User, NotificationSetting
from app.extensions import db

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

    enabled_labels = _get_enabled_labels(
        user, ['person', 'Face: Unknown', 'Face: Known', 'car']
    )

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
