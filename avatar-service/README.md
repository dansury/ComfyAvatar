# 🎭 ComfyAvatar

Локальный сервис для генерации **говорящих AI-аватаров** с веб-интерфейсом.
Загружаете фото, записываете/загружаете голос, вводите текст — сервис клонирует
голос (Coqui XTTS v2), а затем анимирует фото через **SadTalker** в ComfyUI.

Всё работает **локально и офлайн** после первой настройки.

---

## ✨ Возможности

- 🔍 **Автопоиск ComfyUI** (включая portable-версию с `python_embeded`) и
  автозапуск на порту `8188`.
- 🖼️ Загрузка фото drag&drop с валидацией формата и размера.
- 🎙️ Запись голоса с микрофона (5–15 с) или загрузка `WAV/MP3`.
- 🗣️ **TTS с клонированием голоса**: Coqui XTTS v2 (или Kokoro TTS).
- 🎬 Анимация фото через **SadTalker** workflow в ComfyUI.
- 📊 Прогресс генерации в реальном времени через **WebSocket**.
- 🕓 **История** генераций (фото, аудио, видео, дата) в `storage/history.json`.
- ⚙️ Настройки в `localStorage` + `storage/settings.json` (путь к ComfyUI кешируется).
- 📜 Все ошибки видны **в логах и прямо в веб-интерфейсе** — их легко скопировать
  и отправить разработчику.
- 🌐 Русскоязычный адаптивный интерфейс (десктоп + планшет).
- ⬇️ Устойчивые к обрывам сети загрузки (докачка, а не повтор с нуля).

---

## 🚀 Быстрый старт

### Вариант 1. Одной командой (скрипты-обёртки)

- **Windows:** дважды кликните `start.bat`
- **Linux/macOS:** `bash start.sh`

Скрипты создают виртуальное окружение, ставят зависимости (с докачкой при
обрыве интернета) и запускают сервис. **Окно не закроется при ошибке** —
вы успеете прочитать и скопировать лог.

### Вариант 2. Вручную

```bash
cd avatar-service
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
python -m backend.main
```

Затем откройте в браузере: **http://127.0.0.1:8000**

> ⚠️ `torch` лучше ставить под вашу видеокарту по инструкции
> https://pytorch.org/get-started/locally/ (CPU-версия тоже работает, но
> медленнее).

---

## 🧩 Требования к ComfyUI

Для генерации видео нужен установленный **ComfyUI** с нодами **SadTalker**
(например, `ComfyUI-SadTalker`) и, для сборки видео, `ComfyUI-VideoHelperSuite`.

ComfyAvatar ищет ComfyUI по типичным путям:

- Windows: `C:\ComfyUI`, `C:\ComfyUI_windows-portable`,
  `%USERPROFILE%\ComfyUI`, `%APPDATA%\ComfyUI`, Desktop/Downloads и др.
- Portable: определяется по `python_embeded/python.exe` или `run_nvidia_gpu.bat`
  и запускается её **встроенным Python**.

Если автопоиск не сработал — укажите путь вручную в ⚙️ **Настройках**.

---

## 📁 Структура проекта

```
avatar-service/
├── backend/
│   ├── main.py             # FastAPI приложение, REST + WebSocket
│   ├── comfy_utils.py      # обнаружение/запуск ComfyUI + SadTalker workflow
│   ├── tts_engine.py       # Coqui XTTS v2 / Kokoro TTS
│   ├── history_manager.py  # история + настройки
│   ├── downloader.py       # докачка файлов при обрывах сети
│   └── logging_utils.py    # логи в консоль/файл/веб-интерфейс
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── storage/
│   ├── history.json
│   ├── settings.json
│   ├── uploads/            # загруженные фото/голос
│   └── outputs/            # сгенерированные аудио/видео
├── requirements.txt
├── start.bat / start.sh
└── README.md
```

---

## 🔌 Основные API-эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/status` | Статус ComfyUI и окружения |
| POST | `/api/comfyui/detect` | Поиск пути к ComfyUI |
| POST | `/api/comfyui/start` | Найти и запустить ComfyUI |
| GET/POST | `/api/settings` | Чтение/сохранение настроек |
| GET | `/api/logs` | Последние логи для UI |
| POST | `/api/upload/photo` | Загрузка фото |
| POST | `/api/upload/voice` | Загрузка голоса |
| POST | `/api/generate` | Запуск генерации (возвращает `job_id`) |
| WS | `/ws/{job_id}` | Прогресс генерации |
| GET | `/api/history` | История генераций |
| DELETE | `/api/history/{id}` | Удалить запись |

---

## 🛠️ Решение проблем

- **«ComfyUI не найден»** — укажите путь в ⚙️ Настройках или установите ComfyUI.
- **«Движок TTS недоступен»** — не установлены `torch`/`coqui-tts`; поставьте их
  из `requirements.txt`.
- **Видео не сгенерировалось** — убедитесь, что в ComfyUI установлены ноды
  SadTalker и VideoHelperSuite; подробности смотрите в блоке **Логи** на странице.
- Любую ошибку можно скопировать кнопкой **«Копировать»** в разделе «Логи».

---

## 🔒 Приватность

Все вычисления и файлы остаются на вашем компьютере. Интернет нужен только для
первичной загрузки моделей и зависимостей.
