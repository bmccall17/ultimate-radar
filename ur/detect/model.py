"""D-FINE, person class only.

Apache-2.0 code *and* Apache-2.0 weights — both checked, separately, before
install (`docs/07-licenses.md`). Ultralytics YOLO is AGPL-3.0 in every version
and is not used anywhere in this project.

**No SAHI.** The architecture originally required tiled inference on the grounds
that a downfield player is 25–45 px. M0 measured 50–70 px at the widest live
framing and 80–130 px in a typical wide play shot — the camera never frames the
whole field, so players never recede far enough to get small. So whole-frame
inference is tried first and measured against the M2 gate, and tiling is added
only if recall asks for it (`docs/04-milestones.md` M2, as revised).

Determinism: inference is seeded and run with cuDNN in deterministic mode. The
same frame gives the same boxes, which the eval numbers depend on being true.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "ustc-community/dfine-medium-coco"
COCO_PERSON = "person"
SEED = 20260827


def set_determinism(seed: int = SEED) -> None:
    import random

    import torch

    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


@dataclass
class Detection:
    box: tuple[float, float, float, float]     # x0, y0, x1, y1 in image pixels
    score: float

    @property
    def foot(self) -> tuple[float, float]:
        """Bottom-centre. docs/02-architecture.md flags this as wrong for an
        occluded or airborne player; M3 measures how wrong before anyone reaches
        for pose keypoints."""
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2.0, y1)

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]


class PersonDetector:
    """Thin wrapper. Loads once, runs batched, returns person boxes only."""

    def __init__(self, model_id: str = DEFAULT_MODEL, *, device: str | None = None,
                 threshold: float = 0.30, batch_size: int = 8,
                 nms_iou: float = 0.55, contain_frac: float = 0.80):
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        set_determinism()
        self.model_id = model_id
        self.threshold = threshold
        self.batch_size = batch_size
        # DETR-family detectors are described as NMS-free, and at a high score
        # threshold they are. Run one at 0.25 on this footage and a single player
        # can come back four times - the whole body plus the torso plus two
        # part-boxes - which is 0.86 duplicate pairs per frame, most of M2's
        # false-positive budget spent on one person. Both suppressions below are
        # post-processing on the detector's own output, not a labelling decision.
        self.nms_iou = nms_iou
        self.contain_frac = contain_frac
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForObjectDetection.from_pretrained(model_id).to(self.device)
        self.model.eval()

        id2label = self.model.config.id2label
        self.person_ids = {int(i) for i, lab in id2label.items()
                           if str(lab).lower() == COCO_PERSON}
        if not self.person_ids:
            raise RuntimeError(f"{model_id} has no 'person' class: {id2label}")

    def detect(self, images: list[np.ndarray]) -> list[list[Detection]]:
        """`images` are BGR, as OpenCV reads them."""
        import torch

        out: list[list[Detection]] = []
        for i in range(0, len(images), self.batch_size):
            chunk = images[i:i + self.batch_size]
            # ascontiguousarray, not just the slice: the BGR->RGB reversal leaves
            # a negative stride, which torch.from_numpy refuses.
            rgb = [np.ascontiguousarray(im[:, :, ::-1]) for im in chunk]
            inputs = self.processor(images=rgb, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                outputs = self.model(**inputs)
            sizes = torch.tensor([[im.shape[0], im.shape[1]] for im in chunk],
                                 device=self.device)
            results = self.processor.post_process_object_detection(
                outputs, target_sizes=sizes, threshold=self.threshold)
            for res in results:
                dets = []
                labels = res["labels"].tolist()
                scores = res["scores"].tolist()
                boxes = res["boxes"].tolist()
                for lab, sc, bx in zip(labels, scores, boxes):
                    if int(lab) in self.person_ids:
                        dets.append(Detection(box=tuple(float(v) for v in bx),
                                              score=float(sc)))
                dets.sort(key=lambda d: -d.score)
                out.append(self._suppress(dets))
        return out

    def _suppress(self, dets: list[Detection]) -> list[Detection]:
        """Standard IoU NMS, plus containment.

        Containment matters more than IoU here: a box round a player's torso sits
        entirely inside the box round the player, and their IoU can be only ~0.5
        while they are plainly the same person. Suppress a box when most of *it*
        lies inside a better-scoring one, whatever the union says.
        """
        import torch
        from torchvision.ops import nms

        if len(dets) < 2:
            return dets
        boxes = torch.tensor([d.box for d in dets], dtype=torch.float32)
        scores = torch.tensor([d.score for d in dets], dtype=torch.float32)
        keep = nms(boxes, scores, self.nms_iou).tolist()
        keep.sort(key=lambda i: -dets[i].score)

        final: list[int] = []
        for i in keep:
            bi = dets[i].box
            ai = max((bi[2] - bi[0]) * (bi[3] - bi[1]), 1e-6)
            covered = False
            for j in final:
                bj = dets[j].box
                ix = max(0.0, min(bi[2], bj[2]) - max(bi[0], bj[0]))
                iy = max(0.0, min(bi[3], bj[3]) - max(bi[1], bj[1]))
                if (ix * iy) / ai >= self.contain_frac:
                    covered = True
                    break
            if not covered:
                final.append(i)
        return [dets[i] for i in sorted(final, key=lambda i: -dets[i].score)]

    def info(self) -> dict:
        return {"model_id": self.model_id, "device": self.device,
                "threshold": self.threshold, "nms_iou": self.nms_iou,
                "contain_frac": self.contain_frac, "seed": SEED,
                "tiling": "none - whole frame; see the note in this module"}
