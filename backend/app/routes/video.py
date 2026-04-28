from flask import Blueprint, Response, stream_with_context, current_app, jsonify, request
import time
from app.models import Camera, Detection
from app.extensions import db

video_bp = Blueprint('video', __name__, url_prefix='/api')


@video_bp.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    def generate():
        vp = getattr(current_app, 'video_processor', None)
        if vp is None:
            return

        if vp.camera_id != camera_id:
            camera = db.session.get(Camera, camera_id)
            if camera is None:
                return
            vp.start_processing(camera.id, camera.stream_url, camera.name)

        while True:
            frame = vp.get_frame()
            if frame:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
            else:
                time.sleep(0.05)

    return Response(
        stream_with_context(generate()),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )


@video_bp.route('/live_status')
def live_status():
    vp = getattr(current_app, 'video_processor', None)
    if vp is None:
        return jsonify({'person_count': 0, 'faces': []})

    with vp._frame_lock:
        faces = list(vp.current_faces)
        person_count = vp.current_person_count

    return jsonify({'person_count': person_count, 'faces': faces})


@video_bp.route('/detections', methods=['GET'])
def get_recent_detections():
    detections = (
        Detection.query
        .filter(Detection.image_path.isnot(None))
        .order_by(Detection.timestamp.desc())
        .limit(50)
        .all()
    )
    return jsonify({'success': True, 'detections': [d.to_dict() for d in detections]})
