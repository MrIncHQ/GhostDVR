from __future__ import annotations

import re


_URL_CREDENTIALS = re.compile(r"(rtsp://)([^/@\s]+)@")


def redact_url_credentials(text: str) -> str:
    return _URL_CREDENTIALS.sub(r"\1<credentials>@", text)
