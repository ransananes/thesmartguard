from flask import Blueprint, Response, stream_with_context, current_app
import time
from ..models import Camera
from ..video_processor import VideoProcessor

video_bp = Blueprint('video', __name__, url_prefix='/api')

@video_bp.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    def generate():
        if not hasattr(current_app, 'video_processor') or current_app.video_processor is None:
             # Initialize processor if needed
             current_app.video_processor = VideoProcessor(current_app._get_current_object())

        # Check if we need to switch cameras
        if current_app.video_processor.camera_id != camera_id:
            camera = Camera.query.get(camera_id)
            if camera:
                current_app.video_processor.start_processing(camera.id, camera.stream_url)
            else:
                return "Camera not found", 404


        while True:
            frame = current_app.video_processor.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # If no frame, small sleep to prevent CPU spin
                time.sleep(0.1)
                
    return Response(stream_with_context(generate()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
