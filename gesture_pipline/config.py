###############################################################################
# config.py — Single source of truth for all constants
# All servo limits, named poses, and calibration values live here.
# Nothing in this file changes at runtime.
###############################################################################

# --- Serial ---
SERIAL_PORT = "COM10"
SERIAL_BAUD = 115200  # lssc.LSS_DefaultBaud

# --- Servo IDs ---
SERVO_BASE    = 1
SERVO_BOTTOM  = 2
SERVO_TOP     = 3
SERVO_WRIST   = 4
SERVO_GRIPPER = 5

ALL_SERVO_IDS = [SERVO_BASE, SERVO_BOTTOM, SERVO_TOP, SERVO_WRIST, SERVO_GRIPPER]

# --- Safe position limits (tenths-of-degrees, inclusive) ---
SERVO_LIMITS = {
    SERVO_BASE:    (-900,  900),
    SERVO_BOTTOM:  (-900,    0),   # -900 = parallel to ground, 0 = straight up
    SERVO_TOP:     (   0,  850),   #    0 = straight up, 850 = parallel to bottom arm
    SERVO_WRIST:   (-800,    0),   # -800 = straight up, 0 = straight out
    SERVO_GRIPPER: (-300,  750),   # -300 = widest open, 0 = default open, 750 = fully closed
}

# --- Per-servo max speed (tenths-of-degrees per second) ---
# LSS-ST1 standard servos have a hard ceiling around 600 deg/s (6000 in tenths).
# Conservative values chosen per joint load:
#   - Base/Bottom carry the arm's weight, so they move slower
#   - Wrist is lightly loaded and can move faster
#   - Gripper is deliberately slow to avoid crushing grabbed objects
SERVO_MAX_SPEED = {
    SERVO_BASE:    600,
    SERVO_BOTTOM:  400,
    SERVO_TOP:     500,
    SERVO_WRIST:   700,
    SERVO_GRIPPER: 300,
}

# --- Per-servo angular stiffness (range -4 to 4, LSS default 0) ---
# Higher stiffness resists external torque better but draws more current and
# can oscillate. Load-bearing joints get a small positive bias.
SERVO_STIFFNESS = {
    SERVO_BASE:    2,
    SERVO_BOTTOM:  3,
    SERVO_TOP:     2,
    SERVO_WRIST:   0,
    SERVO_GRIPPER: 0,
}

# --- Per-servo angular holding stiffness (range -4 to 4, LSS default 4) ---
# Controls how firmly the servo resists motion at the target position.
# Max on all joints: prevents the arm from drooping while carrying a pose.
SERVO_HOLDING_STIFFNESS = {
    SERVO_BASE:    4,
    SERVO_BOTTOM:  4,
    SERVO_TOP:     4,
    SERVO_WRIST:   3,
    SERVO_GRIPPER: 2,   # lower on gripper — don't clamp too hard on held objects
}

# --- Per-servo angular acceleration / deceleration (1-100, default 100) ---
# Lower values ramp up/down slowly for smoother motion on heavy joints.
SERVO_ACCEL = {
    SERVO_BASE:    50,
    SERVO_BOTTOM:  40,
    SERVO_TOP:     50,
    SERVO_WRIST:   80,
    SERVO_GRIPPER: 60,
}
SERVO_DECEL = {
    SERVO_BASE:    50,
    SERVO_BOTTOM:  40,
    SERVO_TOP:     50,
    SERVO_WRIST:   80,
    SERVO_GRIPPER: 60,
}

# --- LED colour codes (match lss_const.LSS_LED_*) ---
LED_BLACK   = 0
LED_RED     = 1
LED_GREEN   = 2
LED_BLUE    = 3
LED_YELLOW  = 4
LED_CYAN    = 5
LED_MAGENTA = 6
LED_WHITE   = 7

# --- Per-state LED colours ---
# Visual feedback on the servos themselves so an operator can read arm status
# at a glance without watching the laptop screen.
STATE_LED_COLOURS = {
    "IDLE":           LED_GREEN,
    "HOMING":         LED_CYAN,
    "WAVING":         LED_YELLOW,
    "REACHING":       LED_BLUE,
    "BOWING":         LED_MAGENTA,
    "POINTING_UP":    LED_WHITE,
    "DANCING":        LED_YELLOW,
    "WIGGLING":       LED_CYAN,
    "EMERGENCY_STOP": LED_RED,
}

# --- Health monitoring thresholds ---
# LSS reports voltage in millivolts, temperature in tenths of Celsius,
# current in milliamps. Warn above/below these values.
VOLTAGE_MIN_MV     = 7000   # 7.0 V — 2S LiPo cutoff with margin
VOLTAGE_NOMINAL_MV = 11100  # 11.1 V — 3S LiPo nominal
TEMPERATURE_MAX_DC = 650    # 65.0 C
CURRENT_MAX_MA     = 1500   # 1.5 A sustained per servo

HEALTH_POLL_INTERVAL = 2.0  # seconds between voltage/temp/current polls

