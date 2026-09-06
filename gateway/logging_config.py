from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_file_logger(base_dir: Path) -> logging.Logger:
    # MCP stdio 模式不能把业务日志打印到 stdout，否则可能干扰协议通信。
    # 所以运行状态统一写入 logs/guard_gateway.log。
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger("guard_gateway")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        log_path = log_dir / "guard_gateway.log"
        try:
            handler = logging.FileHandler(log_path, encoding="utf-8")
        except PermissionError:
            # Windows 下日志文件可能被另一个进程占用，退到带 pid 的文件名。
            try:
                log_path = log_dir / f"guard_gateway_{os.getpid()}.log"
                handler = logging.FileHandler(log_path, encoding="utf-8")
            except PermissionError:
                # 最坏情况禁用文件日志，但不影响主流程。
                handler = logging.NullHandler()
        if not isinstance(handler, logging.NullHandler):
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def append_jsonl(base_dir: Path, name: str, payload: dict[str, Any]) -> None:
    # 结构化审计日志：一行一个 JSON 事件，便于后续导入日志系统或审计平台。
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    try:
        with (log_dir / name).open("a", encoding="utf-8") as fh:
            fh.write(line)
    except PermissionError:
        # 同样处理文件占用问题，尽量保证审计事件可落盘。
        fallback = f"{Path(name).stem}_{os.getpid()}{Path(name).suffix}"
        try:
            with (log_dir / fallback).open("a", encoding="utf-8") as fh:
                fh.write(line)
        except PermissionError:
            return
