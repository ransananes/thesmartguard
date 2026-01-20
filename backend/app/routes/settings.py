from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import NotificationSetting, User
from ..extensions import db

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

@settings_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notification_settings():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()

    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    settings = NotificationSetting.query.filter_by(user_id=user.id).all()
    
    # Default settings if none exist
    if not settings:
        defaults = ['person', 'car', 'Face: Unknown', 'Face: Known']
        settings_list = []
        for label in defaults:
            settings_list.append({'label': label, 'enabled': True})
        return jsonify({'success': True, 'settings': settings_list})

    return jsonify({'success': True, 'settings': [s.to_dict() for s in settings]})

@settings_bp.route('/notifications', methods=['POST'])
@jwt_required()
def update_notification_settings():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    if not user:
         return jsonify({'success': False, 'message': 'User not found'}), 404

    data = request.json
    if not isinstance(data, list):
        return jsonify({'success': False, 'message': 'Invalid data format. Expected list of settings.'}), 400

    try:
        # Clear existing (or update)
        # Simple strategy: Delete all for user and recreate (fine for small # of settings)
        NotificationSetting.query.filter_by(user_id=user.id).delete()
        
        new_settings = []
        for item in data:
            setting = NotificationSetting(
                user_id=user.id,
                label=item['label'],
                enabled=item['enabled']
            )
            db.session.add(setting)
            new_settings.append(setting)
        
        db.session.commit()
        return jsonify({'success': True, 'settings': [s.to_dict() for s in new_settings]})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
