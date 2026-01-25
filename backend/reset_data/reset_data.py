import os
import shutil
from app import create_app, db
from app.models import Detection, KnownFace

def reset_data():
    app = create_app()
    with app.app_context():
        # Clear Database
        print("Clearing database tables...")
        try:
            num_detections = db.session.query(Detection).delete()
            num_faces = db.session.query(KnownFace).delete()
            db.session.commit()
            print(f"Deleted {num_detections} detections and {num_faces} faces from database.")
        except Exception as e:
            db.session.rollback()
            print(f"Error clearing database: {e}")
            return

        # Clear Files
        def clean_directory(folder_name):
            folder_path = os.path.join(app.root_path, 'static', folder_name)
            if not os.path.exists(folder_path):
                print(f"Directory {folder_path} does not exist, skipping.")
                return
            
            print(f"Cleaning {folder_path}...")
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'Failed to delete {file_path}. Reason: {e}')

        clean_directory('detections')
        clean_directory('faces')
        
        print("Reset complete.")

if __name__ == "__main__":
    reset_data()
