# 🧩 Workflow для ComfyUI

Здесь лежат готовые графы в формате интерфейса ComfyUI — их можно открыть прямо
в самом ComfyUI и запустить вручную, без веб-сервиса ComfyAvatar.

## Файлы

### 1. `talking_avatar_full.json` — полный конвейер (рекомендуется)

Текст → озвучка с заданной манерой речи → анимация фото → сведение в MP4 →
выбор качества / опциональный апскейл.

```
Текст ───────────────┐
Манера речи (.ogg) ──┤▶ BarkTTS ─┬─▶ SadTalker ─▶ [Upscale*] ─▶ VHS_VideoCombine ─▶ MP4
Фото ─────────────────────────────┘   audio ───────────────────────▲
```

`* Upscale` — опциональное повышение качества (по умолчанию **выключено**, Bypass).

| № | Нода | Назначение |
|---|------|-----------|
| 1 | `LoadImage` | Фото аватара |
| 2 | `Text Multiline` | Текст для озвучки |
| 3 | `LoadAudio` | Референс манеры речи (`.ogg`/`.wav`) |
| 4 | `BarkTTS` | Синтез речи (Bark/TTS) с клонированием голоса по референсу |
| 5 | `SadTalker` | Анимация лица под аудио |
| 6 | `UpscaleModelLoader` | Загрузка модели апскейла (RealESRGAN/UltraSharp) |
| 7 | `ImageUpscaleWithModel` | Повышение качества кадров (опционально) |
| 8 | `VHS_VideoCombine` | Сведение кадров + аудио в `MP4` |

### 2. `sadtalker_avatar.json` — базовый граф

Упрощённый вариант без TTS: готовое аудио подаётся напрямую
(`LoadImage → SadTalker ← LoadAudio → VHS_VideoCombine`). Совпадает с тем, что
backend отправляет в ComfyUI (`backend/comfy_utils.py → build_sadtalker_workflow`).

## Как открыть в ComfyUI

1. Запустите ComfyUI (portable: `run_nvidia_gpu.bat`, либо порт `8188`).
2. **Перетащите** нужный `.json` в окно ComfyUI
   (или меню **Workflow → Open** / иконка папки на панели).
3. Заполните входы:
   - **Фото аватара** (`LoadImage`);
   - **Текст для озвучки** (`Text Multiline`);
   - **Манера речи** (`LoadAudio`) — короткий образец голоса `.ogg`/`.wav`.
4. Нажмите **Queue Prompt** — итоговое видео сохранится через `VHS_VideoCombine`
   с префиксом имени `ComfyAvatar`.

## Управление качеством

- **SadTalker** (нода 5):
  - `size` — `256` (быстро) или `512` (качественнее, по умолчанию `512`);
  - `enhancer` — `None` / `gfpgan` / `RestoreFormer` (по умолчанию `gfpgan`).
- **Опциональный апскейл** (ноды 6–7): по умолчанию нода `ImageUpscaleWithModel`
  стоит в режиме **Bypass** (выключена). Чтобы включить повышение качества,
  выделите её и снимите Bypass (ПКМ → *Bypass*, или `Ctrl+B`), и убедитесь, что
  файл модели из ноды 6 (например `RealESRGAN_x4plus.pth`) лежит в
  `ComfyUI/models/upscale_models/`.
- **VHS_VideoCombine** (нода 8): `crf` — качество сжатия `MP4`
  (меньше = качественнее, по умолчанию `17`); `format` = `video/h264-mp4`;
  `frame_rate` = `25`.

## Требуемые кастомные ноды

- **SadTalker** — например, `ComfyUI-SadTalker` (нода `SadTalker`).
- **VideoHelperSuite** — `ComfyUI-VideoHelperSuite` (нода `VHS_VideoCombine`).
- **TTS** — нода типа `BarkTTS` (например, `ComfyUI-Bark`/`suno-bark`).
  Bark озвучивает по пресету голоса; для клонирования манеры из произвольного
  `.ogg` подойдёт XTTS-нода (например, `ComfyUI-XTTS`) — в этом случае замените
  ноду 4 на неё, сохранив связи `text` и `reference_audio`.
- **Text Multiline** — мультистрочный текстовый ввод (например, из
  `WAS Node Suite`). Если такой ноды нет, можно вводить текст прямо в виджете
  ноды TTS.
- **Upscale** — `UpscaleModelLoader` + `ImageUpscaleWithModel` входят в ядро
  ComfyUI; нужна лишь сама модель в `models/upscale_models/`.

> Имена нод и набор параметров могут отличаться между версиями расширений.
> Если нода подсвечена красным — установите соответствующее расширение через
> **ComfyUI Manager** или поправьте параметры/связи под свою версию.
