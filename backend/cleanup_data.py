from app import create_app, db
from app.models import Detection

app = create_app()

with app.app_context():
    try:
        num_deleted = db.session.query(Detection).delete()
        db.session.commit()
        print(f"Successfully deleted {num_deleted} detection records.")
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting records: {e}")
