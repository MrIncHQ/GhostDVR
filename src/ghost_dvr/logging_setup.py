from __future__ import annotations

import logging
from pathlib import Path


def configure_event_logger(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_path = path.resolve()

    logger = logging.getLogger("ghost_dvr.events")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) != target_path:
            logger.removeHandler(handler)
            handler.close()

    if not any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename) == target_path
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(target_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    return logger


def close_event_logger() -> None:
    logger = logging.getLogger("ghost_dvr.events")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
