###############################################################################
# gesture_recogniser.py — MediaPipe Hands gesture detection (Tasks API)
#
# Uses MediaPipe 0.10+ HandLandmarker (Tasks API).
# On first run, downloads hand_landmarker.task model (~4 MB) automatically.
###############################################################################

import logging
import os
import pickle
import time
import urllib.request
from dataclasses import dataclass, field

import cv2
import numpy as np
import config

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "hand_landmarker.task")
MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)
SVM_MODEL_PATH = os.path.join(_HERE, "model.pkl")

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MP_AVAILABLE = True
except ImportError:
    log.warning("mediapipe not installed — GestureRecogniser in SIMULATION mode")
    _MP_AVAILABLE = False

# MediaPipe landmark indices
_THUMB_TIP,  _THUMB_IP   = 4,  3
_INDEX_TIP,  _INDEX_PIP  = 8,  6
_MIDDLE_TIP, _MIDDLE_PIP = 12, 10
_RING_TIP,   _RING_PIP   = 16, 14
_PINKY_TIP,  _PINKY_PIP  = 20, 18

# Connections used for drawing the hand skeleton
_HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17),
]


@dataclass
class GestureResult:
    name: str = "NONE"
    raw_name: str = "NONE"
    confidence: float = 0.0
    landmarks: object = field(default=None, repr=False)


class GestureRecogniser:
    def __init__(self):
        self._landmarker  = None
        self._svm = None
        self._scaler = None
        self._stable_count: int = 0
        self._last_raw: str = "NONE"
        self._stable_gesture: str = "NONE"
        self._start_time_ms: int = 0

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def _ensure_model(self) -> None:
        if not os.path.exists(MODEL_PATH):
            log.info("Downloading hand landmark model (~4 MB) ...")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            log.info("Model saved to %s", MODEL_PATH)

    def start(self) -> None:
        if not _MP_AVAILABLE:
            log.info("GestureRecogniser: simulation mode (no MediaPipe)")
            return

        self._ensure_model()
        self._start_time_ms = int(time.time() * 1000)

        options = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)

        # Load trained SVM classifier
        if os.path.exists(SVM_MODEL_PATH):
            with open(SVM_MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)
            self._scaler = bundle["scaler"]
            self._svm = bundle["svm"]
            log.info("GestureRecogniser started (MediaPipe + trained SVM)")
        else:
            log.warning("No trained model found at %s — falling back to rules", SVM_MODEL_PATH)
            log.info("GestureRecogniser started (MediaPipe Tasks API)")

    def stop(self) -> None:
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #

    def process_frame(self, bgr_frame: np.ndarray) -> GestureResult:
        if not _MP_AVAILABLE or self._landmarker is None:
            return GestureResult()

        # Mirror + convert to RGB
        flipped = cv2.flip(bgr_frame, 1)
        rgb     = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)

        mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int(time.time() * 1000) - self._start_time_ms

        detection = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not detection.hand_landmarks:
            self._apply_stability("NONE")
            return GestureResult(name=self._stable_gesture)

        landmarks  = detection.hand_landmarks[0]
        handedness = (detection.handedness[0][0].category_name
                      if detection.handedness else "Right")

        raw_name, conf = self._classify(landmarks, handedness)
        self._apply_stability(raw_name)

        return GestureResult(
            name=self._stable_gesture,
            raw_name=raw_name,
            confidence=conf,
            landmarks=landmarks,
        )

    # ------------------------------------------------------------------ #
    # Stability filter                                                     #
    # ------------------------------------------------------------------ #

    def _apply_stability(self, raw: str) -> None:
        if raw == self._last_raw:
            self._stable_count += 1
        else:
            self._stable_count = 1
            self._last_raw = raw

        if self._stable_count >= config.GESTURE_STABLE_FRAMES:
            self._stable_gesture = raw
        elif raw == "NONE":
            self._stable_gesture = "NONE"

    # ------------------------------------------------------------------ #
    # Landmark classification                                              #
    # ------------------------------------------------------------------ #

    def _classify(self, landmarks, handedness: str) -> tuple:
        if self._svm is not None:
            # Trained SVM path: flatten landmarks into 63 features
            features = []
            for lm in landmarks:
                features.extend([lm.x, lm.y, lm.z])
            scaled = self._scaler.transform([features])
            name = self._svm.predict(scaled)[0]
            return name, 1.0

        # Fallback: rule-based classification (used if model.pkl is missing)
        lm = landmarks

        def finger_extended(tip, pip) -> bool:
            return lm[tip].y < lm[pip].y

        def thumb_extended() -> bool:
            if handedness == "Right":
                return lm[_THUMB_TIP].x < lm[_THUMB_IP].x
            return lm[_THUMB_TIP].x > lm[_THUMB_IP].x

        thumb  = thumb_extended()
        index  = finger_extended(_INDEX_TIP,  _INDEX_PIP)
        middle = finger_extended(_MIDDLE_TIP, _MIDDLE_PIP)
        ring   = finger_extended(_RING_TIP,   _RING_PIP)
        pinky  = finger_extended(_PINKY_TIP,  _PINKY_PIP)

        patterns = {
            "OPEN_PALM":     [True,  True,  True,  True,  True ],
            "FIST":          [False, False, False, False, False],
            "PEACE":         [None,  True,  True,  False, False],
            "THUMBS_UP":     [True,  False, False, False, False],
            "POINT":         [None,  True,  False, False, False],
            "THREE_FINGERS": [None,  True,  True,  True,  False],
            "ROCK_ON":       [True,  True,  False, False, True ],
            "PINKY_UP":      [False, False, False, False, True ],
        }
        detected = [thumb, index, middle, ring, pinky]

        best_name, best_score = "NONE", 0.0
        for name, pattern in patterns.items():
            score = sum(
                1 for e, a in zip(pattern, detected) if e is None or e == a
            ) / len(pattern)
            if score > best_score:
                best_score, best_name = score, name

        if best_score < 0.8:
            return "NONE", 0.0
        return best_name, best_score

    # ------------------------------------------------------------------ #
    # Drawing                                                              #
    # ------------------------------------------------------------------ #

    def draw_landmarks(self, bgr_frame: np.ndarray, result: GestureResult) -> np.ndarray:
        frame = cv2.flip(bgr_frame.copy(), 1)
        h, w  = frame.shape[:2]

        if result.landmarks:
            lm = result.landmarks
            for a, b in _HAND_CONNECTIONS:
                x1, y1 = int(lm[a].x * w), int(lm[a].y * h)
                x2, y2 = int(lm[b].x * w), int(lm[b].y * h)
                cv2.line(frame, (x1, y1), (x2, y2), (80, 80, 80), 1)
            for point in lm:
                cx, cy = int(point.x * w), int(point.y * h)
                cv2.circle(frame, (cx, cy), 5, (255, 255, 255), -1)
                cv2.circle(frame, (cx, cy), 5, (0, 128, 255),   1)

        colour = (0, 255, 0) if result.name != "NONE" else (128, 128, 128)
        cv2.putText(frame, f"Gesture: {result.name}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)

        # Show raw SVM prediction (before stability filter)
        raw_colour = (0, 255, 255) if result.raw_name != "NONE" else (128, 128, 128)
        cv2.putText(frame, f"Raw: {result.raw_name}",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, raw_colour, 2)

        if result.name != "NONE" and result.name in config.GESTURE_BEHAVIOUR_MAP:
            cv2.putText(frame, f"-> {config.GESTURE_BEHAVIOUR_MAP[result.name]}",
                        (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
        return frame
