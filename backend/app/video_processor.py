import cv2
import time
import threading
import face_recognition
import numpy as np
import pickle
from ultralytics import YOLO
from .extensions import db
from .models import Detection, Camera, KnownFace
from flask import current_app

class VideoProcessor:
    def __init__(self, app):
        self.app = app
        self.model = YOLO('yolov8n.pt')  # Load pretrained YOLOv8n model
        self.processing = False
        self.thread = None
        self.camera_url = None
        self.camera_id = None

        self.lock = threading.Lock()
        self.last_frame = None
        
        # Load known faces
        self.known_face_encodings = []
        self.known_face_names = []
        
        # Persistent state for debouncing
        self.last_detection_alert = {}
        self.ALERT_COOLDOWN = 5.0
        
        self.reload_faces()

    def reload_faces(self):
        with self.lock: # Should probably lock while reloading
            self.known_face_encodings = []
            self.known_face_names = []
            
        with self.app.app_context():
            faces = KnownFace.query.all()
            for face in faces:
                self.known_face_names.append(face.name)
                self.known_face_encodings.append(pickle.loads(face.encoding) if isinstance(face.encoding, bytes) else face.encoding)
            print(f"Loaded {len(self.known_face_names)} known faces.")

    def start_processing(self, camera_id, stream_url):
        if self.processing:
            self.stop_processing()
        
        self.camera_id = camera_id
        self.camera_url = stream_url
        
        with self.lock:
            self.last_frame = None
            
        self.processing = True
        self.thread = threading.Thread(target=self._process_stream)
        self.thread.daemon = True
        self.thread.start()
        print(f"Started processing for camera {camera_id} at {stream_url}")

    def stop_processing(self):
        self.processing = False
        if self.thread:
            self.thread.join()
            self.thread = None
        
        with self.lock:
            self.last_frame = None
            
        print("Stopped processing.")

    def get_frame(self):
        with self.lock:
            if self.last_frame is None:
                return None
            
            # Encode frame to jpg
            ret, buffer = cv2.imencode('.jpg', self.last_frame)
            if not ret:
                return None
            return buffer.tobytes()

    def _process_stream(self):
        cap = cv2.VideoCapture(self.camera_url)
        
        frame_count = 0
        last_results = None
        last_face_locations = []
        last_face_names = []
        
        last_loop_time = time.time()

        # We need an app context for DB operations
        with self.app.app_context():
            while self.processing and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_count += 1
                detections_to_save_this_frame = []
                current_time = time.time()
                fps = 1.0 / (current_time - last_loop_time) if last_loop_time != current_time else 0
                last_loop_time = current_time
                
                # OPTIMIZATION: Process only 1 out of every 3 frames
                if frame_count % 3 == 0:
                    # Run inference (YOLO) with higher confidence
                    results = self.model(frame, verbose=False, conf=0.6)
                    last_results = results
                    
                    # Logic 1: Check Alerts for YOLO Detections
                    for r in results:
                        for box in r.boxes:
                            cls_id = int(box.cls[0])
                            label = self.model.names[cls_id]
                            conf = float(box.conf[0])
                            
                            # Check Last Seen BEFORE updating it
                            last_seen = self.last_detection_alert.get(label, 0)
                            time_since_seen = current_time - last_seen
                            
                            # Update heartbeat (Prevent Spam: set strictly to NOW)
                            self.last_detection_alert[label] = current_time
                            
                            # If gap is large, we have a NEW event suitable for alerting
                            if time_since_seen > self.ALERT_COOLDOWN:
                                new_detection = Detection(
                                    camera_id=self.camera_id,
                                    label=label,
                                    confidence=conf
                                )
                                detections_to_save_this_frame.append(new_detection)
                                print(f"ALERT TRIGGERED: {label} (Gap: {time_since_seen:.2f}s) FPS: {fps:.1f}")

                    # Check if any person is detected
                    person_detected = False
                    for r in results:
                        for c in r.boxes.cls:
                            if self.model.names[int(c)] == 'person':
                                person_detected = True
                                break
                        if person_detected: break
                    
                    # Face Recognition - ONLY if a person is in the frame
                    if person_detected:
                        # Resize frame of video to 1/4 size for faster face recognition processing
                        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                        face_locations = face_recognition.face_locations(rgb_small_frame)
                        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                        face_names = []
                        for face_encoding in face_encodings:
                            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding)
                            name = "Unknown"

                            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
                            if len(face_distances) > 0:
                                best_match_index = np.argmin(face_distances)
                                if matches[best_match_index]:
                                    name = self.known_face_names[best_match_index]

                            face_names.append(name)
                            
                            # Heartbeat for faces
                            face_label = "Face: Unknown" if name == "Unknown" else "Face: Known"
                            last_seen_face = self.last_detection_alert.get(face_label, 0)
                            time_since_seen_face = current_time - last_seen_face
                            self.last_detection_alert[face_label] = current_time
                            
                            if time_since_seen_face > self.ALERT_COOLDOWN:
                                 face_detection = Detection(
                                     camera_id=self.camera_id,
                                     label=face_label,
                                     confidence=1.0
                                 )
                                 detections_to_save_this_frame.append(face_detection)
                                 print(f"ALERT TRIGGERED: {face_label} (Gap: {time_since_seen_face:.2f}s)")
                        
                        last_face_locations = face_locations
                        last_face_names = face_names
                    else:
                        last_face_locations = []
                        last_face_names = []
                        
                    # Save Detections (Immediate)
                    if detections_to_save_this_frame:
                         try:
                             for d in detections_to_save_this_frame:
                                 db.session.add(d)
                             db.session.commit()
                             print(f"Saved {len(detections_to_save_this_frame)} detections.")
                         except Exception as e:
                             print(f"Error saving detections: {e}")
                             db.session.rollback()
                
                # Annotate frame using LAST results (persisted across skipped frames)
                annotated_frame = frame.copy()
                
                # DEBUG VISUALS
                cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if last_results:
                    count = 0
                    for r in last_results:
                        for box in r.boxes:
                            count += 1
                            # Get box coordinates
                            x1, y1, x2, y2 = box.xyxy[0]
                            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                            
                            cls_id = int(box.cls[0])
                            label = self.model.names[cls_id]
                            conf = float(box.conf[0])
                            
                            # Draw THICK Red Box (Force Visibility)
                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            
                            # Draw Label
                            label_text = f"{label} {conf:.2f}"
                            cv2.putText(annotated_frame, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                            
                            # Print coords to helpful debug logs if curious
                            # print(f"DRAWING: {label} at {x1},{y1}-{x2},{y2} Conf:{conf}")

                    cv2.putText(annotated_frame, f"Objects: {count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                # Annotate Faces
                for (top, right, bottom, left), name in zip(last_face_locations, last_face_names):
                    # Scale back up
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4

                    cv2.rectangle(annotated_frame, (left, top), (right, bottom), (0, 255, 0), 2) # Green for faces
                    cv2.rectangle(annotated_frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                    font = cv2.FONT_HERSHEY_DUPLEX
                    cv2.putText(annotated_frame, name, (left + 6, bottom - 6), font, 1.0, (255, 255, 255), 1)

                with self.lock:
                    self.last_frame = annotated_frame
                
                # Small sleep to yield CPU
                time.sleep(0.005)

        cap.release()
