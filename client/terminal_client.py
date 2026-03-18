import threading
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
CLIENT_VERSION = "1.1.0"
TOKEN_PATH = Path.home() / ".chatonrender_token"
RENDER_AWAKE_CHECKED = False
KEEPALIVE_STARTED = False
STOP_EVENT = threading.Event()


def load_token() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    return TOKEN_PATH.read_text(encoding="utf-8").strip() or None


def save_token(token: str) -> None:
    TOKEN_PATH.write_text(token, encoding="utf-8")


def clear_token() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def headers() -> dict[str, str]:
    token = load_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def is_render_server() -> bool:
    return "onrender.com" in BASE_URL.lower()


def warmup_render_if_needed() -> None:
    global RENDER_AWAKE_CHECKED
    if not is_render_server() or RENDER_AWAKE_CHECKED:
        return

    print("Render просыпается, подождите...")
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=15)
            if response.status_code == 200:
                print("Render уже проснулся.")
                RENDER_AWAKE_CHECKED = True
                return
        except requests.RequestException:
            pass
        time.sleep(3)

    raise RuntimeError("Render долго не отвечает. Попробуйте снова через минуту.")


def keepalive_loop():
    while not STOP_EVENT.is_set():
        if is_render_server():
            try:
                requests.get(f"{BASE_URL}/health", timeout=15)
            except requests.RequestException:
                pass
        STOP_EVENT.wait(45)


def start_keepalive_once():
    global KEEPALIVE_STARTED
    if KEEPALIVE_STARTED:
        return
    thread = threading.Thread(target=keepalive_loop, daemon=True)
    thread.start()
    KEEPALIVE_STARTED = True


def check_version_policy():
    try:
        warmup_render_if_needed()
        response = requests.get(
            f"{BASE_URL}/client/version-policy",
            params={"client_version": CLIENT_VERSION},
            timeout=15,
        )
    except requests.RequestException:
        return

    if response.status_code == 404:
        return
    if response.status_code >= 400:
        return

    data = response.json()
    if data.get("supported") is False:
        print(
            f"ВНИМАНИЕ: клиент {CLIENT_VERSION} больше не поддерживается. "
            f"Минимальная версия: {data.get('min_supported')}."
        )
    elif data.get("update_available"):
        print(
            f"Есть обновление клиента: {data.get('latest')} (текущая: {CLIENT_VERSION})."
        )
        download_url = data.get("download_url")
        if download_url:
            print(f"Ссылка на обновление: {download_url}")


def call(method: str, path: str, **kwargs):
    warmup_render_if_needed()
    url = f"{BASE_URL}{path}"
    response = requests.request(method, url, timeout=20, **kwargs)
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}
        raise RuntimeError(f"{response.status_code}: {body.get('detail', body)}")
    if response.text:
        return response.json()
    return None


def format_time(value: str | None) -> str:
    if not value:
        return "--:--"
    text = value.replace("T", " ")
    if "." in text:
        text = text.split(".", maxsplit=1)[0]
    return text[-8:] if len(text) >= 8 else text


def print_message_line(item: dict):
    print(
        f"[{format_time(item.get('created_at'))}] "
        f"{item.get('sender_username')} -> {item.get('recipient_username')}: "
        f"{item.get('content')}"
    )


def cmd_register(args: list[str]):
    if len(args) != 2:
        print("usage: register <username> <password>")
        return
    username, password = args
    data = call("POST", "/auth/register", json={"username": username, "password": password})
    print(f"registered: {data['username']} (id={data['id']})")


def cmd_login(args: list[str]):
    if len(args) != 2:
        print("usage: login <username> <password>")
        return
    username, password = args
    data = call("POST", "/auth/login", json={"username": username, "password": password})
    save_token(data["access_token"])
    print("login successful")


def cmd_add_tg(args: list[str]):
    if len(args) != 0:
        print("usage: /add-tg")
        return
    result = call("POST", "/tg/add/request", headers=headers())
    print(f"telegram bot: {result['bot_username']}")
    print(f"link code: {result['link_code']}")
    print("Откройте Telegram бота и отправьте команду:")
    print(f"/link {result['link_code']}")
    print("После этого проверьте статус командой /manage-tg")


def cmd_manage_tg(args: list[str]):
    if not load_token():
        print("Сначала выполните login.")
        return
    if len(args) == 0:
        data = call("GET", "/tg/manage", headers=headers())
        print(
            f"linked={data.get('linked')} enabled={data.get('enabled')} "
            f"telegram_user_id={data.get('telegram_user_id')}"
        )
        return
    if len(args) != 1 or args[0] not in {"on", "off"}:
        print("usage: /manage-tg [on|off]")
        return
    enabled = args[0] == "on"
    data = call("POST", "/tg/manage", headers=headers(), json={"enabled": enabled})
    print(
        f"updated: linked={data.get('linked')} enabled={data.get('enabled')} "
        f"telegram_user_id={data.get('telegram_user_id')}"
    )


