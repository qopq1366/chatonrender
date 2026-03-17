from functools import wraps
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests
from flask import Flask, jsonify, request
from sqlalchemy import and_, desc, or_, text

if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from backend.app.auth import create_access_token, decode_token, hash_password, verify_password
    from backend.app.config import settings
    from backend.app.database import Base, SessionLocal, engine
    from backend.app.models import (
        LoginCode,
        Message,
        NotificationEvent,
        TelegramLink,
        TelegramLinkCode,
        User,
    )
else:
    from .auth import create_access_token, decode_token, hash_password, verify_password
    from .config import settings
    from .database import Base, SessionLocal, engine
    from .models import LoginCode, Message, NotificationEvent, TelegramLink, TelegramLinkCode, User

def _column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(str(row[1]) == column_name for row in rows)


def migrate_schema():
    with engine.begin() as connection:
        try:
            if not _column_exists(connection, "telegram_links", "telegram_user_id"):
                connection.execute(text("ALTER TABLE telegram_links ADD COLUMN telegram_user_id INTEGER"))
            if not _column_exists(connection, "telegram_links", "telegram_chat_id"):
                connection.execute(text("ALTER TABLE telegram_links ADD COLUMN telegram_chat_id INTEGER"))
        except Exception:
            pass


Base.metadata.create_all(bind=engine)
migrate_schema()

app = Flask(__name__)
_TELEGRAM_BOT_THREAD_STARTED = False


def json_error(status_code: int, detail: str):
    return jsonify({"detail": detail}), status_code


def telegram_api(method: str, payload: dict):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, json=payload, timeout=20)
    if response.status_code >= 400:
        return None
    return response.json()


def send_telegram_message(chat_id: int, text: str):
    telegram_api("sendMessage", {"chat_id": chat_id, "text": text})


def process_telegram_update(update: dict):
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = chat.get("id")
    telegram_user_id = from_user.get("id")
    if not isinstance(chat_id, int) or not isinstance(telegram_user_id, int):
        return

    parts = text.split()
    command = parts[0].lower()

    db = SessionLocal()
    try:
        if command == "/start":
            send_telegram_message(
                chat_id,
                "Бот активен. Для привязки используйте /link <code>.",
            )
            return

        if command == "/link":
            if len(parts) != 2:
                send_telegram_message(chat_id, "Использование: /link <code>")
                return
            code = parts[1].strip()
            now = datetime.now(tz=timezone.utc)
            row = (
                db.query(TelegramLinkCode)
                .filter(
                    TelegramLinkCode.code == code,
                    TelegramLinkCode.used_at.is_(None),
                    TelegramLinkCode.expires_at > now,
                )
                .order_by(TelegramLinkCode.id.desc())
                .first()
            )
            if row is None:
                send_telegram_message(chat_id, "Код не найден или истек.")
                return

            link = db.query(TelegramLink).filter(TelegramLink.user_id == row.user_id).first()
            if link is None:
                link = TelegramLink(
                    user_id=row.user_id,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=chat_id,
                    is_enabled=True,
                )
                db.add(link)
            else:
                link.telegram_user_id = telegram_user_id
                link.telegram_chat_id = chat_id
                link.is_enabled = True
            row.used_at = now
            db.commit()
            send_telegram_message(chat_id, "Аккаунт успешно привязан к мессенджеру.")
            return

        if command == "/manage":
            link = (
                db.query(TelegramLink)
                .filter(TelegramLink.telegram_user_id == telegram_user_id)
                .first()
            )
            if link is None:
                send_telegram_message(chat_id, "Аккаунт не привязан. Сначала /link <code>.")
                return
            if len(parts) == 1:
                state = "on" if link.is_enabled else "off"
                send_telegram_message(chat_id, f"Текущий статус уведомлений: {state}")
                return
            if len(parts) == 2 and parts[1].lower() in {"on", "off"}:
                link.is_enabled = parts[1].lower() == "on"
                db.commit()
                send_telegram_message(chat_id, "Статус обновлен.")
                return
            send_telegram_message(chat_id, "Использование: /manage [on|off]")
    finally:
        db.close()


