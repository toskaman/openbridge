"""Generate two sparse demos: black and white backgrounds (ball + text + bar).

Goal: prove the OLED skip-black gain and the auto-invert payoff.
"""

import cv2
import numpy as np

W, H, FPS, SECONDS = 640, 480, 15, 12


def gen(path, bg, fg):
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = FPS * SECONDS
    for i in range(n):
        img = np.full((H, W, 3), bg, dtype=np.uint8)
        bx = int(W / 2 + (W / 2 - 60) * np.sin(2 * np.pi * i / n * 3))
        by = int(H / 2 + (H / 2 - 120) * abs(np.sin(2 * np.pi * i / n * 5)))
        cv2.circle(img, (bx, by), 30, fg, -1)
        cv2.putText(img, "SAMPLE SUBTITLE: hello glasses", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, fg, 2)
        cv2.rectangle(img, (30, H - 50), (30 + int((W - 60) * i / n), H - 30), fg, -1)
        out.write(img)
    out.release()
    print(f"Generated: {path}")


if __name__ == "__main__":
    gen("sparse_dark.mp4", (0, 0, 0), (255, 255, 255))
    gen("sparse_light.mp4", (255, 255, 255), (0, 0, 0))
