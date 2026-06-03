#!/usr/bin/env bash
# ComfyAvatar — запуск на Linux/macOS.
# Скрипт не закрывает терминал при ошибке: ждёт нажатия Enter, чтобы вы увидели лог.

set -u
cd "$(dirname "$0")"

# UTF-8 для Python: чтобы русский текст в логах был читаемым в любом терминале.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

echo "============================================================"
echo "                     ComfyAvatar"
echo "============================================================"

hold() {
  echo
  echo "============================================================"
  echo " Нажмите Enter, чтобы закрыть. Скопируйте лог выше при ошибке."
  echo "============================================================"
  read -r _ || true
}

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[ОШИБКА] Python не найден. Установите Python 3.10+."
  hold; exit 1
fi
echo "[i] Python: $PY"; "$PY" --version

if [ ! -d ".venv" ]; then
  echo "[i] Создание виртуального окружения .venv ..."
  "$PY" -m venv .venv || { echo "[ОШИБКА] venv"; hold; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[i] Установка зависимостей (pip докачивает при обрывах сети)..."
python -m pip install --upgrade pip
if ! python -m pip install --retries 100 --timeout 120 -r requirements.txt; then
  echo "[ОШИБКА] Не удалось установить зависимости. Запустите снова — уже скачанное не качается заново."
  hold; exit 1
fi

echo
echo "[i] Запуск. Откройте в браузере: http://127.0.0.1:8000"
echo
if ! python -m backend.main; then
  echo "[ОШИБКА] Сервис завершился с ошибкой."
  hold; exit 1
fi

hold
