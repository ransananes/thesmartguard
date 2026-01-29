import sys
import os

# Add the backend directory to sys.path so 'app' can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

from app import create_app
from app.extensions import db
from app.video_processor import VideoProcessor
import logging
logger = logging.getLogger(__name__)

app = create_app()
with app.app_context():
    logger.info("Initializing VideoProcessor...")
    vp = VideoProcessor(app)
    
    logger.info("Calling clear_all_data()...")
    vp.clear_all_data()
    logger.info("Done.")
