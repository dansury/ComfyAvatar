"""Генерация речи (TTS) с клонированием голоса.

Поддерживаются два движка:
- Coqui XTTS v2 (tts_engine="xtts") — клонирование голоса по образцу.
- Kokoro TTS (tts_engine="kokoro") — лёгкий быстрый движок (без клонирования).

Загрузка моделей ленивая и кешируется. Если нужные библиотеки не установлены,
функция возвращает понятную ошибку, а не падает — сервис остаётся работающим.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from .history_manager import load_settings
from .logging_utils import setup_logging

logger = setup_logging()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "storage" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_MODEL_LOCK = Lock()
_xtts_model = None  # кеш модели XTTS
_kokoro_pipeline = None  # кеш пайплайна Kokoro


def _detect_device() -> str:
    try:
        import torch  # type: ignore

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


# --------------------------------------------------------------------------- #
# XTTS v2
# --------------------------------------------------------------------------- #
def _load_xtts():
    global _xtts_model
    if _xtts_model is not None:
        return _xtts_model
    with _MODEL_LOCK:
        if _xtts_model is not None:
            return _xtts_model
        from TTS.api import TTS  # type: ignore  # noqa: N811

        device = _detect_device()
        logger.info("Загрузка Coqui XTTS v2 на устройство %s...", device)
        model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        model.to(device)
        _xtts_model = model
        logger.info("XTTS v2 загружена.")
        return _xtts_model


def _generate_xtts(text: str, voice_sample: Optional[Path], language: str, out_path: Path) -> None:
    from . import audio_utils

    model = _load_xtts()
    kwargs = {"text": text, "file_path": str(out_path), "language": language}
    if voice_sample and voice_sample.exists():
        # Если файл OGG, пытаемся использовать напрямую.
        # Если ошибка — конвертируем в WAV.
        speaker_wav = str(voice_sample)
        if voice_sample.suffix.lower() == ".ogg":
            try:
                # Пытаемся использовать OGG напрямую
                kwargs["speaker_wav"] = speaker_wav
                logger.debug("Используется OGG файл для клонирования голоса: %s", voice_sample)
            except Exception:  # noqa: BLE001
                # Если не работает, конвертируем
                logger.warning("OGG не поддерживается, конвертируем в WAV: %s", voice_sample)
                try:
                    wav_path = audio_utils.convert_to_wav(voice_sample)
                    kwargs["speaker_wav"] = str(wav_path)
                except Exception as exc:
                    logger.error("Ошибка конвертации OGG: %s", exc)
                    raise
        else:
            kwargs["speaker_wav"] = speaker_wav
    else:
        # Без образца используем встроенный голос (первый доступный).
        try:
            speakers = getattr(model, "speakers", None)
            if speakers:
                kwargs["speaker"] = speakers[0]
        except Exception:  # noqa: BLE001
            pass
    model.tts_to_file(**kwargs)


# --------------------------------------------------------------------------- #
# Kokoro
# --------------------------------------------------------------------------- #
def _load_kokoro():
    global _kokoro_pipeline
    if _kokoro_pipeline is not None:
        return _kokoro_pipeline
    with _MODEL_LOCK:
        if _kokoro_pipeline is not None:
            return _kokoro_pipeline
        from kokoro import KPipeline  # type: ignore

        logger.info("Загрузка Kokoro TTS...")
        _kokoro_pipeline = KPipeline(lang_code="a")
        logger.info("Kokoro загружена.")
        return _kokoro_pipeline


def _generate_kokoro(text: str, out_path: Path) -> None:
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore

    pipeline = _load_kokoro()
    chunks = []
    for _, _, audio in pipeline(text, voice="af_heart"):
        chunks.append(audio)
    if not chunks:
        raise RuntimeError("Kokoro не вернул аудио")
    audio = np.concatenate(chunks)
    sf.write(str(out_path), audio, 24000)


# --------------------------------------------------------------------------- #
# Публичный API
# --------------------------------------------------------------------------- #
def generate_tts(
    text: str,
    voice_sample: Optional[Path] = None,
    engine: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict[str, object]:
    """Генерирует аудио из текста.

    Возвращает {success, audio: <abs path or None>, message}.
    Никогда не бросает исключение наружу — ошибки возвращаются в message.
    """

    text = (text or "").strip()
    if not text:
        return {"success": False, "audio": None, "message": "Текст для озвучки пуст"}

    settings = load_settings()
    engine = (engine or settings.get("tts_engine") or "xtts").lower()
    language = language or settings.get("language") or "ru"

    out_path = OUTPUT_DIR / f"tts_{uuid.uuid4().hex}.wav"
    logger.info("Генерация TTS: engine=%s, lang=%s, chars=%d", engine, language, len(text))

    try:
        if engine == "kokoro":
            _generate_kokoro(text, out_path)
        else:
            _generate_xtts(text, voice_sample, language, out_path)
    except ImportError as exc:
        msg = (
            f"Движок TTS '{engine}' недоступен: не установлены зависимости ({exc}). "
            "Установите их из requirements.txt."
        )
        logger.error(msg)
        return {"success": False, "audio": None, "message": msg}
    except Exception as exc:  # noqa: BLE001
        msg = f"Ошибка генерации TTS ({engine}): {exc}"
        logger.exception(msg)
        return {"success": False, "audio": None, "message": msg}

    if not out_path.exists():
        return {"success": False, "audio": None, "message": "Файл аудио не создан"}

    logger.info("TTS готов: %s", out_path)
    return {"success": True, "audio": str(out_path), "message": "Аудио сгенерировано"}