def telegram_bot_loop():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            response = requests.get(
                url,
                params={"timeout": 25, "offset": offset},
                timeout=35,
            )
            if response.status_code >= 400:
                time.sleep(2)
                continue
            data = response.json()
            if not data.get("ok"):
                time.sleep(2)
                continue
            for update in data.get("result", []):
                update_id = int(update.get("update_id", 0))
                offset = max(offset, update_id + 1)
                process_telegram_update(update)
        except Exception:
            time.sleep(2)


def start_telegram_bot_once():
    global _TELEGRAM_BOT_THREAD_STARTED
    if _TELEGRAM_BOT_THREAD_STARTED:
        return
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        return
    thread = threading.Thread(target=telegram_bot_loop, daemon=True)
    thread.start()
    _TELEGRAM_BOT_THREAD_STARTED = True


start_telegram_bot_once()


def require_server_key(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("X-Server-Key", "")
        if api_key != settings.integration_api_key:
            return json_error(401, "Invalid server key")
        return handler(*args, **kwargs)

    return wrapper


def require_auth(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return json_error(401, "Missing bearer token")

        token = auth_header.split(" ", maxsplit=1)[1]
        try:
            username = decode_token(token)
        except jwt.PyJWTError:
            return json_error(401, "Invalid or expired token")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if user is None:
                return json_error(401, "User from token does not exist")
        finally:
            db.close()

        return handler(user, *args, **kwargs)

    return wrapper


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if len(username) < 3 or len(username) > 64:
        return json_error(400, "Username must be 3-64 characters")
    if len(password) < 6 or len(password) > 128:
        return json_error(400, "Password must be 6-128 characters")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return json_error(409, "Username already exists")
        user = User(username=username, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return (
            jsonify(
                {"id": user.id, "username": user.username, "created_at": user.created_at}
            ),
            201,
        )
    finally:
        db.close()


@app.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.password_hash):
            return json_error(401, "Invalid credentials")
        token = create_access_token(user.username)
        return jsonify({"access_token": token, "token_type": "bearer"})
    finally:
        db.close()


@app.get("/auth/bot-info")
def bot_info():
    return jsonify({"bot_username": settings.telegram_bot_username})


@app.post("/auth/login/request-code")
def login_request_code():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.password_hash):
            return json_error(401, "Invalid credentials")

        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.login_code_ttl_minutes
        )
        row = LoginCode(username=username, code=code, expires_at=expires_at)
        db.add(row)
        db.commit()
        return jsonify({"detail": "Login code created"})
    finally:
        db.close()


@app.post("/auth/login/code")
def login_with_code():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    code = (payload.get("code") or "").strip()
    if len(code) != 6 or not code.isdigit():
        return json_error(400, "Code must be 6 digits")

    db = SessionLocal()
    try:
        now = datetime.now(tz=timezone.utc)
        row = (
            db.query(LoginCode)
            .filter(
                LoginCode.username == username,
                LoginCode.code == code,
                LoginCode.used_at.is_(None),
                LoginCode.expires_at > now,
            )
            .order_by(LoginCode.id.desc())
            .first()
        )
        if row is None:
            return json_error(401, "Invalid or expired code")

        user = db.query(User).filter(User.username == username).first()
        if user is None:
            return json_error(401, "User not found")

        row.used_at = now
        db.commit()
        token = create_access_token(user.username)
        return jsonify({"access_token": token, "token_type": "bearer"})
    finally:
        db.close()


@app.get("/auth/me")
@require_auth
def me(current_user: User):
    return jsonify(
        {
            "id": current_user.id,
            "username": current_user.username,
            "created_at": current_user.created_at,
        }
    )


@app.post("/tg/add/request")
@require_auth
def tg_add_request(current_user: User):
    db = SessionLocal()
    try:
        me_user = db.query(User).filter(User.id == current_user.id).first()
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.tg_link_code_ttl_minutes
        )
        row = TelegramLinkCode(
            user_id=me_user.id, username=me_user.username, code=code, expires_at=expires_at
        )
        db.add(row)
        db.commit()
        return jsonify(
            {
                "detail": "Telegram link code created",
                "bot_username": settings.telegram_bot_username,
                "link_code": code,
                "expires_in_minutes": settings.tg_link_code_ttl_minutes,
            }
        )
    finally:
        db.close()


