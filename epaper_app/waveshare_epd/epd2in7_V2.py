"""Lightweight epd2in7_V2 stub used for local runs/tests.
This implements the small subset of the real driver used by
`epaper_train_disp_w_button.py` so the script can run without actual
Waveshare hardware.
"""

class EPD:
    def __init__(self):
        # Typical resolution for 2.7" Waveshare panels
        self.width = 176
        self.height = 264

    def init_Fast(self):
        # no-op for stub
        return 0

    def init(self):
        return 0

    def Clear(self):
        # no-op: real device clears panel
        print("[epd stub] Clear() called")

    def getbuffer(self, image):
        # Accept a PIL Image and return bytes representation; callers will
        # hash/convert this — return `bytes` to be friendly to hashlib
        try:
            return image.tobytes()
        except Exception:
            # Fallback: try raw bytes conversion
            return bytes(image)

    def display_Base(self, buf):
        # In the real driver, buf is a sequence of bytes. For the stub do nothing
        print(f"[epd stub] display_Base called (buffer length={len(buf) if buf is not None else 0})")

    def sleep(self):
        print("[epd stub] sleep() called")

    def init_Fast(self):
        return 0
