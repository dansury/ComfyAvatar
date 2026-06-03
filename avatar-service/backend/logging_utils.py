"""Logging utilities.

Все логи пишутся одновременно:
- в консоль (stdout),
- в файл storage/app.log,
- в кольцевой буфер в памяти, который отдаётся в веб-интерфейс через /api/logs.

Это нужно, чтобы любую ошибку было легко увидеть и отправить разработчику.
"""

from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Deque, Dict, List

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = STORAGE_DIR / "app.log"

# Кольцевой буфер последних сообщений для отображения в UI.
_MEM_BUFFER: Deque[Dict[str, str]] = deque(maxlen=2000)
_BUFFER_LOCK = Lock()


class _MemoryHandler(logging.Handler):
    """Хендлер, складывающий записи в память для отдачи в веб-интерфейс."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            msg = self.format(record)
        except Exception:  # pragma: no cover - форматирование не должно падать
            msg = record.getMessage()
        with _BUFFER_LOCK:
            _MEM_BUFFER.append(
                {
                    "time": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                }
            )


_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Настраивает корневой логгер один раз и возвращает логгер приложения."""

    global _CONFIGURED
    logger = logging.getLogger("comfyavatar")
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception as exc:  # pragma: no cover
        logger.warning("Не удалось открыть лог-файл %s: %s", LOG_FILE, exc)

    mem = _MemoryHandler()
    mem.setFormatter(fmt)
    logger.addHandler(mem)

    _CONFIGURED = True
    return logger


def get_recent_logs(limit: int = 500) -> List[Dict[str, str]]:
    """Возвращает последние записи лога для веб-интерфейса."""

    with _BUFFER_LOCK:
        items = list(_MEM_BUFFER)
    if limit and limit < len(items):
        items = items[-limit:]
    return items
