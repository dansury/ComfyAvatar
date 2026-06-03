"""Устойчивая к обрывам сети загрузка файлов (моделей и т.п.).

Поддерживает докачку через HTTP Range: если соединение оборвалось, загрузка
продолжается с того места, где остановилась, а не начинается заново.
Прогресс сохраняется на диск (частичный файл .part), поэтому переживает даже
перезапуск процесса.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

import requests

from .logging_utils import setup_logging

logger = setup_logging()


def download_with_resume(
    url: str,
    dest: Path,
    *,
    chunk_size: int = 1024 * 1024,
    max_retries: int = 100,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
    timeout: int = 60,
) -> Path:
    """Скачивает url в dest с поддержкой докачки.

    Загружает в dest.part, по завершении переименовывает в dest.
    progress_cb(downloaded_bytes, total_bytes) вызывается по мере прогресса.
    Повторяет попытки с экспоненциальной задержкой при сетевых ошибках.
    """

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    if dest.exists():
        logger.info("Файл уже загружен: %s", dest)
        return dest

    attempt = 0
    while True:
        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
                # Если сервер не поддерживает докачку — начинаем заново.
                if downloaded and resp.status_code == 200:
                    logger.warning("Сервер не поддерживает докачку, загрузка с нуля.")
                    downloaded = 0
                    part.unlink(missing_ok=True)
                elif downloaded and resp.status_code != 206:
                    resp.raise_for_status()

                total = _total_size(resp, downloaded)
                mode = "ab" if downloaded else "wb"
                with part.open(mode) as fh:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            try:
                                progress_cb(downloaded, total)
                            except Exception:  # noqa: BLE001
                                logger.exception("Ошибка в progress callback загрузчика")

            part.replace(dest)
            logger.info("Загрузка завершена: %s (%d байт)", dest, downloaded)
            return dest

        except (requests.RequestException, OSError) as exc:
            attempt += 1
            if attempt > max_retries:
                logger.error("Загрузка %s провалена после %d попыток: %s", url, max_retries, exc)
                raise
            delay = min(30, 2 ** min(attempt, 5))
            logger.warning(
                "Обрыв загрузки (%s). Докачаем %s с байта %d через %ds (попытка %d/%d).",
                exc, dest.name, downloaded, delay, attempt, max_retries,
            )
            time.sleep(delay)


def _total_size(resp: requests.Response, already: int) -> Optional[int]:
    """Вычисляет полный размер файла по заголовкам ответа."""

    cr = resp.headers.get("Content-Range")
    if cr and "/" in cr:
        try:
            return int(cr.split("/")[-1])
        except ValueError:
            pass
    cl = resp.headers.get("Content-Length")
    if cl:
        try:
            return int(cl) + already
        except ValueError:
            pass
    return None
