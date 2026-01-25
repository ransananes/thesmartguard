import sys
import os
import face_recognition
import numpy as np
from app import create_app
from app.models import Detection, KnownFace
from app.extensions import db

# Initialize Flask App
app = create_app()

def debug_cleanup_logic(detection_id):
    with app.app_context():
        # 1. Get the source detection (the one we want to turn into a KnownFace)
        source_det = Detection.query.get(detection_id)
        if not source_det:
            print("Source detection not found.")
            return

        print(f"Source Detection: ID={source_det.id}, Path={source_det.image_path}")
        
        # Load encoding for source
        source_real_path = os.path.join(app.root_path, 'static', 'detections', source_det.image_path)
        if not os.path.exists(source_real_path):
             print(f"File missing at {source_real_path}")
             return
             
        source_img = face_recognition.load_image_file(source_real_path)
        source_encs = face_recognition.face_encodings(source_img)
        
        if not source_encs:
            print("No face found in source image!")
            return
            
        source_encoding = source_encs[0]
        
        # 2. Find other "Unknown" faces
        unknowns = Detection.query.filter_by(label="Face: Unknown").all()
        print(f"Found {len(unknowns)} total unknown detections.")
        
        for d in unknowns:
            if d.id == source_det.id:
                continue
                
            if not d.image_path:
                print(f"Skipping {d.id} (no image)")
                continue
                
            d_path = os.path.join(app.root_path, 'static', 'detections', d.image_path)
            if not os.path.exists(d_path):
                print(f"File missing for {d.id} at {d_path}")
                continue
                
            try:
                d_img = face_recognition.load_image_file(d_path)
                d_encs = face_recognition.face_encodings(d_img)
                
                if not d_encs:
                    print(f"No face in {d.id}")
                    continue
                    
                match = face_recognition.compare_faces([source_encoding], d_encs[0], tolerance=0.6)
                dist = face_recognition.face_distance([source_encoding], d_encs[0])
                
                print(f"Comparing {source_det.id} vs {d.id}: Match={match[0]}, Dist={dist[0]}")
                
            except Exception as e:
                print(f"Error checking {d.id}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_cleanup.py <detection_id_to_add>")
    else:
        debug_cleanup_logic(int(sys.argv[1]))
