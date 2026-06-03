"""ComfyAvatar — FastAPI backend.

Запуск:  python -m backend.main
Открыть: http://127.0.0.1:8000

Эндпоинты:
- GET  /                          — веб-интерфейс
- GET  /api/status                — статус ComfyUI и окружения
- POST /api/comfyui/start         — найти и запустить ComfyUI
- POST /api/comfyui/detect        — только поиск пути
- GET  /api/settings              — получить настройки
- POST /api/settings              — сохранить настройки
- GET  /api/logs                  — последние логи (для UI)
- POST /api/upload/photo          — загрузить фото
- POST /api/upload/voice          — загрузить голос (wav/mp3/ogg)
- POST /api/upload/voice-from-url — загрузить голос по URL (Telegram и т.д.)
- POST /api/generate              — запустить генерацию (возвращает job_id)
- GET  /api/history               — история генераций
- DELETE /api/history/{id}        — удалить запись
- WS   /ws/{job_id}               — прогресс генерации
- GET  /media/...                 — отдача загруженных/сгенерированных файлов
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import threading
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import comfy_utils, history_manager, tts_engine
from .logging_utils import get_recent_logs, setup_logging

logger = setup_logging()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
OUTPUT_DIR = STORAGE_DIR / "outputs"
for d in (UPLOAD_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
ALLOWED_AUDIO_EXT = {".wav", ".mp3", ".ogg", ".m4a", ".webm"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB

# --- Сетевые настройки сервера --------------------------------------------- #
HOST = "127.0.0.1"
DEFAULT_PORT = 8000
# Фактический адрес, на котором поднялся сервер. Выставляется в main() до старта
# uvicorn, чтобы стартовый хук открыл браузер по правильному порту.
_server_url = f"http://{HOST}:{DEFAULT_PORT}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Старт и остановка приложения (современная замена устаревшему on_event).

    jobs и _open_browser_delayed определены ниже по модулю — имена в теле
    разрешаются во время запуска, поэтому порядок их определения роли не играет.
    """
    jobs.loop = asyncio.get_running_loop()
    logger.info("ComfyAvatar backend запущен. Frontend: %s", FRONTEND_DIR)
    _open_browser_delayed(_server_url, delay=1.5)
    yield


app = FastAPI(title="ComfyAvatar", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Менеджер фоновых задач и прогресса
# --------------------------------------------------------------------------- #
class JobManager:
    """Хранит состояние генераций и транслирует прогресс в WebSocket."""

    def __init__(self) -> None:
        self.jobs: Dict[str, Dict] = {}
        self.queues: Dict[str, asyncio.Queue] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def create(self) -> str:
        job_id = uuid.uuid4().hex
        self.jobs[job_id] = {"status": "pending", "progress": 0.0, "message": "Ожидание", "result": None}
        self.queues[job_id] = asyncio.Queue()
        return job_id

    def update(self, job_id: str, *, message: str, progress: float, status: str = "running") -> None:
        job = self.jobs.get(job_id)
        if job is None:
            return
        job.update({"status": status, "progress": progress, "message": message})
        self._push(job_id, dict(job))

    def finish(self, job_id: str, *, status: str, message: str, result: Optional[Dict]) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            return
        job.update({"status": status, "message": message, "result": result, "progress": 1.0})
        self._push(job_id, dict(job))

    def _push(self, job_id: str, payload: Dict) -> None:
        queue = self.queues.get(job_id)
        if queue is None or self.loop is None:
            return
        # Безопасно кладём в очередь из любого потока.
        self.loop.call_soon_threadsafe(queue.put_nowait, payload)


jobs = JobManager()


def _open_browser_delayed(url: str, delay: float = 1.0) -> None:
    """Open browser after delay to ensure server is ready."""
    def _open():
        import time
        time.sleep(delay)
        webbrowser.open(url)
    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


# --------------------------------------------------------------------------- #
# Утилиты файлов
# --------------------------------------------------------------------------- #
def _save_upload(upload: UploadFile, dest_dir: Path, allowed_ext: set, max_bytes: int) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Недопустимый формат: {ext or 'нет расширения'}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}{ext}"
    size = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="Файл слишком большой")
            out.write(chunk)
    logger.info("Загружен файл: %s (%d байт)", dest.name, size)
    return dest


