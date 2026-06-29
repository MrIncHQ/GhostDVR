from __future__ import annotations

import unittest

from ghost_dvr.discovery import _parse_probe_match


class DiscoveryTests(unittest.TestCase):
    def test_parse_probe_match_extracts_name_host_and_rtsp_suggestions(self):
        payload = b"""<?xml version="1.0"?>
        <Envelope xmlns="http://www.w3.org/2003/05/soap-envelope">
          <Body>
            <ProbeMatches xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
              <ProbeMatch>
                <Scopes>onvif://www.onvif.org/name/Back%20PTZ</Scopes>
                <XAddrs>http://192.168.0.56:8000/onvif/device_service</XAddrs>
              </ProbeMatch>
            </ProbeMatches>
          </Body>
        </Envelope>"""

        camera = _parse_probe_match(payload)

        self.assertIsNotNone(camera)
        assert camera is not None
        self.assertEqual(camera.name, "Back PTZ")
        self.assertEqual(camera.host, "192.168.0.56")
        self.assertIn("rtsp://192.168.0.56:554/h264Preview_01_sub", camera.rtsp_suggestions)

    def test_parse_probe_match_ignores_invalid_xml(self):
        self.assertIsNone(_parse_probe_match(b"not xml"))


if __name__ == "__main__":
    unittest.main()
