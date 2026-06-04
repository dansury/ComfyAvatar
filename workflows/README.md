# 🧩 Workflow для ComfyUI

Готовые графы в формате интерфейса ComfyUI — открываются перетаскиванием в окно
ComfyUI. Имена нод и сигнатуры **сверены с исходниками** реальных расширений
(см. «Источники» внизу).

## ⚠️ Главное про совместимость

Эти расширения создавались независимо и **по-разному типизируют аудио**, поэтому
единый граф «текст → озвучка → говорящий аватар» из них **не собирается напрямую**:

| Этап | Расширение | Тип аудио |
|------|-----------|-----------|
| Озвучка | `ComfyUI-XTTS` | отдаёт `AUDIOPATH` (путь к WAV) |
| SadTalker | `Comfyui-SadTalker` | ждёт нативный `AUDIO` |
| AniPortrait | `ComfyUI_Aniportrait` | ждёт путь `Audio_Path` |

Поэтому конвейер собирается **в два шага** (через WAV-файл на диске), а не одним
графом — см. ниже.

---

## Файлы

### 1. `xtts_voice_clone.json` — озвучка с клоном голоса (этап 1)

`LoadAudioPath → XTTS_INFER → PreViewAudio`. Берёт референс манеры речи и текст,
синтезирует WAV в `ComfyUI/output`. Выпадающий список `language` (17 языков).

### 2. `sadtalker_avatar.json` — говорящий аватар (этап 2, SadTalker)

`LoadImage + LoadAudio → SadTalker → ShowVideo`.
**SadTalker сам сохраняет MP4** и возвращает `video_path` — `VHS_VideoCombine`
не нужен. Аудио — нативный `AUDIO` (нода `LoadAudio` ядра ComfyUI).
Дропдауны на ноде: `faceModelResolution` (256/512), `preprocess`, `refInfo`,
переключатель `gfpganAsFaceEnhancer`.

### 3. `aniportrait_avatar_full.json` — говорящий аватар (этап 2, AniPortrait)

Зеркало официального `assets/audio2video_workflow.json`:
`LoadImage + VHS_LoadVideo(pose) + AniPortrait_Audio_Path → AniPortrait_Audio2Video
→ VHS_VHSAudioToAudio → VHS_VideoCombine`.

- **Pose-driven** — встроен: движение головы задаёт pose-видео (`VHS_LoadVideo`).
- **Face reenactment** *(опц., Bypass)* — нода `AniPortrait_Pose_Gen_Video`
  переносит мимику с кадров драйвер-видео на портрет.
- **Выбор моделей** — выпадающие списки прямо на ноде `Audio2Video`
  (`vae`, `base_model`, `motion_module`, `image_encoder`,
  `denoising_unet`, `reference_unet`, `pose_guider` из папки `pretrained_model`).

> ⚠️ Виджеты AniPortrait заметно «дрейфуют» между версиями. Для гарантии
> загрузите официальный пример из репозитория (см. источники) и подставьте свои
> входы.

---

## Как собрать полный конвейер (2 шага)

1. **Озвучка:** откройте `xtts_voice_clone.json`, задайте референс (`.ogg`/`.wav`)
   и текст → Queue Prompt. Получите WAV в `ComfyUI/output`. При желании скопируйте
   его в `ComfyUI/input`.
2. **Аватар:**
   - **SadTalker:** в `sadtalker_avatar.json` выберите этот WAV в `LoadAudio`.
   - **или AniPortrait:** в `aniportrait_avatar_full.json` укажите путь к WAV в
     виджете `audio_file_path` ноды `AniPortrait_Audio_Path`.

---

## Рекомендации по форматам

| Что | Формат | Лучше всего | Ограничения |
|-----|--------|-------------|-------------|
| Фото/портрет | PNG / JPG | Лицо анфас, квадрат, ≥512px, видны глаза и рот | Профиль, очки, чёлка, поворот ухудшают результат |
| Референс голоса (XTTS) | WAV / OGG / MP3 | 6–20 с чистой речи одного диктора, моно, 16–24 кГц | Шум/музыка/несколько голосов ломают клон |
| Pose/драйвер видео (AniPortrait) | MP4 / MOV | Одно лицо, стабильный план, тот же ракурс | Длинное видео = долго и много VRAM |
| Выход | MP4 (H.264) | `crf` 17 ≈ высокое качество | Меньше `crf` = больше файл |

Эти подсказки продублированы в **Note-нодах** внутри каждого графа.

---

## Управление качеством

- **SadTalker:** `faceModelResolution` 256/512, `gfpganAsFaceEnhancer` (чище лицо).
- **AniPortrait:** `width`/`height` (512 база; больше = чётче и медленнее),
  `steps`, `cfg`.
- **VHS_VideoCombine:** `crf` (меньше = чётче), `format` = `video/h264-mp4`.

---

## Требуемые расширения и точные имена нод

| Нода (тип) | Расширение |
|-----------|-----------|
| `SadTalker`, `ShowVideo`, `LoadAudio` | `Comfyui-SadTalker` (+ ядро ComfyUI) |
| `XTTS_INFER`, `LoadAudioPath`, `PreViewAudio` | `ComfyUI-XTTS` |
| `AniPortrait_Audio2Video`, `AniPortrait_Audio_Path`, `AniPortrait_Pose_Gen_Video` | `ComfyUI_Aniportrait` |
| `VHS_LoadVideo`, `VHS_VHSAudioToAudio`, `VHS_VideoCombine` | `ComfyUI-VideoHelperSuite` |
| `Note` | ядро ComfyUI |

Если нода красная — установите расширение через **ComfyUI Manager**.

---

## Источники (сверка нод)

- SadTalker: https://github.com/haomole/Comfyui-SadTalker
- XTTS: https://github.com/AIFSH/ComfyUI-XTTS
- AniPortrait: https://github.com/frankchieng/ComfyUI_Aniportrait
  (примеры: `assets/audio2video_workflow.json`, `assets/face_reenacment_workflow.json`)
- VideoHelperSuite: https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
