from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Detection, Camera, User, NotificationSetting
from app.extensions import db

monitor_bp = Blueprint('monitor', __name__, url_prefix='/api')

@monitor_bp.route('/detections', methods=['POST'])
@jwt_required()
def add_detection():
    data = request.json
    camera_id = data.get('camera_id')
    label = data.get('label')
    confidence = data.get('confidence')

    if not camera_id or not label or confidence is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    new_detection = Detection(
        camera_id=camera_id,
        label=label,
        confidence=confidence
    )
    
    try:
        db.session.add(new_detection)
        db.session.commit()
        return jsonify({'success': True, 'detection': new_detection.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@monitor_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()

    total_detections = Detection.query.count()
    active_cameras = Camera.query.filter_by(status='online').count()
    
    alerts_count = 0
    if user:
        settings = NotificationSetting.query.filter_by(user_id=user.id, enabled=True).all()
        enabled_labels = [s.label for s in settings]
        
        if not settings:
             enabled_labels = ['person', 'Face: Unknown']


        alerts_count = Detection.query.filter(Detection.label.in_(enabled_labels)).count()
    
    return jsonify({
        'success': True,
        'stats': {
            'active_cameras': active_cameras,
            'detections': total_detections,
            'alerts': alerts_count,
            'security_level': 'High'
        }
    })

@monitor_bp.route('/detections/history', methods=['GET'])
@jwt_required()
def get_history():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()

    if not user:
         return jsonify({'success': False, 'message': 'User not found'}), 404
         
    settings = NotificationSetting.query.filter_by(user_id=user.id, enabled=True).all()
    
    if not settings:
         enabled_labels = ['person', 'Face: Unknown', 'Face: Known', 'car']
    else:
         enabled_labels = [s.label for s in settings]

    history = Detection.query.filter(Detection.label.in_(enabled_labels))\
              .order_by(Detection.timestamp.desc())\
              .limit(50).all()
              
    return jsonify({
        'success': True,
        'history': [d.to_dict() for d in history]
    })
