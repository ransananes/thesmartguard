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

logger = logging.getLogger(__name__)

VALID_COMMANDS  = frozenset({'F', 'B', 'L', 'R', 'S'})
CMD_PORT        = 3000
CONNECT_TIMEOUT = 5   # seconds for the initial TCP handshake
SEND_TIMEOUT    = 2   # seconds for each sendall call


class RobotController:
    def __init__(self, host: str | None = None, port: int = CMD_PORT) -> None:
        self.host = host
        self.port = port

        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._last_command: str | None = None

        self.autonomous_enabled    = False
        self._last_manual_override = 0.0

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
        command = command.strip().upper()
        if not command:
            return False, 'Empty command.'

        if not force and command == self._last_command:
            self._last_manual_override = time.time()
            return True, f'Command {command} debounced (no change)'

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
                logger.error(f'RobotController send error: {exc}')
                # Socket is dead — drop it and reconnect on next call
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                # Attempt one immediate reconnect and retry
                ok, msg = self._open_socket()
                if ok:
                    try:
                        self._sock.sendall(f'{command}\n'.encode())
                        return True, f'Command {command} sent (after reconnect)'
                    except Exception as exc2:
                        logger.error(f'RobotController retry error: {exc2}')
                        self._sock = None
                        return False, str(exc2)
                return False, f'Reconnect failed: {msg}'

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
        return {
            'connected':  self.is_connected,
            'host':       self.host,
            'port':       self.port,
            'autonomous': self.autonomous_enabled,
        }


robot_controller = RobotController()
