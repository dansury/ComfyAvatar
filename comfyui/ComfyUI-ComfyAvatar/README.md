# ComfyUI-ComfyAvatar (нода-мост)

Маленькое расширение для ComfyUI, которое связывает озвучку (ComfyUI-XTTS) с
говорящими аватарами (SadTalker / AniPortrait) и убирает ручное копирование WAV.

## Зачем

`XTTS_INFER` (ComfyUI-XTTS) возвращает тип **`AUDIOPATH`** — путь к WAV со
случайным именем `{timestamp}_xtts.wav` в папке `output`. Этот тип **не
подключается** ни к `SadTalker` (нужен нативный `AUDIO`), ни к
`AniPortrait_Audio2Video` (нужен `Audio_Path`). Имя файла тоже не контролируется.

## Ноды

### `ComfyAvatarVoiceBridge`
Вход: `audio_path` (`AUDIOPATH`, от `XTTS_INFER`).
Опции: `filename` (по умолчанию `comfyavatar_voice.wav`), `save_to` (`input`/`output`).
Выходы: `audio` (`AUDIO`), `audio_path` (`Audio_Path`), `filename` (`STRING`).

Что делает: копирует WAV под фиксированным именем в `ComfyUI/input` («поэтапная
выгрузка с определённым именем») и отдаёт то же аудио сразу в трёх типах, чтобы
весь конвейер «текст → клон голоса → видео» собирался **одним графом**.
`OUTPUT_NODE = True` — исполняется даже без подключённых выходов (ради записи файла).

### `ComfyAvatarLoadVoice`
Вход: `audio` (выпадающий список wav/mp3/flac/m4a из `ComfyUI/input`).
Выходы: `audio` (`AUDIO`), `audio_path` (`Audio_Path`), `filename` (`STRING`).
Догрузка ранее сохранённого фиксированного файла, если этапы запускаются разными
графами.

## Установка

```
cp -r comfyui/ComfyUI-ComfyAvatar  <ComfyUI>/custom_nodes/
```

Затем перезапустите ComfyUI. Ноды появятся в категории **ComfyAvatar**.
Зависимости — `torch` и `torchaudio` (есть в любой установке ComfyUI; при
отсутствии `torchaudio` используется `soundfile`).
