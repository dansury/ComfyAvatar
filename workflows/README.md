# 🧩 Workflow для ComfyUI

Здесь лежит готовый граф **SadTalker** в формате интерфейса ComfyUI — его можно
открыть прямо в самом ComfyUI и запустить вручную, без веб-сервиса ComfyAvatar.

## Файл

- **`sadtalker_avatar.json`** — граф анимации фото с озвучкой:

  ```
  LoadImage ─┐
             ├─▶ SadTalker ──▶ VHS_VideoCombine ──▶ видео (mp4)
  LoadAudio ─┘                      ▲
             └──────── audio ───────┘
  ```

Структура полностью совпадает с тем, что backend отправляет в ComfyUI
(`backend/comfy_utils.py → build_sadtalker_workflow`), описанным в `TZ.md`.

## Как открыть в ComfyUI

1. Запустите ComfyUI (portable: `run_nvidia_gpu.bat`, либо порт `8188`).
2. **Перетащите** файл `sadtalker_avatar.json` в окно ComfyUI
   (или меню **Workflow → Open** / иконка папки на панели).
3. В ноде **«Фото аватара»** (`LoadImage`) выберите/загрузите фото.
4. В ноде **«Голос»** (`LoadAudio`) выберите аудиофайл (`WAV`/`MP3`).
5. Нажмите **Queue Prompt** — результат сохранится через `VHS_VideoCombine`
   с префиксом имени `ComfyAvatar`.

## Требуемые кастомные ноды

- **SadTalker** — например, `ComfyUI-SadTalker`.
- **VideoHelperSuite** — `ComfyUI-VideoHelperSuite` (нода `VHS_VideoCombine`).

> Имена нод и набор параметров могут отличаться между версиями расширений.
> Если нода подсвечена красным — установите соответствующее расширение через
> **ComfyUI Manager** или поправьте параметры под свою версию.

## Параметры SadTalker по умолчанию

| Параметр | Значение |
|----------|----------|
| `preprocess` | `crop` |
| `still_mode` | `true` |
| `enhancer` | `None` |
| `batch_size` | `1` |
| `size` | `256` |
| `pose_style` | `0` |
