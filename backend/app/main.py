from functools import wraps
import os
import sys

import jwt
from flask import Flask, jsonify, request
from sqlalchemy import and_, desc, or_

if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from backend.app.auth import create_access_token, decode_token, hash_password, verify_password
    from backend.app.config import settings
    from backend.app.database import Base, SessionLocal, engine
    from backend.app.models import Message, NotificationEvent, User
else:
    from .auth import create_access_token, decode_token, hash_password, verify_password
    from .config import settings
    from .database import Base, SessionLocal, engine
    from .models import Message, NotificationEvent, User

Base.metadata.create_all(bind=engine)

app = Flask(__name__)


def json_error(status_code: int, detail: str):
    return jsonify({"detail": detail}), status_code


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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
