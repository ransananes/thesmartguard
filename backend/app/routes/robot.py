import logging
import time
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
    """Serve the robot camera stream with face-recognition annotations.

    When the VideoProcessor has an active robot camera pipeline the route
    serves annotated MJPEG frames (same format as the main /video_feed).
    Falls back to a raw proxy of the ESP32-CAM stream when the processor
    is not running (e.g. robot not yet connected through the UI).

    Optional query params ``host`` and ``port`` are honoured in fallback mode.
    """
    vp = getattr(current_app, 'video_processor', None)

    if vp and vp._robot_processing:
        def generate_annotated():
            interval = 1.0 / Config.STREAM_TARGET_FPS
            last_frame = None
            while vp._robot_processing:
                t0 = time.time()
                frame = vp.get_robot_frame()
                if frame:
                    last_frame = frame
                if last_frame:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + last_frame + b'\r\n'
                sleep_t = interval - (time.time() - t0)
                time.sleep(max(0.005, sleep_t))

        return Response(
            stream_with_context(generate_annotated()),
            mimetype='multipart/x-mixed-replace; boundary=frame',
        )

    # Fallback: proxy the raw ESP32-CAM MJPEG stream
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

    if success and robot_controller.host:
        vp = getattr(current_app, 'video_processor', None)
        if vp:
            cam_url = f'http://{robot_controller.host}:{Config.ROBOT_CAMERA_PORT}/stream'
            vp.start_robot_camera_processing(cam_url)

    return jsonify({'success': success, 'message': message})


@robot_bp.route('/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    vp = getattr(current_app, 'video_processor', None)
    if vp:
        vp.stop_robot_camera_processing()
        vp.set_auto_follow(False)
        vp.set_follow_unknowns(False)

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

    if enabled and not robot_controller.is_connected:
        return jsonify({'success': False, 'message': 'Robot is not connected'}), 409

    vp.set_auto_follow(enabled, known_only=known_only)
    return jsonify({
        'success': True,
        'message': f"Auto-follow {'enabled' if enabled else 'disabled'}, known_only={known_only}",
        'auto_follow': enabled,
        'known_only':  known_only,
    })


@robot_bp.route('/return_home', methods=['POST'])
@jwt_required()
def return_home():
    """Send the robot back to its registered home position at fast return speed."""
    vp = getattr(current_app, 'video_processor', None)
    if vp:
        started = vp.start_return_home()
    else:
        started = robot_controller.return_to_home()

    if started:
        return jsonify({'success': True, 'message': 'Returning to home position'})
    status = robot_controller.get_home_status()
    if status['returning_home']:
        return jsonify({'success': False, 'message': 'Already returning home'})
    return jsonify({'success': False, 'message': 'Robot not connected'})


@robot_bp.route('/register_home', methods=['POST'])
@jwt_required()
def register_home():
    """Mark the robot's current position as home for dead-reckoning intercept."""
    robot_controller.register_home()
    status = robot_controller.get_home_status()
    return jsonify({'success': True, 'message': 'Home position registered', **status})


@robot_bp.route('/follow_unknowns', methods=['POST'])
@jwt_required()
def toggle_follow_unknowns():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', False))

    vp = getattr(current_app, 'video_processor', None)
    if not vp:
        return jsonify({'success': False, 'message': 'Video processor not active'}), 503

    if enabled and not robot_controller.is_connected:
        return jsonify({'success': False, 'message': 'Robot is not connected'}), 409

    vp.set_follow_unknowns(enabled)
    return jsonify({
        'success': True,
        'message': f"Follow-unknowns {'enabled' if enabled else 'disabled'}",
        'follow_unknowns': enabled,
    })