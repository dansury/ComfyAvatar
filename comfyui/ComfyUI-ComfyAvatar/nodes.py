"""ComfyAvatar — нода-мост для озвучки.

Зачем нужна:
- ComfyUI-XTTS (нода XTTS_INFER) возвращает тип AUDIOPATH — путь к WAV со
  СЛУЧАЙНЫМ именем `{timestamp}_xtts.wav` в папке output. Имя контролировать
  нельзя, а тип AUDIOPATH несовместим ни с нативным AUDIO (нужен SadTalker и
  VHS_VideoCombine), ни с Audio_Path (нужен AniPortrait_Audio2Video).

Что делает ComfyAvatarVoiceBridge:
1. принимает AUDIOPATH от XTTS_INFER;
2. КОПИРУЕТ файл в ComfyUI/input под ФИКСИРОВАННЫМ именем (по умолчанию
   `comfyavatar_voice.wav`) — это и есть «поэтапная выгрузка с определённым
   именем», чтобы потом его можно было автоматически подхватить;
3. отдаёт сразу три представления одного аудио:
   - AUDIO       — для SadTalker / VHS_VideoCombine,
   - Audio_Path  — для AniPortrait_Audio2Video,
   - STRING      — имя файла.

Так весь конвейер «текст → клон голоса → говорящий аватар» собирается одним
графом, без ручного копирования WAV.

ComfyAvatarLoadVoice — догрузка ранее сохранённого фиксированного файла из
папки input (если озвучка и анимация запускаются разными графами).
"""

from __future__ import annotations

import os
import shutil
import time

try:  # доступно внутри ComfyUI
    import folder_paths
except Exception:  # вне ComfyUI (для автономной проверки импорта)
    folder_paths = None


AUDIO_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".ogg")


def _input_dir() -> str:
    if folder_paths is not None:
        return folder_paths.get_input_directory()
    return os.path.join(os.getcwd(), "input")


def _output_dir() -> str:
    if folder_paths is not None:
        return folder_paths.get_output_directory()
    return os.path.join(os.getcwd(), "output")


def _unwrap(value):
    """XTTS может отдать путь строкой или в кортеже/списке — нормализуем."""
    while isinstance(value, (list, tuple)) and value:
        value = value[0]
    return value


def _sanitize_filename(name: str) -> str:
    name = os.path.basename((name or "").strip()) or "comfyavatar_voice.wav"
    if not name.lower().endswith(AUDIO_EXTS):
        name += ".wav"
    return name


def load_audio_dict(path: str) -> dict:
    """Грузит аудио в формате ComfyUI AUDIO: {waveform:[B,C,T], sample_rate}."""

    import torch

    try:
        import torchaudio

        waveform, sample_rate = torchaudio.load(path)  # [C, T]
    except Exception:
        import soundfile as sf  # запасной путь

        data, sample_rate = sf.read(path, always_2d=True)  # [T, C]
        waveform = torch.from_numpy(data.T).float()  # [C, T]

    if waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)
    if waveform.dim() == 2:
        waveform = waveform.unsqueeze(0)  # -> [1, C, T]
    return {"waveform": waveform, "sample_rate": int(sample_rate)}


class ComfyAvatarVoiceBridge:
    """AUDIOPATH (XTTS) -> AUDIO + Audio_Path + фиксированный файл в input/."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_path": ("AUDIOPATH",),
            },
            "optional": {
                "filename": ("STRING", {"default": "comfyavatar_voice.wav"}),
                "save_to": (["input", "output"], {"default": "input"}),
            },
        }

    RETURN_TYPES = ("AUDIO", "Audio_Path", "STRING")
    RETURN_NAMES = ("audio", "audio_path", "filename")
    FUNCTION = "bridge"
    CATEGORY = "ComfyAvatar"
    # Исполняться даже если выходы не подключены (нужно ради записи файла).
    OUTPUT_NODE = True

    def bridge(self, audio_path, filename="comfyavatar_voice.wav", save_to="input"):
        src = _unwrap(audio_path)
        if not src or not os.path.isfile(src):
            raise FileNotFoundError(
                f"ComfyAvatarVoiceBridge: исходный аудиофайл не найден: {src!r}"
            )

        filename = _sanitize_filename(filename)
        base = _input_dir() if save_to == "input" else _output_dir()
        os.makedirs(base, exist_ok=True)
        dst = os.path.join(base, filename)

        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)

        return (load_audio_dict(dst), dst, filename)

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):  # всегда перезаписывать
        return time.time()


class ComfyAvatarLoadVoice:
    """Догрузка фиксированного WAV из input/ -> AUDIO + Audio_Path."""

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = _input_dir()
        files = []
        if os.path.isdir(input_dir):
            files = [
                f for f in os.listdir(input_dir)
                if f.lower().endswith(AUDIO_EXTS)
                and os.path.isfile(os.path.join(input_dir, f))
            ]
        return {"required": {"audio": (sorted(files) or ["comfyavatar_voice.wav"],)}}

    RETURN_TYPES = ("AUDIO", "Audio_Path", "STRING")
    RETURN_NAMES = ("audio", "audio_path", "filename")
    FUNCTION = "load"
    CATEGORY = "ComfyAvatar"

    def load(self, audio):
        path = os.path.join(_input_dir(), audio)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"ComfyAvatarLoadVoice: файл не найден в input/: {audio!r}"
            )
        return (load_audio_dict(path), path, audio)


NODE_CLASS_MAPPINGS = {
    "ComfyAvatarVoiceBridge": ComfyAvatarVoiceBridge,
    "ComfyAvatarLoadVoice": ComfyAvatarLoadVoice,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ComfyAvatarVoiceBridge": "ComfyAvatar Voice Bridge (XTTS→AUDIO/Audio_Path)",
    "ComfyAvatarLoadVoice": "ComfyAvatar Load Voice (input/*.wav)",
}
