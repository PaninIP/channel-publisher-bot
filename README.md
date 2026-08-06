# Channel Publisher Bot

Telegram-бот и Mini App для создания, планирования и публикации контента в Telegram-каналах.

## Возможности

- подключение каналов, где бот имеет право публиковать сообщения;
- создание текстовых, фото- и видеопубликаций;
- предпросмотр перед отправкой;
- немедленная публикация;
- планирование по дате и времени в часовом поясе устройства;
- календарный контент-план в Telegram Mini App;
- подробный Mini App редактор запланированных публикаций;
- визуальное форматирование без ручного Markdown: жирный, курсив, подчёркивание,
  зачёркивание, спойлер, код, блок кода, обычная и сворачиваемая цитата, ссылка;
- сохранение форматирования через Telegram `MessageEntity`;
- живой предпросмотр сообщения;
- история версий и защита от одновременного редактирования;
- редактирование текста, канала и времени запланированной публикации;
- отмена запланированной публикации;
- защищённый API Mini App с проверкой Telegram `initData`;
- worker запланированных публикаций с атомарным захватом задач;
- защита от повторной отправки при одновременной работе нескольких процессов;
- восстановление прерванных отправок в статус `failed` без автоматического повтора.

## Стек

- Python 3.12;
- aiogram;
- FastAPI;
- SQLAlchemy Async;
- SQLite через aiosqlite;
- Docker Compose;
- Caddy;
- uv;
- Pytest;
- Ruff.

## Структура

```text
app/
├── bot/             Telegram handlers, keyboards и FSM
├── database/        модели, repositories и подключение к БД
├── services/        бизнес-логика и интеграции
├── workers/         worker запланированных публикаций
├── config.py        настройки приложения
├── main.py          запуск Telegram-бота и worker
└── web.py           FastAPI и API Mini App

webapp/               HTML, CSS и JavaScript Mini App
tests/                автоматические тесты
deploy/               deploy и rollback scripts
```

## Переменные окружения

Создайте `.env` на основе `.env.example`.

```dotenv
BOT_TOKEN=
DATABASE_URL=sqlite+aiosqlite:///./data/app.db

APP_TIMEZONE=Europe/Moscow
PUBLICATION_WORKER_INTERVAL_SECONDS=10
PUBLICATION_PUBLISHING_TIMEOUT_SECONDS=300

MINI_APP_URL=https://publisher.example.com/
CADDY_DOMAIN=publisher.example.com
MINI_APP_AUTH_MAX_AGE_SECONDS=3600
```

`PUBLICATION_PUBLISHING_TIMEOUT_SECONDS` определяет, через сколько секунд прерванная отправка считается зависшей. При следующем запуске worker переводит такую публикацию в `failed`. Автоматический повтор намеренно не выполняется, поскольку Telegram мог принять сообщение до обрыва соединения.

Часовой пояс публикации определяется Mini App по настройкам устройства.
`APP_TIMEZONE` используется только как серверный fallback для старых клиентов
и служебных сценариев. Ближайшее доступное время в календаре — начало
следующей минуты; текущая и прошедшие минуты недоступны.

## Локальный запуск

Требуется Python 3.12 и установленный `uv`.

```bash
uv sync --locked
cp .env.example .env
```

Заполните `.env`, затем выполните проверки:

```bash
uv run ruff format --check app tests
uv run ruff check app tests
uv run python -m compileall app tests
uv run python -m pytest
```

Запуск бота:

```bash
uv run python -m app.main
```

Запуск Mini App API:

```bash
uv run uvicorn app.web:app --host 0.0.0.0 --port 8080
```

Не запускайте локальный polling с production-токеном одновременно с VPS.

## Docker Compose

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f bot web caddy
```

Проверка API внутри контейнера:

```bash
docker compose exec -T web python -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5).read().decode())'
```

Ожидаемый ответ:

```json
{"status":"ok","database":"ok"}
```

## База данных и миграция

Текущий MVP использует SQLite-файл `data/app.db`.

При старте бот:

1. создаёт отсутствующие таблицы;
2. выполняет идемпотентную миграцию;
3. добавляет недостающие колонки `publishing_started_at`, `text_entities_json`,
   `version` и `updated_at`;
4. создаёт таблицу `publication_versions` для снимков предыдущих версий.

Миграция является добавочной. Существующие публикации и каналы не удаляются.

Перед production-деплоем обязательно создаётся копия БД. Скрипт `deploy/deploy.sh` делает это автоматически.

## CI

GitHub Actions запускает Ruff, компиляцию Python, Pytest, проверку JavaScript и shell-скриптов, а также сборку Docker-образа для push в `main` и pull request.

## Production deploy

На VPS проект ожидается в `/opt/channel-publisher-bot`.

```bash
cd /opt/channel-publisher-bot
chmod +x deploy/deploy.sh deploy/rollback.sh
./deploy/deploy.sh
```

Скрипт:

1. сохраняет текущий commit;
2. создаёт резервную копию `data/app.db`;
3. получает `origin/main`;
4. пересобирает контейнеры;
5. проверяет `/health` внутри `web`;
6. при неуспешной проверке автоматически возвращает предыдущий commit.

Резервные копии находятся в:

```text
/opt/channel-publisher-bot/backups/
```

## Ручной rollback

Вернуть предыдущий commit без восстановления БД:

```bash
cd /opt/channel-publisher-bot
./deploy/rollback.sh
```

Вернуть конкретный commit:

```bash
TARGET_COMMIT=<commit_sha> ./deploy/rollback.sh
```

Восстановление БД выполняется только вручную и только после проверки, поскольку возврат старой копии удалит публикации, созданные после backup:

```bash
RESTORE_DB=/opt/channel-publisher-bot/backups/app-YYYYmmdd-HHMMSS.db \
  ./deploy/rollback.sh
```

## Проверка после deploy

```bash
docker compose ps
docker compose logs --tail=200 bot web caddy
```

Ручной smoke test:

1. открыть главное меню бота;
2. открыть контент-план;
3. открыть карточку запланированной публикации;
4. изменить текст и время;
5. применить несколько видов форматирования и проверить предпросмотр;
6. сохранить, повторно открыть публикацию и убедиться, что форматирование сохранилось;
7. открыть историю версий и загрузить предыдущий вариант;
8. проверить фото или видео в редакторе;
9. создать тестовую публикацию на следующую минуту;
10. убедиться, что форматирование появилось в канале и пост отправлен один раз;
11. проверить статус и логи worker-а.

## Ограничения текущего MVP

- SQLite остаётся временным решением для небольшой нагрузки;
- медиа хранится через Telegram `file_id`;
- альбомы и несколько вложений не поддерживаются;
- Redis и отдельная очередь задач пока отсутствуют;
- автоматический повтор неоднозначно прерванных отправок намеренно отключён;
- замена, удаление, несколько вложений и drag-and-drop пока не включены;
- следующий продуктовый этап: Backblaze B2, `PublicationMedia` и медиатека;
- следующий инфраструктурный этап: PostgreSQL, Alembic и Redis.
