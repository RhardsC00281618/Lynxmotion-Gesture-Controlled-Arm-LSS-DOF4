###############################################################################
# capture_landmarks.py — Collect hand landmark data for gesture training
#
# Usage:
#   python capture_landmarks.py
#
# The script cycles through each gesture. For each one:
#   1. Hold the gesture in front of the camera
#   2. Press SPACE to start capturing (200 samples over ~20 seconds)
#   3. Press S to skip a gesture, Q to quit early
#
# Output: gestures_dataset.csv  (appends if file already exists)
###############################################################################

import os
import csv
import time

import cv2
import numpy as np

# Constants for model, gestures, and capture settings
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)

GESTURES = ["OPEN_PALM", "FIST", "PEACE", "THUMBS_UP", "POINT",
            "THREE_FINGERS", "ROCK_ON", "PINKY_UP"]
SAMPLES_PER_GESTURE = 200
CAPTURE_DELAY = 0.1          # seconds between captures (~100 ms)
CAMERA_INDEX = 0
CSV_FILE = "gestures_dataset.csv"

# 21 landmarks × 3 coords = 63 features
HEADER = [f"lm{i}_{axis}" for i in range(21) for axis in ("x", "y", "z")] + ["label"]

# Function to download the model if it doesn't exist locally
def ensure_model():
    if not os.path.exists(MODEL_PATH):
        import urllib.request  # Import here to avoid dependency if model exists
        print("Downloading hand landmark model (~4 MB) ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"Model saved to {MODEL_PATH}")

# Function to draw UI information on the video frame
def draw_info(frame, gesture, count, total, status):
    """Draw capture status on the frame."""
    h, w = frame.shape[:2]

    # Create a dark overlay at the top for better text readability
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 100), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    # Display the current gesture name
    cv2.putText(frame, f"Gesture: {gesture}", (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

    # Display capture progress
    cv2.putText(frame, f"Captured: {count}/{total}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Draw progress bar
    bar_x, bar_y, bar_w, bar_h = 10, 80, w - 20, 12
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  (100, 100, 100), 1)
    fill = int(bar_w * count / total) if total > 0 else 0
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill, bar_y + bar_h),
                  (0, 255, 0), -1)

    # Display status message at the bottom
    colour = (0, 255, 0) if status == "CAPTURING" else (0, 200, 255)
    cv2.putText(frame, status, (10, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)

    return frame

# Function to convert landmarks to a CSV row
def landmarks_to_row(landmarks, label):
    """Flatten 21 landmarks into a list of 63 floats + label."""
    row = []
    for lm in landmarks:
        row.extend([lm.x, lm.y, lm.z])
    row.append(label)
    return row

# Main function that runs the capture process
def main():
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    ensure_model()  # Download model if needed

    # Set up MediaPipe HandLandmarker (same config as gesture_recogniser.py)
    options = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    landmarker = mp_vision.HandLandmarker.create_from_options(options)
    start_time_ms = int(time.time() * 1000)  # For timestamping frames

    # Open camera
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"Cannot open camera index {CAMERA_INDEX}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Prepare CSV — write header only if file is new
    file_exists = os.path.exists(CSV_FILE)
    csv_file = open(CSV_FILE, "a", newline="")
    writer = csv.writer(csv_file)
    if not file_exists:
        writer.writerow(HEADER)

    # Print instructions to the user
    print("GESTURE LANDMARK CAPTURE")
    print("=" * 50)
    print("Controls:")
    print("  SPACE  = start capturing current gesture")
    print("  S      = skip to next gesture")
    print("  Q      = quit")
    print("=" * 50)

    # Loop through each gesture to capture samples
    for gesture in GESTURES:
        print(f"\nNext gesture: {gesture}")
        print("Hold the gesture and press SPACE to start capturing...")

        capturing = False
        count = 0

        # Main loop for capturing samples for this gesture
        while True:
            ret, frame = cap.read()
            if not ret:
                continue  # Skip if frame read failed

            # Process frame for MediaPipe
            flipped = cv2.flip(frame, 1)  # Mirror for natural preview
            rgb = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)  # Convert to RGB
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(time.time() * 1000) - start_time_ms

            detection = landmarker.detect_for_video(mp_image, timestamp_ms)
            hand_detected = bool(detection.hand_landmarks)

            # Draw hand skeleton on preview if hand detected
            if hand_detected:
                lm = detection.hand_landmarks[0]
                h, w = flipped.shape[:2]
                # Define connections between landmark points for drawing skeleton
                connections = [
                    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
                    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
                    (13,17),(17,18),(18,19),(19,20),(0,17),
                ]
                # Draw lines for hand bones
                for a, b in connections:
                    x1, y1 = int(lm[a].x * w), int(lm[a].y * h)
                    x2, y2 = int(lm[b].x * w), int(lm[b].y * h)
                    cv2.line(flipped, (x1, y1), (x2, y2), (80, 80, 80), 1)
                # Draw circles for landmark points
                for point in lm:
                    cx, cy = int(point.x * w), int(point.y * h)
                    cv2.circle(flipped, (cx, cy), 5, (255, 255, 255), -1)
                    cv2.circle(flipped, (cx, cy), 5, (0, 128, 255), 1)

            # Set status text based on capture state
            if capturing:
                status = f"CAPTURING — {'HAND OK' if hand_detected else 'NO HAND!'}"
            else:
                status = "SPACE=capture  S=skip  Q=quit"

            display = draw_info(flipped, gesture, count, SAMPLES_PER_GESTURE, status)
            cv2.imshow("Capture Landmarks", display)  # Show the frame with UI

            # Capture logic
            if capturing and hand_detected:
                landmarks = detection.hand_landmarks[0]
                row = landmarks_to_row(landmarks, gesture)
                writer.writerow(row)
                count += 1

                if count >= SAMPLES_PER_GESTURE:
                    print(f"  Done! Captured {count} samples for {gesture}")
                    break

                time.sleep(CAPTURE_DELAY)

            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                # Quit early
                print("Quit early.")
                csv_file.close()
                cap.release()
                landmarker.close()
                cv2.destroyAllWindows()
                return
            elif key == ord(' ') and not capturing:
                # Start capturing if hand is detected
                if hand_detected:
                    capturing = True
                    print(f"  Capturing {gesture}...")
                else:
                    print("  No hand detected — show your hand first!")
            elif key == ord('s'):
                # Skip to next gesture
                print(f"  Skipped {gesture} ({count} samples captured)")
                break

    # Cleanup after all gestures
    csv_file.close()
    cap.release()
    landmarker.close()
    cv2.destroyAllWindows()

    # Print completion message
    print("\n" + "=" * 50)
    print(f"Dataset saved to {CSV_FILE}")
    print("Run train_model.py next to train the classifier.")
    print("=" * 50)


# Run main if script is executed directly
if __name__ == "__main__":
    main()
