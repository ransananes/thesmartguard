import os
import uuid
import subprocess
import json
import logging
import face_recognition
import numpy as np
import pickle
from PIL import Image
import imagehash
import shutil
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import KnownFace, User, Detection
from app.extensions import db

logger = logging.getLogger(__name__)

faces_bp = Blueprint('faces', __name__, url_prefix='/api')

@faces_bp.route('/faces', methods=['GET'])
@jwt_required()
def get_faces():
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    if not user:
         return jsonify({'success': False, 'message': 'User not found'}), 404

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
        filename = f"{uuid.uuid4()}_{file.filename}"
        storage_root = os.path.join(os.path.dirname(current_app.root_path), 'storage')
        save_path = os.path.join(storage_root, 'faces', filename)
        

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        file.save(save_path)
        

        img = face_recognition.load_image_file(save_path)

        encodings = face_recognition.face_encodings(img)

        if not encodings:
            os.remove(save_path)
            return jsonify({'success': False, 'message': 'No face found in image'}), 400
        

        encoding = encodings[0]
        
        new_face = KnownFace(
            name=name, 
            encoding=encoding,
            image_path=filename,
            user_id=user.id if user else None
        )
        db.session.add(new_face)
        db.session.commit()
        

        if hasattr(current_app, 'video_processor') and current_app.video_processor:
            if hasattr(current_app.video_processor, 'reload_faces'):
                current_app.video_processor.reload_faces()
            else:
                logger.warning("VideoProcessor instance missing reload_faces method") 

        return jsonify({'success': True, 'face': new_face.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@faces_bp.route('/faces/from_detection', methods=['POST'])
@jwt_required()
def add_face_from_detection():
    logger.info("=== STARTING add_face_from_detection ===")
    data = request.get_json()
    if not data or 'detection_id' not in data or 'name' not in data:
        return jsonify({'success': False, 'message': 'detection_id and name are required'}), 400
        
    detection_id = data['detection_id']
    name = data['name']
    logger.info(f"Processing: detection_id={detection_id}, name={name}")
    
    current_user_name = get_jwt_identity()
    user = User.query.filter_by(username=current_user_name).first()
    
    try:
        logger.info("Step 1: Fetching detection...")
        detection = Detection.query.get(detection_id)
        if not detection:
             return jsonify({'success': False, 'message': 'Detection not found'}), 404
             
        if not detection.image_path:
             return jsonify({'success': False, 'message': 'No image associated with this detection'}), 400
        
        logger.info(f"Step 2: Setting up paths for {detection.image_path}...")
        storage_root = os.path.join(os.path.dirname(current_app.root_path), 'storage')
        source_path = os.path.join(storage_root, 'detections', detection.image_path)
        dest_filename = f"{uuid.uuid4()}_{detection.image_path}"
        dest_path = os.path.join(storage_root, 'faces', dest_filename)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        if not os.path.exists(source_path):
             logger.error(f"Source file missing: {source_path}")
             return jsonify({'success': False, 'message': 'Source image file missing'}), 404
        
        logger.info("Step 3: Copying file...")
        shutil.copy2(source_path, dest_path)
        
        logger.info("Step 4: Encoding face (in subprocess to prevent crashes)...") 
        
        try:
            encode_script = os.path.join(os.path.dirname(current_app.root_path), 'encode_face.py')
            result = subprocess.run(
                ['python', encode_script, dest_path],
                capture_output=True,
                text=True,
                timeout=30  
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                if data.get('success') and data.get('encoding'):
                    encoding = np.array(data['encoding'])
                    logger.info(f"Successfully encoded face (size: {len(encoding)})")
                else:
                    logger.error(f"Encoding failed: {data.get('error', 'Unknown error')}")
                    encoding = np.zeros(128)
            else:
                logger.error(f"Subprocess failed: {result.stderr}")
                encoding = np.zeros(128)
                
        except subprocess.TimeoutExpired:
            logger.error("Encoding timed out, using dummy encoding")
            encoding = np.zeros(128)
        except Exception as enc_err:
            logger.error(f"Error during face encoding: {enc_err}")
            encoding = np.zeros(128)
        
        logger.info("Step 5: Saving to database...")
        new_face = KnownFace(
            name=name, 
            encoding=encoding,
            image_path=dest_filename,
            user_id=user.id if user else None
        )
        db.session.add(new_face)
        db.session.commit()
        

        if hasattr(current_app, 'video_processor') and current_app.video_processor:
             current_app.video_processor.reload_faces()
             logger.info("Face reload triggered successfully")
             
        logger.info("Step 7: Cleaning up similar detections...")
        deleted_count = 0
        
        try:

            
            storage_root = os.path.join(os.path.dirname(current_app.root_path), 'storage')
            source_path = os.path.join(storage_root, 'detections', detection.image_path)
            
            if os.path.exists(source_path):
                source_hash = imagehash.phash(Image.open(source_path))
                logger.info(f"Source image hash: {source_hash}")
                
                unknown_detections = Detection.query.filter_by(label="Face: Unknown").all()
                logger.info(f"Checking {len(unknown_detections)} unknown detections...")
                
                for d in unknown_detections:
                    try:
                        if not d.image_path:
                            continue
                            
                        d_path = os.path.join(storage_root, 'detections', d.image_path)
                        if not os.path.exists(d_path):
                            db.session.delete(d)  
                            continue
                        
                        d_hash = imagehash.phash(Image.open(d_path))
                        hash_diff = source_hash - d_hash
                        
                        if hash_diff < 15:
                            logger.info(f"Removing similar detection {d.id} (hash diff: {hash_diff})")
                            os.remove(d_path)
                            db.session.delete(d)
                            deleted_count += 1
                    except Exception as cmp_err:
                        logger.error(f"Error comparing detection {d.id}: {cmp_err}")
                        continue
            else:
                logger.info(f"Source file not found: {source_path}")
                        
        except ImportError:
            logger.warning("imagehash not installed - falling back to simple cleanup")
            try:
                source_det_path = os.path.join(os.path.dirname(current_app.root_path), 'storage', 'detections', detection.image_path)
                if os.path.exists(source_det_path):
                    os.remove(source_det_path)
                db.session.delete(detection)
                deleted_count = 1
            except Exception as del_err:
                logger.error(f"Error during fallback cleanup: {del_err}")
        except Exception as hash_err:
            logger.error(f"Error during hash-based cleanup: {hash_err}")
                
        db.session.commit()
        logger.info(f"Cleaned up {deleted_count} detection(s) for {name}")

        return jsonify({'success': True, 'face': new_face.to_dict(), 'cleaned_up': deleted_count}), 201

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
    

    if face.user_id != user.id and user.role != 'admin':
         return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:

        if face.image_path:
             storage_root = os.path.join(os.path.dirname(current_app.root_path), 'storage')
             path = os.path.join(storage_root, 'faces', face.image_path)
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
