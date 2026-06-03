@echo off
chcp 65001 >nul
title ComfyAvatar
setlocal enabledelayedexpansion

REM ==========================================================================
REM  ComfyAvatar - запуск на Windows.
REM  Это окно НЕ закроется при ошибке: вы успеете увидеть и скопировать вывод.
REM ==========================================================================

cd /d "%~dp0"

echo ============================================================
echo                     ComfyAvatar
echo ============================================================
echo.

REM --- 1. Поиск Python -------------------------------------------------------
set "PY="
where python >nul 2>nul && set "PY=python"
if "%PY%"=="" where py >nul 2>nul && set "PY=py"

REM Если рядом есть portable ComfyUI с python_embeded - используем его.
if exist "..\ComfyUI_windows-portable\python_embeded\python.exe" (
    set "PY=..\ComfyUI_windows-portable\python_embeded\python.exe"
    echo [i] Используется встроенный Python из ComfyUI portable.
)

if "%PY%"=="" (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
    echo          и поставьте галочку "Add Python to PATH".
    goto :hold
)

echo [i] Python: %PY%
"%PY%" --version
echo.

REM --- 2. Виртуальное окружение ----------------------------------------------
if not exist ".venv" (
    echo [i] Создание виртуального окружения .venv ...
    "%PY%" -m venv .venv || goto :fail
)
call ".venv\Scripts\activate.bat"

REM --- 3. Установка зависимостей (с докачкой при обрыве) ----------------------
echo [i] Установка зависимостей (pip докачивает при обрывах сети)...
python -m pip install --upgrade pip
python -m pip install --retries 100 --timeout 120 -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    echo          Проверьте интернет и сообщение выше. Запустите start.bat снова —
    echo          уже скачанные пакеты не будут качаться заново.
    goto :hold
)

echo.
echo [i] Запуск ComfyAvatar. Откройте в браузере: http://127.0.0.1:8000
echo.

REM --- 4. Запуск -------------------------------------------------------------
python -m backend.main
if errorlevel 1 goto :fail

goto :hold

:fail
echo.
echo [ОШИБКА] Сервис завершился с ошибкой. Скопируйте текст выше и пришлите разработчику.

:hold
echo.
echo ============================================================
echo  Окно НЕ закрыто специально. Скопируйте лог при необходимости.
echo  Нажмите любую клавишу, чтобы выйти.
echo ============================================================
pause >nul
endlocal