def _media_url(path: Optional[str]) -> Optional[str]:
    """Преобразует абсолютный путь внутри storage в URL /media/..."""

    if not path:
        return None
    p = Path(path)
    try:
        rel = p.relative_to(STORAGE_DIR)
    except ValueError:
        return None
    return f"/media/{rel.as_posix()}"


# --------------------------------------------------------------------------- #
# API: статус / настройки / логи
# --------------------------------------------------------------------------- #
@app.get("/api/status")
async def api_status() -> Dict:
    info = comfy_utils.find_comfyui()
    running = comfy_utils.is_comfyui_running()
    return {
        "comfyui_found": info is not None,
        "comfyui_info": info,
        "comfyui_running": running,
        "settings": history_manager.load_settings(),
    }


@app.get("/api/ping")
async def api_ping() -> Dict:
    """Лёгкая отметка «я — ComfyAvatar»: позволяет распознать уже запущенный экземпляр."""
    return {"app": "comfyavatar", "version": app.version}


@app.post("/api/comfyui/detect")
async def api_detect() -> Dict:
    info = comfy_utils.find_comfyui(use_cache=False)
    if not info:
        return {"found": False, "message": "ComfyUI не найден на стандартных путях"}
    return {"found": True, "info": info}


@app.post("/api/comfyui/start")
async def api_start() -> Dict:
    # Запуск может занять время — выполняем в пуле потоков.
    result = await asyncio.to_thread(comfy_utils.start_comfyui_if_needed)
    return result


@app.get("/api/settings")
async def api_get_settings() -> Dict:
    return history_manager.load_settings()


class SettingsBody(BaseModel):
    comfyui_path: Optional[str] = None
    comfyui_url: Optional[str] = None
    tts_engine: Optional[str] = None
    last_text: Optional[str] = None
    language: Optional[str] = None


@app.post("/api/settings")
async def api_save_settings(body: SettingsBody) -> Dict:
    updates = {k: v for k, v in body.dict().items() if v is not None}
    return history_manager.save_settings(updates)


@app.get("/api/logs")
async def api_logs(limit: int = 300) -> Dict:
    return {"logs": get_recent_logs(limit)}


# --------------------------------------------------------------------------- #
# API: загрузка
# --------------------------------------------------------------------------- #
@app.post("/api/upload/photo")
async def api_upload_photo(file: UploadFile = File(...)) -> Dict:
    dest = _save_upload(file, UPLOAD_DIR, ALLOWED_IMAGE_EXT, MAX_IMAGE_BYTES)
    return {"path": str(dest), "url": _media_url(str(dest)), "name": dest.name}


@app.post("/api/upload/voice")
async def api_upload_voice(file: UploadFile = File(...)) -> Dict:
    dest = _save_upload(file, UPLOAD_DIR, ALLOWED_AUDIO_EXT, MAX_AUDIO_BYTES)
    return {"path": str(dest), "url": _media_url(str(dest)), "name": dest.name}


class UploadFromUrlBody(BaseModel):
    url: str
    convert_to_wav: bool = False  # Конвертировать OGG в WAV для совместимости


@app.post("/api/upload/voice-from-url")
async def api_upload_voice_from_url(body: UploadFromUrlBody) -> Dict:
    """Загружает аудиофайл по URL (например, OGG из Telegram).

    Поддерживает прямые ссылки на аудиофайлы.
    Если convert_to_wav=true, конвертирует в WAV для лучшей совместимости.
    """
    from . import audio_utils, downloader

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL не может быть пустым")

    # Определяем расширение из URL или используем .ogg по умолчанию
    url_path = url.split("?")[0] if "?" in url else url  # убираем query параметры
    ext = Path(url_path).suffix.lower()
    if not ext or ext not in ALLOWED_AUDIO_EXT:
        ext = ".ogg"  # по умолчанию OGG для Telegram

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    try:
        logger.info("Загрузка голоса с URL: %s", url)
        # Используем встроенный downloader для загрузки с поддержкой докачки
        downloaded = await asyncio.to_thread(downloader.download_with_resume, url, dest)

        # Проверяем размер
        size = downloaded.stat().st_size
        if size > MAX_AUDIO_BYTES:
            downloaded.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Файл слишком большой")

        # Опционально конвертируем в WAV
        if body.convert_to_wav and downloaded.suffix.lower() != ".wav":
            try:
                downloaded = await asyncio.to_thread(audio_utils.convert_to_wav, downloaded)
            except Exception as exc:
                logger.warning("Не удалось конвертировать в WAV: %s (используем оригинальный формат)", exc)
                # Продолжаем с оригинальным форматом

        logger.info("Загружен голос с URL: %s (%d байт)", downloaded.name, size)
        return {"path": str(downloaded), "url": _media_url(str(downloaded)), "name": downloaded.name}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка при загрузке с URL %s: %s", url, exc)
        raise HTTPException(status_code=400, detail=f"Ошибка загрузки: {str(exc)}")


