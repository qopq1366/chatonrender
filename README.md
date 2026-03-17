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
- `GET /auth/me`
- `POST /messages`
- `GET /messages/history/{other_username}`
- `GET /messages/inbox?since_id=0`

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
