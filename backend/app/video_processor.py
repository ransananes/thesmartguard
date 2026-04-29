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

        self.model = YOLO('yolov8n.pt')
        self.model.to(self.device)
        logger.info('YOLO object model loaded')

        self.face_model = YOLO('yolov8n-face.pt')
        self.face_model.to(self.device)
        logger.info('YOLO face model loaded')

        # ── Stream state ────────────────────────────────────────────────
        self.processing = False
        self.camera_id: Optional[int] = None
        self.camera_url: Optional[str] = None
        self.camera_name: str = ''

        # ── Shared frame (written by processing thread, read by route) ──
        self._frame_lock = threading.Lock()
        self._last_frame: Optional[np.ndarray] = None
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
        self._reload_faces_needed = False

        # ── Detection settings ───────────────────────────────────────────
        self.enabled_labels: set[str] = {'person', 'car', 'face: unknown'}
        self.detect_others: bool = False
        self._settings_lock = threading.Lock()

        # ── Cooldown / alert tracking ────────────────────────────────────
        self._last_detection_alert: dict[str, float] = {}
        self._alert_lock = threading.Lock()

        # track_id → {name, last_seen, face_encoding, last_face_check, future}
        self.track_names: dict[int, dict] = {}

        # ── Robot / auto-follow ──────────────────────────────────────────
        self.auto_follow: bool = False
        self.follow_known_only: bool = False          # NEW: only chase known faces
        self._last_robot_command_time: float = 0.0
        self._current_follow_target: Optional[str] = None  # NEW: name being followed

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
            self._last_frame   = None
            self.current_faces = []

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

        with self._frame_lock:
            self._last_frame = None

        logger.info('Processing stopped.')

    # ════════════════════════════════════════════════════════════════════
    # Frame retrieval
    # ════════════════════════════════════════════════════════════════════

    def get_frame(self) -> Optional[bytes]:
        with self._frame_lock:
            if self._last_frame is None:
                return None
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, Config.STREAM_JPEG_QUALITY]
        with self._frame_lock:
            ret, buffer = cv2.imencode('.jpg', self._last_frame, encode_params)
        return buffer.tobytes() if ret else None

    # ════════════════════════════════════════════════════════════════════
    # Capture thread
    # ════════════════════════════════════════════════════════════════════

    def _capture_loop(self) -> None:
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
        with self.app.app_context():
            while self.processing:
                try:
                    item = self._frame_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is _STOP:
                    break

                frame = item

                if self._reload_faces_needed:
                    self._perform_face_reload()
                    self._reload_faces_needed = False

                current_time = time.time()

                # ── Evict stale tracks ───────────────────────────────────
                stale_ids = [
                    tid for tid, info in self.track_names.items()
                    if current_time - info.get('last_seen', 0) > Config.STALE_TRACK_TTL
                ]
                for tid in stale_ids:
                    del self.track_names[tid]

                # ── YOLO tracking ────────────────────────────────────────
                try:
                    results = self.model.track(
                        frame,
                        persist=True,
                        verbose=False,
                        conf=Config.YOLO_CONF_THRESHOLD,
                        tracker='bytetrack.yaml',
                    )
                except Exception as exc:
                    logger.error(f'Tracking error: {exc}')
                    try:
                        results = self.model(frame, verbose=False, conf=Config.YOLO_CONF_THRESHOLD)
                    except Exception as exc2:
                        logger.error(f'Fallback detection error: {exc2}')
                        continue

                annotated    = frame.copy()
                object_count = 0
                current_frame_names: list[str] = []

                # ── Follow candidates ────────────────────────────────────
                # known_target  → (x1,y1,x2,y2, name)  best known face seen
                # unknown_target→ (x1,y1,x2,y2, name)  largest unknown person
                known_target:   Optional[tuple] = None
                unknown_target: Optional[tuple] = None
                max_known_area   = 0
                max_unknown_area = 0

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
                                track_id, current_time, current_frame_names,
                            )

                            # ── Build follow candidate ───────────────────
                            if self.auto_follow and track_id is not None:
                                area = (x2 - x1) * (y2 - y1)
                                name = self.track_names.get(track_id, {}).get('name', 'Unknown')

                                if name not in ('Unknown', 'Checking...'):
                                    # Known face — highest priority
                                    if area > max_known_area:
                                        max_known_area = area
                                        known_target   = (x1, y1, x2, y2, name)
                                else:
                                    # Unknown person — fallback
                                    if area > max_unknown_area:
                                        max_unknown_area = area
                                        unknown_target   = (x1, y1, x2, y2, name)

                        else:
                            label_lower = label.lower()
                            if label_lower not in enabled and not detect_others:
                                continue
                            display_text = f'{label} {conf:.2f}'
                            self._queue_object_alert(label, conf, current_time)

                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(
                            annotated, display_text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                        )

                cv2.putText(
                    annotated, f'Objects: {object_count}', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
                )

                # ── Auto-follow decision ─────────────────────────────────
                if self.auto_follow:
                    # Decide which target to chase
                    if self.follow_known_only:
                        # Only recognised faces — ignore strangers
                        follow_target = known_target
                    else:
                        # Known face takes priority; fall back to any person
                        follow_target = known_target or unknown_target

                    if follow_target:
                        fx1, fy1, fx2, fy2, follow_name = follow_target
                        self._current_follow_target = follow_name

                        # Draw a distinct cyan box around the chosen target
                        cv2.rectangle(annotated, (fx1, fy1), (fx2, fy2), (255, 255, 0), 3)
                        cv2.putText(
                            annotated,
                            f'FOLLOWING: {follow_name}',
                            (fx1, fy1 - 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2,
                        )
                        self._handle_auto_follow((fx1, fy1, fx2, fy2), frame.shape[1])

                    else:
                        self._current_follow_target = None
                        # No target visible — stop the robot
                        if current_time - self._last_robot_command_time > Config.ROBOT_COMMAND_INTERVAL:
                            robot_controller.send_command('S')
                            self._last_robot_command_time = current_time

                # ── Follow mode HUD ──────────────────────────────────────
                if self.auto_follow:
                    mode_label = 'Known only' if self.follow_known_only else 'All persons'
                    cv2.putText(
                        annotated,
                        f'Follow mode: {mode_label}',
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2,
                    )

                # ── Publish annotated frame ──────────────────────────────
                with self._frame_lock:
                    self._last_frame         = annotated
                    self.current_faces       = current_frame_names
                    self.current_person_count = object_count

        logger.info('Processing thread exited.')

    # ════════════════════════════════════════════════════════════════════
    # Person / face handling
    # ════════════════════════════════════════════════════════════════════

    def _handle_person(
        self,
        frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        track_id: Optional[int],
        current_time: float,
        current_frame_names: list[str],
    ) -> tuple[str, tuple]:
        color = (0, 0, 255)   # red = unknown

        if track_id is None:
            current_frame_names.append('Unknown')
            return 'person', color

        info = self.track_names.get(track_id)

        if info is None:
            future = self._face_executor.submit(
                self._identify_face_in_box, frame.copy(), x1, y1, x2, y2
            )
            self.track_names[track_id] = {
                'name':            'Checking...',
                'last_seen':       current_time,
                'face_encoding':   None,
                'last_face_check': current_time,
                'future':          future,
            }
            name = 'Checking...'
        else:
            info['last_seen'] = current_time

            future: Optional[Future] = info.get('future')
            if future is not None and future.done():
                try:
                    identified_name, enc = future.result()
                    info['name'] = identified_name
                    if enc is not None:
                        info['face_encoding'] = enc
                except Exception as exc:
                    logger.error(f'Face future error: {exc}')
                    info['name'] = 'Unknown'
                info['future']          = None
                info['last_face_check'] = current_time

            name = info['name']

            if (
                name == 'Unknown'
                and info.get('future') is None
                and current_time - info.get('last_face_check', 0) > Config.UNKNOWN_FACE_RECHECK_INTERVAL
            ):
                info['future'] = self._face_executor.submit(
                    self._identify_face_in_box, frame.copy(), x1, y1, x2, y2
                )

        name = self.track_names[track_id]['name']
        current_frame_names.append(name)

        if name not in ('Unknown', 'Checking...'):
            color = (0, 255, 0)   # green = known

        self._queue_face_alert(name, track_id, frame, current_time, x1, y1, x2, y2)
        return name, color

    # ════════════════════════════════════════════════════════════════════
    # Face identification (runs in thread pool)
    # ════════════════════════════════════════════════════════════════════

    def _identify_face_in_box(
        self, frame: np.ndarray, x1: int, y1: int, x2: int, y2: int
    ) -> tuple[str, Optional[np.ndarray]]:
        h, w = frame.shape[:2]
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            return 'Unknown', None

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb, number_of_times_to_upsample=1)
        if not locs:
            return 'Unknown', None

        encs = face_recognition.face_encodings(rgb, locs)
        if not encs:
            return 'Unknown', None

        face_enc = encs[0]

        with self._faces_lock:
            known_encs  = list(self.known_face_encodings)
            known_names = list(self.known_face_names)

        if not known_encs:
            return 'Unknown', face_enc

        distances = face_recognition.face_distance(known_encs, face_enc)
        matches   = face_recognition.compare_faces(known_encs, face_enc, tolerance=Config.FACE_TOLERANCE)
        best_idx  = int(np.argmin(distances))

        if matches[best_idx]:
            name = known_names[best_idx]
            logger.info(f'Face match: {name} (dist={distances[best_idx]:.4f})')
        else:
            name = 'Unknown'
            logger.debug(f'No face match (best dist={distances[best_idx]:.4f})')

        return name, face_enc

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
            with self._frame_lock:
                frame_height = self._last_frame.shape[0] if self._last_frame is not None else 480
            person_height_pct = (y2 - y1) / frame_height
            command = 'F' if person_height_pct < 0.6 else 'S'

        robot_controller.send_command(command)
        self._last_robot_command_time = current_time

    def set_auto_follow(self, enabled: bool, known_only: bool = False) -> None:
        self.auto_follow        = enabled
        self.follow_known_only  = known_only
        self._current_follow_target = None
        logger.info(f'Auto-follow: {enabled}, known_only: {known_only}')
        if not enabled:
            robot_controller.send_command('S', force=True)

    def get_follow_status(self) -> dict:
        """Return current follow state for the /api/robot/status endpoint."""
        return {
            'auto_follow':    self.auto_follow,
            'known_only':     self.follow_known_only,
            'follow_target':  self._current_follow_target,
        }

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
        frame: np.ndarray,
        current_time: float,
        x1: int, y1: int, x2: int, y2: int,
    ) -> None:
        alert_category = 'face: unknown' if name == 'Unknown' else 'face: known'

        with self._settings_lock:
            if alert_category not in self.enabled_labels:
                return

        track_key = f'track:{track_id}'
        with self._alert_lock:
            if current_time - self._last_detection_alert.get(track_key, 0) < Config.ALERT_COOLDOWN:
                return
            self._last_detection_alert[track_key] = current_time

        logger.info(f'[FACE ALERT] {name} (track={track_id})')

        image_path = self._save_face_crop(name, frame, x1, y1, x2, y2)
        if image_path is None:
            return

        det = Detection(
            camera_id=self.camera_id,
            label=f'Face: {name}',
            confidence=1.0,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            image_path=image_path,
        )
        self._enqueue_detection(det)

    def _save_face_crop(
        self, name: str, frame: np.ndarray, x1: int, y1: int, x2: int, y2: int
    ) -> Optional[str]:
        h, w = frame.shape[:2]
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            return None

        rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        face_locs = face_recognition.face_locations(rgb_crop, number_of_times_to_upsample=1)
        if not face_locs:
            logger.debug(f'No face found in crop for {name} — skipping save')
            return None

        top, right, bottom, left = face_locs[0]
        pad  = 20
        f_h, f_w = crop.shape[:2]
        tight = crop[
            max(0, top - pad):min(f_h, bottom + pad),
            max(0, left - pad):min(f_w, right + pad),
        ]

        filename    = f'face_{uuid.uuid4()}.jpg'
        storage_root = Config.STORAGE_ROOT
        filepath    = os.path.join(storage_root, 'detections', filename)

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            cv2.imwrite(filepath, tight)
            return filename
        except Exception as exc:
            logger.error(f'Error saving face crop: {exc}')
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