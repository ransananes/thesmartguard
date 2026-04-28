from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required
from app.robot_controller import robot_controller, VALID_COMMANDS

robot_bp = Blueprint('robot', __name__, url_prefix='/api/robot')


@robot_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    return jsonify({'success': True, 'status': robot_controller.get_status()})


@robot_bp.route('/connect', methods=['POST'])
@jwt_required()
def connect():
    data = request.get_json(silent=True) or {}
    port = data.get('port')
    success, message = robot_controller.connect(port)
    return jsonify({'success': success, 'message': message})


@robot_bp.route('/disconnect', methods=['POST'])
@jwt_required()
def disconnect():
    success, message = robot_controller.disconnect()
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
    enabled = bool(data.get('enabled', False))

    vp = getattr(current_app, 'video_processor', None)
    if not vp:
        return jsonify({'success': False, 'message': 'Video processor not active'}), 503

    vp.set_auto_follow(enabled)
    return jsonify({
        'success': True,
        'message': f"Auto-follow {'enabled' if enabled else 'disabled'}",
    })
