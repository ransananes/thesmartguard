"""
Serial/Firmata communication driver for the Arduino robot.

Converts the previous Arduino C++ logic (Ultrasonic sensor, servo sweeping, and 
shift-register motor control) into a Python implementation using `pyfirmata`.
Seamlessly integrates with the backend's camera auto-follow logic.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import inspect
if not hasattr(inspect, 'getargspec'):
    # Python 3.11+ removed inspect.getargspec; pyfirmata still uses it.
    inspect.getargspec = inspect.getfullargspec

import pyfirmata2 as pyfirmata
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# Arduino Pin Definitions
TRIG_PIN = 12
ECHO_PIN = 13
PWM1_PIN = 5
PWM2_PIN = 6      
SHCP_PIN = 2
EN_PIN = 7
DATA_PIN = 8
STCP_PIN = 4
SERVO_PIN = 9

# Motor Directions (shift register values)
DIR_FORWARD = 92
DIR_BACKWARD = 163
DIR_STOP = 0
DIR_CONTRAROTATE = 172
DIR_CLOCKWISE = 83

VALID_COMMANDS = frozenset({'F', 'B', 'L', 'R', 'S'})


class RobotController:
    def __init__(self, port: str | None = None, baudrate: int = 57600, timeout: int = 1) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self.board: pyfirmata.Arduino | None = None
        self._lock = threading.Lock()          # guards connect/disconnect
        self._serial_lock = threading.Lock()   # guards shift-register / motor writes
        self._sensor_lock = threading.Lock()   # guards trig pulse (not echo polling)
        self._last_command: str | None = None
        
        # Pins
        self.servo = None
        self.trig = None
        self.echo = None
        self.pwm1 = None
        self.pwm2 = None
        self.shcp = None
        self.en = None
        self.data = None
        self.stcp = None
        
        # Autonomous logic
        self.autonomous_enabled = True
        self._last_manual_override = 0.0
        self._run_thread = False
        self._thread: threading.Thread | None = None

        if self.port:
            with self._lock:
                self._connect_unlocked()

    def _connect_unlocked(self, port: str | None = None) -> tuple[bool, str]:
        if port:
            self.port = port

        if not self.port:
            for p in serial.tools.list_ports.comports():
                desc = p.description or ''
                if any(kw in desc for kw in ('Arduino', 'CH340', 'USB Serial')):
                    self.port = p.device
                    break

        if not self.port:
            return False, 'No port specified and no Arduino detected.'

        try:
            if self.board:
                try:
                    self.board.exit()
                except Exception:
                    pass
                    
            # Connect via pyfirmata2
            self.board = pyfirmata.Arduino(self.port, baudrate=self.baudrate)

            # pyfirmata2 handles its own iterator thread automatically;
            # start it explicitly for pyfirmata compatibility shim if needed.
            try:
                self.it = pyfirmata.util.Iterator(self.board)
                self.it.start()
            except AttributeError:
                pass  # pyfirmata2 starts the read loop internally
            
            # Configure Pins
            self.servo = self.board.get_pin(f'd:{SERVO_PIN}:s')
            self.trig = self.board.get_pin(f'd:{TRIG_PIN}:o')
            self.echo = self.board.get_pin(f'd:{ECHO_PIN}:i')
            
            self.pwm1 = self.board.get_pin(f'd:{PWM1_PIN}:p')
            self.pwm2 = self.board.get_pin(f'd:{PWM2_PIN}:p')
            
            self.shcp = self.board.get_pin(f'd:{SHCP_PIN}:o')
            self.en = self.board.get_pin(f'd:{EN_PIN}:o')
            self.data = self.board.get_pin(f'd:{DATA_PIN}:o')
            self.stcp = self.board.get_pin(f'd:{STCP_PIN}:o')
            
            # Initial setup
            self.servo.write(90)
            self.en.write(1) # Disable motors
            self.trig.write(0)
            
            time.sleep(1) # wait for board to stabilize
            logger.info(f'RobotController connected to pyfirmata on {self.port}')
            
            # Start background loop
            if not self._run_thread:
                self._run_thread = True
                self._thread = threading.Thread(target=self._autonomous_loop, daemon=True)
                self._thread.start()
                
            return True, f'Connected to {self.port}'
            
        except Exception as exc:
            logger.error(f'RobotController connect error: {exc}')
            return False, str(exc)

    @property
    def is_connected(self) -> bool:
        return bool(self.board)

    def connect(self, port: str | None = None) -> tuple[bool, str]:
        with self._lock:
            return self._connect_unlocked(port)

    def disconnect(self) -> tuple[bool, str]:
        self._run_thread = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None        # allow reconnect to spawn a fresh thread

        with self._lock:
            if self.board:
                try:
                    self.board.exit()
                except Exception:
                    pass
                self.board = None
                self._last_command = None
                return True, 'Disconnected'
            return False, 'Not connected'

    # ------------------------------------------------------------------
    # Hardware Control Methods
    # ------------------------------------------------------------------

    def shift_out(self, val: int) -> None:
        """Software shiftOut implementation for MSBFIRST."""
        for i in range(8):
            bit = (val >> (7 - i)) & 1
            self.data.write(bit)
            self.shcp.write(1)
            self.shcp.write(0)

    def motor(self, direction: int, speed1: int, speed2: int) -> None:
        """Control motors via 74HCT595N shift register and PWM."""
        if not self.is_connected:
            return

        with self._serial_lock:   # dedicated serial-write lock, never held by sr04_read
            if direction == DIR_STOP:
                # Disable motor driver outputs immediately
                self.en.write(1)
                self.pwm1.write(0)
                self.pwm2.write(0)
                self.stcp.write(0)
                self.shift_out(DIR_STOP)
                self.stcp.write(1)
                return

            # Enable outputs
            self.en.write(0)

            # PWM values in pyfirmata are 0.0–1.0
            self.pwm1.write(speed1 / 255.0)
            self.pwm2.write(speed2 / 255.0)

            # Latch shift-register data
            self.stcp.write(0)
            self.shift_out(direction)
            self.stcp.write(1)

    def sr04_read(self) -> float:
        """Read HC-SR04 ultrasonic sensor. Returns distance in cm."""
        if not self.is_connected:
            return 999.0

        # Only lock during the brief trig pulse — release BEFORE echo busy-wait
        # so that motor() / send_command() are never blocked by sensor polling.
        with self._sensor_lock:
            self.trig.write(0)
            time.sleep(0.000002)
            self.trig.write(1)
            time.sleep(0.000010)
            self.trig.write(0)
        # _sensor_lock is now released — motor writes can proceed freely

        # Wait for echo to go high (timeout 50 ms)
        timeout = time.time() + 0.05
        while not self.echo.read():
            if time.time() > timeout:
                return 999.0

        start_time = time.time()
        timeout = time.time() + 0.05
        # Wait for echo to go low
        while self.echo.read():
            if time.time() > timeout:
                return 999.0

        pulse_duration = time.time() - start_time
        distance = pulse_duration * 17150  # 34300 cm/s ÷ 2
        time.sleep(0.01)
        return distance

    # ------------------------------------------------------------------
    # Command Interface (Auto-Follow & Manual)
    # ------------------------------------------------------------------

    def send_command(self, command: str, force: bool = False) -> tuple[bool, str]:
        """
        Send a single-character command to the robot.
        Overrides the autonomous loop for 2 seconds.
        """
        command = command.strip().upper()
        if not command:
            return False, 'Empty command.'

        if not force and command == self._last_command:
            # Reset manual override timer even if debounced
            self._last_manual_override = time.time()
            return True, f'Command {command} debounced (no change)'

        if not self.is_connected:
            ok, msg = self.connect()   # connect() acquires _lock internally
            if not ok:
                return False, f'Not connected to Arduino: {msg}'

        self._last_manual_override = time.time()
        self._last_command = command
        
        try:
            if command == 'F':
                self.motor(DIR_FORWARD, 250, 250)
            elif command == 'B':
                self.motor(DIR_BACKWARD, 180, 180)
            elif command == 'L':
                self.motor(DIR_CONTRAROTATE, 250, 250)
            elif command == 'R':
                self.motor(DIR_CLOCKWISE, 250, 250)
            elif command == 'S':
                self.motor(DIR_STOP, 0, 0)
                
            return True, f'Command {command} executed'
        except Exception as exc:
            logger.error(f'RobotController command error: {exc}')
            return False, str(exc)

    def get_status(self) -> dict:
        return {
            'connected': self.is_connected,
            'port': self.port,
            'baudrate': self.baudrate,
            'autonomous': self.autonomous_enabled,
        }

    # ------------------------------------------------------------------
    # Autonomous Loop (Translated from Arduino)
    # ------------------------------------------------------------------

    def _autonomous_loop(self) -> None:
        """Background loop running the obstacle avoidance logic."""
        while self._run_thread:
            if not self.is_connected:
                time.sleep(1)
                continue
                
            # If manual commands are received, pause autonomous behavior for 2 seconds
            if time.time() - self._last_manual_override < 2.0 or not self.autonomous_enabled:
                time.sleep(0.1)
                continue
                
            try:
                middle_distance = self.sr04_read()
                
                if middle_distance <= 25:
                    self.motor(DIR_STOP, 0, 0)
                    time.sleep(0.5)
                    self.servo.write(10)
                    time.sleep(0.5)
                    right_distance = self.sr04_read()
                    
                    time.sleep(0.5)
                    self.servo.write(90)
                    time.sleep(0.5)
                    self.servo.write(170)
                    time.sleep(0.5)
                    left_distance = self.sr04_read()
                    
                    time.sleep(0.5)
                    self.servo.write(90)
                    time.sleep(0.5)
                    
                    # Prevent overriding if manual command was sent during sleep
                    if time.time() - self._last_manual_override < 2.0:
                        continue
                        
                    if right_distance > left_distance:
                        self.motor(DIR_STOP, 0, 0)
                        time.sleep(0.1)
                        self.motor(DIR_BACKWARD, 180, 180)
                        time.sleep(1.0)
                        self.motor(DIR_CLOCKWISE, 250, 250)
                        time.sleep(0.6)
                    elif right_distance < left_distance:
                        self.motor(DIR_STOP, 0, 0)
                        time.sleep(0.1)
                        self.motor(DIR_BACKWARD, 180, 180)
                        time.sleep(1.0)
                        self.motor(DIR_CONTRAROTATE, 250, 250)
                        time.sleep(0.6)
                    elif right_distance < 20 or left_distance < 20:
                        self.motor(DIR_BACKWARD, 180, 180)
                        time.sleep(1.0)
                        self.motor(DIR_CONTRAROTATE, 250, 250)
                        time.sleep(0.6)
                    else:
                        self.motor(DIR_BACKWARD, 180, 180)
                        time.sleep(1.0)
                        self.motor(DIR_CLOCKWISE, 250, 250)
                        time.sleep(0.6)
                else:
                    self.motor(DIR_FORWARD, 250, 250)
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in autonomous loop: {e}")
                time.sleep(1)


# Module-level singleton — imported by routes and VideoProcessor
robot_controller = RobotController()
