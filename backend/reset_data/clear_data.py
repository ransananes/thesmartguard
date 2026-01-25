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