# --- Named poses (dict keyed by servo ID) ---
POSE_HOME = {
    SERVO_BASE:    0,
    SERVO_BOTTOM:  -900,
    SERVO_TOP:      850,
    SERVO_WRIST:   -400,
    SERVO_GRIPPER:    0,
}

POSE_READY = {
    SERVO_BASE:    0,
    SERVO_BOTTOM:  -450,
    SERVO_TOP:      400,
    SERVO_WRIST:   -200,
    SERVO_GRIPPER:    0,
}

POSE_WAVE_A = {
    SERVO_BASE:    -300,
    SERVO_BOTTOM:  -500,
    SERVO_TOP:      200,
    SERVO_WRIST:   -400,
    SERVO_GRIPPER:    0,
}

POSE_WAVE_B = {
    SERVO_BASE:     300,
    SERVO_BOTTOM:  -500,
    SERVO_TOP:      200,
    SERVO_WRIST:   -400,
    SERVO_GRIPPER:    0,
}

POSE_REACH = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -600,
    SERVO_TOP:      600,
    SERVO_WRIST:   -100,
    SERVO_GRIPPER:    0,
}

POSE_BOW = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -800,
    SERVO_TOP:      700,
    SERVO_WRIST:   -600,
    SERVO_GRIPPER:    0,
}

# --- Expanded gesture poses ---

# Arm fully extended upward — like pointing at the sky.
POSE_POINT_UP = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -300,
    SERVO_TOP:      100,
    SERVO_WRIST:   -400,
    SERVO_GRIPPER:    0,
}

# Dance sequence — three pose frames swinging around the base.
POSE_DANCE_A = {
    SERVO_BASE:    -500,
    SERVO_BOTTOM:  -400,
    SERVO_TOP:      300,
    SERVO_WRIST:   -500,
    SERVO_GRIPPER:  400,
}
POSE_DANCE_B = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -200,
    SERVO_TOP:      200,
    SERVO_WRIST:   -600,
    SERVO_GRIPPER:  400,
}
POSE_DANCE_C = {
    SERVO_BASE:     500,
    SERVO_BOTTOM:  -400,
    SERVO_TOP:      300,
    SERVO_WRIST:   -500,
    SERVO_GRIPPER:  400,
}

# Wiggle — small wrist oscillation around the READY pose.
POSE_WIGGLE_A = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -450,
    SERVO_TOP:      400,
    SERVO_WRIST:   -100,
    SERVO_GRIPPER:    0,
}
POSE_WIGGLE_B = {
    SERVO_BASE:      0,
    SERVO_BOTTOM:  -450,
    SERVO_TOP:      400,
    SERVO_WRIST:   -500,
    SERVO_GRIPPER:    0,
}

# --- Movement ---
SERVO_MAX_SPEED = 370

MOVE_COMPLETION_TIMEOUT = 2.5


GESTURE_STABLE_FRAMES = 20   # consecutive identical detections required before firing

# --- Camera ---
CAMERA_INDEX   = 0
FRAME_WIDTH    = 640
FRAME_HEIGHT   = 480

# --- Gesture → behaviour mapping ---
GESTURE_BEHAVIOUR_MAP = {
    "OPEN_PALM":     "HOME",
    "FIST":          "EMERGENCY_STOP",
    "PEACE":         "WAVE",
    "THUMBS_UP":     "BOW",
    "POINT":         "REACH",
    "THREE_FINGERS": "POINT_UP",
    "ROCK_ON":       "DANCE",
    "PINKY_UP":      "WIGGLE",
}

# --- Jog mode (main_jog.py) ---
# Step size per keyboard press for the one-shot jogs (TOP / GRIPPER).
# 50 tenths ≈ 5°.
JOG_STEP_TENTHS = 50

# Per-frame step applied while a jog gesture is held. At ~30 FPS this
# multiplies up to the commanded rate: e.g. 5 tenths/frame × 30 FPS =
# 150 tenths/sec ≈ 15°/sec. Must stay below SERVO_MAX_SPEED / fps for the
# step rate (not the servo ceiling) to control the visible speed.
JOG_CONTINUOUS_STEP_TENTHS = 5

# Each gesture jogs one joint by a fixed per-frame delta. FIST and
# OPEN_PALM are deliberately absent — they keep their safety roles.
GESTURE_JOG_MAP = {
    "POINT":         (SERVO_TOP,    +JOG_CONTINUOUS_STEP_TENTHS),  # top up
    "THREE_FINGERS": (SERVO_TOP,    -JOG_CONTINUOUS_STEP_TENTHS),  # top down
    "THUMBS_UP":     (SERVO_BOTTOM, +JOG_CONTINUOUS_STEP_TENTHS),  # bottom up
    "PINKY_UP":      (SERVO_BOTTOM, -JOG_CONTINUOUS_STEP_TENTHS),  # bottom down
    "PEACE":         (SERVO_WRIST,  +JOG_CONTINUOUS_STEP_TENTHS),  # wrist up
    "ROCK_ON":       (SERVO_WRIST,  -JOG_CONTINUOUS_STEP_TENTHS),  # wrist down
}
