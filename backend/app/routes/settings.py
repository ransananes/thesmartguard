from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import NotificationSetting, User
from app.extensions import db

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

@settings_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notification_settings():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()

    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    settings = NotificationSetting.query.filter_by(user_id=user.id).all()
    
    defaults = ['person', 'car', 'Face: Unknown', 'Face: Known', 'cat', 'dog', 'bird', 'horse']
    
    if not settings:
        settings_list = []
        for label in defaults:
            settings_list.append({'label': label, 'enabled': True})
        return jsonify({'success': True, 'settings': settings_list})

    existing_labels = {s.label for s in settings}
    merged_settings = [s.to_dict() for s in settings]
    
    missing_defaults = [d for d in defaults if d not in existing_labels]
    
    for label in missing_defaults:
        merged_settings.append({'label': label, 'enabled': True})

    return jsonify({'success': True, 'settings': merged_settings})

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
        
        if hasattr(current_app, 'video_processor') and current_app.video_processor:
            current_app.video_processor.update_settings(new_settings)

        return jsonify({'success': True, 'settings': [s.to_dict() for s in new_settings]})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@settings_bp.route('/reset-system', methods=['POST'])
@jwt_required()
def reset_system():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    if not user:
         return jsonify({'success': False, 'message': 'User not found'}), 404

    try:
        if hasattr(current_app, 'video_processor') and current_app.video_processor:
            current_app.video_processor.clear_all_data()
            return jsonify({'success': True, 'message': 'System data cleared and reset.'})
        else:
            return jsonify({'success': False, 'message': 'Video processor not active.'}), 503
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
