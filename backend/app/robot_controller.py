"""
WiFi TCP communication driver for the ESP32-CAM robot.

Keeps a single persistent TCP connection to the ESP32's command server
(port 3000). Commands are sent fire-and-forget — we do NOT wait for the
'OK:<cmd>' echo so the lock is released immediately and rapid commands
(auto-follow) are never queued behind a blocking recv.

A new connection is opened automatically if the socket breaks.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable, Optional

import cv2

from app.config import Config

logger = logging.getLogger(__name__)

VALID_COMMANDS  = frozenset({'F', 'B', 'L', 'R', 'S'})
CMD_PORT        = 3000
CONNECT_TIMEOUT = 5   # seconds for the initial TCP handshake
SEND_TIMEOUT    = 2   # seconds for each sendall call


def _cap_open(url: str, timeout: float = 2.5) -> 'cv2.VideoCapture | None':
    """Open a VideoCapture with a wall-clock timeout; returns None on timeout/failure."""
    holder: list = [None]

    def _open():
        c = cv2.VideoCapture(url)
        if c.isOpened():
            holder[0] = c
        else:
            c.release()

    t = threading.Thread(target=_open, daemon=True)
    t.start()
    t.join(timeout)
    return holder[0]  # None if timed out or failed to open


def _cap_read(cap: 'cv2.VideoCapture', timeout: float = 0.4) -> tuple[bool, object]:
    """cap.read() with a wall-clock timeout; returns (False, None) on timeout."""
    holder: list = [False, None]

    def _read():
        holder[0], holder[1] = cap.read()

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return holder[0], holder[1]


class RobotController:
    def __init__(self, host: str | None = None, port: int = CMD_PORT) -> None:
        self.host = host
        self.port = port

        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._last_command: str | None = None

        self.autonomous_enabled    = False
        self._last_manual_override = 0.0

        # Dead-reckoning: log every directional move so we can reverse back to home
        self._movement_log: list[tuple[str, int]] = []   # (command, duration_ms)
        self._current_move_cmd: str | None = None
        self._current_move_start: float | None = None
        self._returning_home: bool = False
        self._logging_paused: bool = False
        self._move_lock = threading.Lock()

        if self.host:
            self.connect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _open_socket(self) -> tuple[bool, str]:
        """Open a persistent TCP connection (lock must already be held)."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                # Windows: idle=10 s, interval=3 s, max probes=3
                s.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10_000, 3_000))
            except AttributeError:
                pass  # non-Windows — kernel defaults apply
            s.settimeout(CONNECT_TIMEOUT)
            s.connect((self.host, self.port))
            s.settimeout(SEND_TIMEOUT)
            self._sock = s
            logger.info(f'RobotController connected to {self.host}:{self.port}')
            return True, f'Connected to {self.host}:{self.port}'
        except Exception as exc:
            logger.error(f'RobotController connect error: {exc}')
            self._sock = None
            return False, str(exc)

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def connect(self, host: str | None = None, port: int | None = None) -> tuple[bool, str]:
        if host:
            self.host = host
        if port:
            self.port = port
        if not self.host:
            return False, 'No ESP32 IP address configured.'
        with self._lock:
            return self._open_socket()

    def disconnect(self) -> tuple[bool, str]:
        with self._lock:
            if self._sock:
                try:
                    self._sock.sendall(b'S\n')   # stop the robot
                except Exception:
                    pass
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                self._last_command = None
                return True, 'Disconnected'
            return False, 'Not connected'

    # ------------------------------------------------------------------
    # Command sending
    # ------------------------------------------------------------------

    def send_command(self, command: str, force: bool = False) -> tuple[bool, str]:
        """
        Send one command over the persistent TCP connection.
        Fire-and-forget — does NOT wait for the 'OK:' echo.
        Reconnects automatically if the socket is broken.
        """
        command = command.strip()
        if not command:
            return False, 'Empty command.'

        if not force and command == self._last_command:
            self._last_manual_override = time.time()
            return True, f'Command {command} debounced (no change)'

        if not self._returning_home:
            self._track_movement(command)

        if not self.is_connected:
            ok, msg = self.connect()
            if not ok:
                return False, f'Not connected to ESP32: {msg}'

        self._last_manual_override = time.time()
        self._last_command = command

        with self._lock:
            try:
                self._sock.sendall(f'{command}\n'.encode())
                return True, f'Command {command} sent'
            except Exception as exc:
                # Socket was reset (e.g. ESP32 rebooted) — reconnect and retry once.
                logger.warning(f'RobotController: connection lost ({exc}), reconnecting…')
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                ok, msg = self._open_socket()
                if ok:
                    try:
                        self._sock.sendall(f'{command}\n'.encode())
                        logger.info('RobotController: reconnected and command sent')
                        return True, f'Command {command} sent (after reconnect)'
                    except Exception as exc2:
                        logger.error(f'RobotController retry error: {exc2}')
                        self._sock = None
                        return False, str(exc2)
                return False, f'Reconnect failed: {msg}'

    # ------------------------------------------------------------------
    # Dead-reckoning home return
    # ------------------------------------------------------------------

    def _track_movement(self, command: str) -> None:
        """Close out the previous move duration and start timing the new one."""
        if self._logging_paused:
            return
        with self._move_lock:
            # Same command still running — don't reset the clock or log a partial entry.
            # The duration keeps accumulating until the command actually changes.
            if command == self._current_move_cmd:
                return
            now = time.time()
            if self._current_move_cmd is not None and self._current_move_start is not None:
                duration_ms = int((now - self._current_move_start) * 1000)
                if duration_ms >= 50:
                    self._movement_log.append((self._current_move_cmd, duration_ms))
                    logger.debug(f'Move logged: {self._current_move_cmd} {duration_ms}ms')
            if command in ('F', 'B', 'L', 'R'):
                self._current_move_cmd = command
                self._current_move_start = now
            else:
                self._current_move_cmd = None
                self._current_move_start = None

    def pause_movement_logging(self) -> None:
        """Stop recording moves — call during scan/search so turns don't corrupt the path log."""
        self._logging_paused = True
        with self._move_lock:
            self._current_move_cmd = None
            self._current_move_start = None

    def resume_movement_logging(self) -> None:
        """Resume recording moves — call when the robot is actively navigating again."""
        self._logging_paused = False

    def register_home(self) -> None:
        """Mark the robot's current position as home — clears the movement log."""
        self._logging_paused = False
        with self._move_lock:
            self._movement_log.clear()
            self._current_move_cmd = None
            self._current_move_start = None
        logger.info('Robot home position registered — movement log cleared.')

    def return_to_home(
        self,
        on_complete: Optional[Callable] = None,
        obstacle_check_cb: Optional[Callable] = None,
    ) -> bool:
        """
        Navigate back to the home position by reversing the movement log.

        Spins 180° first so the camera faces the direction of travel throughout
        the return, then replays every move at fast-return speed.  The reversed
        mapping keeps F/B as forward/backward (camera always ahead) and swaps
        L/R to undo the original turns.

        If obstacle_check_cb is supplied, the robot's ESP32-CAM stream is opened
        and checked every frame during straight moves; when an obstacle is
        detected the robot steers around it before continuing.

        Runs in a background thread; calls on_complete() when finished.
        Returns False if not connected or already returning.
        """
        if not self.is_connected:
            logger.warning('return_to_home: robot not connected')
            return False
        if self._returning_home:
            logger.warning('return_to_home: already in progress')
            return False

        self._track_movement('S')

        with self._move_lock:
            log_snapshot = list(self._movement_log)

        if not log_snapshot:
            logger.info('return_to_home: movement log empty — already at home')
            if on_complete:
                threading.Thread(target=on_complete, daemon=True, name='robot-home-cb').start()
            return True

        self._returning_home = True
        logger.info(f'return_to_home: reversing {len(log_snapshot)} moves')

        # After the initial 180° spin the robot faces its origin, so F/B keep
        # their direction and only turns need to be flipped.
        _REVERSE = {'F': 'f', 'B': 'b', 'L': 'r', 'R': 'l'}
        _DURATION_SCALE = {
            'F': 190 / 220,  # avg fwd speed (180+200)/2 vs SPEED_RETURN_BWD 220
            'B': 160 / 220,  # SPEED_BACK vs SPEED_RETURN_BWD
            'L': 130 / 185,  # SPEED_TURN vs SPEED_RETURN_TURN
            'R': 130 / 185,
        }
        _REFRESH = 0.2   # re-send interval (s) to beat Arduino 300 ms auto-stop

        def _execute() -> None:
            cap = None
            try:
                # Open the robot's own camera for obstacle detection.
                # _cap_open uses a background thread with a hard timeout so a
                # slow or unreachable stream never blocks the return sequence.
                if obstacle_check_cb is not None and self.host:
                    cam_url = f'http://{self.host}:{Config.ROBOT_CAMERA_PORT}/stream'
                    cap = _cap_open(cam_url, timeout=2.5)
                    if cap is None:
                        logger.warning('return_to_home: robot camera unavailable — obstacle detection disabled')

                # Spin 180° so the camera always faces the direction of travel
                logger.info('return_to_home: spinning 180°')
                spin_end = time.time() + Config.SPIN_180_MS / 1000.0
                while time.time() < spin_end:
                    self.send_command('l', force=True)
                    time.sleep(min(_REFRESH, spin_end - time.time()))
                self.send_command('S', force=True)
                time.sleep(0.1)  # let the robot settle after spinning

                # Replay the path in reverse
                for cmd, duration_ms in reversed(log_snapshot):
                    rev = _REVERSE.get(cmd)
                    if not rev:
                        continue
                    scale      = _DURATION_SCALE.get(cmd, 1.0)
                    adjusted_s = max(0.05, duration_ms / 1000.0 * scale)
                    end_time   = time.time() + adjusted_s
                    steers     = 0          # cap obstacle steers per segment

                    while time.time() < end_time:
                        # Obstacle detection only during straight moves (camera sees ahead).
                        # Capped at 3 steers per segment to prevent infinite extension.
                        if cap is not None and cmd in ('F', 'B') and steers < 3:
                            ret, frame = _cap_read(cap, timeout=0.4)
                            if ret and frame is not None:
                                steer = obstacle_check_cb(frame)
                                if steer:
                                    steers   += 1
                                    avoid_s   = Config.OBSTACLE_AVOID_STEER_MS / 1000.0
                                    end_time += avoid_s   # pause the return timer
                                    avoid_end = time.time() + avoid_s
                                    logger.debug(f'return_to_home: obstacle → steering {steer} ({steers}/3)')
                                    while time.time() < avoid_end:
                                        self.send_command(steer.lower(), force=True)
                                        time.sleep(min(_REFRESH, avoid_end - time.time()))
                                    continue

                        self.send_command(rev, force=True)
                        time.sleep(min(_REFRESH, end_time - time.time()))

                self.send_command('S', force=True)

            finally:
                if cap is not None:
                    cap.release()
                with self._move_lock:
                    self._movement_log.clear()
                    self._current_move_cmd = None
                    self._current_move_start = None
                self._returning_home = False
                logger.info('return_to_home: complete')
                if on_complete:
                    on_complete()

        threading.Thread(target=_execute, daemon=True, name='robot-return-home').start()
        return True

    def get_home_status(self) -> dict:
        with self._move_lock:
            steps    = len(self._movement_log)
            total_ms = sum(d for _, d in self._movement_log)
        return {
            'returning_home':          self._returning_home,
            'movement_log_steps':      steps,
            'movement_log_duration_ms': total_ms,
        }

    # ------------------------------------------------------------------
    # Ping / diagnostics
    # ------------------------------------------------------------------

    def ping(self) -> tuple[bool, str]:
        """Send 'S' and read back the 'OK:S' echo to verify end-to-end connectivity."""
        if not self.host:
            return False, 'No ESP32 IP address configured.'

        try:
            t0 = time.time()
            # Use a fresh socket so ping is independent of the main connection
            with socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT) as s:
                s.sendall(b'S\n')
                s.settimeout(CONNECT_TIMEOUT)
                response = s.recv(64).decode(errors='replace').strip()
            rtt = int((time.time() - t0) * 1000)
            return True, f'Ping OK — response: "{response}", RTT: {rtt} ms'
        except Exception as exc:
            logger.error(f'RobotController ping error: {exc}')
            return False, str(exc)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        status = {
            'connected':  self.is_connected,
            'host':       self.host,
            'port':       self.port,
            'autonomous': self.autonomous_enabled,
        }
        status.update(self.get_home_status())
        return status


robot_controller = RobotController()
