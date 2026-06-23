from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeviceIdentity:
    uuid: str
    device_id: str
    hostname: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def generate_identity() -> DeviceIdentity:
    device_id = secrets.token_hex(2).upper()
    return DeviceIdentity(
        uuid=str(uuid.uuid4()),
        device_id=device_id,
        hostname=f"ghostdvr-{device_id.lower()}",
    )


def load_or_create_identity(path: Path) -> DeviceIdentity:
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return DeviceIdentity(
            uuid=data["uuid"],
            device_id=data["device_id"],
            hostname=data["hostname"],
        )

    identity = generate_identity()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(identity.to_dict(), file, indent=2)
        file.write("\n")
    return identity
