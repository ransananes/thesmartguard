from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context
import time
from .models import User, Camera, Detection
from .extensions import db
from flask_jwt_extended import create_access_token, jwt_required
from sqlalchemy import func
from .video_processor import VideoProcessor

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    def generate():
        if not hasattr(current_app, 'video_processor'):
             # If no processor, maybe just yield logical nothing or restart it?
             # For now, let's assume it exists or return error frame?
             # But streaming response expects bytes.
             return

        while True:
            frame = current_app.video_processor.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # If no frame, small sleep to prevent CPU spin
                time.sleep(0.1)
                
    return Response(stream_with_context(generate()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        access_token = create_access_token(identity=username)
        return jsonify({
            'success': True, 
            'token': access_token,
            'user': user.to_dict()
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@bp.route('/verify', methods=['GET'])
@jwt_required()
def verify_token():
    return jsonify({'success': True, 'message': 'Token is valid'})

@bp.route('/cameras', methods=['GET'])
@jwt_required()
def get_cameras():
    cameras = Camera.query.all()
    return jsonify({'cameras': [cam.to_dict() for cam in cameras]})

@bp.route('/cameras', methods=['POST'])
@jwt_required()
def add_camera():
    data = request.json
    name = data.get('name')
    ip_address = data.get('ip_address')
    port = data.get('port')
    
    if not name or not ip_address:
        return jsonify({'success': False, 'message': 'Name and IP Address are required'}), 400
        
    # Construct stream URL
    if ip_address.startswith(('http://', 'https://', 'rtsp://')):
        stream_url = ip_address
    else:
        stream_url = f"http://{ip_address}:{port}" if port else f"http://{ip_address}"
    
    new_camera = Camera(
        name=name,
        ip_address=ip_address,
        port=port,
        stream_url=stream_url,
        status='online' # Default status
    )
    
    try:
        db.session.add(new_camera)
        db.session.commit()

        if not hasattr(current_app, 'video_processor'):
            from .video_processor import VideoProcessor
            current_app.video_processor = VideoProcessor(current_app._get_current_object())
        
        current_app.video_processor.start_processing(new_camera.id, stream_url)

        return jsonify({'success': True, 'camera': new_camera.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/cameras/<int:camera_id>', methods=['DELETE'])
@jwt_required()
def delete_camera(camera_id):
    camera = Camera.query.get(camera_id)
    if not camera:
        return jsonify({'success': False, 'message': 'Camera not found'}), 404
        
    try:
        # Delete associated detections first to satisfy Foreign Key
        Detection.query.filter_by(camera_id=camera_id).delete()
        
        db.session.delete(camera)
        db.session.commit()
        
        # Stop processing if it's the current camera
        if hasattr(current_app, 'video_processor') and current_app.video_processor.camera_id == camera_id:
            current_app.video_processor.stop_processing()
            
        return jsonify({'success': True, 'message': 'Camera deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/detections', methods=['POST'])
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

@bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    total_detections = Detection.query.count()
    
    active_cameras = Camera.query.filter_by(status='online').count()
    
    alerts_count = Detection.query.filter(Detection.label == 'person', Detection.confidence > 0.8).count()
    
    return jsonify({
        'success': True,
        'stats': {
            'active_cameras': active_cameras,
            'detections': total_detections,
            'alerts': alerts_count,
            'security_level': 'High'
        }
    })
