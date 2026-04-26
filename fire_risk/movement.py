# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : movement.py
#  Purpose : Real-time movement intensity via frame differencing
# ============================================================
#
#  Algorithm (lightweight — no optical flow, no tracking):
#    1. Convert consecutive frames to grayscale
#    2. Apply Gaussian blur  → suppress sensor noise
#    3. Compute pixel-wise absolute difference
#    4. Threshold the diff  → binary map of changed pixels
#    5. Count white pixels and normalise by frame size → score ∈ [0, 1]
#
#  score ≈ 0.0  → static scene (no movement)
#  score ≈ 1.0  → entire frame changed (maximum crowd movement)
# ============================================================

import cv2
import numpy as np


def compute_movement(
    prev_frame,
    curr_frame,
    blur_ksize : int = 5,
    threshold  : int = 25,
) -> float:
    """
    Estimate movement intensity between two consecutive BGR frames.

    Parameters
    ----------
    prev_frame : np.ndarray | None   Previous video frame (BGR)
    curr_frame : np.ndarray          Current video frame  (BGR)
    blur_ksize : int                 Gaussian kernel size (must be odd)
    threshold  : int                 Pixel-change sensitivity (0–255)

    Returns
    -------
    float  Movement score in [0.0, 1.0]
    """
    # Guard: first frame has no predecessor
    if prev_frame is None or curr_frame is None:
        return 0.0

    # Step 1 · Grayscale conversion
    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

    # Step 2 · Gaussian blur (noise suppression)
    ksize     = (blur_ksize, blur_ksize)
    gray_prev = cv2.GaussianBlur(gray_prev, ksize, 0)
    gray_curr = cv2.GaussianBlur(gray_curr, ksize, 0)

    # Step 3 · Absolute difference
    diff = cv2.absdiff(gray_prev, gray_curr)

    # Step 4 · Binary threshold → isolate changed pixels
    _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # Step 5 · Normalise changed pixel count to [0, 1]
    score = int(np.sum(thresh == 255)) / thresh.size

    return round(min(score, 1.0), 4)
