import json
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
TOKEN_PATH = Path.home() / ".chatonrender_token"


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


def call(method: str, path: str, **kwargs):
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


def cmd_register(args: list[str]):
    if len(args) != 2:
        print("usage: register <username> <password>")
        return
    username, password = args
    data = call("POST", "/auth/register", json={"username": username, "password": password})
    print("registered:")
    print_json(data)


def cmd_login(args: list[str]):
    if len(args) != 2:
        print("usage: login <username> <password>")
        return
    username, password = args
    data = call("POST", "/auth/login", json={"username": username, "password": password})
    save_token(data["access_token"])
    print("login successful")


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
    global BASE_URL
    if len(args) != 1:
        print("usage: server <base_url>")
        return
    BASE_URL = args[0].rstrip("/")
    print(f"server set to {BASE_URL}")


def help_text():
    print("commands:")
    print("  help")
    print("  server <base_url>")
    print("  register <username> <password>")
    print("  login <username> <password>")
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
    "me": cmd_me,
    "send": cmd_send,
    "history": cmd_history,
    "inbox": cmd_inbox,
}


def main():
    print("ChatOnRender terminal client. Type 'help' for commands.")
    while True:
        raw = input("> ").strip()
        if not raw:
            continue
        if raw in {"exit", "quit"}:
            print("bye")
            return

        parts = raw.split()
        command, args = parts[0], parts[1:]
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

