from __future__ import annotations

import socket
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from urllib.parse import urlparse


WS_DISCOVERY_ADDRESS = ("239.255.255.250", 3702)


@dataclass(frozen=True)
class DiscoveredCamera:
    name: str
    host: str
    xaddrs: list[str]
    rtsp_suggestions: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def discover_onvif_cameras(timeout_seconds: float = 3.0) -> list[DiscoveredCamera]:
    message = _probe_message()
    responses: list[bytes] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout_seconds)
        sock.sendto(message.encode("utf-8"), WS_DISCOVERY_ADDRESS)
        while True:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                break
            responses.append(data)

    cameras = [_parse_probe_match(response) for response in responses]
    unique: dict[str, DiscoveredCamera] = {}
    for camera in cameras:
        if camera is None:
            continue
        unique[camera.host] = camera
    return sorted(unique.values(), key=lambda camera: camera.host)


def _probe_message() -> str:
    message_id = f"uuid:{uuid.uuid4()}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
  xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>{message_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""


def _parse_probe_match(payload: bytes) -> DiscoveredCamera | None:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None

    xaddrs_text = _first_text(root, "XAddrs")
    if not xaddrs_text:
        return None
    xaddrs = [item for item in xaddrs_text.split() if item]
    host = _host_from_xaddrs(xaddrs)
    if not host:
        return None

    scopes_text = _first_text(root, "Scopes") or ""
    name = _name_from_scopes(scopes_text) or f"Camera {host}"
    return DiscoveredCamera(
        name=name,
        host=host,
        xaddrs=xaddrs,
        rtsp_suggestions=_rtsp_suggestions(host, name, scopes_text, xaddrs),
    )


def _first_text(root: ET.Element, local_name: str) -> str | None:
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == local_name and element.text:
            return element.text.strip()
    return None


def _host_from_xaddrs(xaddrs: list[str]) -> str:
    for address in xaddrs:
        parsed = urlparse(address)
        if parsed.hostname:
            return parsed.hostname
    return ""


def _name_from_scopes(scopes: str) -> str:
    for scope in scopes.split():
        if "/name/" in scope:
            return scope.rsplit("/name/", 1)[-1].replace("%20", " ")
        if "/hardware/" in scope:
            return scope.rsplit("/hardware/", 1)[-1].replace("%20", " ")
    return ""


def _rtsp_suggestions(host: str, name: str = "", scopes: str = "", xaddrs: list[str] | None = None) -> list[str]:
    fingerprint = " ".join([name, scopes, " ".join(xaddrs or [])]).lower()
    suggestions: list[str] = []

    if any(brand in fingerprint for brand in ["amcrest", "dahua"]):
        suggestions.extend(
            [
                f"rtsp://{host}:554/cam/realmonitor?channel=1&subtype=1",
                f"rtsp://{host}:554/cam/realmonitor?channel=1&subtype=0",
            ]
        )
    elif "reolink" in fingerprint:
        suggestions.extend(
            [
                f"rtsp://{host}:554/h264Preview_01_sub",
                f"rtsp://{host}:554/h264Preview_01_main",
            ]
        )

    suggestions.extend(
        [
            f"rtsp://{host}:554/cam/realmonitor?channel=1&subtype=1",
            f"rtsp://{host}:554/cam/realmonitor?channel=1&subtype=0",
            f"rtsp://{host}:554/h264Preview_01_sub",
            f"rtsp://{host}:554/h264Preview_01_main",
            f"rtsp://{host}:554/stream1",
        ]
    )
    return list(dict.fromkeys(suggestions))
