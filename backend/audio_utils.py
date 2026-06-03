"""Утилиты для работы с аудиофайлами: конвертация, валидация, нормализация."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .logging_utils import setup_logging

logger = setup_logging()


def convert_to_wav(source: Path, dest: Optional[Path] = None) -> Path:
    """Конвертирует аудиофайл в WAV формат.

    Если источник уже WAV, просто копирует.
    Если нужна конвертация (OGG, MP3 и т.д.), использует torchaudio.
    Возвращает путь к WAV файлу.
    """

    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Аудиофайл не найден: {source}")

    if dest is None:
        dest = source.with_suffix(".wav")
    else:
        dest = Path(dest)

    # Если уже WAV, просто копируем
    if source.suffix.lower() == ".wav":
        source.rename(dest) if source != dest else None
        logger.info("Аудиофайл уже в формате WAV: %s", dest)
        return dest

    try:
        import torchaudio  # type: ignore

        logger.info("Конвертация %s в WAV...", source.suffix)

        # Загружаем аудио
        waveform, sample_rate = torchaudio.load(str(source))

        # Сохраняем в WAV
        dest.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(dest), waveform, sample_rate)

        logger.info("Конвертация завершена: %s", dest)
        return dest

    except ImportError:
        logger.error("torchaudio не установлен, не могу конвертировать %s", source.suffix)
        raise RuntimeError(
            "Для конвертации аудио из OGG/MP3 требуется torchaudio. "
            "Установите его из requirements.txt или используйте WAV."
        )
    except Exception as exc:
        logger.error("Ошибка конвертации аудио: %s", exc)
        raise


def get_audio_duration(path: Path) -> Optional[float]:
    """Возвращает длительность аудиофайла в секундах, или None если ошибка."""

    try:
        import torchaudio  # type: ignore

        waveform, sample_rate = torchaudio.load(str(path))
        frames = waveform.shape[-1]
        duration = frames / sample_rate
        return float(duration)

    except Exception as exc:
        logger.debug("Не удалось определить длительность %s: %s", path, exc)
        return None
