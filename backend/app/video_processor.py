import cv2
import time
import threading
from ultralytics import YOLO
from .extensions import db
from .models import Detection, Camera
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

    def start_processing(self, camera_id, stream_url):
        if self.processing:
            self.stop_processing()
        
        self.camera_id = camera_id
        self.camera_url = stream_url
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
        
        last_save_time = 0
        save_interval = 2.0  # Save to DB every 2 seconds max
        
        # We need an app context for DB operations
        with self.app.app_context():
            while self.processing and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                # Run inference
                results = self.model(frame, verbose=False)
                
                # Annotate frame
                annotated_frame = results[0].plot()
                
                with self.lock:
                    self.last_frame = annotated_frame
                
                current_time = time.time()
                if current_time - last_save_time > save_interval:
                    for r in results:
                        for box in r.boxes:
                            cls_id = int(box.cls[0])
                            conf = float(box.conf[0])
                            label = self.model.names[cls_id]
                            
                            if conf > 0.5:
                                new_detection = Detection(
                                    camera_id=self.camera_id,
                                    label=label,
                                    confidence=conf
                                )
                                db.session.add(new_detection)
                        
                    try:
                        db.session.commit()
                        last_save_time = current_time
                    except Exception as e:
                        print(f"Error saving detections: {e}")
                        db.session.rollback()

                # Small sleep to yield CPU, but keep frame rate decent
                time.sleep(0.01)

        cap.release()
