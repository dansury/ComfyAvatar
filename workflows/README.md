# 🧩 Workflow для ComfyUI

Готовые графы в формате интерфейса ComfyUI — открываются перетаскиванием в окно.
**Все ноды сверены с исходниками** соответствующих расширений (таблица ниже),
непровалидированных нод нет.

## 🔌 Авто-передача озвучки (без ручного копирования WAV)

`XTTS_INFER` отдаёт тип `AUDIOPATH` (путь к WAV со случайным именем
`{timestamp}_xtts.wav`), который **не стыкуется** напрямую с `SadTalker` (нужен
`AUDIO`) и `AniPortrait` (нужен `Audio_Path`). Поэтому в проект добавлена
маленькая нода-мост **`ComfyAvatarVoiceBridge`** (папка
`comfyui/ComfyUI-ComfyAvatar`), которая:

- копирует WAV под фиксированным именем `input/comfyavatar_voice.wav`;
- отдаёт то же аудио сразу как `AUDIO` и как `Audio_Path`.

Благодаря ей каждый граф ниже — **единый конвейер «текст → клон голоса → видео»**,
ручная передача файла не нужна.

> Установка ноды-моста: скопируйте `comfyui/ComfyUI-ComfyAvatar` в
> `<ComfyUI>/custom_nodes/` и перезапустите ComfyUI (см. её README).

---

## Два режима

- **Режим A — всё в одном графе** (озвучка XTTS встроена). Удобно, но XTTS и
  аватар-модель грузятся вместе → выше пик VRAM.
- **Режим B — озвучка отдельным графом** (`_separate_voice`). Сначала гоните
  `xtts_voice_clone.json` (он пишет `input/comfyavatar_voice.wav`), затем граф
  аватара грузит этот файл нодой `ComfyAvatarLoadVoice`. XTTS в графе аватара не
  загружается → меньше VRAM.

## Файлы

| Файл | Режим | Конвейер |
|------|-------|----------|
| `xtts_voice_clone.json` | — | Озвучка (этап 1): `LoadAudioPath → XTTS_INFER → PreViewAudio` + запись `input/comfyavatar_voice.wav` |
| `sadtalker_avatar.json` | A | `LoadAudioPath → XTTS_INFER → Bridge → SadTalker → ShowVideo` |
| `aniportrait_avatar_full.json` | A | `… → Bridge → AniPortrait_Audio2Video → VHS_VideoCombine` (+ опц. reenactment) |
| `sadtalker_avatar_separate_voice.json` | B | `ComfyAvatarLoadVoice → SadTalker → ShowVideo` |
| `aniportrait_avatar_separate_voice.json` | B | `ComfyAvatarLoadVoice → AniPortrait_Audio2Video → VHS_VideoCombine` (+ опц. reenactment) |

> 🔒 **AniPortrait зафиксирован под последнюю версию** ноды
> (`frankchieng/ComfyUI_Aniportrait`, `main`): точный порядок виджетов и
> канонические пути моделей `./pretrained_model/...`, `frame_count` для
> reenactment заведён с `VHS_LoadVideo` (это `forceInput`). Ничего не «дрейфует».

- **SadTalker** сам сохраняет MP4 (отдаёт `video_path`) — `VHS_VideoCombine` ему не нужен.
- **AniPortrait**: движение головы задаёт pose-видео (`VHS_LoadVideo`); опциональная
  нода `AniPortrait_Pose_Gen_Video` (Bypass) переносит мимику с драйвер-видео.
- **Выбор моделей** — выпадающие списки прямо на нодах (XTTS `language`; SadTalker
  `faceModelResolution`/`preprocess`/`refInfo`; AniPortrait `vae`/`base_model`/
  `motion_module`/`image_encoder`/`denoising_unet`/`reference_unet`/`pose_guider`).

---

## ⬇️ Что нужно скачать (по нодам)

Подсказки продублированы в Note-нодах внутри каждого графа.

