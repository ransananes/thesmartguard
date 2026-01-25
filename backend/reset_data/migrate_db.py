from app import create_app, db
from app.models import NotificationSetting

app = create_app()

with app.app_context():
    print("Creating new database tables...")
    # This will only create tables that don't exist
    db.create_all()
    print("Database schema updated!")
