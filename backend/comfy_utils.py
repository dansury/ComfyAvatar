"""Автоматическое обнаружение, запуск и общение с ComfyUI.

Возможности:
- find_comfyui(): сканирует типичные пути (включая portable) на всех ОС.
- start_comfyui_if_needed(): запускает ComfyUI на порту 8188, используя
  встроенный python_embeded для portable-версии, если он есть.
- run_sadtalker_workflow(): отправляет workflow и ждёт результат, транслируя
  прогресс через WebSocket ComfyUI.

Модуль рассчитан на отсутствие ComfyUI/зависимостей: все ошибки логируются и
возвращаются вызывающей стороне в виде понятных сообщений, ничего не падает.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

from .history_manager import load_settings, save_settings
from .logging_utils import setup_logging

logger = setup_logging()

DEFAULT_PORT = 8188
DEFAULT_HOST = "127.0.0.1"

# Глобальный handle процесса ComfyUI, если мы его сами запустили.
_comfy_process: Optional[subprocess.Popen] = None


# --------------------------------------------------------------------------- #
# Обнаружение
# --------------------------------------------------------------------------- #
def _candidate_paths() -> List[Path]:
    """Список путей-кандидатов для поиска ComfyUI в зависимости от ОС."""

    paths: List[Path] = []
    home = Path.home()

    if os.name == "nt":  # Windows
        userprofile = Path(os.environ.get("USERPROFILE", str(home)))
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        localappdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        drives = ["C:\\", "D:\\", "E:\\"]
        names = ["ComfyUI", "ComfyUI_windows-portable", "ComfyUI_portable"]
        for drive in drives:
            for name in names:
                paths.append(Path(drive) / name)
        for base in (userprofile, appdata, localappdata, home):
            for name in names:
                paths.append(base / name)
        paths.append(userprofile / "Desktop" / "ComfyUI_windows-portable")
        paths.append(userprofile / "Downloads" / "ComfyUI_windows-portable")
    else:  # Linux / macOS
        for name in ("ComfyUI", "comfyui", "ComfyUI_portable"):
            paths.append(home / name)
            paths.append(home / "Documents" / name)
            paths.append(Path("/opt") / name)
            paths.append(Path.cwd() / name)

    # Уникализируем, сохраняя порядок.
    seen = set()
    unique: List[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _looks_like_comfyui(path: Path) -> bool:
    """Проверяет, что директория действительно похожа на установку ComfyUI."""

    if not path.exists() or not path.is_dir():
        return False
    markers = ["main.py", "ComfyUI/main.py", "run_nvidia_gpu.bat", "run_cpu.bat"]
    for marker in markers:
        if (path / marker).exists():
            return True
    # Иногда внутри лежит подпапка ComfyUI (portable).
    if (path / "ComfyUI").is_dir() and (path / "ComfyUI" / "main.py").exists():
        return True
    return False


def _resolve_main_dir(path: Path) -> Path:
    """Возвращает директорию, содержащую main.py."""

    if (path / "main.py").exists():
        return path
    if (path / "ComfyUI" / "main.py").exists():
        return path / "ComfyUI"
    return path


def _find_embedded_python(path: Path) -> Optional[Path]:
    """Ищет встроенный python_embeded в portable-версии."""

    candidates = [
        path / "python_embeded" / "python.exe",
        path / "python_embeded" / "python",
        path.parent / "python_embeded" / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_comfyui(use_cache: bool = True) -> Optional[Dict[str, Optional[str]]]:
    """Ищет ComfyUI на диске.

    Возвращает dict с ключами path, main_dir, python, portable — либо None.
    Найденный путь кешируется в settings.json.
    """

    settings = load_settings()
    if use_cache and settings.get("comfyui_path"):
        cached = Path(settings["comfyui_path"])
        if _looks_like_comfyui(cached):
            logger.info("ComfyUI взят из кеша настроек: %s", cached)
            return _build_info(cached)
        logger.warning("Кешированный путь к ComfyUI больше не валиден: %s", cached)

    logger.info("Сканирование путей для поиска ComfyUI...")
    for candidate in _candidate_paths():
        if _looks_like_comfyui(candidate):
            logger.info("Найден ComfyUI: %s", candidate)
            info = _build_info(candidate)
            save_settings({"comfyui_path": str(candidate)})
            return info

    logger.warning("ComfyUI не найден ни по одному из стандартных путей.")
    return None


def _build_info(path: Path) -> Dict[str, Optional[str]]:
    embedded = _find_embedded_python(path)
    return {
        "path": str(path),
        "main_dir": str(_resolve_main_dir(path)),
        "python": str(embedded) if embedded else sys.executable,
        "portable": bool(embedded),
    }


# --------------------------------------------------------------------------- #
# Запуск / статус
# --------------------------------------------------------------------------- #
def _comfy_url() -> str:
    return load_settings().get("comfyui_url") or f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def is_comfyui_running(url: Optional[str] = None, timeout: float = 2.0) -> bool:
    """Проверяет, отвечает ли ComfyUI (через /system_stats)."""

    url = url or _comfy_url()
    try:
        resp = requests.get(f"{url}/system_stats", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def start_comfyui_if_needed(wait_seconds: int = 60) -> Dict[str, object]:
    """Запускает ComfyUI, если он ещё не отвечает.

    Возвращает dict: {running: bool, started: bool, message: str, info: ...}
    """

    global _comfy_process

    url = _comfy_url()
    if is_comfyui_running(url):
        logger.info("ComfyUI уже запущен: %s", url)
        return {"running": True, "started": False, "message": "ComfyUI уже запущен", "url": url}

    info = find_comfyui()
    if not info:
        msg = (
            "ComfyUI не найден. Укажите путь вручную в настройках "
            "или установите ComfyUI."
        )
        logger.error(msg)
        return {"running": False, "started": False, "message": msg, "url": url}

    main_dir = Path(info["main_dir"])
    python_exe = info["python"]
    main_py = main_dir / "main.py"
    if not main_py.exists():
        msg = f"Не найден main.py в {main_dir}"
        logger.error(msg)
        return {"running": False, "started": False, "message": msg, "url": url}

    cmd = [str(python_exe), str(main_py), "--port", str(DEFAULT_PORT)]
    logger.info("Запуск ComfyUI: %s (cwd=%s)", " ".join(cmd), main_dir)
    try:
        _comfy_process = subprocess.Popen(
            cmd,
            cwd=str(main_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        msg = f"Не удалось запустить ComfyUI: {exc}"
        logger.exception(msg)
        return {"running": False, "started": False, "message": msg, "url": url}

    # Ждём, пока ComfyUI поднимется.
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _comfy_process.poll() is not None:
            # Процесс завершился раньше времени — соберём вывод.
            output = ""
            if _comfy_process.stdout:
                output = _comfy_process.stdout.read()
            msg = f"ComfyUI завершился при запуске. Вывод:\n{output[-2000:]}"
            logger.error(msg)
            return {"running": False, "started": False, "message": msg, "url": url}
        if is_comfyui_running(url, timeout=1.5):
            logger.info("ComfyUI успешно запущен на %s", url)
            return {"running": True, "started": True, "message": "ComfyUI запущен", "url": url}
        time.sleep(1.5)

    msg = f"ComfyUI не ответил за {wait_seconds} секунд. Проверьте лог ComfyUI."
    logger.error(msg)
    return {"running": False, "started": True, "message": msg, "url": url}


# --------------------------------------------------------------------------- #
# Workflow
# --------------------------------------------------------------------------- #
def upload_image(file_path: Path, url: Optional[str] = None) -> str:
    """Загружает изображение/файл в ComfyUI (/upload/image) и возвращает имя."""

    url = url or _comfy_url()
    with file_path.open("rb") as fh:
        files = {"image": (file_path.name, fh, "application/octet-stream")}
        resp = requests.post(f"{url}/upload/image", files=files, data={"overwrite": "true"}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    name = data.get("name", file_path.name)
    logger.info("Файл загружен в ComfyUI: %s", name)
    return name


def build_sadtalker_workflow(image_name: str, audio_name: str) -> Dict:
    """Строит граф SadTalker для ComfyUI API (/prompt).

    Структура совместима с нодами SadTalker для ComfyUI:
    LoadImage -> SadTalker <- LoadAudio (через VHS) -> VHS_VideoCombine (SaveVideo).
    При другой версии нод схему можно скорректировать в settings.json в будущем.
    """

    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "2": {
            "class_type": "LoadAudio",
            "inputs": {"audio": audio_name},
        },
        "3": {
            "class_type": "SadTalker",
            "inputs": {
                "source_image": ["1", 0],
                "driven_audio": ["2", 0],
                "preprocess": "crop",
                "still_mode": True,
                "enhancer": "None",
                "batch_size": 1,
                "size": 256,
                "pose_style": 0,
            },
        },
        "4": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["3", 0],
                "audio": ["2", 0],
                "frame_rate": 25,
                "format": "video/h264-mp4",
                "filename_prefix": "ComfyAvatar",
                "save_output": True,
            },
        },
    }


def run_sadtalker_workflow(
    image_path: Path,
    audio_path: Path,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    url: Optional[str] = None,
    timeout: int = 1800,
) -> Dict[str, object]:
    """Отправляет SadTalker workflow в ComfyUI и ждёт готовое видео.

    progress_cb(message, fraction) вызывается по мере прогресса.
    Возвращает {success: bool, video: <abs path or None>, message: str}.
    """

    url = url or _comfy_url()

    def _report(msg: str, frac: float) -> None:
        logger.info("[workflow] %s (%.0f%%)", msg, frac * 100)
        if progress_cb:
            try:
                progress_cb(msg, frac)
            except Exception:  # noqa: BLE001
                logger.exception("Ошибка в progress callback")

    if not is_comfyui_running(url):
        return {"success": False, "video": None, "message": "ComfyUI не отвечает"}

    try:
        _report("Загрузка фото в ComfyUI", 0.05)
        image_name = upload_image(image_path, url)
        _report("Загрузка аудио в ComfyUI", 0.1)
        audio_name = upload_image(audio_path, url)

        workflow = build_sadtalker_workflow(image_name, audio_name)
        client_id = uuid.uuid4().hex
        _report("Отправка workflow в ComfyUI", 0.15)
        resp = requests.post(
            f"{url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=60,
        )
        if resp.status_code != 200:
            return {
                "success": False,
                "video": None,
                "message": f"ComfyUI отклонил workflow ({resp.status_code}): {resp.text[:500]}",
            }
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            return {"success": False, "video": None, "message": "ComfyUI не вернул prompt_id"}

        _report("Генерация видео (SadTalker)...", 0.2)
        video = _poll_until_done(url, prompt_id, _report, timeout)
        if video is None:
            return {"success": False, "video": None, "message": "Видео не получено от ComfyUI"}

        _report("Готово", 1.0)
        return {"success": True, "video": str(video), "message": "Видео успешно сгенерировано"}

    except requests.RequestException as exc:
        msg = f"Ошибка связи с ComfyUI: {exc}"
        logger.exception(msg)
        return {"success": False, "video": None, "message": msg}
    except Exception as exc:  # noqa: BLE001
        msg = f"Ошибка при выполнении workflow: {exc}"
        logger.exception(msg)
        return {"success": False, "video": None, "message": msg}


def _poll_until_done(
    url: str,
    prompt_id: str,
    report: Callable[[str, float], None],
    timeout: int,
) -> Optional[Path]:
    """Опрашивает /history, пока workflow не завершится, и скачивает видео."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/history/{prompt_id}", timeout=15)
            if resp.status_code == 200:
                hist = resp.json()
                entry = hist.get(prompt_id)
                if entry:
                    outputs = entry.get("outputs", {})
                    video = _extract_video_from_outputs(url, outputs)
                    if video:
                        return video
                    # Завершено, но видео нет — ошибка нод.
                    status = entry.get("status", {})
                    if status.get("completed"):
                        report("Workflow завершился без видео-выхода", 0.9)
                        return None
        except requests.RequestException as exc:
            logger.warning("Ошибка опроса history: %s", exc)
        # Грубая оценка прогресса по времени ожидания.
        report("Генерация видео (SadTalker)...", min(0.85, 0.2 + (time.time() % 30) / 60))
        time.sleep(2.0)
    return None


