# Gesture-Controlled Lynxmotion LSS Robotic Arm

Real-time hand-gesture control of a Lynxmotion LSS 5-DOF robotic arm.
Hand landmarks come from MediaPipe's `HandLandmarker` (Tasks API) and are
classified into eight gestures by an RBF-kernel SVM trained on 21×3
landmark coordinates.

Two independent control front-ends share the same low-level arm controller,
gesture recogniser, and `config.py`:

- **`gesture_pipeline/`** — **behaviour mode.** Each recognised gesture fires
  a pre-programmed routine (HOME, WAVE, BOW, REACH, DANCE, WIGGLE, POINT UP,
  EMERGENCY STOP) via a state machine.
- **`jog_mode/`** — **continuous jog mode.** Holding a gesture moves one joint
  continuously; releasing it halts the joint. The safety gestures (FIST,
  OPEN_PALM) keep their roles.

## Hardware

- Lynxmotion LSS robotic arm, 5 servos: base (ID 1), bottom (2), top (3),
  wrist (4), gripper (5)
- LSS adapter board over USB serial (default `COM10` at 115200 baud — edit
  `config.SERIAL_PORT`)
- Webcam (default index `0`, 640×480)
- 2S–3S LiPo or bench supply (low-voltage cutoff: 7.0 V)

If the `lss` Python library or MediaPipe isn't installed, both the arm and
the recogniser fall back to **simulation mode** so the pipeline can be run
and developed without hardware.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

The `hand_landmarker.task` MediaPipe model and the trained `model.pkl`
classifier are bundled in each mode's folder. If `hand_landmarker.task` is
ever missing it will be downloaded on first run (~4 MB).

## Running

**Behaviour mode:**

```bash
cd gesture_pipeline
python main.py
```

**Jog mode:**

```bash
cd jog_mode
python main_jog.py
```

## Controls

### Behaviour mode (`gesture_pipeline/main.py`)

| Gesture        | Action           |
| -------------- | ---------------- |
| OPEN_PALM      | HOME             |
| FIST           | EMERGENCY STOP   |
| PEACE          | WAVE sequence    |
| THUMBS_UP      | BOW              |
| POINT          | REACH forward    |
| THREE_FINGERS  | POINT UP         |
| ROCK_ON        | DANCE sequence   |
| PINKY_UP       | WIGGLE (wrist)   |

Keys: **Q** quit · **C** clear E-stop.

### Jog mode (`jog_mode/main_jog.py`)

| Gesture        | Joint action              |
| -------------- | ------------------------- |
| OPEN_PALM      | HOME / clear E-stop       |
| FIST           | EMERGENCY STOP            |
| POINT          | TOP up                    |
| THREE_FINGERS  | TOP down                  |
| THUMBS_UP      | BOTTOM up                 |
| PINKY_UP       | BOTTOM down               |
| PEACE          | WRIST up                  |
| ROCK_ON        | WRIST down                |

Keys: **A/D** base left/right · **O/K** gripper open/close ·
**H** home · **C** clear E-stop · **Q** quit.

## Architecture

```
main.py / main_jog.py              ← camera loop + HUD
    │
    ├── GestureRecogniser          ← MediaPipe landmarks + SVM + stability filter
    ├── BehaviourEngine / JogEngine ← state machine or per-frame jog dispatch
    └── ArmController              ← clamped moves, E-stop, health, LEDs
            │
            └── lss / lss_const    ← LSS serial protocol (vendor)
```

All tunables live in `config.py`: serial port, servo limits, per-joint
stiffness / acceleration / deceleration, named poses (HOME, READY, WAVE A/B,
REACH, BOW, POINT_UP, DANCE A/B/C, WIGGLE A/B), gesture→behaviour map,
gesture→jog map, camera settings, and health thresholds.

## Safety features

- **Clamped positions.** Every move passes through `ArmController.clamp()`,
  which hard-limits each servo to the `SERVO_LIMITS` range in `config.py`.
- **Emergency stop.** FIST triggers `emergency_stop()` from any state — all
  servos `hold()`, LEDs go red, and every subsequent move is a no-op until
  OPEN_PALM (or the `C` key) clears it.
- **Stability filter.** A gesture must be detected on
  `GESTURE_STABLE_FRAMES` (20) consecutive frames before it fires, so
  transient mis-classifications can't trigger motion.
- **Sequential multi-joint moves.** Complex poses (HOME, REACH, BOW,
  POINT_UP) move joints in a safe order (wrist → top → bottom → base) and
  each step checks the E-stop flag before issuing the next command.
- **Move timeout.** `move_servo_smooth()` polls position every 50 ms and
  gives up after `MOVE_COMPLETION_TIMEOUT` (2.5 s) rather than blocking
  forever on a stuck servo.
- **Limp on disconnect.** Servos are returned home, then powered down with
  `limp()` on shutdown so they stop drawing holding current and cooking.
- **Health monitoring.** Voltage, temperature, and current are polled every
  2 s per servo; warnings log at < 7.0 V, > 65 °C, or > 1.5 A sustained.
- **LED status.** Each state has a colour (GREEN idle, CYAN homing, RED
  E-stop, etc.) written to the servo onboard LEDs so an operator can read
  arm state without looking at the laptop.

## Training the gesture classifier

From `gesture_pipeline/`:

```bash
python capture_landmarks.py   # interactive — appends to gestures_dataset.csv
python train_model.py         # trains RBF-SVM, writes model.pkl
```

`capture_landmarks.py` cycles through the eight gestures. For each one hold
the pose and press **SPACE** to capture 200 samples (≈ 20 s); **S** skips,
**Q** quits. Each sample is 21 landmarks × 3 coordinates = 63 features.

`train_model.py` does an 80/20 stratified split, fits a `StandardScaler`
and an `SVC(kernel="rbf", C=1, gamma="scale")`, prints accuracy,
classification report, and confusion matrix, then pickles
`{"scaler": ..., "svm": ...}` to `model.pkl`.

If `model.pkl` is missing at runtime, `GestureRecogniser` falls back to a
rule-based finger-extension classifier so the pipeline still works.

## Project layout

```
Project/
├── gesture_pipeline/         # behaviour mode
│   ├── main.py
│   ├── behaviours.py         # state machine
│   ├── arm_controller.py
│   ├── gesture_recogniser.py
│   ├── config.py
│   ├── capture_landmarks.py  # training data capture
│   ├── train_model.py        # SVM training
│   ├── gestures_dataset.csv
│   ├── hand_landmarker.task  # MediaPipe model
│   ├── model.pkl             # trained SVM + scaler
│   ├── lss.py / lss_const.py # vendor serial library
├── jog_mode/                 # continuous jog mode
│   ├── main_jog.py
│   ├── jog_controller.py
│   ├── arm_controller.py
│   ├── gesture_recogniser.py
│   ├── config.py
│   ├── hand_landmarker.task
│   ├── model.pkl
│   ├── lss.py / lss_const.py
├── requirements.txt
└── Group Project-Robots(1).pdf
```
