import cv2
import time
import threading
import logging
import face_recognition
import numpy as np
import pickle
import os
import uuid
from app.models import NotificationSetting, User
from ultralytics import YOLO
from app.extensions import db
from app.models import Detection, Camera, KnownFace
from flask import current_app
import datetime
import pytz

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, app):
        self.app = app
        self.model = YOLO('yolov8n.pt')
        self.processing = False
        self.thread = None
        self.camera_url = None
        self.camera_id = None

        self.lock = threading.Lock()
        self.last_frame = None
        
        self.known_face_encodings = []
        self.known_face_names = []
        
        self.enabled_labels = {'person', 'car', 'face: unknown'}
        self.detect_others = False
        
        self.current_person_count = 0
        self.current_faces = []
        
        self.last_detection_alert = {}
        self.ALERT_COOLDOWN = 5.0
        self.recent_unknown_faces = [] 
        self.UNKNOWN_FACE_COOLDOWN = 60.0
        
        self.reload_faces_needed = False
        
        self._perform_face_reload()
        self.reload_settings()

    def reload_settings(self):
        with self.app.app_context():
            try:
                user = User.query.filter_by(username='root').first()
                if user:
                     settings = NotificationSetting.query.filter_by(user_id=user.id).all()
                     if settings:
                         self.update_settings(settings)
                     else:
                         logger.info("No settings found in DB, using defaults.")
                         defaults = [{'label': 'person', 'enabled': True}, 
                                     {'label': 'car', 'enabled': True},
                                     {'label': 'Face: Unknown', 'enabled': True},
                                     {'label': 'Face: Known', 'enabled': True}]
                         self.update_settings(defaults)
            except Exception as e:
                logger.error(f"Failed to load settings on init: {e}")

    def update_settings(self, settings):
        """
        Updates detection filters based on Settings objects.
        settings: list of NotificationSetting objects (or dicts)
        """
        with self.lock:
            self.enabled_labels = set()
            self.detect_others = False
            
            for s in settings:

                label = s.label if hasattr(s, 'label') else s.get('label')
                enabled = s.enabled if hasattr(s, 'enabled') else s.get('enabled')
                
                if enabled:
                    if label == 'Other Objects':
                        self.detect_others = True
                    else:
                        self.enabled_labels.add(label.lower())
            
            logger.info(f"Updated settings: Labels={self.enabled_labels}, DetectOthers={self.detect_others}")

    def reload_faces(self):
        """Signal the processing loop to reload faces safely."""
        with self.lock:
            self.reload_faces_needed = True
        logger.info("Signal sent: Reload faces on next frame.")

    def _perform_face_reload(self):
        """Internal method to actually load from DB. Call this from the processing thread or init."""
        with self.lock: 
            self.known_face_encodings = []
            self.known_face_names = []
            self.track_names = {}
            
        try:
             with self.app.app_context():
                faces = KnownFace.query.all()
                for face in faces:
                    self.known_face_names.append(face.name)
                    self.known_face_encodings.append(pickle.loads(face.encoding) if isinstance(face.encoding, bytes) else face.encoding)
                logger.info(f"Loaded {len(self.known_face_names)} known faces.")
        except Exception as e:
            logger.error(f"Error loading faces: {e}")

    def start_processing(self, camera_id, stream_url, camera_name="Camera"):
        if self.processing:
            self.stop_processing()
        
        self.camera_id = camera_id
        self.camera_url = stream_url
        self.camera_name = camera_name
        
        with self.lock:
            self.last_frame = None
            self.recent_unknown_faces = [] 
            self.last_detection_alert = {}
            
        self.processing = True
        self.thread = threading.Thread(target=self._process_stream)
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"Started processing for camera {camera_name} ({camera_id}) at {stream_url}")

    def stop_processing(self):
        self.processing = False
        if self.thread:
            self.thread.join()
            self.thread = None
        
        with self.lock:
            self.last_frame = None
            
        logger.info("Stopped processing.")

    def get_frame(self):
        with self.lock:
            if self.last_frame is None:
                return None
            
            ret, buffer = cv2.imencode('.jpg', self.last_frame)
            if not ret:
                return None
            return buffer.tobytes()

    def _process_stream(self):
        cap = cv2.VideoCapture(self.camera_url)
        
        fps_input = cap.get(cv2.CAP_PROP_FPS)
        if not fps_input or fps_input <= 0:
            fps_input = 24.0
        
        target_frame_time = 1.0 / fps_input
        
        self.track_names = {} 
        
        last_loop_time = time.time()
        
        with self.app.app_context():
            while self.processing and cap.isOpened():
                loop_start = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                
                if self.reload_faces_needed:
                    self._perform_face_reload()
                    self.reload_faces_needed = False

                try:
                    results = self.model.track(frame, persist=True, verbose=False, conf=0.4, tracker="bytetrack.yaml")
                except Exception as e:
                     logger.error(f"Tracking error: {e}")

                     results = self.model(frame, verbose=False, conf=0.4)
                
                current_time = time.time()
                
                detections_to_save_this_frame = []
                
                annotated_frame = frame.copy()
                
                fps_disp = 1.0 / (current_time - last_loop_time) if last_loop_time != current_time else 0
                last_loop_time = current_time
                
                cv2.putText(annotated_frame, f"FPS: {fps_disp:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if self.camera_name:
                     cv2.putText(annotated_frame, f"CAM: {self.camera_name}", (10, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                
                object_count = 0
                current_frame_names = []
                
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        label = self.model.names[cls_id]
                        
                        is_enabled = (label in self.enabled_labels) or (self.detect_others and label not in ['person', 'car'])
                        
                        if not is_enabled:
                            continue

                        object_count += 1
                        
                        x1, y1, x2, y2 = box.xyxy[0]
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                        conf = float(box.conf[0])
                        
                        track_id = int(box.id[0]) if box.id is not None else None
                        

                        color = (0, 0, 255)
                        
                        if label == 'person':
                            name = "Checking..."
                            
                            if track_id is not None:
                                if track_id not in self.track_names:
                                     name, enc = self._identify_face_in_box(frame, x1, y1, x2, y2)
                                     self.track_names[track_id] = {
                                         'name': name,
                                         'last_seen': current_time,
                                         'face_encoding': enc,
                                         'last_face_check': current_time
                                     }
                                else:
                                    track_info = self.track_names[track_id]
                                    name = track_info['name']
                                    last_check = track_info.get('last_face_check', 0)
                                    
                                    if name == "Unknown" and (current_time - last_check > 2.0):
                                         name, enc = self._identify_face_in_box(frame, x1, y1, x2, y2)
                                         self.track_names[track_id]['name'] = name
                                         self.track_names[track_id]['last_face_check'] = current_time
                                         if enc is not None:
                                              self.track_names[track_id]['face_encoding'] = enc
                                
                                name = self.track_names[track_id]['name']

                                
                                display_text = f"{name}"

                                current_frame_names.append(name)
                                
                                self._process_face_alert_v2(name, track_id, frame, current_time, x1, y1, x2, y2)
                                

                                if name != "Unknown" and name != "Checking...":
                                    color = (0, 255, 0)
                            else:
                                display_text = f"{label} {conf:.2f}"

                                if label == 'person':
                                    current_frame_names.append("Unknown")

                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        

                        if label != 'person':
                            self._process_object_alert(label, conf, current_time, self.camera_id)
                        

                        cv2.putText(annotated_frame, display_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


                cv2.putText(annotated_frame, f"Objects: {object_count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                with self.lock:
                    self.last_frame = annotated_frame
                    self.current_faces = current_frame_names
                    self.current_person_count = object_count
                
                loop_duration = time.time() - loop_start
                if loop_duration < target_frame_time:
                    time.sleep(target_frame_time - loop_duration)

        cap.release()

    def _identify_face_in_box(self, frame, x1, y1, x2, y2):
        """Runs face recognition on the specific crop. Returns (Name, Encoding)."""
        h, w, _ = frame.shape
        pad = 20
        crop_x1 = max(0, x1 - pad)
        crop_y1 = max(0, y1 - pad)
        crop_x2 = min(w, x2 + pad)
        crop_y2 = min(h, y2 + pad)
        

        person_crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        if person_crop.size == 0:
            return "Unknown", None

        rgb_crop = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)
        

        crop_face_locations = face_recognition.face_locations(rgb_crop, number_of_times_to_upsample=1)
        if not crop_face_locations:
            return "Unknown", None
            
        crop_face_encodings = face_recognition.face_encodings(rgb_crop, crop_face_locations)
        

        if crop_face_encodings:
            face_encoding = crop_face_encodings[0]
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding)
            name = "Unknown"
            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = self.known_face_names[best_match_index]
            
            return name, face_encoding
            
        return "Unknown", None

    def _process_object_alert(self, label, conf, current_time, camera_id):
        alert_key = f"Object: {label}"
        last_seen = self.last_detection_alert.get(alert_key, 0)
        time_since_seen = current_time - last_seen
        
        self.last_detection_alert[alert_key] = current_time
        
        if time_since_seen > self.ALERT_COOLDOWN:
             tz = pytz.timezone('Asia/Jerusalem')
             now_jerusalem = datetime.datetime.now(tz)
             
             new_detection = Detection(
                 camera_id=camera_id,
                 label=f"Object: {label}",
                 confidence=conf,
                 timestamp=now_jerusalem
             )
             self._save_detections_to_db([new_detection])
             logger.info(f"ALERT TRIGGERED: {label} (Gap: {time_since_seen:.2f}s) at {now_jerusalem}")

    def _process_face_alert_v2(self, name, track_id, frame, current_time, x1, y1, x2, y2):
        face_label = f"Face: {name}"
        is_unknown = (name == "Unknown")
        alert_label = "Face: Unknown" if is_unknown else "Face: Known"
        
        should_alert = (name == "Unknown") and (alert_label.lower() in self.enabled_labels)
        
        if not should_alert:
            return

        track_cooldown_key = f"track_{track_id}"
        last_track_alert = self.last_detection_alert.get(track_cooldown_key, 0)
        
        TRACK_COOLDOWN = 5
        
        if current_time - last_track_alert < TRACK_COOLDOWN:
            return
        
        logger.info(f"[FACE DETECTION] {name} (track: {track_id}) - Creating detection...")
        self.last_detection_alert[track_cooldown_key] = current_time

        tz = pytz.timezone('Asia/Jerusalem')
        now_jerusalem = datetime.datetime.now(tz)
        
        filename = f"face_{uuid.uuid4()}.jpg"

        storage_root = os.path.join(os.path.dirname(self.app.root_path), 'storage')
        filepath = os.path.join(storage_root, 'detections', filename)
        image_path = filename
        
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            

            h, w, _ = frame.shape
            y1_c, y2_c = max(0, y1), min(h, y2)
            x1_c, x2_c = max(0, x1), min(w, x2)
            
            person_crop = frame[y1_c:y2_c, x1_c:x2_c]
            
            if person_crop.size > 0:
                rgb_person = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)
                face_locs = face_recognition.face_locations(rgb_person, number_of_times_to_upsample=1)
                
                final_crop = person_crop
                
                if face_locs:
                    top, right, bottom, left = face_locs[0]
                    

                    pad = 20
                    f_h, f_w, _ = person_crop.shape
                    
                    crop_top = max(0, top - pad)
                    crop_bottom = min(f_h, bottom + pad)
                    crop_left = max(0, left - pad)
                    crop_right = min(f_w, right + pad)
                    
                    final_crop = person_crop[crop_top:crop_bottom, crop_left:crop_right]
                    
                    cv2.imwrite(filepath, final_crop)
                    image_path = filename
                else:
                    logger.info(f"Skipping alert for {name}: No face found in crop.")
                    return

        except Exception as e:
            logger.error(f"Error saving face crop: {e}")
            image_path = None

        dets = [Detection(
            camera_id=self.camera_id, 
            label=alert_label, 
            confidence=1.0, 
            timestamp=now_jerusalem,
            image_path=image_path
        )]
        self._save_detections_to_db(dets)
        logger.info(f"ALERT TRIGGERED: {alert_label} (Track: {track_id}, Cooldown: {TRACK_COOLDOWN}s) at {now_jerusalem}")

    def clear_all_data(self):
        """Clears all detections, known faces, and internal tracking state."""
        with self.lock:
            self.track_names = {}
            self.last_detection_alert = {}
            self.current_faces = []
            
        with self.app.app_context():
            try:
                num_detections = Detection.query.delete()
                num_faces = KnownFace.query.delete()
                db.session.commit()
                logger.info(f"CLEARED DATA: {num_detections} detections, {num_faces} known faces removed.")
                
                self.known_face_encodings = []
                self.known_face_names = []
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error clearing data: {e}")
                
            try:
                storage_root = os.path.join(os.path.dirname(self.app.root_path), 'storage')
                
                det_folder = os.path.join(storage_root, 'detections')
                if os.path.exists(det_folder):
                    for f in os.listdir(det_folder):
                        if f.endswith('.jpg'):
                            try:
                                os.remove(os.path.join(det_folder, f))
                            except: pass
                            
                face_folder = os.path.join(storage_root, 'faces')
                if os.path.exists(face_folder):
                    for f in os.listdir(face_folder):
                        if f.endswith('.jpg'):
                            try:
                                os.remove(os.path.join(face_folder, f))
                            except: pass
                            
                logger.info("CLEARED DISK: Removed images from detections and faces folders.")
            except Exception as e:
                logger.error(f"Error clearing disk files: {e}")


    def _save_detections_to_db(self, detections):
         try:
             for d in detections:
                 db.session.add(d)
             db.session.commit()
             logger.info(f"Saved {len(detections)} detections.")
         except Exception as e:
             logger.error(f"Error saving detections: {e}")
             db.session.rollback()
