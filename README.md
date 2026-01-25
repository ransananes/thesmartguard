# The Smart Guard 🛡️

A real-time intelligent security monitoring system with face recognition, object detection, and live video streaming capabilities.

## 🎯 Features

### Core Functionality
- **Live Video Streaming** - Stream video feeds from local files or IP cameras via MJPEG
- **Object Detection** - Real-time detection using YOLOv8 (persons, cars, animals, etc.)
- **Face Recognition** - Identify known faces and flag unknown individuals
- **Alert System** - Configurable notifications based on detection types
- **Multi-Camera Support** - Manage multiple camera feeds simultaneously

### Face Management
- Add known faces via image upload or from detected unknowns
- Per-user face isolation (users manage their own known faces)
- Automatic duplicate detection cleanup using image hashing

### Dashboard
- Real-time statistics (detections, alerts, active cameras)
- Live detection feed with face thumbnails
- Detection history with filtering by settings
- Camera selector with live preview

## 🏗️ Architecture

```
TheSmartGuard/
├── backend/                 # Flask REST API
│   ├── app/
│   │   ├── __init__.py     # App factory
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── extensions.py   # Flask extensions (db, jwt)
│   │   ├── video_processor.py  # Video processing & detection
│   │   └── routes/
│   │       ├── auth.py     # Authentication endpoints
│   │       ├── cameras.py  # Camera management
│   │       ├── video.py    # Video streaming
│   │       ├── monitor.py  # Stats & history
│   │       ├── faces.py    # Face management
│   │       └── settings.py # User settings
│   ├── storage/            # Persistent storage
│   │   ├── detections/     # Detection thumbnails
│   │   └── faces/          # Known face images
│   ├── reset_data/         # Data management scripts
│   └── run.py              # Entry point
│
└── frontend/               # React SPA
    └── src/
        ├── pages/
        │   ├── Login.jsx         # Auth screen
        │   └── StatusMonitor.jsx # Main dashboard
        ├── components/
        │   ├── VideoPlayer.jsx     # MJPEG stream viewer
        │   ├── RecognizedFaces.jsx # Face management UI
        │   ├── AddCameraModal.jsx  # Camera creation
        │   └── SettingsModal.jsx   # Notification settings
        └── services/
            └── api.js        # Backend API client
```

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|------------|---------|
| Flask | REST API framework |
| SQLAlchemy | ORM & database |
| SQLite | Data storage |
| Flask-JWT-Extended | Authentication |
| OpenCV | Video capture & processing |
| YOLOv8 | Object detection |
| face_recognition | Face encoding & matching |
| imagehash | Duplicate detection |

### Frontend
| Technology | Purpose |
|------------|---------|
| React | UI framework |
| Vite | Build tool |
| TailwindCSS | Styling |
| Framer Motion | Animations |
| Lucide React | Icons |
| React Hot Toast | Notifications |

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Node.js 18+
- CMake (for dlib/face_recognition)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from app import create_app; from app.extensions import db; app = create_app(); app.app_context().push(); db.create_all()"

# Seed initial user
python reset_data/seed_db.py

# Run the server
flask run
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Default Login
- **Username:** `root`
- **Password:** `root`

## 📡 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/login` | User login, returns JWT |
| GET | `/api/verify` | Verify token validity |

### Cameras
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras` | List all cameras |
| POST | `/api/cameras` | Add new camera |
| DELETE | `/api/cameras/:id` | Remove camera |

### Video
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/video_feed/:id` | MJPEG stream for camera |
| GET | `/api/live_status` | Current person count & faces |
| GET | `/api/detections` | Recent detections with images |

### Faces
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/faces` | List known faces (per user) |
| POST | `/api/faces` | Add face via image upload |
| POST | `/api/faces/from_detection` | Add face from detection |
| DELETE | `/api/faces/:id` | Remove known face |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings/notifications` | Get notification settings |
| POST | `/api/settings/notifications` | Update settings |
| POST | `/api/settings/reset-system` | Clear all data |

## ⚙️ Configuration

### Detection Labels
Configure which detections trigger alerts in Settings:
- `person` - Human detection
- `car` - Vehicle detection
- `Face: Unknown` - Unrecognized face
- `Face: Known` - Recognized face
- `cat`, `dog`, `bird`, `horse` - Animal detection

### Adding Cameras
Cameras can be added with:
- **Local video files** - Full path to .mp4 files
- **IP cameras** - RTSP or HTTP streams
- **Webcams** - Device index (0, 1, etc.)

## 🔧 Utility Scripts

Located in `backend/reset_data/`:

| Script | Purpose |
|--------|---------|
| `seed_db.py` | Create initial root user |
| `migrate_db.py` | Run database migrations |
| `setup_video01.py` | Setup single test camera |
| `setup_cameras.py` | Setup multiple test cameras |
| `clear_data.py` | Clear all detections and faces |
| `debug_cleanup.py` | Debug face comparison logic |

## 📊 Database Models

### User
- `id`, `username`, `password_hash`, `role`

### Camera
- `id`, `name`, `location`, `ip_address`, `port`, `stream_url`, `status`

### Detection
- `id`, `camera_id`, `label`, `confidence`, `image_path`, `timestamp`

### KnownFace
- `id`, `name`, `encoding`, `image_path`, `user_id`, `created_at`

### NotificationSetting
- `id`, `user_id`, `label`, `enabled`

## 🔒 Security Features

- JWT-based authentication with secure token handling
- Password hashing using Werkzeug
- Per-user data isolation for face management
- Protected API routes with `@jwt_required()` decorator

## 🎨 UI Features

- Modern glassmorphism design
- Dark mode interface
- Responsive layout (desktop/tablet)
- Real-time updates with polling
- Smooth animations and transitions
- Live video feed with FPS overlay

## 📝 License

This project is proprietary software.

---

**Developed by:** Ran Sana'anes  
**Version:** 1.0.0
