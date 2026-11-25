"""Generate a synthetic demo video (reproducible, no download needed).

Content: bouncing ball + sine bars + scrolling text + static title
(ideal for delta mode testing: static areas + motion).
"""

import cv2
import numpy as np

W, H, FPS, SECONDS = 640, 480, 15, 12


def main(path="demo.mp4"):
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = FPS * SECONDS
    for i in range(n):
        img = np.zeros((H, W, 3), dtype=np.uint8)
        # Flat background
        img[:] = (20, 20, 20)
        # Sine bars
        for b in range(5):
            x = int(W / 2 + (W / 3) * np.sin(2 * np.pi * (i / FPS * 0.5 + b / 5)))
            cv2.line(img, (x, 60), (x, H - 60), (60, 60, 60), 8)
        # Bouncing ball
        bx = int(W / 2 + (W / 2 - 60) * np.sin(2 * np.pi * i / n * 3))
        by = int(H / 2 + (H / 2 - 120) * abs(np.sin(2 * np.pi * i / n * 5)))
        cv2.circle(img, (bx, by), 30, (255, 255, 255), -1)
        # Static title
        cv2.putText(img, "ENGO STREAM POC", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (0, 255, 0), 2)
        # Scrolling text
        msg = "TEST VIDEO - subtitles and motion - "
        tw = 620
        off = (i * 12) % (tw + W)
        cv2.putText(img, msg, (W - off, H - 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (255, 255, 0), 2)
        # Counter (small changing area)
        cv2.putText(img, f"f{i:04d}", (W - 110, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (200, 200, 200), 2)
        out.write(img)
    out.release()
    print(f"Demo generated: {path} ({n} frames, {W}x{H}@{FPS}fps)")


if __name__ == "__main__":
    main()
