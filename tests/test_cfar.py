"""CFAR ship-detection unit tests against synthetic SAR.

The synthetic field is Gaussian-distributed sea clutter with a handful of
planted point targets at known locations. CFAR must:
  1. Find every planted target (high recall),
  2. Not invent ghost detections (low false positive count),
  3. Produce centroids within a couple of pixels of ground truth.

The seed is fixed so this is deterministic across machines.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.sensors.cfar import CFARParams, cfar_detect


def _synthetic_sar(
    h: int = 512,
    w: int = 512,
    targets: list[tuple[int, int, float, int]] | None = None,
    clutter_mean_db: float = -16.0,
    clutter_std_db: float = 1.5,
    seed: int = 42,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Generate Gaussian clutter + planted targets.

    Each target is a (row, col, peak_db, radius_px) tuple drawn as a small
    bright disc. Returns (image_db, ground_truth_pixel_centroids).
    """
    rng = np.random.default_rng(seed)
    img = rng.normal(clutter_mean_db, clutter_std_db, size=(h, w)).astype(np.float32)
    truth: list[tuple[int, int]] = []
    for r, c, peak_db, radius in targets or []:
        rr, cc = np.ogrid[:h, :w]
        mask = (rr - r) ** 2 + (cc - c) ** 2 <= radius * radius
        img[mask] = np.maximum(img[mask], peak_db)
        truth.append((r, c))
    return img, truth


def test_cfar_finds_planted_targets():
    targets = [
        # (row, col, peak_db, radius_px)
        (100, 100, -2.0, 2),     # bright, small (~50m vessel)
        (300, 250, -5.0, 3),     # bright, medium
        (400, 400, -8.0, 4),     # less bright, larger (~80m vessel)
    ]
    img, truth = _synthetic_sar(targets=targets)

    detections = cfar_detect(img, CFARParams(alpha=4.0))

    assert detections, "CFAR returned no detections at all"

    # Every planted target must have a detection within 4 px
    for tr, tc in truth:
        nearest = min(detections, key=lambda d: (d.row - tr) ** 2 + (d.col - tc) ** 2)
        dist = ((nearest.row - tr) ** 2 + (nearest.col - tc) ** 2) ** 0.5
        assert dist <= 4.0, f"Target ({tr},{tc}) not found; nearest detection at ({nearest.row},{nearest.col}), dist={dist:.1f}px"

    # All detections should have valid confidence in [0, 1]
    for d in detections:
        assert 0.0 <= d.confidence <= 1.0


def test_cfar_low_false_positive_rate_on_clean_clutter():
    img, _ = _synthetic_sar(targets=[])  # pure clutter
    detections = cfar_detect(img, CFARParams(alpha=4.0))
    # Pfa is low but not zero — accept up to a small handful of speckle hits.
    # On 512x512 = 262k pixels at Pfa~3e-5 we expect ~8 single-pixel hits, but
    # min_size_pixels=3 filters most. Empirically 0-3 with seed=42.
    assert len(detections) <= 5, f"Too many false positives on clean clutter: {len(detections)}"


def test_cfar_confidence_grows_with_signal():
    """A brighter target should yield a higher confidence score than a dimmer one."""
    dim = [(100, 100, -10.0, 2)]
    bright = [(100, 100, 0.0, 4)]
    d_dim    = cfar_detect(_synthetic_sar(targets=dim)[0])
    d_bright = cfar_detect(_synthetic_sar(targets=bright)[0])
    assert d_dim and d_bright
    assert d_bright[0].confidence > d_dim[0].confidence


def test_cfar_rejects_pathological_input():
    with pytest.raises(ValueError):
        cfar_detect(np.zeros((10, 10, 3)))  # 3-D input
    with pytest.raises(ValueError):
        cfar_detect(np.zeros((10, 10)), CFARParams(training_cells=0))
