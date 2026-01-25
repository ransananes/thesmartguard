from flask import Blueprint, Response, stream_with_context, current_app, jsonify, request
import time
from app.models import Camera, Detection
from app.video_processor import VideoProcessor

video_bp = Blueprint('video', __name__, url_prefix='/api')

@video_bp.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    def generate():
        if not hasattr(current_app, 'video_processor') or current_app.video_processor is None:
             current_app.video_processor = VideoProcessor(current_app._get_current_object())


        if current_app.video_processor.camera_id != camera_id:
            camera = Camera.query.get(camera_id)
            if camera:
                current_app.video_processor.start_processing(camera.id, camera.stream_url, camera.name)
            else:
                return "Camera not found", 404


        while True:
            frame = current_app.video_processor.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:

                time.sleep(0.1)
                
    return Response(stream_with_context(generate()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@video_bp.route('/live_status')
def live_status():
    if not hasattr(current_app, 'video_processor') or current_app.video_processor is None:
         return {"person_count": 0, "faces": []}
         
    with current_app.video_processor.lock:
        faces = current_app.video_processor.current_faces
        person_count = current_app.video_processor.current_person_count
        
    return {
        "person_count": person_count,
        "faces": faces
    }

@video_bp.route('/detections', methods=['GET'])
def get_recent_detections():

    try:
        detections = Detection.query.filter(Detection.image_path != None).order_by(Detection.timestamp.desc()).limit(50).all()
        return jsonify({'success': True, 'detections': [d.to_dict() for d in detections]})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
