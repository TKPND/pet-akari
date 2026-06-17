import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_pro_keypose_motion as motion
from pet_akari import clawd_hq_theme as hq


@contextmanager
def temporary_theme_sizes(master_size=(128, 160), runtime_size=(32, 40)):
    original_master = hq.MASTER_SIZE
    original_runtime = hq.RUNTIME_SIZE
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE = original_master
        hq.RUNTIME_SIZE = original_runtime


def raw_sample(path: Path, state_index: int = 0):
    image = Image.new("RGB", (80, 120), (242, 242, 242))
    for y in range(24, 105):
        for x in range(24 + state_index, 56 + state_index):
            image.putpixel((x, y), (20 + state_index * 20, 140, 210))
    for y in range(48, 58):
        for x in range(34, 46):
            image.putpixel((x, y), (248, 248, 248))
    image.save(path)


class AkariPhase4ProKeyposeMotionTests(unittest.TestCase):
    def test_remove_boundary_background_keeps_enclosed_light_foreground(self):
        image = Image.new("RGB", (20, 20), (245, 245, 245))
        for y in range(5, 15):
            for x in range(5, 15):
                image.putpixel((x, y), (10, 10, 10))
        for y in range(8, 12):
            for x in range(8, 12):
                image.putpixel((x, y), (245, 245, 245))

        transparent = motion.remove_boundary_background(image, tolerance=18)

        self.assertEqual(transparent.getpixel((0, 0))[3], 0)
        self.assertEqual(transparent.getpixel((9, 9))[3], 255)

    def test_build_motion_preview_from_keyposes_writes_frames_and_qa(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            source_dir = root / "raw"
            source_dir.mkdir()
            for index, state in enumerate(hq.CORE_STATES):
                raw_sample(source_dir / f"{state}.png", index)

            result = motion.build_keypose_motion_preview(
                source_dir=source_dir,
                run_dir=root / "run",
                frame_count=8,
            )

            self.assertTrue((result.run_dir / "normalized" / "idle.png").is_file())
            self.assertEqual(len(list((result.run_dir / "masters" / "idle").glob("*.png"))), 8)
            self.assertTrue((result.run_dir / "qa" / "previews" / "idle.gif").is_file())
            self.assertTrue((result.run_dir / "qa" / "contact-sheet.png").is_file())
            self.assertTrue((result.run_dir / "qa" / "keypose-motion-summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
