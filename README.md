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


