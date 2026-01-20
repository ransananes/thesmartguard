import os
import uuid
import face_recognition
import numpy as np
import pickle
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import KnownFace, User
from ..extensions import db

faces_bp = Blueprint('faces', __name__, url_prefix='/api')

@faces_bp.route('/faces', methods=['GET'])
@jwt_required()
def get_faces():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    if not user:
         return jsonify({'success': False, 'message': 'User not found'}), 404

    # Filter faces by user_id
    faces = KnownFace.query.filter_by(user_id=user.id).all()
    return jsonify({'success': True, 'faces': [f.to_dict() for f in faces]})

@faces_bp.route('/faces', methods=['POST'])
@jwt_required()
def add_face():
    if 'image' not in request.files or 'name' not in request.form:
        return jsonify({'success': False, 'message': 'Image and name are required'}), 400

    file = request.files['image']
    name = request.form['name']
    
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()

    try:
        # Save image file
        filename = f"{uuid.uuid4()}_{file.filename}"
        save_path = os.path.join(current_app.root_path, 'static', 'faces', filename)
        file.save(save_path)
        
        # Load image for recognition
        img = face_recognition.load_image_file(save_path)
        # Get encoding (assume 1 face per photo for now)
        encodings = face_recognition.face_encodings(img)

        if not encodings:
            os.remove(save_path) # Cleanup
            return jsonify({'success': False, 'message': 'No face found in image'}), 400
        
        # Take the first face found
        encoding = encodings[0]
        
        new_face = KnownFace(
            name=name, 
            encoding=encoding,
            image_path=filename,
            user_id=user.id if user else None
        )
        db.session.add(new_face)
        db.session.commit()
        
        # Trigger reload of faces in VideoProcessor if possible
        if hasattr(current_app, 'video_processor') and current_app.video_processor:
            if hasattr(current_app.video_processor, 'reload_faces'):
                current_app.video_processor.reload_faces()
            else:
                print("WARNING: VideoProcessor instance missing reload_faces method") 

        return jsonify({'success': True, 'face': new_face.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@faces_bp.route('/faces/<int:face_id>', methods=['DELETE'])
@jwt_required()
def delete_face(face_id):
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    face = KnownFace.query.get(face_id)
    if not face:
        return jsonify({'success': False, 'message': 'Face not found'}), 404
    
    # Check ownership
    if face.user_id != user.id and user.role != 'admin': # Assuming admin can delete any
         return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Delete file
        if face.image_path:
             path = os.path.join(current_app.root_path, 'static', 'faces', face.image_path)
             if os.path.exists(path):
                 os.remove(path)

        db.session.delete(face)
        db.session.commit()
        
        if hasattr(current_app, 'video_processor') and current_app.video_processor:
             current_app.video_processor.reload_faces()

        return jsonify({'success': True, 'message': 'Face deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
