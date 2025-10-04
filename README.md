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

## Установка

Используйте подготовленный скрипт:

```bash
./scripts/install.sh
```

Он создаст виртуальное окружение `.venv`, установит зависимости и подсказки по дальнейшим шагам.

## Обновление из GitHub

Скрипт `scripts/update_from_github.sh` обновляет рабочую копию до последней версии ветки `main`:

```bash
./scripts/update_from_github.sh https://github.com/<org>/<repo>.git
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
