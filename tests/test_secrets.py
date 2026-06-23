from __future__ import annotations

import unittest

from ghost_dvr.secrets import redact_url_credentials


class SecretsTests(unittest.TestCase):
    def test_redacts_rtsp_credentials(self):
        text = "Error opening rtsp://admin:secret@192.168.0.56:554/stream1"

        self.assertEqual(
            redact_url_credentials(text),
            "Error opening rtsp://<credentials>@192.168.0.56:554/stream1",
        )

    def test_leaves_urls_without_credentials(self):
        text = "Error opening rtsp://192.168.0.56:554/stream1"

        self.assertEqual(redact_url_credentials(text), text)


if __name__ == "__main__":
    unittest.main()