### ComfyUI-XTTS
- Модель **`coqui/XTTS-v2`** скачивается **автоматически** с HuggingFace при
  первом запуске (нужен интернет однократно).

### Comfyui-SadTalker
- Чекпойнты → `custom_nodes/Comfyui-SadTalker/SadTalker/checkpoints/`:
  `SadTalker_V0.0.2_256.safetensors`, `SadTalker_V0.0.2_512.safetensors`,
  `mapping_00109-model.pth.tar`, `mapping_00229-model.pth.tar`.
- GFPGAN-веса → `<ComfyUI>/gfpgan/weights/`:
  `GFPGANv1.4.pth`, `detection_Resnet50_Final.pth`, `parsing_parsenet.pth`,
  `alignment_WFLW_4HG.pth`. Источник: `github.com/OpenTalker/SadTalker`.

### ComfyUI_Aniportrait → `custom_nodes/ComfyUI_Aniportrait/pretrained_model/`
- `stable-diffusion-v1-5/` — `runwayml/stable-diffusion-v1-5`
- `sd-vae-ft-mse/` — `stabilityai/sd-vae-ft-mse`
- `image_encoder/` — `lambdalabs/sd-image-variations-diffusers`
- `wav2vec2-base-960h/` — `facebook/wav2vec2-base-960h`
- веса AniPortrait (`denoising_unet.pth`, `reference_unet.pth`, `motion_module.pth`,
  `pose_guider.pth`, `audio2mesh.pt`, `audio2pose.pt`, `film_net_fp16.pt`) —
  HuggingFace `ZJYang/AniPortrait`.

### Нода-мост
- `comfyui/ComfyUI-ComfyAvatar` → `<ComfyUI>/custom_nodes/`.

---

## 📋 Форматы входов/выходов

| Что | Формат | Лучше всего | Ограничения |
|-----|--------|-------------|-------------|
| Референс голоса (LoadAudioPath) | **WAV / MP3 / FLAC / M4A** | 6–20 с чистой моно-речи, 16–24 кГц, из `ComfyUI/input` | **OGG не поддерживается** — конвертируйте в WAV |
| Фото/портрет | PNG / JPG | Лицо анфас, квадрат, ≥512px, видны глаза и рот | Профиль/очки/чёлка/поворот ухудшают результат |
| Pose/драйвер видео | MP4 / MOV | Одно лицо, стабильный план, тот же ракурс | Длинное видео = долго и много VRAM |
| Выход | MP4 (H.264) | `crf` 17 ≈ высокое качество | Меньше `crf` = больше файл |

---

## ✅ Сверенные ноды и источники

| Нода (тип) | Расширение | Статус |
|-----------|-----------|--------|
| `LoadImage`, `Note` | ядро ComfyUI | ✅ |
| `LoadAudioPath`, `XTTS_INFER`, `PreViewAudio` | [ComfyUI-XTTS](https://github.com/AIFSH/ComfyUI-XTTS) | ✅ |
| `SadTalker`, `ShowVideo` | [Comfyui-SadTalker](https://github.com/haomole/Comfyui-SadTalker) | ✅ |
| `AniPortrait_Audio2Video`, `AniPortrait_Pose_Gen_Video` | [ComfyUI_Aniportrait](https://github.com/frankchieng/ComfyUI_Aniportrait) | ✅ |
| `VHS_LoadVideo`, `VHS_VideoCombine` | [VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | ✅ |
| `ComfyAvatarVoiceBridge`, `ComfyAvatarLoadVoice` | `comfyui/ComfyUI-ComfyAvatar` (этот репозиторий) | ✅ |

> ⚠️ У AniPortrait значения виджетов-моделей **дрейфуют между версиями**. Сами
> ноды и типы валидны; если значение по умолчанию не совпало с вашими файлами —
> просто выберите нужное в выпадающем списке. Для точного примера можно загрузить
> официальный `assets/audio2video_workflow.json` из их репозитория.
