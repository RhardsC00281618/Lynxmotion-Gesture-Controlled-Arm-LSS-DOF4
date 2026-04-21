###############################################################################
# behaviours.py — State machine for high-level arm behaviours
#
# Gesture-only control. No camera-guided pick-up or colour detection.
#
# State transition rules:
#   - FIST → EMERGENCY_STOP from ANY state (checked first in update())
#   - OPEN_PALM clears estop and returns to IDLE
###############################################################################

import time
import logging
from enum import Enum, auto
from typing import Optional

import config
from arm_controller import ArmController

log = logging.getLogger(__name__)


class State(Enum):
    IDLE           = auto()
    HOMING         = auto()
    WAVING         = auto()
    REACHING       = auto()
    BOWING         = auto()
    POINTING_UP    = auto()
    DANCING        = auto()
    WIGGLING       = auto()
    EMERGENCY_STOP = auto()


class BehaviourEngine:
    def __init__(self, arm: ArmController):
        self._arm = arm
        self._state: State = State.IDLE
        self._state_entry_time: float = time.time()
        self._wave_step: int = 0
        self._dance_step: int = 0
        self._wiggle_step: int = 0
        self._pending_gesture: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def trigger_gesture(self, gesture_name: str) -> None:
        self._pending_gesture = gesture_name

    def update(self) -> State:
        gesture = self._pending_gesture
        self._pending_gesture = None

        # FIST overrides everything, always
        if gesture == "FIST" and self._state != State.EMERGENCY_STOP:
            self._arm.emergency_stop()
            self._transition(State.EMERGENCY_STOP)
            return self._state

        if self._state == State.EMERGENCY_STOP:
            self._handle_estop(gesture)
        elif self._state == State.IDLE:
            self._handle_idle(gesture)
        elif self._state == State.HOMING:
            self._handle_homing()
        elif self._state == State.WAVING:
            self._handle_waving()
        elif self._state == State.REACHING:
            self._handle_reaching()
        elif self._state == State.BOWING:
            self._handle_bowing()
        elif self._state == State.POINTING_UP:
            self._handle_pointing_up()
        elif self._state == State.DANCING:
            self._handle_dancing()
        elif self._state == State.WIGGLING:
            self._handle_wiggling()

        return self._state

    def get_state(self) -> State:
        return self._state

    def get_state_name(self) -> str:
        return self._state.name

    # ------------------------------------------------------------------ #
    # State handlers                                                       #
    # ------------------------------------------------------------------ #

    def _handle_estop(self, gesture: Optional[str]) -> None:
        if gesture == "OPEN_PALM":
            self._arm.clear_estop()
            log.info("E-stop cleared by OPEN_PALM")
            self._transition(State.IDLE)

    def _handle_idle(self, gesture: Optional[str]) -> None:
        if gesture is None:
            return
        if gesture == "OPEN_PALM":
            self._transition(State.HOMING)
        elif gesture == "PEACE":
            self._wave_step = 0
            self._transition(State.WAVING)
        elif gesture == "POINT":
            self._transition(State.REACHING)
        elif gesture == "THUMBS_UP":
            self._transition(State.BOWING)
        elif gesture == "THREE_FINGERS":
            self._transition(State.POINTING_UP)
        elif gesture == "ROCK_ON":
            self._dance_step = 0
            self._transition(State.DANCING)
        elif gesture == "PINKY_UP":
            self._wiggle_step = 0
            self._transition(State.WIGGLING)

    def _handle_homing(self) -> None:
        self._arm.go_home()
        self._transition(State.IDLE)

    def _handle_waving(self) -> None:
        wave_sequence = [
            config.POSE_WAVE_A,
            config.POSE_WAVE_B,
            config.POSE_WAVE_A,
            config.POSE_WAVE_B,
            config.POSE_HOME,
        ]
        if self._wave_step < len(wave_sequence):
            self._arm.move_pose(wave_sequence[self._wave_step])
            self._wave_step += 1
        else:
            self._transition(State.IDLE)

    def _handle_reaching(self) -> None:
        self._arm.move_pose_sequential(
            config.POSE_REACH,
            [config.SERVO_WRIST, config.SERVO_TOP,
             config.SERVO_BOTTOM, config.SERVO_BASE]
        )
        time.sleep(1.0)
        self._arm.go_ready()
        self._transition(State.IDLE)

    def _handle_bowing(self) -> None:
        self._arm.move_pose_sequential(
            config.POSE_BOW,
            [config.SERVO_WRIST, config.SERVO_TOP,
             config.SERVO_BOTTOM, config.SERVO_BASE]
        )
        time.sleep(1.0)
        self._arm.go_ready()
        self._transition(State.IDLE)

    def _handle_pointing_up(self) -> None:
        # Raise bottom/top before the wrist so the arm doesn't swing through
        # the table while unfolding.
        self._arm.move_pose_sequential(
            config.POSE_POINT_UP,
            [config.SERVO_BOTTOM, config.SERVO_TOP,
             config.SERVO_WRIST, config.SERVO_BASE]
        )
        time.sleep(1.5)
        self._arm.go_ready()
        self._transition(State.IDLE)

    def _handle_dancing(self) -> None:
        dance_sequence = [
            config.POSE_DANCE_A,
            config.POSE_DANCE_B,
            config.POSE_DANCE_C,
            config.POSE_DANCE_B,
            config.POSE_DANCE_A,
            config.POSE_READY,
        ]
        if self._dance_step < len(dance_sequence):
            self._arm.move_pose(dance_sequence[self._dance_step])
            self._dance_step += 1
        else:
            self._transition(State.IDLE)

    def _handle_wiggling(self) -> None:
        wiggle_sequence = [
            config.POSE_WIGGLE_A,
            config.POSE_WIGGLE_B,
            config.POSE_WIGGLE_A,
            config.POSE_WIGGLE_B,
            config.POSE_READY,
        ]
        if self._wiggle_step < len(wiggle_sequence):
            # Wiggle only moves the wrist — avoid disturbing the rest of the arm
            self._arm.move_servo_smooth(
                config.SERVO_WRIST,
                wiggle_sequence[self._wiggle_step][config.SERVO_WRIST],
            )
            self._wiggle_step += 1
        else:
            self._transition(State.IDLE)

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def _transition(self, new_state: State) -> None:
        if new_state != self._state:
            log.info("State: %s -> %s", self._state.name, new_state.name)
        self._state = new_state
        self._state_entry_time = time.time()
        # Reflect state change on the servo LEDs so operators can read status
        # from the arm itself without looking at the laptop.
        try:
            self._arm.set_led_for_state(new_state.name)
        except Exception:
            pass

    def _time_in_state(self) -> float:
        return time.time() - self._state_entry_time
