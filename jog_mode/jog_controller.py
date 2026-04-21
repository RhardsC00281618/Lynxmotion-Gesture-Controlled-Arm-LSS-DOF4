###############################################################################
# jog_controller.py — Per-gesture incremental joint control ("jog mode")
#
# Each jog-mapped gesture continuously advances one joint while it's being
# held, and the servo halts the moment a non-jog gesture (or no hand) is seen.
# Parallel to behaviours.BehaviourEngine but does NOT return the arm to a
# start pose after each trigger. Safety gestures keep their roles:
#   - FIST       -> emergency_stop()  (edge-triggered)
#   - OPEN_PALM  -> clear_estop() if estopped, else go_home() (edge-triggered)
###############################################################################

import logging
from typing import Optional

import config
from arm_controller import ArmController

log = logging.getLogger(__name__)


class JogEngine:
    def __init__(self, arm: ArmController):
        self._arm = arm
        self._active_jog: Optional[tuple[int, int]] = None
        self._last_safety_gesture: str = ""
        self._last_jog: str = ""
        self._commanded_targets: dict[int, int] = {}

    def set_current_gesture(self, gesture_name: str) -> None:
        """Called every frame with the (stable) current gesture or "NONE".
        Drives edge-triggered safety gestures and latches the active jog."""
        if gesture_name != self._last_safety_gesture:
            if gesture_name == "FIST":
                self._active_jog = None
                self._arm.emergency_stop()
                self._last_jog = "E-STOP"
            elif gesture_name == "OPEN_PALM":
                self._stop_active_jog(hold=False)
                if self._arm.is_estopped():
                    self._arm.clear_estop()
                    self._last_jog = "ESTOP CLEARED"
                else:
                    self._arm.go_home()
                    self._last_jog = "HOME"
            self._last_safety_gesture = gesture_name

        jog = config.GESTURE_JOG_MAP.get(gesture_name)
        if jog is None:
            if self._active_jog is not None:
                self._stop_active_jog(hold=True)
                self._last_jog = "idle"
        else:
            if self._active_jog != jog:
                servo_id, _ = jog
                # Seed the commanded target from the servo's current actual pos
                # so the first step advances from reality rather than stale cache.
                self._commanded_targets[servo_id] = self._arm.get_position(servo_id)
            self._active_jog = jog

    def update(self) -> str:
        """Advance the active jog by one step per call. Intended to run once
        per camera frame — at 30 FPS with JOG_STEP_TENTHS=50, commanded target
        climbs faster than the servo can move, so the servo runs at its own
        max speed. Releasing the gesture halts via hold_servo()."""
        if self._active_jog is None:
            return self._last_jog
        if self._arm.is_estopped():
            self._active_jog = None
            return self._last_jog

        servo_id, step = self._active_jog
        cmd = self._commanded_targets.get(servo_id)
        if cmd is None:
            cmd = self._arm.get_position(servo_id)
        new_target = self._arm.clamp(servo_id, cmd + step)
        if new_target == cmd:
            self._last_jog = f"servo {servo_id} at limit"
            return self._last_jog

        self._arm.move_servo(servo_id, new_target)
        self._commanded_targets[servo_id] = new_target
        self._last_jog = f"JOG servo {servo_id} {'+' if step >= 0 else ''}{step}"
        return self._last_jog

    def jog_servo_manual(self, servo_id: int, delta: int) -> None:
        """Keyboard one-shot jog for joints not in GESTURE_JOG_MAP (TOP, GRIPPER)."""
        if self._arm.is_estopped():
            log.info("jog refused: estop active (show OPEN_PALM to clear)")
            return
        current = self._arm.get_position(servo_id)
        target = self._arm.clamp(servo_id, current + delta)
        if target == current:
            log.info("jog clamped at limit (servo %d, current=%d)", servo_id, current)
            return
        self._arm.move_servo(servo_id, target)
        self._commanded_targets[servo_id] = target
        self._last_jog = f"KEY servo {servo_id} {'+' if delta >= 0 else ''}{delta}"

    def _stop_active_jog(self, hold: bool) -> None:
        if self._active_jog is None:
            return
        servo_id, _ = self._active_jog
        if hold:
            self._arm.hold_servo(servo_id)
            self._commanded_targets[servo_id] = self._arm.get_position(servo_id)
        self._active_jog = None

    def last_status(self) -> str:
        return self._last_jog