# --------------------------------------------------------------------------- #
# API: генерация
# --------------------------------------------------------------------------- #
class GenerateBody(BaseModel):
    photo_path: str
    text: str
    voice_path: Optional[str] = None
    tts_engine: Optional[str] = None
    language: Optional[str] = None


@app.post("/api/generate")
async def api_generate(body: GenerateBody) -> Dict:
    photo = Path(body.photo_path)
    if not photo.exists():
        raise HTTPException(status_code=400, detail="Фото не найдено, загрузите заново")
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="Введите текст для озвучки")

    history_manager.save_settings({"last_text": body.text})

    job_id = jobs.create()
    # Запускаем пайплайн в фоне, чтобы сразу вернуть job_id для WebSocket.
    asyncio.create_task(asyncio.to_thread(_run_pipeline, job_id, body))
    return {"job_id": job_id}


def _run_pipeline(job_id: str, body: GenerateBody) -> None:
    """Полный пайплайн: TTS -> запуск ComfyUI -> SadTalker -> сохранение истории."""

    photo = Path(body.photo_path)
    voice = Path(body.voice_path) if body.voice_path else None

    try:
        jobs.update(job_id, message="Генерация речи (TTS)...", progress=0.1)
        tts_result = tts_engine.generate_tts(
            body.text, voice_sample=voice, engine=body.tts_engine, language=body.language
        )
        if not tts_result["success"]:
            _fail(job_id, body, photo, voice, tts_result["message"])
            return
        audio_path = Path(str(tts_result["audio"]))

        jobs.update(job_id, message="Проверка/запуск ComfyUI...", progress=0.25)
        start_res = comfy_utils.start_comfyui_if_needed()
        if not start_res.get("running"):
            _fail(job_id, body, photo, audio_path, start_res.get("message", "ComfyUI недоступен"))
            return

        def progress_cb(msg: str, frac: float) -> None:
            # Маппим прогресс воркфлоу в диапазон 0.3..0.95.
            jobs.update(job_id, message=msg, progress=0.3 + frac * 0.65)

        wf = comfy_utils.run_sadtalker_workflow(photo, audio_path, progress_cb=progress_cb)
        if not wf["success"]:
            _fail(job_id, body, photo, audio_path, wf["message"])
            return

        video_path = Path(str(wf["video"]))
        entry = history_manager.add_history_entry(
            photo=str(photo),
            audio=str(audio_path),
            video=str(video_path),
            text=body.text,
            status="done",
        )
        result = _entry_to_payload(entry)
        jobs.finish(job_id, status="done", message="Готово", result=result)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка в пайплайне генерации")
        _fail(job_id, body, photo, voice, f"Внутренняя ошибка: {exc}")


def _fail(job_id: str, body: GenerateBody, photo: Path, audio: Optional[Path], message: str) -> None:
    logger.error("Генерация %s провалена: %s", job_id, message)
    history_manager.add_history_entry(
        photo=str(photo),
        audio=str(audio) if audio else None,
        video=None,
        text=body.text,
        status="error",
        error=message,
    )
    jobs.finish(job_id, status="error", message=message, result=None)


def _entry_to_payload(entry: Dict) -> Dict:
    return {
        **entry,
        "photo_url": _media_url(entry.get("photo")),
        "audio_url": _media_url(entry.get("audio")),
        "video_url": _media_url(entry.get("video")),
    }


