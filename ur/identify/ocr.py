"""Read jersey digits off a torso crop. Precision first, recall second.

`docs/07-licenses.md` approves PaddleOCR with PARSeq / docTR / EasyOCR as
fallbacks, all Apache-2.0. EasyOCR is used because torch is already installed and
PaddlePaddle would be a second large runtime for one small job.

**Measured before being trusted.** Run against the 48 crops a human had already
read by hand (`eval/m4/identity_labels.json`), EasyOCR returned nothing on 33,
and of the 15 it did read, 9 were right. That is 18.8 % accuracy and 60 %
precision on crops *chosen for being legible* — the full population is harder.

So this module is built for a voter, not for a reader. It returns every candidate
with its confidence and never decides anything; `vote.py` decides. The single
most important behaviour is that an unreadable crop returns nothing rather than a
guess, because a guess that reaches a vote is worse than a blank.
"""

from __future__ import annotations

import numpy as np

# The torso band, as fractions of the detection box. Same region ur/team.py
# samples for colour, widened slightly: a number sits lower than the shoulders.
TORSO = (0.12, 0.55, -0.06)
UPSCALE = 6                 # digits are 15-25 px tall; the reader wants more
MIN_CONF = 0.30             # below this the reader is guessing at noise
MAX_JERSEY = 99


class JerseyReader:
    """Wraps EasyOCR. Lazy, because loading it costs seconds and a GPU context."""

    def __init__(self, *, gpu: bool = True, upscale: int = UPSCALE):
        self._reader = None
        self.gpu = gpu
        self.upscale = upscale

    @property
    def reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["en"], gpu=self.gpu, verbose=False)
        return self._reader

    def crop(self, img: np.ndarray, box) -> np.ndarray | None:
        import cv2
        t0, t1, pad = TORSO
        x0, y0, x1, y1 = [int(round(v)) for v in box]
        h, w = y1 - y0, x1 - x0
        a = max(0, y0 + int(t0 * h))
        b = min(img.shape[0], y0 + int(t1 * h))
        c = max(0, x0 + int(pad * w))
        d = min(img.shape[1], x1 - int(pad * w))
        if b - a < 6 or d - c < 6:
            return None
        z = img[a:b, c:d]
        return None if z.size == 0 else cv2.resize(
            z, None, fx=self.upscale, fy=self.upscale, interpolation=cv2.INTER_CUBIC)

    def read(self, img: np.ndarray, box) -> list[dict]:
        """Every digit candidate this crop offers, with confidence. May be empty."""
        z = self.crop(img, box)
        if z is None:
            return []
        out = []
        for _, text, conf in self.reader.readtext(z, allowlist="0123456789",
                                                  detail=1, paragraph=False):
            t = text.strip()
            # A jersey is one or two digits. Anything else is the reader finding
            # structure in noise - a sponsor logo, a fold, a shadow.
            if not t.isdigit() or not 1 <= len(t) <= 2:
                continue
            v = int(t)
            if v > MAX_JERSEY or float(conf) < MIN_CONF:
                continue
            out.append({"jersey": v, "conf": round(float(conf), 4)})
        return out
