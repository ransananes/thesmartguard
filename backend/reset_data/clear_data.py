from app import create_app
from app.extensions import db
from app.video_processor import VideoProcessor

app = create_app()
with app.app_context():
    print("Initializing VideoProcessor...")
    # Mocking app context for video processor init if needed, but we just need clear_all_data
    # Actually VideoProcessor needs app to be passed in invalid state? 
    # Just manual init
    vp = VideoProcessor(app)
    
    print("Calling clear_all_data()...")
    vp.clear_all_data()
    print("Done.")
