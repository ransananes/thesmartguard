"""
VideoProcessor — real-time AI analysis of camera streams.
"""
from __future__ import annotations

import datetime
import logging
import os
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional

import cv2
import face_recognition
import numpy as np
import pickle

from ultralytics import YOLO
import torch

from app.config import Config
from app.extensions import db
from app.models import Detection, Camera, KnownFace, NotificationSetting, User
from app.robot_controller import robot_controller

logger = logging.getLogger(__name__)

_STOP = object()


class VideoProcessor:
    """Manages a single camera stream with real-time AI detection."""

    def __init__(self, app) -> None:
        self.app = app

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f'VideoProcessor using device: {self.device}')

        self.model = YOLO('yolo11n.pt')
        self.model.to(self.device)
        logger.info('YOLO object model loaded')

        self.face_model = YOLO('yolov12n-face.pt')
        self.face_model.to(self.device)
        logger.info('YOLO face model loaded')

        # ── Stream state ────────────────────────────────────────────────
        self.processing = False
        self.camera_id: Optional[int] = None
        self.camera_url: Optional[str] = None
        self.camera_name: str = ''

        # ── Raw frame: written by capture thread every frame, read by get_frame() ──
        self._raw_frame_lock = threading.Lock()
        self._raw_frame: Optional[np.ndarray] = None

        # ── Annotations: written by processing thread after YOLO, read by get_frame() ──
        self._detections_lock = threading.Lock()

        # ── current_faces / current_person_count (for live_status endpoint) ──
        self._frame_lock = threading.Lock()
        self.current_faces: list[str] = []
        self.current_person_count: int = 0

        # ── Inter-thread queues ──────────────────────────────────────────
        self._frame_queue: queue.Queue = queue.Queue(maxsize=Config.FRAME_QUEUE_SIZE)
        self._detection_queue: queue.Queue = queue.Queue(maxsize=Config.DETECTION_QUEUE_SIZE)

        # ── Worker threads ───────────────────────────────────────────────
        self._capture_thread: Optional[threading.Thread] = None
        self._process_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None

        # ── Face recognition ─────────────────────────────────────────────
        self._face_executor = ThreadPoolExecutor(
            max_workers=Config.FACE_EXECUTOR_WORKERS,
            thread_name_prefix='face_enc',
        )
        self.known_face_encodings: list = []
        self.known_face_names: list[str] = []
        self._faces_lock = threading.Lock()
        # dlib (used by face_recognition) is not thread-safe; serialize all calls
        self._face_recognition_lock = threading.Lock()
        # serialize face_model inference — concurrent calls saturate CPU and slow main YOLO
        self._face_model_lock = threading.Lock()
        self._reload_faces_needed = False

        # ── Detection settings ───────────────────────────────────────────
        self.enabled_labels: set[str] = {'person', 'car', 'face: unknown'}
        self.detect_others: bool = False
        self._settings_lock = threading.Lock()

        # ── Cooldown / alert tracking ────────────────────────────────────
        self._last_detection_alert: dict[str, float] = {}
        self._alert_lock = threading.Lock()
        # Recent unknown-face encodings: [(encoding, alerted_at)] for dedup across track_ids
        self._recent_alerted_encodings: list[tuple[np.ndarray, float]] = []

        # track_id → {name, last_seen, face_encoding, last_face_check, future}
        self.track_names: dict[int, dict] = {}

        # ── Robot / auto-follow ──────────────────────────────────────────
        self.auto_follow: bool = False
        self.follow_known_only: bool = False
        self.follow_unknowns: bool = False  # auto-engage robot when unknown person confirmed
        self._last_robot_command_time: float = 0.0
        self._current_follow_target: Optional[str] = None
        self._last_follow_time: float = 0.0       # last frame a follow target was visible
        self._last_follow_command: str = 'S'       # last directional command sent while following
        self._follow_track_id: Optional[int] = None  # locked track — don't switch mid-follow

        # ── Intercept: detection-triggered home-return + scan ────────────
        self._homing: bool = False                       # robot is autonomously returning home
        self._scan_active: bool = False                  # robot arrived home, scanning for target
        self._scan_start_time: float = 0.0
        self._priority_track_id: Optional[int] = None
        self._pre_intercept_follow_unknowns: bool = False

        self._last_detections: list = []   # [(x1,y1,x2,y2,color,text)] published each YOLO frame
        self._last_object_count: int = 0
        self._last_hud: list = []          # [(x, y, text, scale, color, thickness)]

        # ── Unknown-person notification counter ──────────────────────────
        # Incremented each time a track stays Unknown for >= UNKNOWN_NOTIFY_DELAY.
        # The frontend polls live_status and shows a notification when the value rises.
        self._unknown_alert_count: int = 0

        # ── Robot camera ─────────────────────────────────────────────────
        # Separate YOLO instance so its bytetrack state never collides with
        # the main camera's tracker (each instance owns its own predictor/tracker).
        self._robot_model = YOLO('yolo11n.pt')
        self._robot_model.to(self.device)

        self._robot_frame_lock = threading.Lock()
        self._robot_last_frame: Optional[np.ndarray] = None
        self._robot_frame_queue: queue.Queue = queue.Queue(maxsize=Config.FRAME_QUEUE_SIZE)
        self._robot_capture_thread: Optional[threading.Thread] = None
        self._robot_process_thread: Optional[threading.Thread] = None
        self._robot_processing: bool = False
        self._robot_cam_url: Optional[str] = None
        self._robot_track_names: dict[int, dict] = {}
        self._robot_process_frame_counter: int = 0

        # Latest person bounding box seen by the robot camera — used to steer when
        # the main camera has lost the target.  Written by robot thread, read by main thread.
        self._robot_follow_box: Optional[tuple] = None   # (x1, y1, x2, y2, frame_w)
        self._robot_follow_box_time: float = 0.0
        self._robot_follow_lock = threading.Lock()

        # ── Bootstrap ────────────────────────────────────────────────────
        self._perform_face_reload()
        self._reload_settings()
        self._start_writer_thread()

    # ════════════════════════════════════════════════════════════════════
    # Settings
    # ════════════════════════════════════════════════════════════════════

    def _reload_settings(self) -> None:
        with self.app.app_context():
            try:
                user = User.query.filter_by(username='root').first()
                if user:
                    settings = NotificationSetting.query.filter_by(user_id=user.id).all()
                    if settings:
                        self.update_settings(settings)
                        return
                defaults = [
                    {'label': 'person',        'enabled': True},
                    {'label': 'car',           'enabled': True},
                    {'label': 'Face: Unknown', 'enabled': True},
                    {'label': 'Face: Known',   'enabled': True},
                ]
                self.update_settings(defaults)
            except Exception as exc:
                logger.error(f'Failed to load settings on init: {exc}')

    def update_settings(self, settings) -> None:
        new_labels: set[str] = set()
        new_detect_others = False

        for s in settings:
            label   = s.label   if hasattr(s, 'label')   else s.get('label',   '')
            enabled = s.enabled if hasattr(s, 'enabled') else s.get('enabled', False)
            if not enabled:
                continue
            if label == 'Other Objects':
                new_detect_others = True
            else:
                new_labels.add(label.lower())

        with self._settings_lock:
            self.enabled_labels  = new_labels
            self.detect_others   = new_detect_others

        logger.info(f'Settings updated: labels={new_labels}, detect_others={new_detect_others}')

    # ════════════════════════════════════════════════════════════════════
    # Face management
    # ════════════════════════════════════════════════════════════════════

    def reload_faces(self) -> None:
        self._reload_faces_needed = True
        logger.info('Face reload signalled.')

    def _perform_face_reload(self) -> None:
        encodings: list = []
        names: list[str] = []
        try:
            with self.app.app_context():
                faces = KnownFace.query.all()
                for face in faces:
                    names.append(face.name)
                    enc = face.encoding
                    if isinstance(enc, bytes):
                        enc = pickle.loads(enc)
                    encodings.append(enc)
            logger.info(f'Loaded {len(names)} known faces.')
        except Exception as exc:
            logger.error(f'Error loading faces: {exc}')

        with self._faces_lock:
            self.known_face_encodings = encodings
            self.known_face_names     = names

    def detect_faces_in_image(self, image_path: str) -> Optional[list]:
        try:
            img_bgr = cv2.imread(image_path)
            if img_bgr is None:
                return None
            results = self.face_model(img_bgr, verbose=False, conf=Config.FACE_CONF_THRESHOLD)
            locs = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        locs.append((y1, x2, y2, x1))
            return locs if locs else None
        except Exception as exc:
            logger.error(f'YOLO face detection failed: {exc}')
            return None

    # ════════════════════════════════════════════════════════════════════
    # Stream control
    # ════════════════════════════════════════════════════════════════════

    def start_processing(self, camera_id: int, stream_url: str, camera_name: str = 'Camera') -> None:
        if self.processing:
            self.stop_processing()

        self.camera_id   = camera_id
        self.camera_url  = stream_url
        self.camera_name = camera_name

        with self._frame_lock:
            self.current_faces = []
        with self._raw_frame_lock:
            self._raw_frame = None
        with self._detections_lock:
            self._last_detections   = []
            self._last_object_count = 0
            self._last_hud          = []

        self._last_detection_alert.clear()
        self.track_names.clear()
        self.processing = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop, name=f'capture-{camera_id}', daemon=True
        )
        self._process_thread = threading.Thread(
            target=self._processing_loop, name=f'process-{camera_id}', daemon=True
        )
        self._capture_thread.start()
        self._process_thread.start()
        logger.info(f'Started processing: camera={camera_name} id={camera_id} url={stream_url}')

    def stop_processing(self) -> None:
        self.processing = False
        try:
            self._frame_queue.put_nowait(_STOP)
        except queue.Full:
            pass

        for thread in (self._capture_thread, self._process_thread):
            if thread and thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f'Thread {thread.name} did not stop within 5 s')

        self._capture_thread = None
        self._process_thread = None

        with self._raw_frame_lock:
            self._raw_frame = None

        logger.info('Processing stopped.')

    # ════════════════════════════════════════════════════════════════════
    # Frame retrieval
    # ════════════════════════════════════════════════════════════════════

    def get_frame(self) -> Optional[bytes]:
        with self._raw_frame_lock:
            if self._raw_frame is None:
                return None
            raw = self._raw_frame  # capture thread replaces reference, never mutates in-place

        with self._detections_lock:
            detections = self._last_detections
            hud        = self._last_hud

        if detections or hud:
            display = raw.copy()
            for dx1, dy1, dx2, dy2, dcolor, dtext in detections:
                cv2.rectangle(display, (dx1, dy1), (dx2, dy2), dcolor, 2)
                cv2.putText(display, dtext, (dx1, dy1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, dcolor, 2)
            for hx, hy, htext, hscale, hcolor, hthick in hud:
                cv2.putText(display, htext, (hx, hy),
                            cv2.FONT_HERSHEY_SIMPLEX, hscale, hcolor, hthick)
        else:
            display = raw

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, Config.STREAM_JPEG_QUALITY]
        ret, buffer = cv2.imencode('.jpg', display, encode_params)
        return buffer.tobytes() if ret else None

    # ════════════════════════════════════════════════════════════════════
    # Capture thread
    # ════════════════════════════════════════════════════════════════════

    def _capture_loop(self) -> None:
        # Force TCP transport for RTSP streams — prevents UDP packet-loss stalls
        # common on WiFi cameras (ICsee, Dahua, Hikvision, etc.)
        if str(self.camera_url).lower().startswith('rtsp://'):
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;10000000'
            cap = cv2.VideoCapture(self.camera_url, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(self.camera_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # always grab the freshest frame
        if not cap.isOpened():
            logger.error(f'Cannot open stream: {self.camera_url}')
            self.processing = False
            return

        stream_fps = cap.get(cv2.CAP_PROP_FPS)
        if stream_fps <= 0:
            stream_fps = Config.DEFAULT_FPS

        frame_delay = 1.0 / stream_fps
        logger.info(f'Capture thread started: target_fps={stream_fps:.1f}')

        consecutive_failures = 0

        while self.processing:
            start_time = time.time()
            ret, frame = cap.read()

            if not ret:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    logger.warning('Too many read failures — rewinding/reconnecting')
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    consecutive_failures = 0
                else:
                    time.sleep(0.05)
                continue

            consecutive_failures = 0

            with self._raw_frame_lock:
                self._raw_frame = frame

            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass

            elapsed    = time.time() - start_time
            sleep_time = max(0, frame_delay - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        logger.info('Capture thread exited.')

    # ════════════════════════════════════════════════════════════════════
    # Processing thread
    # ════════════════════════════════════════════════════════════════════

    def _processing_loop(self) -> None:
        _frame_counter = 0
        with self.app.app_context():
            while self.processing:
                try:
                    item = self._frame_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is _STOP:
                    break

                frame = item
                _frame_counter += 1

                if self._reload_faces_needed:
                    self._perform_face_reload()
                    self._reload_faces_needed = False
                    with self._faces_lock:
                        valid_names = set(self.known_face_names)
                    for info in self.track_names.values():
                        if info.get('name') not in ('Unknown', 'Checking...') and info.get('name') not in valid_names:
                            info['name'] = 'Unknown'
                            info['future'] = None
                            info['last_face_check'] = 0
                            info['unknown_since'] = time.time()
                            info['notified'] = False

                if _frame_counter % Config.YOLO_PROCESS_EVERY_N_FRAMES != 0:
                    continue  # keep last known _last_detections; get_frame() reuses them

                current_time = time.time()

                # ── Evict stale tracks ───────────────────────────────────
                stale_ids = [
                    tid for tid, info in self.track_names.items()
                    if current_time - info.get('last_seen', 0) > Config.STALE_TRACK_TTL
                ]
                for tid in stale_ids:
                    del self.track_names[tid]

                # ── YOLO tracking (every queued frame — ByteTrack requires it) ──
                try:
                    results = self.model.track(
                        frame,
                        persist=True,
                        verbose=False,
                        conf=Config.YOLO_CONF_THRESHOLD,
                        tracker='bytetrack.yaml',
                        imgsz=Config.YOLO_IMGSZ,
                    )
                except Exception as exc:
                    logger.error(f'Tracking error: {exc}')
                    try:
                        results = self.model(frame, verbose=False, conf=Config.YOLO_CONF_THRESHOLD, imgsz=Config.YOLO_IMGSZ)
                    except Exception as exc2:
                        logger.error(f'Fallback detection error: {exc2}')
                        continue

                object_count = 0
                current_frame_names: list[str] = []
                frame_detections: list = []   # (x1, y1, x2, y2, color, text)
                frame_hud: list = []          # (x, y, text, scale, color, thickness)

                # ── Follow candidates ────────────────────────────────────
                # Tuples are (x1, y1, x2, y2, name, track_id)
                known_target:   Optional[tuple] = None
                unknown_target: Optional[tuple] = None
                max_known_area   = 0
                max_unknown_area = 0
                _sticky_box: Optional[tuple] = None  # current _follow_track_id if still visible

                with self._settings_lock:
                    enabled = set(self.enabled_labels)
                    detect_others = self.detect_others

                for result in results:
                    if result.boxes is None:
                        continue

                    boxes      = result.boxes.xyxy.cpu().numpy()   if result.boxes.xyxy   is not None else []
                    confs      = result.boxes.conf.cpu().numpy()   if result.boxes.conf   is not None else []
                    classes    = result.boxes.cls.cpu().numpy()    if result.boxes.cls    is not None else []
                    track_ids  = (
                        result.boxes.id.cpu().numpy().astype(int)
                        if result.boxes.id is not None
                        else [None] * len(boxes)
                    )

                    for box, conf, cls, track_id in zip(boxes, confs, classes, track_ids):
                        x1, y1, x2, y2 = map(int, box)
                        label = self.model.names[int(cls)]
                        color = (128, 128, 128)
                        display_text = f'{label} {conf:.2f}'

                        object_count += 1

                        if label == 'person':
                            if 'person' not in enabled:
                                continue

                            display_text, color = self._handle_person(
                                frame, x1, y1, x2, y2,
                                conf, track_id, current_time, current_frame_names,
                            )

                            # ── Build follow candidate ───────────────────
                            if (self.auto_follow or self.follow_unknowns) and track_id is not None:
                                area = (x2 - x1) * (y2 - y1)
                                name = self.track_names.get(track_id, {}).get('name', 'Unknown')

                                # Track sticky box for the currently-locked target
                                if track_id == self._follow_track_id:
                                    _sticky_box = (x1, y1, x2, y2, name, track_id)

                                if name not in ('Unknown', 'Checking...'):
                                    if area > max_known_area:
                                        max_known_area = area
                                        known_target   = (x1, y1, x2, y2, name, track_id)
                                else:
                                    if area > max_unknown_area:
                                        max_unknown_area = area
                                        unknown_target   = (x1, y1, x2, y2, name, track_id)

                        else:
                            label_lower = label.lower()
                            if label_lower not in enabled and not detect_others:
                                continue
                            display_text = f'{label} {conf:.2f}'
                            self._queue_object_alert(label, conf, current_time)

                        frame_detections.append((x1, y1, x2, y2, color, display_text))

                frame_hud.append((10, 60, f'Objects: {object_count}', 0.7, (0, 255, 255), 2))

                # ── Auto-follow / follow-unknowns decision ───────────────
                in_follow_mode = self.auto_follow or self.follow_unknowns

                if self._homing:
                    self._current_follow_target = None

                elif in_follow_mode:
                    follow_target = None

                    # Sticky targeting: keep following the same track_id if still visible
                    if _sticky_box is not None:
                        follow_target = _sticky_box
                    else:
                        # Locked target disappeared — release the lock and pick a new one
                        if self._follow_track_id is not None:
                            self._follow_track_id = None

                        if self.auto_follow:
                            follow_target = (
                                known_target
                                if self.follow_known_only
                                else unknown_target
                            )

                        if follow_target is None and self.follow_unknowns:
                            follow_target = unknown_target

                        if follow_target is not None:
                            self._follow_track_id = follow_target[5]

                    if follow_target:
                        fx1, fy1, fx2, fy2, follow_name, follow_tid = follow_target
                        self._current_follow_target = follow_name
                        self._last_follow_time = current_time
                        self._follow_track_id = follow_tid

                        if self._scan_active:
                            self._scan_active = False
                            robot_controller.resume_movement_logging()

                        # Yellow highlight over the follow target, drawn on top of its normal box
                        frame_detections.append((fx1, fy1, fx2, fy2, (255, 255, 0), f'FOLLOWING: {follow_name}'))

                        self._handle_auto_follow((fx1, fy1, fx2, fy2), frame.shape[1])

                    else:
                        self._current_follow_target = None
                        self._follow_track_id = None

                        with self._robot_follow_lock:
                            rbox = self._robot_follow_box
                            rbox_time = self._robot_follow_box_time
                        robot_cam_fresh = (
                            rbox is not None
                            and current_time - rbox_time < Config.FOLLOW_PERSISTENCE_S
                        )

                        if robot_cam_fresh and (self._scan_active or self.follow_unknowns or self.auto_follow):
                            if self._scan_active:
                                self._scan_active = False
                                robot_controller.resume_movement_logging()
                            rx1, ry1, rx2, ry2, rfw = rbox
                            self._last_follow_time = current_time
                            self._handle_auto_follow((rx1, ry1, rx2, ry2), rfw)

                        elif self._scan_active:
                            if current_time - self._scan_start_time > Config.INTERCEPT_SCAN_TIMEOUT:
                                self._end_intercept()
                            elif current_time - self._last_robot_command_time > Config.ROBOT_COMMAND_INTERVAL:
                                robot_controller.send_command('L', force=True)
                                # Re-send before the ESP32's auto-stop so the robot spins
                                # continuously rather than doing a stutter-stop-stutter scan.
                                self._last_robot_command_time = current_time
                        elif current_time - self._last_follow_time < Config.FOLLOW_PERSISTENCE_S:
                            if current_time - self._last_robot_command_time > Config.ROBOT_COMMAND_INTERVAL:
                                robot_controller.send_command(self._last_follow_command, force=True)
                                self._last_robot_command_time = current_time
                        else:
                            if current_time - self._last_robot_command_time > Config.ROBOT_COMMAND_INTERVAL:
                                robot_controller.send_command('S', force=True)
                                self._last_robot_command_time = current_time

                # ── Follow mode HUD ──────────────────────────────────────
                if in_follow_mode:
                    if self.follow_unknowns and not self.auto_follow:
                        mode_label = 'Unknowns auto'
                    elif self.follow_unknowns:
                        mode_label = ('Known only' if self.follow_known_only else 'All') + ' + unknowns auto'
                    else:
                        mode_label = 'Known only' if self.follow_known_only else 'All persons'
                    frame_hud.append((10, 30, f'Follow mode: {mode_label}', 0.6, (0, 200, 255), 2))

                # ── Publish detections + face data ───────────────────────
                with self._detections_lock:
                    self._last_detections   = frame_detections
                    self._last_object_count = object_count
                    self._last_hud          = frame_hud
                with self._frame_lock:
                    self.current_faces        = current_frame_names
                    self.current_person_count = object_count

        logger.info('Processing thread exited.')

    # ════════════════════════════════════════════════════════════════════
    # Person / face handling
    # ════════════════════════════════════════════════════════════════════

    def _handle_person(
        self,
        frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        conf: float,
        track_id: Optional[int],
        current_time: float,
        current_frame_names: list[str],
        *,
        track_dict: Optional[dict] = None,
        fire_alerts: bool = True,
        face_tolerance: Optional[float] = None,
    ) -> tuple[str, tuple]:
        """Unified person/face handler used by both the main camera and robot camera.

        track_dict  – which tracking state dict to use; defaults to self.track_names.
        fire_alerts – when False, skips notifications, alert queue, and robot auto-engage
                      (used for the robot camera to avoid duplicating main-camera alerts).
        """
        tracks = track_dict if track_dict is not None else self.track_names
        color = (0, 0, 255)   # red = unknown

        if track_id is None:
            current_frame_names.append('Unknown')
            return 'person', color

        info = tracks.get(track_id)

        if info is None:
            if conf >= Config.PERSON_CONF_THRESHOLD:
                future = self._face_executor.submit(
                    self._identify_face_in_box, frame.copy(), x1, y1, x2, y2, face_tolerance
                )
                name = 'Checking...'
            else:
                future = None
                name = 'Unknown'
            tracks[track_id] = {
                'name':            name,
                'last_seen':       current_time,
                'face_encoding':   None,
                'face_image_path': None,
                'last_face_check': current_time,
                'future':          future,
                'first_seen':      current_time,
                'robot_engaged':   False,
                'unknown_since':   current_time if name == 'Unknown' else None,
                'notified':        False,
            }
        else:
            info['last_seen'] = current_time

            future: Optional[Future] = info.get('future')
            if future is not None and future.done():
                try:
                    identified_name, enc, image_path = future.result()
                    info['name'] = identified_name
                    if enc is not None:
                        info['face_encoding'] = enc
                    if image_path is not None:
                        info['face_image_path'] = image_path
                except Exception as exc:
                    logger.error(f'Face future error: {exc}')
                    info['name'] = 'Unknown'
                info['future']          = None
                info['last_face_check'] = current_time
                if info['name'] == 'Unknown' and info.get('unknown_since') is None:
                    info['unknown_since'] = current_time

            name = info['name']

            if (
                name == 'Unknown'
                and info.get('future') is None
                and conf >= Config.PERSON_CONF_THRESHOLD
                and current_time - info.get('last_face_check', 0) > Config.UNKNOWN_FACE_RECHECK_INTERVAL
            ):
                info['future'] = self._face_executor.submit(
                    self._identify_face_in_box, frame.copy(), x1, y1, x2, y2, face_tolerance
                )

        name = tracks[track_id]['name']
        current_frame_names.append(name)

        if name not in ('Unknown', 'Checking...'):
            color = (0, 255, 0)   # green = known

        if not fire_alerts:
            return name, color

        self._queue_face_alert(name, track_id, current_time)

        track_info = tracks[track_id]
        if (
            name == 'Unknown'
            and not track_info.get('notified', False)
            and track_info.get('unknown_since') is not None
            and current_time - track_info['unknown_since'] >= Config.UNKNOWN_NOTIFY_DELAY
        ):
            track_info['notified'] = True
            self._unknown_alert_count += 1
            logger.info(
                f'Unknown-person notification fired for track {track_id} '
                f'({current_time - track_info["unknown_since"]:.1f}s unidentified)'
            )

        if (
            self.follow_unknowns
            and not self._homing
            and not self._scan_active
            and self._follow_track_id is None   # don't interrupt an active follow
            and robot_controller.is_connected
            and name == 'Unknown'
            and not track_info.get('robot_engaged', False)
            and track_info.get('unknown_since') is not None
            and current_time - track_info['unknown_since'] >= Config.ROBOT_ENGAGE_DELAY
        ):
            track_info['robot_engaged'] = True
            self._trigger_intercept(track_id)
            logger.info(f'Auto-intercept triggered for unknown track {track_id}')

        return name, color

    # ════════════════════════════════════════════════════════════════════
    # Face identification (runs in thread pool)
    # ════════════════════════════════════════════════════════════════════

    def _identify_face_in_box(
        self, frame: np.ndarray, x1: int, y1: int, x2: int, y2: int,
        face_tolerance: Optional[float] = None,
    ) -> tuple[str, Optional[np.ndarray], Optional[str]]:
        """Two-stage pipeline: YOLO face detect → face_recognition encode → save crop.

        Returns (name, encoding, saved_image_filename).
        """
        h, w = frame.shape[:2]
        person_crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if person_crop.size == 0:
            return 'Unknown', None, None

        # Stage 1: YOLO face model locates the face inside the person crop
        try:
            with self._face_model_lock:
                face_results = self.face_model(
                    person_crop, verbose=False, conf=Config.FACE_CONF_THRESHOLD
                )
        except Exception as exc:
            logger.error(f'Face model inference error: {exc}')
            return 'Unknown', None, None

        face_loc_for_enc = None
        face_crop = None

        for result in face_results:
            if result.boxes is None or len(result.boxes) == 0:
                continue
            best = int(result.boxes.conf.argmax())
            fx1, fy1, fx2, fy2 = map(int, result.boxes.xyxy[best].tolist())

            # Geometric sanity check — hands/fists fail these
            face_w, face_h = fx2 - fx1, fy2 - fy1
            if face_w < 10 or face_h < 10:
                continue
            aspect = face_w / face_h if face_h > 0 else 0
            if not (0.5 <= aspect <= 1.8):
                continue

            # face_recognition expects (top, right, bottom, left) order
            face_loc_for_enc = [(fy1, fx2, fy2, fx1)]
            ch, cw = person_crop.shape[:2]
            pad = 10
            face_crop = person_crop[
                max(0, fy1 - pad):min(ch, fy2 + pad),
                max(0, fx1 - pad):min(cw, fx2 + pad),
            ]
            break

        if face_loc_for_enc is None:
            return 'Unknown', None, None

        # Stage 2: encode the YOLO-detected face region directly.
        # We rely on the size/aspect checks above to reject obvious non-faces.
        # A failed encoding (empty list) is still caught below.
        rgb_crop = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)
        with self._face_recognition_lock:
            encs = face_recognition.face_encodings(rgb_crop, face_loc_for_enc)

        if not encs:
            return 'Unknown', None, None

        face_enc = encs[0]

        # Stage 3: Match against known faces
        with self._faces_lock:
            known_encs  = list(self.known_face_encodings)
            known_names = list(self.known_face_names)

        if known_encs:
            tolerance = face_tolerance if face_tolerance is not None else Config.FACE_TOLERANCE
            distances = face_recognition.face_distance(known_encs, face_enc)
            matches   = face_recognition.compare_faces(known_encs, face_enc, tolerance=tolerance)
            best_idx  = int(np.argmin(distances))
            if matches[best_idx]:
                name = known_names[best_idx]
                logger.info(f'Face match: {name} (dist={distances[best_idx]:.4f})')
            else:
                name = 'Unknown'
                logger.debug(f'No face match (best dist={distances[best_idx]:.4f})')
        else:
            name = 'Unknown'

        # Stage 4: Save the tight face crop
        image_path = (
            self._save_face_image(face_crop)
            if face_crop is not None and face_crop.size > 0
            else None
        )

        return name, face_enc, image_path

    # ════════════════════════════════════════════════════════════════════
    # Auto-follow
    # ════════════════════════════════════════════════════════════════════

    def _handle_auto_follow(self, box: tuple, frame_width: int) -> None:
        current_time = time.time()
        if current_time - self._last_robot_command_time < Config.ROBOT_COMMAND_INTERVAL:
            return

        x1, y1, x2, y2 = box
        center_x  = (x1 + x2) / 2
        deadzone  = frame_width * 0.3
        left_boundary  = (frame_width - deadzone) / 2
        right_boundary = (frame_width + deadzone) / 2

        if center_x < left_boundary:
            command = 'L'
        elif center_x > right_boundary:
            command = 'R'
        else:
            with self._raw_frame_lock:
                frame_height = self._raw_frame.shape[0] if self._raw_frame is not None else 480
            person_height_pct = (y2 - y1) / frame_height
            command = 'F' if person_height_pct < 0.4 else 'S'

        ok, _ = robot_controller.send_command(command, force=True)
        if not ok:
            logger.warning('Auto-follow: robot unreachable — disabling follow modes')
            self.auto_follow = False
            self.follow_unknowns = False
            self._current_follow_target = None
            return
        self._last_follow_command = command

        if command in ('L', 'R'):
            # Let the ESP32's built-in 300 ms auto-stop end the turn — no extra
            # send_command('S') needed.  Block new commands until after auto-stop
            # fires so the camera gets a still frame before the next decision.
            self._last_robot_command_time = current_time + Config.ESP32_AUTO_STOP_MS / 1000.0
        else:
            self._last_robot_command_time = current_time

    def set_auto_follow(self, enabled: bool, known_only: bool = False) -> None:
        self.auto_follow       = enabled
        self.follow_known_only = known_only
        self._current_follow_target = None
        self._follow_track_id = None
        logger.info(f'Auto-follow: {enabled}, known_only: {known_only}')
        if not enabled and not self.follow_unknowns:
            robot_controller.send_command('S', force=True)

    def set_follow_unknowns(self, enabled: bool) -> None:
        self.follow_unknowns = enabled
        self._current_follow_target = None
        self._follow_track_id = None
        logger.info(f'Follow-unknowns: {enabled}')
        if not enabled:
            if self._homing or self._scan_active:
                self._homing = False
                self._scan_active = False
                self._priority_track_id = None
            if not self.auto_follow:
                robot_controller.send_command('S', force=True)

    def get_follow_status(self) -> dict:
        return {
            'auto_follow':      self.auto_follow,
            'known_only':       self.follow_known_only,
            'follow_unknowns':  self.follow_unknowns,
            'follow_target':    self._current_follow_target,
            'homing':           self._homing,
            'scan_active':      self._scan_active,
        }

    # ════════════════════════════════════════════════════════════════════
    # Robot camera processing (face confirmation on robot stream)
    # ════════════════════════════════════════════════════════════════════

    def start_robot_camera_processing(self, cam_url: str) -> None:
        if self._robot_processing:
            self.stop_robot_camera_processing()

        self._robot_cam_url = cam_url
        self._robot_track_names.clear()

        with self._robot_frame_lock:
            self._robot_last_frame = None

        self._robot_processing = True

        self._robot_capture_thread = threading.Thread(
            target=self._robot_capture_loop, name='robot-capture', daemon=True
        )
        self._robot_process_thread = threading.Thread(
            target=self._robot_processing_loop, name='robot-process', daemon=True
        )
        self._robot_capture_thread.start()
        self._robot_process_thread.start()
        logger.info(f'Robot camera processing started: {cam_url}')

    def stop_robot_camera_processing(self) -> None:
        self._robot_processing = False
        try:
            self._robot_frame_queue.put_nowait(_STOP)
        except queue.Full:
            pass

        for thread in (self._robot_capture_thread, self._robot_process_thread):
            if thread and thread.is_alive():
                thread.join(timeout=5)

        self._robot_capture_thread = None
        self._robot_process_thread = None

        with self._robot_frame_lock:
            self._robot_last_frame = None

        with self._robot_follow_lock:
            self._robot_follow_box = None

        logger.info('Robot camera processing stopped.')

    def get_robot_frame(self) -> Optional[bytes]:
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, Config.STREAM_JPEG_QUALITY]
        with self._robot_frame_lock:
            if self._robot_last_frame is None:
                return None
            ret, buffer = cv2.imencode('.jpg', self._robot_last_frame, encode_params)
        return buffer.tobytes() if ret else None

    def _robot_capture_loop(self) -> None:
        reconnect_delay = 5.0

        while self._robot_processing:
            cap = cv2.VideoCapture(self._robot_cam_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                logger.warning('Robot camera: cannot open stream, retrying in %.0fs…', reconnect_delay)
                cap.release()
                time.sleep(reconnect_delay)
                continue

            logger.info('Robot camera capture connected: %s', self._robot_cam_url)
            consecutive_failures = 0

            while self._robot_processing:
                ret, frame = cap.read()
                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures > 15:
                        logger.warning('Robot camera: stream lost — reconnecting…')
                        break
                    time.sleep(0.05)
                    continue
                consecutive_failures = 0

                try:
                    self._robot_frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self._robot_frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._robot_frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass

            cap.release()
            if self._robot_processing:
                logger.info('Robot camera: reconnecting in %.0fs…', reconnect_delay)
                time.sleep(reconnect_delay)

        logger.info('Robot camera capture thread exited.')

    def _robot_processing_loop(self) -> None:
        # Persist last YOLO results so they are drawn on every frame, not just
        # the YOLO frame.  Without this the annotated frame is overwritten by the
        # next raw frame within ~1 ms (the queue is almost always full) and the
        # stream reader at 25 fps never receives a frame that has boxes on it.
        last_detections: list = []   # [(x1, y1, x2, y2, text, color)]

        while self._robot_processing:
            try:
                item = self._robot_frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is _STOP:
                break

            frame = item

            self._robot_process_frame_counter += 1
            if self._robot_process_frame_counter % Config.YOLO_PROCESS_EVERY_N_FRAMES != 0:
                # Skipped frame — redraw last known boxes so detection is always visible
                if last_detections:
                    display = frame.copy()
                    for dx1, dy1, dx2, dy2, dtext, dcolor in last_detections:
                        cv2.rectangle(display, (dx1, dy1), (dx2, dy2), dcolor, 2)
                        cv2.putText(display, dtext, (dx1, dy1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, dcolor, 2)
                    with self._robot_frame_lock:
                        self._robot_last_frame = display
                else:
                    with self._robot_frame_lock:
                        self._robot_last_frame = frame
                continue

            current_time = time.time()

            stale_ids = [
                tid for tid, info in self._robot_track_names.items()
                if current_time - info.get('last_seen', 0) > Config.STALE_TRACK_TTL
            ]
            for tid in stale_ids:
                del self._robot_track_names[tid]

            try:
                results = self._robot_model.track(
                    frame,
                    persist=True,
                    verbose=False,
                    conf=Config.YOLO_CONF_THRESHOLD,
                    tracker='bytetrack.yaml',
                    imgsz=Config.ROBOT_YOLO_IMGSZ,
                )
            except Exception as exc:
                logger.error(f'Robot camera tracking error: {exc}')
                try:
                    results = self._robot_model(frame, verbose=False, conf=Config.YOLO_CONF_THRESHOLD, imgsz=Config.ROBOT_YOLO_IMGSZ)
                except Exception:
                    continue

            try:
                annotated = frame.copy()
                best_area = 0
                best_person_box: Optional[tuple] = None
                frame_detections: list = []

                for result in results:
                    if result.boxes is None:
                        continue

                    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes.xyxy is not None else []
                    confs = result.boxes.conf.cpu().numpy() if result.boxes.conf is not None else []
                    classes = result.boxes.cls.cpu().numpy() if result.boxes.cls is not None else []
                    track_ids = (
                        result.boxes.id.cpu().numpy().astype(int)
                        if result.boxes.id is not None
                        else [None] * len(boxes)
                    )

                    for box, conf, cls, track_id in zip(boxes, confs, classes, track_ids):
                        x1, y1, x2, y2 = map(int, box)
                        label = self._robot_model.names[int(cls)]

                        if label != 'person':
                            continue

                        display_text, color = self._handle_robot_person(
                            frame, x1, y1, x2, y2, conf, track_id, current_time
                        )

                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated, display_text, (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                        frame_detections.append((x1, y1, x2, y2, display_text, color))

                        area = (x2 - x1) * (y2 - y1)
                        if area > best_area:
                            best_area = area
                            best_person_box = (x1, y1, x2, y2, frame.shape[1])

                # Always update: clears stale boxes when no person is detected
                last_detections = frame_detections

                with self._robot_follow_lock:
                    self._robot_follow_box = best_person_box
                    if best_person_box is not None:
                        self._robot_follow_box_time = current_time

                with self._robot_frame_lock:
                    self._robot_last_frame = annotated

            except Exception as exc:
                logger.error(f'Robot camera frame processing error: {exc}', exc_info=True)

        logger.info('Robot camera processing thread exited.')

    def _handle_robot_person(
        self,
        frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        conf: float,
        track_id: Optional[int],
        current_time: float,
    ) -> tuple[str, tuple]:
        return self._handle_person(
            frame, x1, y1, x2, y2, conf, track_id, current_time,
            current_frame_names=[],
            track_dict=self._robot_track_names,
            fire_alerts=False,
            face_tolerance=Config.ROBOT_FACE_TOLERANCE,
        )

    def check_obstacle(self, frame: np.ndarray) -> Optional[str]:
        """
        Run a quick YOLO pass on a robot-camera frame.
        Returns 'L' or 'R' to steer around a close obstacle, None if path is clear.
        Only flags objects that are large (close) and centred in the frame.
        """
        try:
            results = self.model(frame, verbose=False, conf=0.45, imgsz=Config.YOLO_IMGSZ)
            if not results or results[0].boxes is None:
                return None
            h, w = frame.shape[:2]
            cx1, cx2 = w * 0.25, w * 0.75
            for box in results[0].boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = map(int, box)
                box_cx      = (x1 + x2) / 2
                box_h_pct   = (y2 - y1) / h
                if cx1 < box_cx < cx2 and box_h_pct > 0.35:
                    # Steer away from the obstacle toward the emptier side
                    return 'R' if box_cx < w / 2 else 'L'
            return None
        except Exception:
            return None

    def start_return_home(self) -> bool:
        """Manual return to home — suppresses follow commands during the return."""
        if self._homing:
            return False
        self._homing = True
        started = robot_controller.return_to_home(
            on_complete=self._on_manual_home_reached,
        )
        if not started:
            self._homing = False
        return started

    def _on_manual_home_reached(self) -> None:
        self._homing = False
        robot_controller.resume_movement_logging()
        logger.info('Manual return to home: complete')

    def _trigger_intercept(self, track_id: int) -> None:
        """Return to camera home position then scan for the detected target."""
        self._priority_track_id = track_id
        self._pre_intercept_follow_unknowns = self.follow_unknowns
        self._homing = True
        logger.info(f'Intercept triggered for track {track_id} — returning to home')

        started = robot_controller.return_to_home(
            on_complete=self._on_home_reached,
        )
        if not started:
            # Not connected or log empty — skip homing and go straight to scan
            self._homing = False
            self._on_home_reached()

    def _on_home_reached(self) -> None:
        """Called when the robot has finished its return-to-home sequence."""
        self._homing = False
        robot_controller.pause_movement_logging()   # scan turns must not enter the path log
        self.follow_unknowns = True
        self._scan_active = True
        self._scan_start_time = time.time()
        logger.info('Intercept: home reached — rotating to scan for target')

    def _end_intercept(self) -> None:
        """Cancel the intercept and restore pre-intercept follow state."""
        self._scan_active = False
        self._priority_track_id = None
        self._follow_track_id = None
        self.follow_unknowns = self._pre_intercept_follow_unknowns
        robot_controller.send_command('S', force=True)
        robot_controller.resume_movement_logging()
        logger.info('Intercept: ended (scan timeout)')

    # ════════════════════════════════════════════════════════════════════
    # Alert helpers
    # ════════════════════════════════════════════════════════════════════

    def _queue_object_alert(self, label: str, conf: float, current_time: float) -> None:
        alert_key = f'Object:{label}'
        with self._alert_lock:
            last_seen = self._last_detection_alert.get(alert_key, 0)
            if current_time - last_seen < Config.ALERT_COOLDOWN:
                return
            self._last_detection_alert[alert_key] = current_time

        det = Detection(
            camera_id=self.camera_id,
            label=f'Object: {label}',
            confidence=conf,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        self._enqueue_detection(det)

    def _queue_face_alert(
        self,
        name: str,
        track_id: int,
        current_time: float,
    ) -> None:
        # Wait until identification is complete and a face image was captured
        if name == 'Checking...':
            return

        image_path = self.track_names.get(track_id, {}).get('face_image_path')
        if image_path is None:
            return

        alert_category = 'face: unknown' if name == 'Unknown' else 'face: known'

        with self._settings_lock:
            if alert_category not in self.enabled_labels:
                return

        if name != 'Unknown':
            # Known face: dedup by name so the same person doesn't re-alert on a new track_id
            alert_key = f'face:{name}'
            with self._alert_lock:
                if current_time - self._last_detection_alert.get(alert_key, 0) < Config.ALERT_COOLDOWN:
                    return
                self._last_detection_alert[alert_key] = current_time
        else:
            # Unknown face: dedup by track_id AND by encoding similarity across track_ids
            alert_key = f'track:{track_id}'
            face_enc = self.track_names.get(track_id, {}).get('face_encoding')
            with self._alert_lock:
                if current_time - self._last_detection_alert.get(alert_key, 0) < Config.ALERT_COOLDOWN:
                    return
                # Evict stale entries then check if this face was recently alerted
                self._recent_alerted_encodings = [
                    (enc, t) for enc, t in self._recent_alerted_encodings
                    if current_time - t < Config.ALERT_COOLDOWN
                ]
                if face_enc is not None:
                    for enc, _ in self._recent_alerted_encodings:
                        if face_recognition.face_distance([enc], face_enc)[0] < Config.FACE_TOLERANCE:
                            return
                    self._recent_alerted_encodings.append((face_enc, current_time))
                self._last_detection_alert[alert_key] = current_time

        logger.info(f'[FACE ALERT] {name} (track={track_id})')

        det = Detection(
            camera_id=self.camera_id,
            label=f'Face: {name}',
            confidence=1.0,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            image_path=image_path,
        )
        self._enqueue_detection(det)

    def _save_face_image(self, img: np.ndarray) -> Optional[str]:
        filename = f'face_{uuid.uuid4()}.jpg'
        filepath = os.path.join(Config.STORAGE_ROOT, 'detections', filename)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            cv2.imwrite(filepath, img)
            return filename
        except Exception as exc:
            logger.error(f'Error saving face image: {exc}')
            return None

    def _enqueue_detection(self, detection: Detection) -> None:
        try:
            self._detection_queue.put_nowait(detection)
        except queue.Full:
            logger.warning('Detection queue full — dropping oldest entry')
            try:
                self._detection_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._detection_queue.put_nowait(detection)
            except queue.Full:
                pass

    # ════════════════════════════════════════════════════════════════════
    # DB writer thread
    # ════════════════════════════════════════════════════════════════════

    def _start_writer_thread(self) -> None:
        self._writer_thread = threading.Thread(
            target=self._db_writer_loop, name='db-writer', daemon=True
        )
        self._writer_thread.start()
        logger.info('DB writer thread started.')

    def _db_writer_loop(self) -> None:
        with self.app.app_context():
            while True:
                batch: list[Detection] = []
                try:
                    first = self._detection_queue.get(timeout=2.0)
                except queue.Empty:
                    continue

                if first is _STOP:
                    break

                batch.append(first)

                while True:
                    try:
                        item = self._detection_queue.get_nowait()
                        if item is _STOP:
                            break
                        batch.append(item)
                    except queue.Empty:
                        break

                if not batch:
                    continue

                try:
                    for det in batch:
                        db.session.add(det)
                    db.session.commit()
                    logger.debug(f'DB writer committed {len(batch)} detection(s).')
                except Exception as exc:
                    logger.error(f'DB writer commit error: {exc}')
                    db.session.rollback()

        logger.info('DB writer thread exited.')

    # ════════════════════════════════════════════════════════════════════
    # Data management
    # ════════════════════════════════════════════════════════════════════

    def clear_all_data(self) -> None:
        self.track_names.clear()
        self._last_detection_alert.clear()
        with self._frame_lock:
            self.current_faces = []

        with self.app.app_context():
            try:
                n_det   = Detection.query.delete()
                n_faces = KnownFace.query.delete()
                db.session.commit()
                logger.info(f'Cleared DB: {n_det} detections, {n_faces} faces')
                with self._faces_lock:
                    self.known_face_encodings = []
                    self.known_face_names     = []
            except Exception as exc:
                db.session.rollback()
                logger.error(f'Error clearing DB: {exc}')

        storage_root = Config.STORAGE_ROOT
        for folder in ('detections', 'faces'):
            folder_path = os.path.join(storage_root, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in os.listdir(folder_path):
                if fname.endswith('.jpg'):
                    try:
                        os.remove(os.path.join(folder_path, fname))
                    except OSError:
                        pass
        logger.info('Disk images cleared.')