@app.post("/tg/add/confirm")
@require_auth
def tg_add_confirm(current_user: User):
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if len(code) != 6 or not code.isdigit():
        return json_error(400, "Code must be 6 digits")

    db = SessionLocal()
    try:
        me_user = db.query(User).filter(User.id == current_user.id).first()
        now = datetime.now(tz=timezone.utc)
        row = (
            db.query(TelegramLinkCode)
            .filter(
                TelegramLinkCode.user_id == me_user.id,
                TelegramLinkCode.code == code,
                TelegramLinkCode.expires_at > now,
            )
            .order_by(TelegramLinkCode.id.desc())
            .first()
        )
        if row is None:
            return json_error(401, "Invalid or expired link code")
        if row.used_at is None:
            return json_error(409, "Code is not confirmed in Telegram bot yet")

        link = db.query(TelegramLink).filter(TelegramLink.user_id == me_user.id).first()
        if link is None or not link.telegram_user_id:
            return json_error(409, "Telegram account is not linked yet")
        return jsonify(
            {
                "detail": "Telegram account linked",
                "linked": True,
                "enabled": bool(link.is_enabled),
                "telegram_user_id": link.telegram_user_id,
            }
        )
    finally:
        db.close()


@app.get("/tg/manage")
@require_auth
def tg_manage(current_user: User):
    db = SessionLocal()
    try:
        link = db.query(TelegramLink).filter(TelegramLink.user_id == current_user.id).first()
        if link is None:
            return jsonify({"linked": False, "enabled": False, "telegram_user_id": None})
        return jsonify(
            {
                "linked": bool(link.telegram_user_id),
                "enabled": bool(link.is_enabled),
                "telegram_user_id": link.telegram_user_id,
            }
        )
    finally:
        db.close()


@app.post("/tg/manage")
@require_auth
def tg_manage_update(current_user: User):
    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return json_error(400, "enabled must be boolean")

    db = SessionLocal()
    try:
        link = db.query(TelegramLink).filter(TelegramLink.user_id == current_user.id).first()
        if link is None:
            return json_error(404, "Telegram is not linked for this account")
        link.is_enabled = enabled
        db.commit()
        return jsonify(
            {
                "linked": bool(link.telegram_user_id),
                "enabled": bool(link.is_enabled),
                "telegram_user_id": link.telegram_user_id,
            }
        )
    finally:
        db.close()


@app.post("/messages")
@require_auth
def send_message(current_user: User):
    payload = request.get_json(silent=True) or {}
    recipient_username = (payload.get("recipient_username") or "").strip()
    content = (payload.get("content") or "").strip()

    if len(recipient_username) < 3:
        return json_error(400, "Recipient username is required")
    if not content:
        return json_error(400, "Message content is required")
    if len(content) > 2000:
        return json_error(400, "Message too long (max 2000 chars)")

    db = SessionLocal()
    try:
        sender = db.query(User).filter(User.id == current_user.id).first()
        recipient = db.query(User).filter(User.username == recipient_username).first()
        if recipient is None:
            return json_error(404, "Recipient not found")

        message = Message(sender_id=sender.id, recipient_id=recipient.id, content=content)
        db.add(message)
        db.commit()
        db.refresh(message)
        event = NotificationEvent(
            message_id=message.id,
            sender_username=sender.username,
            recipient_username=recipient.username,
            content=message.content,
        )
        db.add(event)
        db.commit()
        tg_link = db.query(TelegramLink).filter(TelegramLink.user_id == recipient.id).first()
        if tg_link and tg_link.is_enabled and tg_link.telegram_chat_id:
            send_telegram_message(
                int(tg_link.telegram_chat_id),
                (
                    f"Новое сообщение от {sender.username}\n"
                    f"Текст: {message.content}\n"
                    f"ID: {message.id}"
                ),
            )
        return (
            jsonify(
                {
                    "id": message.id,
                    "sender_username": sender.username,
                    "recipient_username": recipient.username,
                    "content": message.content,
                    "created_at": message.created_at,
                }
            ),
            201,
        )
    finally:
        db.close()


