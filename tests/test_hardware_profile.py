from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ghost_dvr.hardware.profile import (
    PI_4_PROFILE,
    PI_5_PROFILE,
    PI_ZERO_2_W_PROFILE,
    WINDOWS_PC_PROFILE,
    detect_hardware_profile,
)


class HardwareProfileTests(unittest.TestCase):
    def test_detects_pi_zero_2_profile_from_cpuinfo(self):
        self.assertEqual(
            _detect_from_text("Model\t: Raspberry Pi Zero 2 W Rev 1.0").name,
            PI_ZERO_2_W_PROFILE.name,
        )

    def test_detects_pi_4_profile_from_cpuinfo(self):
        self.assertEqual(
            _detect_from_text("Model\t: Raspberry Pi 4 Model B Rev 1.5").name,
            PI_4_PROFILE.name,
        )

    def test_detects_pi_5_profile_from_cpuinfo(self):
        self.assertEqual(
            _detect_from_text("Model\t: Raspberry Pi 5 Model B Rev 1.0").name,
            PI_5_PROFILE.name,
        )

    def test_windows_pc_profile_supports_more_sources_than_pi(self):
        self.assertEqual(WINDOWS_PC_PROFILE.name, "Windows PC")
        self.assertGreater(WINDOWS_PC_PROFILE.recommended_sources, PI_5_PROFILE.recommended_sources)


def _detect_from_text(text: str):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "cpuinfo"
        path.write_text(text, encoding="utf-8")
        return detect_hardware_profile(path)


if __name__ == "__main__":
    unittest.main()