# --------------------------------------------------------------------------- #
# API: история
# --------------------------------------------------------------------------- #
@app.get("/api/history")
async def api_history() -> Dict:
    items = [_entry_to_payload(e) for e in history_manager.get_history()]
    return {"history": items}


@app.delete("/api/history/{entry_id}")
async def api_delete_history(entry_id: str) -> Dict:
    ok = history_manager.delete_history_entry(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# WebSocket прогресса
# --------------------------------------------------------------------------- #
@app.websocket("/ws/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    queue = jobs.queues.get(job_id)
    if queue is None:
        await websocket.send_json({"status": "error", "message": "Задача не найдена", "progress": 1.0})
        await websocket.close()
        return
    # Отправим текущее состояние сразу.
    current = jobs.jobs.get(job_id)
    if current:
        await websocket.send_json(dict(current))
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
            if payload.get("status") in ("done", "error"):
                break
    except WebSocketDisconnect:
        logger.info("WebSocket клиента отключился: %s", job_id)
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Отдача медиа и фронтенда
# --------------------------------------------------------------------------- #
@app.get("/media/{file_path:path}")
async def media(file_path: str):
    target = (STORAGE_DIR / file_path).resolve()
    if STORAGE_DIR.resolve() not in target.parents and target != STORAGE_DIR.resolve():
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(str(target))


# Статика фронтенда монтируется последней, чтобы не перехватывать /api.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:  # pragma: no cover

    @app.get("/")
    async def _no_frontend() -> JSONResponse:
        return JSONResponse({"message": "Frontend не найден", "dir": str(FRONTEND_DIR)})


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #
def _port_is_free(host: str, port: int) -> bool:
    """True, если на (host, port) можно поднять сервер (порт свободен)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _find_free_port(host: str, start_port: int, attempts: int = 20) -> Optional[int]:
    """Ищет ближайший свободный порт, начиная со start_port."""
    for candidate in range(start_port, min(start_port + attempts, 65536)):
        if _port_is_free(host, candidate):
            return candidate
    return None


def _looks_like_comfyavatar(host: str, port: int) -> bool:
    """True, если на занятом порту уже отвечает ComfyAvatar (а не чужая программа)."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/ping", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return isinstance(data, dict) and data.get("app") == "comfyavatar"
    except Exception:  # noqa: BLE001 — любая ошибка означает «это не наш сервер»
        return False


def main() -> None:
    import os

    import uvicorn

    global _server_url

    host = os.environ.get("COMFYAVATAR_HOST", HOST)
    try:
        port = int(os.environ.get("COMFYAVATAR_PORT", str(DEFAULT_PORT)))
    except ValueError:
        port = DEFAULT_PORT

    # Порт уже занят? Не падаем с непонятной ошибкой (Windows 10048),
    # а разбираемся, в чём дело, и подсказываем пользователю.
    if not _port_is_free(host, port):
        # Частый случай: start.bat запустили дважды и ComfyAvatar уже работает.
        if _looks_like_comfyavatar(host, port):
            url = f"http://{host}:{port}"
            logger.info("=" * 60)
            logger.info("ComfyAvatar уже запущен на %s", url)
            logger.info("Открываю его в браузере — запускать второй раз не нужно.")
            logger.info("=" * 60)
            webbrowser.open(url)
            return
        # Порт занят другой программой — берём ближайший свободный.
        alt_port = _find_free_port(host, port + 1)
        if alt_port is None:
            logger.error("=" * 60)
            logger.error("Порт %d занят, и свободный порт рядом не найден.", port)
            logger.error("Закройте программу, которая занимает порт %d, и запустите снова.", port)
            logger.error("=" * 60)
            raise SystemExit(1)
        logger.warning("Порт %d занят другой программой — использую свободный порт %d.", port, alt_port)
        port = alt_port

    _server_url = f"http://{host}:{port}"
    logger.info("=" * 60)
    logger.info("ComfyAvatar запускается на %s", _server_url)
    logger.info("Откройте этот адрес в браузере.")
    logger.info("=" * 60)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
