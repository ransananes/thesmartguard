from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required
from app.models import Camera, Detection
from app.extensions import db

cameras_bp = Blueprint('cameras', __name__, url_prefix='/api')


@cameras_bp.route('/cameras', methods=['GET'])
@jwt_required()
def get_cameras():
    cameras = Camera.query.all()
    return jsonify({'cameras': [cam.to_dict() for cam in cameras]})


@cameras_bp.route('/cameras', methods=['POST'])
@jwt_required()
def add_camera():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Request body must be JSON'}), 400

    name = (data.get('name') or '').strip()
    ip_address = (data.get('ip_address') or '').strip()
    port = data.get('port')
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not name or not ip_address:
        return jsonify({'success': False, 'message': 'name and ip_address are required'}), 400

    # Build stream URL
    if ip_address.startswith(('http://', 'https://', 'rtsp://')):
        stream_url = ip_address
    else:
        protocol = 'rtsp' if port and int(port) == 554 else 'http'
        auth = f'{username}:{password}@' if (username and password) else ''
        port_str = f':{port}' if port else ''
        stream_url = f'{protocol}://{auth}{ip_address}{port_str}'

    new_camera = Camera(
        name=name,
        ip_address=ip_address,
        port=port,
        stream_url=stream_url,
        status='online',
    )

    try:
        db.session.add(new_camera)
        db.session.commit()
        current_app.video_processor.start_processing(new_camera.id, stream_url, name)
        return jsonify({'success': True, 'camera': new_camera.to_dict()}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500


@cameras_bp.route('/cameras/<int:camera_id>', methods=['DELETE'])
@jwt_required()
def delete_camera(camera_id):
    camera = db.session.get(Camera, camera_id)
    if not camera:
        return jsonify({'success': False, 'message': 'Camera not found'}), 404

    try:
        Detection.query.filter_by(camera_id=camera_id).delete()
        db.session.delete(camera)
        db.session.commit()

        vp = getattr(current_app, 'video_processor', None)
        if vp and vp.camera_id == camera_id:
            vp.stop_processing()

        return jsonify({'success': True, 'message': 'Camera deleted successfully'})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 500
