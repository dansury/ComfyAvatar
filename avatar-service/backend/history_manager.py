"""Управление историей генераций и настройками.

История хранится в storage/history.json, настройки — в storage/settings.json.
Все операции потокобезопасны и устойчивы к повреждённым файлам.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from .logging_utils import setup_logging

logger = setup_logging()

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = STORAGE_DIR / "history.json"
SETTINGS_FILE = STORAGE_DIR / "settings.json"

_LOCK = Lock()

DEFAULT_SETTINGS: Dict[str, Any] = {
    "comfyui_path": None,
    "comfyui_url": "http://127.0.0.1:8188",
    "tts_engine": "xtts",  # xtts | kokoro
    "last_text": "",
    "language": "ru",
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Не удалось прочитать %s: %s. Используются значения по умолчанию.", path, exc)
        return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)  # атомарная замена


# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #
def load_settings() -> Dict[str, Any]:
    """Загружает настройки, дополняя отсутствующие ключи значениями по умолчанию."""

    with _LOCK:
        data = _read_json(SETTINGS_FILE, {})
        merged = {**DEFAULT_SETTINGS, **(data if isinstance(data, dict) else {})}
        return merged


def save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Сохраняет (мёрджит) настройки и возвращает актуальное состояние."""

    with _LOCK:
        data = _read_json(SETTINGS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        merged = {**DEFAULT_SETTINGS, **data, **updates}
        _write_json(SETTINGS_FILE, merged)
        logger.info("Настройки сохранены: %s", list(updates.keys()))
        return merged


# --------------------------------------------------------------------------- #
# История
# --------------------------------------------------------------------------- #
def get_history() -> List[Dict[str, Any]]:
    """Возвращает историю генераций (свежие — первыми)."""

    with _LOCK:
        data = _read_json(HISTORY_FILE, [])
        if not isinstance(data, list):
            return []
        return sorted(data, key=lambda x: x.get("timestamp", ""), reverse=True)


def add_history_entry(
    *,
    photo: Optional[str] = None,
    audio: Optional[str] = None,
    video: Optional[str] = None,
    text: str = "",
    status: str = "done",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Добавляет запись в историю и возвращает её."""

    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "photo": photo,
        "audio": audio,
        "video": video,
        "text": text,
        "status": status,
        "error": error,
    }
    with _LOCK:
        data = _read_json(HISTORY_FILE, [])
        if not isinstance(data, list):
            data = []
        data.append(entry)
        _write_json(HISTORY_FILE, data)
    logger.info("Запись истории добавлена: %s (status=%s)", entry["id"], status)
    return entry


def delete_history_entry(entry_id: str) -> bool:
    """Удаляет запись истории по id."""

    with _LOCK:
        data = _read_json(HISTORY_FILE, [])
        if not isinstance(data, list):
            return False
        new_data = [e for e in data if e.get("id") != entry_id]
        if len(new_data) == len(data):
            return False
        _write_json(HISTORY_FILE, new_data)
    logger.info("Запись истории удалена: %s", entry_id)
    return True
