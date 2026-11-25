"""Visually compare bayer vs thresh on a demo frame (PNG, no video)."""

import cv2
import numpy as np

from convert import to_1bit

cap = cv2.VideoCapture("demo.mp4")
for _ in range(30):
    ok, frame = cap.read()
cap.release()
a = to_1bit(frame, 288, 256, "bayer", False, 0.15)
b = to_1bit(frame, 288, 256, "thresh", False, 0.15)
combo = np.hstack([a, b]).astype(np.uint8) * 255
combo = cv2.resize(combo, (combo.shape[1] * 2, combo.shape[0] * 2),
                   interpolation=cv2.INTER_NEAREST)
cv2.putText(combo, "BAYER", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, 128, 2)
cv2.putText(combo, "THRESH", (combo.shape[1] // 2 + 10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 1, 128, 2)
cv2.imwrite("snap_dither_compare.png", combo)
print("white: bayer=%.1f%% thresh=%.1f%%" % (a.mean() * 100, b.mean() * 100))
