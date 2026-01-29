import os
import uuid
import logging
import face_recognition
import numpy as np
import pickle
import cv2
from PIL import Image
import imagehash
import shutil
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import KnownFace, User, Detection
from app.extensions import db

logger = logging.getLogger(__name__)

def detect_face_with_yolo(image_path):
    """
    Uses the video processor's YOLO face model to detect faces.
    Returns face locations in face_recognition format: (top, right, bottom, left)
    """
    if not hasattr(current_app, 'video_processor') or not current_app.video_processor:
        logger.warning("No video_processor available, falling back to face_recognition detection")
        return None
    
    face_model = current_app.video_processor.face_model
    if face_model is None:
        logger.warning("No face_model available, falling back to face_recognition detection")
        return None
    
    try:
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            return None
            
        results = face_model(img_bgr, verbose=False, conf=0.5)
        
        face_locations = []
        for result in results:
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    face_locations.append((y1, x2, y2, x1))
        
        if face_locations:
            logger.info(f"YOLO detected {len(face_locations)} face(s)")
            return face_locations
        return None
        
    except Exception as e:
        logger.error(f"YOLO face detection failed: {e}")
        return None

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
        
        # Load image for encoding
        img = face_recognition.load_image_file(save_path)
        
        # Try YOLO face detection first, fall back to face_recognition
        face_locations = detect_face_with_yolo(save_path)
        
        if face_locations:
            encodings = face_recognition.face_encodings(img, face_locations)
        else:
            # Fallback to face_recognition's built-in detection
            encodings = face_recognition.face_encodings(img)

        if not encodings:
            os.remove(save_path)
            return jsonify({'success': False, 'message': 'No face found in image'}), 400
        
        encoding = encodings[0]
        logger.info(f"Successfully encoded face (sum: {np.sum(np.abs(encoding)):.4f})")
        
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
        
        logger.info("Step 4: Encoding face with YOLO detection...") 
        
        try:
            img = face_recognition.load_image_file(dest_path)
            
            # Try YOLO face detection first
            face_locations = detect_face_with_yolo(dest_path)
            
            if face_locations:
                encodings = face_recognition.face_encodings(img, face_locations)
            else:
                # Fallback to face_recognition's built-in detection
                encodings = face_recognition.face_encodings(img)
            
            if encodings:
                encoding = encodings[0]
                logger.info(f"Successfully encoded face (size: {len(encoding)}, sum: {np.sum(np.abs(encoding)):.4f})")
            else:
                logger.error("No face found in the detection image")
                os.remove(dest_path)
                return jsonify({'success': False, 'message': 'No face found in the detection image'}), 400
                
        except Exception as enc_err:
            logger.error(f"Error during face encoding: {enc_err}")
            os.remove(dest_path)
            return jsonify({'success': False, 'message': f'Failed to encode face: {str(enc_err)}'}), 500
        
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
