from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import NotificationSetting, User
from app.extensions import db

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

_DEFAULT_LABELS = ['person', 'car', 'Face: Unknown', 'Face: Known', 'cat', 'dog', 'bird', 'horse']


def _get_current_user() -> User | None:
    return User.query.filter_by(username=get_jwt_identity()).first()


@settings_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notification_settings():
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    settings = NotificationSetting.query.filter_by(user_id=user.id).all()

    if not settings:
        return jsonify({
            'success': True,
            'settings': [{'label': lbl, 'enabled': True} for lbl in _DEFAULT_LABELS],
        })

    existing_labels = {s.label for s in settings}
    merged = [s.to_dict() for s in settings]

    # Surface any defaults not yet persisted for this user
    for lbl in _DEFAULT_LABELS:
        if lbl not in existing_labels:
            merged.append({'label': lbl, 'enabled': True})

    return jsonify({'success': True, 'settings': merged})


@settings_bp.route('/notifications', methods=['POST'])
@jwt_required()
def update_notification_settings():
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify({'success': False, 'message': 'Expected a JSON array of settings'}), 400

    try:
        NotificationSetting.query.filter_by(user_id=user.id).delete()
        new_settings = []
        for item in data:
            label = item.get('label', '').strip()
            enabled = bool(item.get('enabled', False))
            if not label:
                continue
            setting = NotificationSetting(user_id=user.id, label=label, enabled=enabled)
            db.session.add(setting)
            new_settings.append(setting)

        db.session.commit()

        vp = getattr(current_app, 'video_processor', None)
        if vp:
            vp.update_settings(new_settings)

        return jsonify({'success': True, 'settings': [s.to_dict() for s in new_settings]})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500


@settings_bp.route('/reset-system', methods=['POST'])
@jwt_required()
def reset_system():
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    vp = getattr(current_app, 'video_processor', None)
    if not vp:
        return jsonify({'success': False, 'message': 'Video processor not active'}), 503

    try:
        vp.clear_all_data()
        return jsonify({'success': True, 'message': 'System data cleared and reset.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500
