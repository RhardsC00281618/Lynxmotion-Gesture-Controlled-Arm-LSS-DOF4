###############################################################################
# main_jog.py — Entry point for jog-mode gesture control
#
# Each gesture nudges one joint by config.JOG_STEP_TENTHS and the arm holds
# position. No auto-return to HOME or READY. Runs independently of main.py —
# nothing in the existing behaviour stack is modified.
#
# Gesture controls:
#   OPEN_PALM      -> go home (or clear E-stop if active)
#   FIST           -> EMERGENCY STOP
#   POINT          -> SERVO_TOP    up
#   THREE_FINGERS  -> SERVO_TOP    down
#   THUMBS_UP      -> SERVO_BOTTOM up
#   PINKY_UP       -> SERVO_BOTTOM down
#   PEACE          -> SERVO_WRIST  up
#   ROCK_ON        -> SERVO_WRIST  down
#
# Keyboard controls:
#   A / D  -> SERVO_BASE left / right (unmapped in gesture table)
#   O / K  -> SERVO_GRIPPER open / close
#   H      -> go home
#   C      -> clear emergency stop
#   Q      -> quit cleanly
###############################################################################

import logging
import sys

import cv2
import numpy as np

import config
from arm_controller import ArmController
from gesture_recogniser import GestureRecogniser
from jog_controller import JogEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main_jog")

_JOG_LEGEND = [
    ("OPEN_PALM",     "HOME / clear estop"),
    ("FIST",          "EMERGENCY STOP"),
    ("POINT",         "TOP up"),
    ("THREE_FINGERS", "TOP down"),
    ("THUMBS_UP",     "BOTTOM up"),
    ("PINKY_UP",      "BOTTOM down"),
    ("PEACE",         "WRIST up"),
    ("ROCK_ON",       "WRIST down"),
    ("A / D",         "BASE left / right"),
    ("O / K",         "GRIPPER open / close"),
]


def draw_hud(frame: np.ndarray, status: str, estopped: bool) -> np.ndarray:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 70), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    colour = (0, 0, 255) if estopped else (0, 200, 255)
    cv2.putText(frame, f"JOG: {status or 'idle'}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)
    cv2.putText(frame, "Q=quit  C=clear estop  H=home", (w - 360, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return frame


def draw_legend(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    line_h = 28
    pad = 8
    box_w = 360
    box_h = len(_JOG_LEGEND) * line_h + pad * 2
    y0 = h - box_h - 8

    overlay = frame.copy()
    cv2.rectangle(overlay, (6, y0), (6 + box_w, y0 + box_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    y = y0 + pad + 20
    for gesture, action in _JOG_LEGEND:
        text = f"{gesture}: {action}"
        cv2.putText(frame, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 255), 2, cv2.LINE_AA)
        y += line_h
    return frame


def main():
    arm = ArmController()
    recogniser = GestureRecogniser()

    if not arm.connect():
        log.error("Could not connect to arm on %s — running in camera-only mode.",
                  config.SERIAL_PORT)

    recogniser.start()

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        log.error("Cannot open camera index %d", config.CAMERA_INDEX)
        arm.disconnect()
        recogniser.stop()
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    engine = JogEngine(arm)
    log.info("Jog mode ready. Hold a gesture to keep moving; release to stop.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            gesture_result = recogniser.process_frame(frame)

            # Continuous jog: every frame tells the engine what's currently on
            # screen. Motion continues while a jog gesture is held and halts
            # as soon as it isn't (FIST / OPEN_PALM are still edge-triggered).
            engine.set_current_gesture(gesture_result.name)
            status = engine.update()

            if arm.is_connected():
                arm.poll_health()

            display = recogniser.draw_landmarks(frame, gesture_result)
            display = draw_hud(display, status, arm.is_estopped())
            display = draw_legend(display)
            cv2.imshow("LSS Gesture Arm — Jog Mode", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                log.info("Q pressed — shutting down")
                break
            elif key == ord('c'):
                arm.clear_estop()
            elif key == ord('h'):
                arm.go_home()
            elif key == ord('a'):
                engine.jog_servo_manual(config.SERVO_BASE, -config.JOG_STEP_TENTHS)
            elif key == ord('d'):
                engine.jog_servo_manual(config.SERVO_BASE, +config.JOG_STEP_TENTHS)
            elif key == ord('o'):
                engine.jog_servo_manual(config.SERVO_GRIPPER, -config.JOG_STEP_TENTHS)
            elif key == ord('k'):
                engine.jog_servo_manual(config.SERVO_GRIPPER, +config.JOG_STEP_TENTHS)

    except KeyboardInterrupt:
        log.info("Interrupted by user")

    finally:
        log.info("Shutting down...")
        try:
            arm.disconnect()
        except Exception:
            pass
        recogniser.stop()
        cap.release()
        cv2.destroyAllWindows()
        log.info("Done.")


if __name__ == "__main__":
    main()
