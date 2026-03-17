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

Если сервер на `*.onrender.com`, terminal client:
- покажет `Render просыпается...` при первом подключении;
- дождётся `health=ok`;
- затем будет слать keep-alive запросы `/health` в фоне.

## Fork + Deploy (Render + custom domain)

### 1) Fork репозитория

1. Нажмите `Fork` на GitHub.
2. Склонируйте ваш fork:

```powershell
git clone https://github.com/<your-user>/chatonrender.git
cd chatonrender
```

3. Работайте в своей ветке и пушьте в свой fork.

### 2) Развернуть сервер на Render

1. Render -> `New +` -> `Blueprint`.
2. Подключите ваш fork.
3. Render автоматически применит `render.yaml`.
4. Проверьте env в Render:
   - `JWT_SECRET`
   - `ACCESS_TOKEN_EXPIRE_MINUTES`
   - `INTEGRATION_API_KEY`
   - `TELEGRAM_BOT_USERNAME`
   - `LOGIN_CODE_TTL_MINUTES`

Проверка:

- `https://<service>.onrender.com/health` -> `{"status":"ok"}`

### 3) Подключить custom domain

В Render (service -> `Settings` -> `Custom Domains`):

1. Добавьте домен, например `api.example.com`.
2. Настройте DNS запись у регистратора (обычно `CNAME` на Render target).
3. Дождитесь выпуска SSL сертификата в Render.
4. Проверьте: `https://api.example.com/health`

### 4) Настроить terminal client под ваш домен

Запустите клиент и укажите ваш домен backend:

```text
server https://api.example.com
```

Дальше стандартно:

```text
register <username> <password>
login <username> <password>
```

Важно: на free тарифе Render может засыпать. Клиент уже умеет:
- показывать статус пробуждения Render;
- ждать готовности `/health`;
- отправлять keep-alive ping в фоне.

Важно: SQLite на free web service может быть непостоянной между рестартами. Для production лучше Postgres.
