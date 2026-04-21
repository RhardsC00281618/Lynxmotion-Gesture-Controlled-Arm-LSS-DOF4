###############################################################################
# arm_controller.py — Low-level LSS servo control with safety guarantees
#
# Safety contract:
#   1. Every position command passes through clamp() before reaching hardware.
#   2. move_servo_smooth checks _estop on every 50 ms poll tick while waiting
#      for a move to complete, and gives up after MOVE_COMPLETION_TIMEOUT.
#   3. Serial/hardware exceptions are caught, logged, and set _connected=False
#      rather than crashing the main loop.
#   4. On connect() each servo is configured with its real-life parameters
#      (SERVO_MAX_SPEED, angular stiffness, holding stiffness, accel/decel)
#      pulled from config.py. Speed is a single scalar applied to every joint;
#      stiffness / accel / decel remain per-servo.
#   5. On disconnect() servos are limped (power removed) after returning home,
#      preventing them from cooking while idle.
###############################################################################

import time
import logging
import config

log = logging.getLogger(__name__)

try:
    import lss
    import lss_const as lssc
    _LSS_AVAILABLE = True
except ImportError:
    log.warning("LSS library not installed — arm_controller running in SIMULATION mode")
    _LSS_AVAILABLE = False


class _FakeServo:
    """Simulated servo for offline development/testing."""
    def __init__(self, servo_id):
        self.servoID = servo_id
        self._pos = 0

    def move(self, pos):
        self._pos = pos

    def getPosition(self):
        return str(self._pos)

    def setColorLED(self, color):
        pass

    def setMaxSpeed(self, speed):
        pass

    def setAngularStiffness(self, value):
        pass

    def setAngularHoldingStiffness(self, value):
        pass

    def setAngularAcceleration(self, value):
        pass

    def setAngularDeceleration(self, value):
        pass

    def hold(self):
        pass

    def limp(self):
        pass

    def getVoltage(self):
        return str(config.VOLTAGE_NOMINAL_MV)

    def getTemperature(self):
        return "250"  # 25.0 C

    def getCurrent(self):
        return "100"  # 100 mA


