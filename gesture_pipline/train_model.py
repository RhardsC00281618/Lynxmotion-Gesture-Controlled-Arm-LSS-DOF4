###############################################################################
# train_model.py — Train an SVM gesture classifier on captured landmarks
#
# Usage:
#   python train_model.py
#
# Input:  gestures_dataset.csv  (from capture_landmarks.py)
# Output: model.pkl             (trained SVM + scaler, loaded by gesture_recogniser.py)
###############################################################################

import pickle

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

CSV_FILE = "gestures_dataset.csv"
MODEL_FILE = "model.pkl"


def main():
    # 1. Load dataset
    df = pd.read_csv(CSV_FILE)
    print(f"Loaded {len(df)} samples, {df['label'].nunique()} gestures")
    print(f"Gestures: {sorted(df['label'].unique())}\n")

    X = df.drop(columns=["label"]).values   # 63 landmark features
    y = df["label"].values                   # gesture labels

    # 2. Split into train (80%) and test (20%)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train: {len(X_train)}  Test: {len(X_test)}\n")

    # 3. Scale features (SVM needs this for good performance)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    # 4. Train SVM
    print("Training SVM...")
    svm = SVC(kernel="rbf", C=1, gamma="scale", random_state=42)
    svm.fit(X_train, y_train)
    print("Training complete.\n")

    # 5. Evaluate
    y_pred = svm.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {acc:.1%}\n")

    print("Classification Report:")
    print(classification_report(y_test, y_pred))

    print("Confusion Matrix:")
    labels = sorted(df["label"].unique())
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    # Print with labels
    header = "              " + "  ".join(f"{l[:6]:>6}" for l in labels)
    print(header)
    for i, row in enumerate(cm):
        row_str = "  ".join(f"{v:>6}" for v in row)
        print(f"{labels[i]:>14}  {row_str}")

    # 6. Save model + scaler together
    with open(MODEL_FILE, "wb") as f:
        pickle.dump({"scaler": scaler, "svm": svm}, f)

    print(f"\nModel saved to {MODEL_FILE}")


if __name__ == "__main__":
    main()