def cmd_logout(_: list[str]):
    clear_token()
    print("logged out")


def cmd_me(_: list[str]):
    data = call("GET", "/auth/me", headers=headers())
    print(f"user: {data['username']} (id={data['id']})")


def cmd_send(args: list[str]):
    if len(args) < 2:
        print("usage: send <recipient> <message>")
        return
    recipient = args[0]
    content = " ".join(args[1:])
    data = call(
        "POST",
        "/messages",
        headers=headers(),
        json={"recipient_username": recipient, "content": content},
    )
    print_message_line(data)


def cmd_history(args: list[str]):
    if len(args) != 1:
        print("usage: history <username>")
        return
    other = args[0]
    data = call("GET", f"/messages/history/{other}?limit=20", headers=headers())
    rows = list(reversed(data))
    if not rows:
        print("История пуста.")
        return
    for item in rows:
        print_message_line(item)


def cmd_inbox(args: list[str]):
    since_id = int(args[0]) if args else 0
    data = call("GET", f"/messages/inbox?since_id={since_id}", headers=headers())
    if not data:
        print("Новых сообщений нет.")
        return
    for item in data:
        print_message_line(item)


def get_max_inbox_id() -> int:
    rows = call("GET", "/messages/inbox?since_id=0&limit=200", headers=headers())
    return max((int(item["id"]) for item in rows), default=0)


def print_chat_window(other_username: str, limit: int = 12):
    rows = call(
        "GET",
        f"/messages/history/{other_username}?limit={limit}&offset=0",
        headers=headers(),
    )
    rows = list(reversed(rows))
    print(f"--- Диалог с {other_username} (последние {len(rows)}) ---")
    for item in rows:
        print_message_line(item)
    print("Введите текст. Команды: /exit, /refresh")


def poll_chat_incoming(other_username: str, since_id: int) -> int:
    rows = call("GET", f"/messages/inbox?since_id={since_id}", headers=headers())
    max_id = since_id
    for item in rows:
        msg_id = int(item["id"])
        if msg_id > max_id:
            max_id = msg_id
        if item.get("sender_username") == other_username:
            print_message_line(item)
    return max_id


def cmd_chat(args: list[str]):
    if len(args) != 1:
        print("usage: chat <username>")
        return
    other_username = args[0]
    if not load_token():
        print("Сначала выполните login.")
        return

    last_inbox_id = get_max_inbox_id()
    print_chat_window(other_username)

    while True:
        last_inbox_id = poll_chat_incoming(other_username, last_inbox_id)
        text = input(f"[{other_username}]> ").strip()
        if not text:
            continue
        if text == "/exit":
            print("Выход из диалога.")
            return
        if text == "/refresh":
            print_chat_window(other_username)
            continue

        sent = call(
            "POST",
            "/messages",
            headers=headers(),
            json={"recipient_username": other_username, "content": text},
        )
        print_message_line(sent)


def cmd_set_server(args: list[str]):
    global BASE_URL, RENDER_AWAKE_CHECKED
    if len(args) != 1:
        print("usage: server <base_url>")
        return
    BASE_URL = args[0].rstrip("/")
    RENDER_AWAKE_CHECKED = False
    print(f"server set to {BASE_URL}")
    check_version_policy()


def help_text():
    print("commands:")
    print("  help")
    print("  server <base_url>")
    print("  register <username> <password>")
    print("  login <username> <password>")
    print("  chat <username>               # удобный режим диалога")
    print("  send <recipient> <message>")
    print("  history <username>")
    print("  inbox [since_id]")
    print("  /add-tg")
    print("  /manage-tg [on|off]")
    print("  me")
    print("  logout")
    print("  exit")


COMMANDS = {
    "help": help_text,
    "server": cmd_set_server,
    "register": cmd_register,
    "login": cmd_login,
    "chat": cmd_chat,
    "open": cmd_chat,
    "logout": cmd_logout,
    "add-tg": cmd_add_tg,
    "manage-tg": cmd_manage_tg,
    "me": cmd_me,
    "send": cmd_send,
    "history": cmd_history,
    "inbox": cmd_inbox,
}


def main():
    start_keepalive_once()
    check_version_policy()
    print(f"ChatOnRender terminal client v{CLIENT_VERSION}. Type 'help' for commands.")
    while True:
        raw = input("> ").strip()
        if not raw:
            continue
        if raw in {"exit", "quit"}:
            STOP_EVENT.set()
            print("bye")
            return

        parts = raw.split()
        command, args = parts[0], parts[1:]
        if command.startswith("/"):
            command = command[1:]
        handler = COMMANDS.get(command)
        if handler is None:
            print("unknown command")
            continue

        try:
            if command == "help":
                handler()
            else:
                handler(args)
        except Exception as exc:
            print(f"error: {exc}")


if __name__ == "__main__":
    main()