class ArmController:
    def __init__(self):
        self._servos: dict[int, object] = {}
        self._current_positions: dict[int, int] = {sid: 0 for sid in config.ALL_SERVO_IDS}
        self._connected: bool = False
        self._estop: bool = False
        self._carrying: bool = False        # True after successful pick-up lift
        self._last_health_poll: float = 0.0
        self._last_led_colour: int = -1     # avoid spamming LED serial writes

    # ------------------------------------------------------------------ #
    # Connection                                                           #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        try:
            if _LSS_AVAILABLE:
                lss.initBus(config.SERIAL_PORT, config.SERIAL_BAUD)
                for sid in config.ALL_SERVO_IDS:
                    self._servos[sid] = lss.LSS(sid)
            else:
                for sid in config.ALL_SERVO_IDS:
                    self._servos[sid] = _FakeServo(sid)

            # Push per-servo real-life parameters down to each motor.
            # Without this the servos run at their (fast) factory defaults,
            # which causes overshoot on the bottom/top joints under load.
            self._apply_servo_profiles()

            # Sync position cache from hardware
            for sid in config.ALL_SERVO_IDS:
                self._current_positions[sid] = self.get_position(sid)

            self._connected = True
            self.set_all_leds(config.LED_GREEN)
            log.info("ArmController connected (simulation=%s)", not _LSS_AVAILABLE)
            self._log_health()
            return True

        except Exception as exc:
            log.error("connect() failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._connected:
            try:
                self.go_home()
            except Exception:
                pass
            try:
                self.set_all_leds(config.LED_BLACK)
            except Exception:
                pass
            # Limp all servos so they stop drawing holding current — the LSS
            # library doesn't do this on close, so without it the motors
            # keep torque applied (and heat up) until power is physically cut.
            for sid, servo in self._servos.items():
                try:
                    servo.limp()
                except Exception as exc:
                    log.warning("limp() failed on servo %d: %s", sid, exc)
            try:
                if _LSS_AVAILABLE:
                    lss.closeBus()
            except Exception:
                pass
        self._connected = False
        log.info("ArmController disconnected")

    def _apply_servo_profiles(self) -> None:
        """Push max-speed, stiffness, and accel/decel to hardware.
        config.SERVO_MAX_SPEED is a single scalar applied to every joint;
        stiffness / accel / decel remain per-servo."""
        for sid, servo in self._servos.items():
            try:
                servo.setMaxSpeed(config.SERVO_MAX_SPEED)
                servo.setAngularStiffness(config.SERVO_STIFFNESS[sid])
                servo.setAngularHoldingStiffness(config.SERVO_HOLDING_STIFFNESS[sid])
                servo.setAngularAcceleration(config.SERVO_ACCEL[sid])
                servo.setAngularDeceleration(config.SERVO_DECEL[sid])
                log.debug(
                    "Servo %d profile: speed=%d stiff=%d hold=%d accel=%d decel=%d",
                    sid,
                    config.SERVO_MAX_SPEED,
                    config.SERVO_STIFFNESS[sid],
                    config.SERVO_HOLDING_STIFFNESS[sid],
                    config.SERVO_ACCEL[sid],
                    config.SERVO_DECEL[sid],
                )
            except Exception as exc:
                log.warning("Failed to apply profile to servo %d: %s", sid, exc)

    # ------------------------------------------------------------------ #
    # Safety core                                                          #
    # ------------------------------------------------------------------ #

    def clamp(self, servo_id: int, position: int) -> int:
        lo, hi = config.SERVO_LIMITS.get(servo_id, (-9999, 9999))
        return max(lo, min(hi, int(position)))

    def emergency_stop(self) -> None:
        self._estop = True
        self.set_all_leds(config.LED_RED)
        for sid, servo in self._servos.items():
            try:
                if _LSS_AVAILABLE:
                    servo.hold()
                log.warning("E-STOP: servo %d held", sid)
            except Exception as exc:
                log.error("E-STOP hold failed on servo %d: %s", sid, exc)

    def clear_estop(self) -> None:
        self._estop = False
        self.set_all_leds(config.LED_GREEN)
        log.info("E-stop cleared")

    # ------------------------------------------------------------------ #
    # Movement primitives                                                  #
    # ------------------------------------------------------------------ #

    def move_servo(self, servo_id: int, position: int) -> None:
        """Issue a single move command (clamped). Non-blocking at hardware level."""
        if self._estop:
            return
        position = self.clamp(servo_id, position)
        try:
            self._servos[servo_id].move(position)
            self._current_positions[servo_id] = position
        except Exception as exc:
            log.error("move_servo(%d, %d) failed: %s", servo_id, position, exc)
            self._connected = False

    def move_servo_smooth(self, servo_id: int, target: int) -> None:
        """Issue a single move to target and wait up to MOVE_COMPLETION_TIMEOUT
        for the servo to arrive. Ramping is handled on the servo itself via
        SERVO_MAX_SPEED / SERVO_ACCEL / SERVO_DECEL, so no client-side
        interpolation is needed. _estop is checked on every poll tick."""
        if self._estop:
            return
        target = self.clamp(servo_id, target)
        try:
            self._servos[servo_id].move(target)
            self._current_positions[servo_id] = target
        except Exception as exc:
            log.error("move_servo_smooth(%d): %s", servo_id, exc)
            self._connected = False
            return

        deadline = time.time() + config.MOVE_COMPLETION_TIMEOUT
        tolerance = 10  # tenths-of-deg — servo rarely lands bang on target
        while time.time() < deadline:
            if self._estop:
                log.info("move_servo_smooth: aborted by estop (servo %d)", servo_id)
                return
            try:
                raw = self._servos[servo_id].getPosition()
                current = int(raw) if raw is not None else target
            except Exception:
                current = target
            if abs(current - target) <= tolerance:
                return
            time.sleep(0.05)
        log.warning("move_servo_smooth(%d): timeout waiting for target %d",
                    servo_id, target)

    def hold_servo(self, servo_id: int) -> None:
        """Halt a single servo at its current position without triggering
        E-stop. Used by jog mode to stop continuous motion cleanly —
        supersedes any in-flight move command."""
        try:
            self._servos[servo_id].hold()
            self._current_positions[servo_id] = self.get_position(servo_id)
        except Exception as exc:
            log.error("hold_servo(%d) failed: %s", servo_id, exc)

    def move_pose_sequential(self, pose: dict, order: list) -> None:
        """Move servos in a specified order (safety-critical for multi-joint
        moves). Blocks until each servo reports arrival or
        MOVE_COMPLETION_TIMEOUT elapses."""
        for sid in order:
            if sid in pose:
                self.move_servo_smooth(sid, pose[sid])
            if self._estop:
                return

    def move_pose(self, pose: dict) -> None:
        """Move all servos in pose using default safe order."""
        self.move_pose_sequential(pose, config.ALL_SERVO_IDS)

    # ------------------------------------------------------------------ #
    # Named pose helpers                                                   #
    # ------------------------------------------------------------------ #

    def go_home(self) -> None:
        # Safe order: wrist first, then fold top, lower bottom, centre base
        self.move_pose_sequential(config.POSE_HOME,
                                  [config.SERVO_WRIST, config.SERVO_TOP,
                                   config.SERVO_BOTTOM, config.SERVO_BASE,
                                   config.SERVO_GRIPPER])

    def go_ready(self) -> None:
        self.move_pose_sequential(config.POSE_READY,
                                  [config.SERVO_WRIST, config.SERVO_TOP,
                                   config.SERVO_BOTTOM, config.SERVO_BASE,
                                   config.SERVO_GRIPPER])

    def gripper_open(self) -> None:
        self.move_servo_smooth(config.SERVO_GRIPPER, 0)

    def gripper_close(self, position: int = 600) -> None:
        self.move_servo_smooth(config.SERVO_GRIPPER,
                               self.clamp(config.SERVO_GRIPPER, position))

    # ------------------------------------------------------------------ #
    # LED / status indication                                              #
    # ------------------------------------------------------------------ #

    def set_all_leds(self, colour: int) -> None:
        """Set every servo's onboard LED to the same colour.
        No-op if the colour hasn't changed — avoids flooding the serial bus
        on every state-machine tick."""
        if colour == self._last_led_colour:
            return
        for sid, servo in self._servos.items():
            try:
                servo.setColorLED(colour)
            except Exception as exc:
                log.debug("setColorLED failed on servo %d: %s", sid, exc)
        self._last_led_colour = colour

    def set_led_for_state(self, state_name: str) -> None:
        colour = config.STATE_LED_COLOURS.get(state_name, config.LED_GREEN)
        self.set_all_leds(colour)

    # ------------------------------------------------------------------ #
    # Health monitoring                                                    #
    # ------------------------------------------------------------------ #

    def _safe_int(self, raw, default: int = 0) -> int:
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def poll_health(self) -> dict:
        """Read voltage (mV), temperature (tenths-C) and current (mA) from
        each servo. Returns a dict keyed by servo id. Rate-limited by
        config.HEALTH_POLL_INTERVAL to avoid hammering the serial bus."""
        now = time.time()
        if now - self._last_health_poll < config.HEALTH_POLL_INTERVAL:
            return {}
        self._last_health_poll = now

        readings = {}
        for sid, servo in self._servos.items():
            try:
                voltage_mv = self._safe_int(servo.getVoltage(), default=-1)
                temp_dc    = self._safe_int(servo.getTemperature(), default=-1)
                current_ma = self._safe_int(servo.getCurrent(), default=-1)
            except Exception as exc:
                log.debug("health poll failed on servo %d: %s", sid, exc)
                continue

            readings[sid] = {
                "voltage_mv": voltage_mv,
                "temperature_dc": temp_dc,
                "current_ma": current_ma,
            }

            if 0 < voltage_mv < config.VOLTAGE_MIN_MV:
                log.warning("Servo %d LOW VOLTAGE: %.2f V", sid, voltage_mv / 1000.0)
            if 0 < temp_dc and temp_dc > config.TEMPERATURE_MAX_DC:
                log.warning("Servo %d HIGH TEMPERATURE: %.1f C", sid, temp_dc / 10.0)
            if 0 < current_ma and current_ma > config.CURRENT_MAX_MA:
                log.warning("Servo %d HIGH CURRENT: %d mA", sid, current_ma)

        return readings

    def _log_health(self) -> None:
        """One-shot health log at connect() — useful for confirming battery
        voltage before the arm starts moving."""
        # Force the health poll regardless of the rate limiter.
        self._last_health_poll = 0.0
        readings = self.poll_health()
        for sid, r in readings.items():
            log.info(
                "Servo %d health: %.2f V, %.1f C, %d mA",
                sid,
                r["voltage_mv"] / 1000.0,
                r["temperature_dc"] / 10.0,
                r["current_ma"],
            )

    # ------------------------------------------------------------------ #
    # State queries                                                        #
    # ------------------------------------------------------------------ #

    def get_position(self, servo_id: int) -> int:
        try:
            raw = self._servos[servo_id].getPosition()
            pos = int(raw) if raw is not None else self._current_positions.get(servo_id, 0)
            self._current_positions[servo_id] = pos
            return pos
        except Exception:
            return self._current_positions.get(servo_id, 0)

    def get_all_positions(self) -> dict:
        return {sid: self.get_position(sid) for sid in config.ALL_SERVO_IDS}

    def is_connected(self) -> bool:
        return self._connected

    def is_estopped(self) -> bool:
        return self._estop

    def set_carrying(self, value: bool) -> None:
        self._carrying = value

    def is_carrying(self) -> bool:
        return self._carrying
