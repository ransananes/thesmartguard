import logging
import requests as req_lib
from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context
from flask_jwt_extended import jwt_required
from app.robot_controller import robot_controller, VALID_COMMANDS
from app.config import Config

logger = logging.getLogger(__name__)

robot_bp = Blueprint('robot', __name__, url_prefix='/api/robot')


@robot_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    status = robot_controller.get_status()

    if robot_controller.host:
        status['camera_feed_url'] = '/api/robot/camera_feed'

    # Merge follow state from VideoProcessor if available
    vp = getattr(current_app, 'video_processor', None)
    if vp:
        status.update(vp.get_follow_status())

    return jsonify({'success': True, 'status': status})


@robot_bp.route('/camera_feed')
def robot_camera_feed():
    """Proxy the ESP32-CAM MJPEG stream — avoids browser CORS restrictions.

    Optional query params ``host`` and ``port`` allow per-camera robot streams.
    Falls back to the globally connected robot when omitted.
    """
    host = (request.args.get('host') or '').strip() or robot_controller.host
    port = int(request.args.get('port') or Config.ROBOT_CAMERA_PORT)

    if not host:
        return jsonify({'error': 'Robot host not configured'}), 503

    cam_url = f'http://{host}:{port}/stream'

    try:
        upstream = req_lib.get(cam_url, stream=True, timeout=(5, None))
        upstream.raise_for_status()
        content_type = upstream.headers.get(
            'Content-Type', 'multipart/x-mixed-replace; boundary=frame'
        )
    except Exception as exc:
        logger.error(f'Robot camera connection error: {exc}')
        return jsonify({'error': str(exc)}), 503

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        except Exception as exc:
            logger.error(f'Robot camera stream interrupted: {exc}')
        finally:
            upstream.close()

    return Response(
        stream_with_context(generate()),
        content_type=content_type,
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


@robot_bp.route('/connect', methods=['POST'])
@jwt_required()
def connect():
    data = request.get_json(silent=True) or {}
    host = data.get('host')
    port = data.get('port')
    success, message = robot_controller.connect(host, int(port) if port else None)
    return jsonify({'success': success, 'message': message})


@robot_bp.route('/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    success, message = robot_controller.disconnect()
    return jsonify({'success': success, 'message': message})


@robot_bp.route('/ping', methods=['GET'])
@jwt_required()
def ping():
    success, message = robot_controller.ping()
    return jsonify({'success': success, 'message': message})


@robot_bp.route('/control', methods=['POST'])
@jwt_required()
def control():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Request body must be JSON'}), 400

    command = (data.get('command') or '').strip().upper()
    if not command:
        return jsonify({'success': False, 'message': 'command is required'}), 400

    cmd_char = command[0]
    if cmd_char not in VALID_COMMANDS:
        return jsonify({
            'success': False,
            'message': f'Invalid command. Valid commands: {sorted(VALID_COMMANDS)}',
        }), 400

    success, message = robot_controller.send_command(command, force=True)
    return jsonify({'success': success, 'message': message})


@robot_bp.route('/follow', methods=['POST'])
@jwt_required()
def toggle_follow():
    data = request.get_json(silent=True) or {}
    enabled    = bool(data.get('enabled', False))
    known_only = bool(data.get('known_only', False))

    vp = getattr(current_app, 'video_processor', None)
    if not vp:
        return jsonify({'success': False, 'message': 'Video processor not active'}), 503

    vp.set_auto_follow(enabled, known_only=known_only)
    return jsonify({
        'success': True,
        'message': f"Auto-follow {'enabled' if enabled else 'disabled'}, known_only={known_only}",
        'auto_follow': enabled,
        'known_only':  known_only,
    })


@robot_bp.route('/follow_unknowns', methods=['POST'])
@jwt_required()
def toggle_follow_unknowns():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', False))

    vp = getattr(current_app, 'video_processor', None)
    if not vp:
        return jsonify({'success': False, 'message': 'Video processor not active'}), 503

    vp.set_follow_unknowns(enabled)
    return jsonify({
        'success': True,
        'message': f"Follow-unknowns {'enabled' if enabled else 'disabled'}",
        'follow_unknowns': enabled,
    })