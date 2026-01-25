import os
import sys

# Ensure backend directory is in python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Camera

app = create_app()

with app.app_context():
    try:
        # Clear existing cameras
        num_deleted = db.session.query(Camera).delete()
        print(f"Deleted {num_deleted} existing cameras.")
        
        base_dir = os.path.abspath(os.path.dirname(__file__))
        
        # Camera 1
        video1_path = os.path.join(base_dir, 'app', 'static', 'videos', 'video01.mp4')
        if not os.path.exists(video1_path):
             print(f"Error: video01.mp4 not found at {video1_path}")
        else:
            cam1 = Camera(
                name="Video 01",
                location="Main Entrance",
                stream_url=video1_path,
                status="online"
            )
            db.session.add(cam1)

        # Camera 2
        video2_path = os.path.join(base_dir, 'app', 'static', 'videos', 'video02.mp4')
        if not os.path.exists(video2_path):
             print(f"Error: video02.mp4 not found at {video2_path}")
             # Fallback to video01 if missing, for testing? 
             # No, I alread copied it.
        else:
            cam2 = Camera(
                name="Video 02",
                location="Back Alley",
                stream_url=video2_path,
                status="online"
            )
            db.session.add(cam2)
        
        db.session.commit()
        
        print("Database updated successfully.")
        
        # Verify
        cameras = Camera.query.all()
        for c in cameras:
            print(f"Camera ID {c.id}: {c.name} ({c.location})")
            
    except Exception as e:
        db.session.rollback()
        print(f"An error occurred: {e}")
        sys.exit(1)
