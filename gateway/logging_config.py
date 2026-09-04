from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_file_logger(base_dir: Path) -> logging.Logger:
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger("guard_gateway")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(log_dir / "guard_gateway.log", encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def append_jsonl(base_dir: Path, name: str, payload: dict[str, Any]) -> None:
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with (log_dir / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
