from app import create_app, db
from app.models import User, Camera

app = create_app()

with app.app_context():
    print("Creating database tables...")
    db.create_all()

    # Create Root User if not exists
    if not User.query.filter_by(username='root').first():
        print("Creating root user...")
        # In a real app, hash this password!
        user = User(username='root', role='admin')
        user.set_password('root')
        db.session.add(user)
    
    # Create Seed Cameras
    if not Camera.query.first():
        print("Seeding cameras...")
        cameras = [
            Camera(name='Main Gate', location='North Perimeter', stream_url='https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8'),
            Camera(name='Lobby', location='Entrance Hall', stream_url='https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8'),
            Camera(name='Parking Lot', location='South Zone', stream_url='https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8')
        ]
        db.session.add_all(cameras)

    db.session.commit()
    print("Database seeded successfully!")
