import json
import threading
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
TOKEN_PATH = Path.home() / ".chatonrender_token"
RENDER_AWAKE_CHECKED = False
KEEPALIVE_STARTED = False
STOP_EVENT = threading.Event()
LAST_USERNAME: str | None = None
LAST_PASSWORD: str | None = None


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


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def login_with_bot_code(username: str, password: str):
    global LAST_USERNAME, LAST_PASSWORD
    info = call("GET", "/auth/bot-info")
    print(f"telegram bot: {info['bot_username']}")
    print("Получите код в Telegram и введите его (код действует 5 минут).")
    call(
        "POST",
        "/auth/login/request-code",
        json={"username": username, "password": password},
    )
    code = input("enter code from bot: ").strip()
    data = call("POST", "/auth/login/code", json={"username": username, "code": code})
    save_token(data["access_token"])
    LAST_USERNAME = username
    LAST_PASSWORD = password
    print("login successful")


def cmd_register(args: list[str]):
    global LAST_USERNAME, LAST_PASSWORD
    if len(args) != 2:
        print("usage: register <username> <password>")
        return
    username, password = args
    data = call("POST", "/auth/register", json={"username": username, "password": password})
    LAST_USERNAME = username
    LAST_PASSWORD = password
    print("registered:")
    print_json(data)


def cmd_login(args: list[str]):
    if len(args) != 2:
        print("usage: login <username> <password>")
        return
    username, password = args
    login_with_bot_code(username, password)


def cmd_add_tg(args: list[str]):
    if len(args) != 0:
        print("usage: /add-tg")
        return
    result = call("POST", "/tg/add/request", headers=headers())
    print(f"telegram bot: {result['bot_username']}")
    print("Введите код из бота (действует 5 минут).")
    code = input("tg link code: ").strip()
    call("POST", "/tg/add/confirm", headers=headers(), json={"code": code})
    print("telegram account linked")


def cmd_manage_tg(args: list[str]):
    if not load_token():
        print("Сначала выполните login.")
        return
    if len(args) == 0:
        data = call("GET", "/tg/manage", headers=headers())
        print_json(data)
        return
    if len(args) != 1 or args[0] not in {"on", "off"}:
        print("usage: /manage-tg [on|off]")
        return
    enabled = args[0] == "on"
    data = call("POST", "/tg/manage", headers=headers(), json={"enabled": enabled})
    print_json(data)


def cmd_logout(_: list[str]):
    clear_token()
    print("logged out")


def cmd_me(_: list[str]):
    data = call("GET", "/auth/me", headers=headers())
    print_json(data)


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
    print_json(data)


def cmd_history(args: list[str]):
    if len(args) != 1:
        print("usage: history <username>")
        return
    other = args[0]
    data = call("GET", f"/messages/history/{other}", headers=headers())
    print_json(data)


def cmd_inbox(args: list[str]):
    since_id = int(args[0]) if args else 0
    data = call("GET", f"/messages/inbox?since_id={since_id}", headers=headers())
    print_json(data)


def cmd_set_server(args: list[str]):
    global BASE_URL, RENDER_AWAKE_CHECKED
    if len(args) != 1:
        print("usage: server <base_url>")
        return
    BASE_URL = args[0].rstrip("/")
    RENDER_AWAKE_CHECKED = False
    print(f"server set to {BASE_URL}")


def help_text():
    print("commands:")
    print("  help")
    print("  server <base_url>")
    print("  register <username> <password>")
    print("  login <username> <password>  # asks code from admin bot")
    print("  /add-tg [username password]  # link account via Telegram code")
    print("  /manage-tg [on|off]          # show/toggle Telegram link")
    print("  logout")
    print("  me")
    print("  send <recipient> <message>")
    print("  history <username>")
    print("  inbox [since_id]")
    print("  exit")


COMMANDS = {
    "help": help_text,
    "server": cmd_set_server,
    "register": cmd_register,
    "login": cmd_login,
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
    print("ChatOnRender terminal client. Type 'help' for commands.")
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

