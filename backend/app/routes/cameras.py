from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required
from app.models import Camera, Detection
from app.extensions import db
from app.video_processor import VideoProcessor

cameras_bp = Blueprint('cameras', __name__, url_prefix='/api')

@cameras_bp.route('/cameras', methods=['GET'])
@jwt_required()
def get_cameras():
    cameras = Camera.query.all()
    return jsonify({'cameras': [cam.to_dict() for cam in cameras]})

@cameras_bp.route('/cameras', methods=['POST'])
@jwt_required()
def add_camera():
    data = request.json
    name = data.get('name')
    ip_address = data.get('ip_address')
    port = data.get('port')
    username = data.get('username')
    password = data.get('password')
    
    if not name or not ip_address:
        return jsonify({'success': False, 'message': 'Name and IP Address are required'}), 400
        
    if ip_address.startswith(('http://', 'https://', 'rtsp://')):
        stream_url = ip_address
    else:

        if port and int(port) == 554:
            protocol = 'rtsp'
        else:
            protocol = 'http'
            
        auth = f"{username}:{password}@" if (username and password) else ""
        port_str = f":{port}" if port else ""
        
        stream_url = f"{protocol}://{auth}{ip_address}{port_str}"
    
    new_camera = Camera(
        name=name,
        ip_address=ip_address,
        port=port,
        stream_url=stream_url,
        status='online'
    )
    
    try:
        db.session.add(new_camera)
        db.session.commit()

        if not hasattr(current_app, 'video_processor'):
            current_app.video_processor = VideoProcessor(current_app._get_current_object())
        
        current_app.video_processor.start_processing(new_camera.id, stream_url)

        return jsonify({'success': True, 'camera': new_camera.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@cameras_bp.route('/cameras/<int:camera_id>', methods=['DELETE'])
@jwt_required()
def delete_camera(camera_id):
    camera = Camera.query.get(camera_id)
    if not camera:
        return jsonify({'success': False, 'message': 'Camera not found'}), 404
        
    try:

        Detection.query.filter_by(camera_id=camera_id).delete()
        
        db.session.delete(camera)
        db.session.commit()
        
        if hasattr(current_app, 'video_processor') and current_app.video_processor.camera_id == camera_id:
            current_app.video_processor.stop_processing()
            
        return jsonify({'success': True, 'message': 'Camera deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
