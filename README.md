# ChatOnRender

MVP мессенджер: backend для Render free + Python terminal клиент.

## Стек

- Backend: Flask + SQLAlchemy + SQLite
- Auth: логин/пароль + JWT Bearer
- Client: Python terminal app (requests)
- Transport: REST + polling (`/messages/inbox`)

## Локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m backend.app.main
```

В отдельном терминале:

```powershell
.venv\Scripts\Activate.ps1
python client\terminal_client.py
```

## Основные API endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/bot-info`
- `POST /auth/login/request-code`
- `POST /auth/login/code`
- `GET /auth/me`
- `POST /messages`
- `GET /messages/history/{other_username}`
- `GET /messages/inbox?since_id=0`
- `GET /integrations/events` (только с заголовком `X-Server-Key`)
- `GET /integrations/login-codes` (только с заголовком `X-Server-Key`)

## Telegram-бот уведомлений (домен + ключ)

Бот подключается к серверу по домену и ключу, читает события новых сообщений и отправляет их в Telegram.

1) На backend задайте ключ интеграции:

- env `INTEGRATION_API_KEY` (в Render уже добавлен в `render.yaml`)

2) На backend задайте username бота админа:

- env `TELEGRAM_BOT_USERNAME` (например `@my_admin_bot`)

3) Запустите notifier-бота (локально/VPS):

```powershell
.venv\Scripts\Activate.ps1
$env:BACKEND_DOMAIN="https://<your-service>.onrender.com"
$env:SERVER_KEY="<INTEGRATION_API_KEY>"
$env:TELEGRAM_BOT_TOKEN="<telegram_bot_token>"
$env:TELEGRAM_CHAT_ID="<chat_id>"
python client\telegram_notifier.py
```

3) Что делает бот:

- запрашивает `GET /integrations/events?after_id=<id>`
- запрашивает `GET /integrations/login-codes?after_id=<id>`
- передаёт `X-Server-Key: <SERVER_KEY>`
- при новых сообщениях отправляет уведомление в Telegram
- при запросе входа отправляет одноразовый код

## Новый вход в terminal client

Команда:

```text
login <username> <password>
```

Клиент:
- сначала показывает `bot username`, который настроил админ;
- затем запрашивает одноразовый код, который пришёл в Telegram;
- после ввода кода выполняет вход и сохраняет JWT токен.

## Deploy на Render free

### 1) Залить проект в GitHub

```powershell
git init
git add .
git commit -m "init chatonrender"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

### 2) Deploy на Render (через Blueprint)

1. В Render нажмите `New +` -> `Blueprint`.
2. Подключите GitHub-репозиторий.
3. Render подхватит `render.yaml` автоматически.
4. Нажмите `Apply`.

`render.yaml` уже содержит:
- `buildCommand`: `pip install -r requirements.txt`
- `startCommand`: `gunicorn backend.app.main:app --bind 0.0.0.0:$PORT`
- env-переменные: `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`

### 3) Проверка после деплоя

- Откройте `https://<your-service>.onrender.com/health`
- Должно вернуть: `{"status":"ok"}`

Важно: SQLite на free web service может быть непостоянной между рестартами инстанса. Для production лучше внешняя БД (например, Postgres).

## Обычный deploy (не Render)

На любом Linux/VPS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET="change-me"
gunicorn backend.app.main:app --bind 0.0.0.0:8000
```

Для Python-клиента задайте сервер командой:

```text
server https://<your-domain>
```