@app.get("/messages/history/<other_username>")
@require_auth
def conversation_history(current_user: User, other_username: str):
    limit = min(max(int(request.args.get("limit", 30)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)

    db = SessionLocal()
    try:
        me_user = db.query(User).filter(User.id == current_user.id).first()
        other_user = db.query(User).filter(User.username == other_username).first()
        if other_user is None:
            return json_error(404, "User not found")

        rows = (
            db.query(Message)
            .filter(
                or_(
                    and_(
                        Message.sender_id == me_user.id, Message.recipient_id == other_user.id
                    ),
                    and_(
                        Message.sender_id == other_user.id, Message.recipient_id == me_user.id
                    ),
                )
            )
            .order_by(desc(Message.id))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return jsonify(
            [
                {
                    "id": m.id,
                    "sender_username": me_user.username
                    if m.sender_id == me_user.id
                    else other_user.username,
                    "recipient_username": other_user.username
                    if m.sender_id == me_user.id
                    else me_user.username,
                    "content": m.content,
                    "created_at": m.created_at,
                }
                for m in rows
            ]
        )
    finally:
        db.close()


@app.get("/messages/inbox")
@require_auth
def inbox(current_user: User):
    since_id = max(int(request.args.get("since_id", 0)), 0)
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)

    db = SessionLocal()
    try:
        me_user = db.query(User).filter(User.id == current_user.id).first()
        rows = (
            db.query(Message, User.username.label("sender_username"))
            .join(User, User.id == Message.sender_id)
            .filter(Message.recipient_id == me_user.id, Message.id > since_id)
            .order_by(Message.id.asc())
            .limit(limit)
            .all()
        )
        return jsonify(
            [
                {
                    "id": message.id,
                    "sender_username": sender_username,
                    "recipient_username": me_user.username,
                    "content": message.content,
                    "created_at": message.created_at,
                }
                for message, sender_username in rows
            ]
        )
    finally:
        db.close()


@app.get("/integrations/events")
@require_server_key
def integration_events():
    after_id = max(int(request.args.get("after_id", 0)), 0)
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)

    db = SessionLocal()
    try:
        rows = (
            db.query(NotificationEvent)
            .filter(NotificationEvent.id > after_id)
            .order_by(NotificationEvent.id.asc())
            .limit(limit)
            .all()
        )
        return jsonify(
            [
                {
                    "id": row.id,
                    "message_id": row.message_id,
                    "sender_username": row.sender_username,
                    "recipient_username": row.recipient_username,
                    "content": row.content,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        )
    finally:
        db.close()


@app.get("/integrations/login-codes")
@require_server_key
def integration_login_codes():
    after_id = max(int(request.args.get("after_id", 0)), 0)
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    now = datetime.now(tz=timezone.utc)

    db = SessionLocal()
    try:
        rows = (
            db.query(LoginCode)
            .filter(
                LoginCode.id > after_id,
                LoginCode.used_at.is_(None),
                LoginCode.expires_at > now,
                LoginCode.dispatched_at.is_(None),
            )
            .order_by(LoginCode.id.asc())
            .limit(limit)
            .all()
        )
        response = []
        for row in rows:
            response.append(
                {
                    "id": row.id,
                    "username": row.username,
                    "code": row.code,
                    "expires_at": row.expires_at,
                }
            )
            row.dispatched_at = now
        db.commit()
        return jsonify(response)
    finally:
        db.close()


@app.get("/integrations/tg-link-codes")
@require_server_key
def integration_tg_link_codes():
    after_id = max(int(request.args.get("after_id", 0)), 0)
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    now = datetime.now(tz=timezone.utc)

    db = SessionLocal()
    try:
        rows = (
            db.query(TelegramLinkCode)
            .filter(
                TelegramLinkCode.id > after_id,
                TelegramLinkCode.used_at.is_(None),
                TelegramLinkCode.expires_at > now,
                TelegramLinkCode.dispatched_at.is_(None),
            )
            .order_by(TelegramLinkCode.id.asc())
            .limit(limit)
            .all()
        )
        response = []
        for row in rows:
            response.append(
                {
                    "id": row.id,
                    "username": row.username,
                    "code": row.code,
                    "expires_at": row.expires_at,
                }
            )
            row.dispatched_at = now
        db.commit()
        return jsonify(response)
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
