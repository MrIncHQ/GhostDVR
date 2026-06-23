from __future__ import annotations

import unittest

from ghost_dvr.stream_profile import describe_stream_profile


class StreamProfileTests(unittest.TestCase):
    def test_describes_mock_file(self):
        self.assertEqual(
            describe_stream_profile("test_video.mp4", "mock"),
            "Mock File (test_video.mp4)",
        )

    def test_describes_reolink_sub_stream(self):
        self.assertEqual(
            describe_stream_profile(
                "rtsp://camera/h264Preview_01_sub",
                "rtsp",
            ),
            "Reolink Sub Stream (H.264)",
        )

    def test_describes_unknown_rtsp(self):
        self.assertEqual(describe_stream_profile("rtsp://camera/live", "rtsp"), "RTSP Stream")


if __name__ == "__main__":
    unittest.main()
