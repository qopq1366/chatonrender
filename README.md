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
- `GET /auth/me`
- `POST /tg/add/request`
- `GET /tg/manage`
- `POST /tg/manage`
- `POST /messages`
- `GET /messages/history/{other_username}`
- `GET /messages/inbox?since_id=0`

## Telegram привязка аккаунта (`/add-tg` и `/manage-tg`)

Целевой UX:

1. Пользователь в terminal client регистрируется/логинится.
2. В клиенте вводит команду `/add-tg`.
3. Клиент показывает `username` Telegram-бота (который задал админ).
4. Клиент показывает код привязки (5 минут).
5. Пользователь отправляет боту команду `/link <code>`.
6. Сервер связывает `telegram_user_id` и `user_id` мессенджера в БД.
7. Командой `/manage-tg` можно смотреть/включать/выключать Telegram-уведомления.

Ограничение кода:

- Код привязки действует **5 минут**, потом становится недействительным.

После привязки:

- В клиенте доступна команда `/manage-tg` (управление Telegram-привязкой).
- В Telegram приходят уведомления о новых сообщениях с сервера.

### Как это работает на сервере

- Telegram-бот запускается внутри backend процесса (один серверный процесс).
- Бот обрабатывает `/start`, `/link <code>`, `/manage [on|off]`.
- При новом сообщении сервер сразу отправляет Telegram-уведомление получателю, если привязка включена.

Если сервер на `*.onrender.com`, terminal client:
- показывает статус пробуждения Render;
- ждёт готовности `/health`;
- отправляет keep-alive ping в фоне.

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
   - `TELEGRAM_BOT_USERNAME`
   - `TELEGRAM_BOT_TOKEN`
   - `TG_LINK_CODE_TTL_MINUTES`

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
