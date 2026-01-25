import os
import sys

from app import create_app
from app.extensions import db
from app.models import Camera

app = create_app()

with app.app_context():
    try:
        num_deleted = db.session.query(Camera).delete()
        print(f"Deleted {num_deleted} existing cameras.")
        
        base_dir = os.path.abspath(os.path.dirname(__file__))
        video_path = os.path.join(base_dir, 'app', 'static', 'videos', 'video01.mp4')
        
        if not os.path.exists(video_path):
            print(f"Error: Video file not found at {video_path}")
            sys.exit(1)
            
        print(f"Video found at: {video_path}")

        new_camera = Camera(
            name="Video 01",
            location="Local File",
            stream_url=video_path,
            status="online"
        )
        
        db.session.add(new_camera)
        db.session.commit()
        
        print("Database updated successfully: Added 'Video 01'.")
        
        cameras = Camera.query.all()
        for c in cameras:
            print(f"Camera: {c.name}, URL: {c.stream_url}")
            
    except Exception as e:
        db.session.rollback()
        print(f"An error occurred: {e}")
        sys.exit(1)