def _extract_video_from_outputs(url: str, outputs: Dict) -> Optional[Path]:
    """Находит видеофайл в выходах ComfyUI и скачивает его в storage/outputs."""

    out_dir = Path(__file__).resolve().parent.parent / "storage" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    for node_output in outputs.values():
        # VHS_VideoCombine кладёт результат в ключи gifs/videos.
        for key in ("gifs", "videos", "images"):
            for item in node_output.get(key, []) or []:
                filename = item.get("filename")
                if not filename:
                    continue
                if not filename.lower().endswith((".mp4", ".webm", ".mov", ".gif")):
                    continue
                subfolder = item.get("subfolder", "")
                ftype = item.get("type", "output")
                params = {"filename": filename, "subfolder": subfolder, "type": ftype}
                try:
                    resp = requests.get(f"{url}/view", params=params, timeout=120)
                    resp.raise_for_status()
                except requests.RequestException as exc:
                    logger.error("Не удалось скачать видео из ComfyUI: %s", exc)
                    continue
                local = out_dir / f"{uuid.uuid4().hex}_{filename}"
                local.write_bytes(resp.content)
                logger.info("Видео сохранено: %s", local)
                return local
    return None


def stop_comfyui() -> None:
    """Останавливает запущенный нами процесс ComfyUI (если есть)."""

    global _comfy_process
    if _comfy_process and _comfy_process.poll() is None:
        logger.info("Остановка ComfyUI...")
        _comfy_process.terminate()
        try:
            _comfy_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _comfy_process.kill()
    _comfy_process = None
