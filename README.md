# ContractBot

ContractBot — десктопный сервис для автоматизации приёма игровых контрактов.
Проект разбит на модули внутри пакета `contractbot`:

- `config.py` — работа с JSON-конфигом и Discord-настройками;
- `adb.py` — вспомогательные функции для взаимодействия с ADB;
- `ocr.py` — обёртка над `pytesseract` и безопасное кадрирование изображений;
- `parsing.py` — парсинг OCR-результатов, таблиц и клипбордов;
- `database.py` — слой SQLite и бизнес-логика учёта;
- `buyback.py` — управление текущим процентом выкупа;
- `discord_bot.py` — интеграция с Discord (slash-команды, уведомления);
- `processor.py` — основной цикл обработки контрактов;
- `app.py` — точка сборки компонентов и запуск сервиса.

Точка входа для запуска: `python -m contractbot` (или `python Bot_Vikup.py` для обратной совместимости).

## Требования

- Python 3.9+
- [ADB](https://developer.android.com/studio/command-line/adb)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- Библиотеки Python из `requirements.txt`

### Ubuntu 22.04+

```bash
sudo apt update
sudo apt install adb tesseract-ocr python3-venv xclip xsel
```

`xclip` и `xsel` используются для чтения буфера обмена на Linux.

### Windows 10/11

1. Установите [Python 3.9+ для Windows](https://www.python.org/downloads/windows/) и при установке отметьте галочку **Add Python to PATH**.
2. Скачайте и установите [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (нужны для сборки некоторых зависимостей).
3. Установите [Android Platform Tools](https://developer.android.com/studio/releases/platform-tools) и добавьте папку с `adb.exe` в переменную `PATH`.
4. Скачайте и установите [Tesseract OCR для Windows](https://github.com/UB-Mannheim/tesseract/wiki). Включите нужные языковые пакеты (например, русский и английский) и убедитесь, что путь к `tesseract.exe` прописан в `PATH`.
5. (Опционально) Если проект будет работать с буфером обмена, установите [AutoHotkey](https://www.autohotkey.com/) и добавьте его в `PATH` — используется для симуляции клавиатуры.
6. Перезапустите PowerShell/Terminal, чтобы PATH обновился.

Дополнительные зависимости Python будут установлены автоматически скриптом из следующего раздела.

## Установка

Используйте подготовленный скрипт (работает одинаково на Windows, Linux и macOS):

```bash
python scripts/install.py
```

Он создаст виртуальное окружение `.venv`, установит зависимости и подскажет дальнейшие шаги.
Если предпочитаете Bash-скрипты на Unix-системах, остаётся доступным `./scripts/install.sh`.

### Пошаговая установка в Windows (PowerShell)

1. Откройте **PowerShell** (Win + X → Windows PowerShell) и перейдите в папку с проектом:
   ```powershell
   cd C:\\path\\to\\Bot_Vikup
   ```
2. (Однократно) Разрешите запуск локальных скриптов, если политика безопасности блокирует их:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
3. Запустите установочный скрипт из корня репозитория:
   ```powershell
   python scripts/install.py
   ```
4. Дождитесь окончания установки. Скрипт создаст `.venv`, установит `requirements.txt`, предложит активировать окружение и укажет путь к `config.json`.
5. Активируйте виртуальное окружение и запустите сервис:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m contractbot C:\\path\\to\\config.json
   ```
6. Для последующих запусков достаточно выполнить пункты 1, 5.

> **Примечание.** Если `tesseract.exe` установлен не в `PATH`, укажите полный путь в `config.json` в поле `tesseract_cmd`.

## Обновление из GitHub

Скрипт `scripts/update_from_github.py` обновляет рабочую копию до последней версии ветки `main` и одинаково работает во всех поддерживаемых ОС:

```bash
python scripts/update_from_github.py https://github.com/<org>/<repo>.git
```

Для Linux по-прежнему доступна версия на Bash — `scripts/update_from_github.sh`.

```bash
python scripts/update_from_github.py --branch develop https://github.com/<org>/<repo>.git
```

Если репозиторий уже клонирован, достаточно указать URL. Скрипт выполнит `git fetch` и `git pull` в текущей директории.

## Конфигурация

Создайте `config.json` по образцу из спецификации. Основные поля:

- `adb.serial` — серийный номер устройства (`"auto"` предложит выбрать при запуске);
- `db_path` — путь к файлу SQLite;
- `tesseract_cmd` — путь к бинарю Tesseract (необязательно, если доступен в `PATH`);
- `ocr_lang` — языки OCR (например, `"rus+eng"`);
- `poll_interval_sec`, `cooldown_after_contract_sec` — интервалы циклов;
- `ui` — последовательности действий ADB (тапы/свайпы/команды);
- `ocr_boxes` — координаты областей для OCR;
- `discord` — настройки токена, гильдии, ролей и канала уведомлений.

## Запуск

После подготовки окружения и конфигурации запустите сервис:

```bash
. .venv/bin/activate
python -m contractbot /путь/к/config.json
```

При отсутствии токена Discord сервис работает автономно и логирует обработанные контракты.

## Тестирование

Быстрая проверка синтаксиса:

```bash
. .venv/bin/activate
python -m compileall contractbot
```

## Обновления модулей

Каждый модуль отвечает за отдельный аспект сервиса, упрощая поддержку и тестирование. Дополнительные функции можно добавлять в соответствующие файлы, не затрагивая остальные части системы.
