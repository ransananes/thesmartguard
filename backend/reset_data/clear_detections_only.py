import sys
import os

# Add the backend directory to sys.path so 'app' can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

from app import create_app
from app.extensions import db
from app.models import Detection
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    app = create_app()

    with app.app_context():
        try:
            # Delete from DB
            num_deleted = Detection.query.delete()
            db.session.commit()
            logger.info(f"Deleted {num_deleted} detection records from database.")
            
            # Delete files
            storage_root = os.path.join(os.path.dirname(app.root_path), 'storage')
            det_folder = os.path.join(storage_root, 'detections')
            
            if os.path.exists(det_folder):
                files = [f for f in os.listdir(det_folder) if f.endswith('.jpg')]
                count = 0
                for f in files:
                    try:
                        os.remove(os.path.join(det_folder, f))
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {f}: {e}")
                logger.info(f"Deleted {count} detection images from disk.")
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error executing deletion: {e}")
