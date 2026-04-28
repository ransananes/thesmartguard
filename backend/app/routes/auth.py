from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required
from app.models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/api')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Request body must be JSON'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': 'username and password are required'}), 400

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        access_token = create_access_token(identity=username)
        return jsonify({
            'success': True,
            'token': access_token,
            'user': user.to_dict(),
        })

    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401


@auth_bp.route('/verify', methods=['GET'])
@jwt_required()
def verify_token():
    return jsonify({'success': True, 'message': 'Token is valid'})
