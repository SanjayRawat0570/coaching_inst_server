"""Image preprocessing for vision — Pillow + opencv (headless).

Photographed questions / handwritten answers are often skewed, low-contrast, or
noisy. Cleaning them up before sending to Gemini Vision improves OCR/grading.
Fails soft: if anything goes wrong it returns the original base64 unchanged.
"""

import base64
import io


def preprocess_b64(image_b64: str) -> str:
    """Auto-orient, grayscale, denoise and boost contrast. Returns base64 JPEG.

    On any error returns the input unchanged so the vision call still happens.
    """
    try:
        import numpy as np
        import cv2
        from PIL import Image, ImageOps

        raw = base64.b64decode(image_b64)
        pil = Image.open(io.BytesIO(raw))
        pil = ImageOps.exif_transpose(pil)          # honor camera rotation
        pil = pil.convert("RGB")

        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, h=10)  # remove speckle
        # Adaptive threshold sharpens handwriting against uneven lighting
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )

        ok, buf = cv2.imencode(".jpg", thresh)
        if not ok:
            return image_b64
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception as e:
        print(f"[image_utils] preprocess skipped: {e}")
        return image_b64
