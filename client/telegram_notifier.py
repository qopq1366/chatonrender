import os
import time

import requests

BACKEND_DOMAIN = os.getenv("BACKEND_DOMAIN", "http://127.0.0.1:8000").rstrip("/")
SERVER_KEY = os.getenv("SERVER_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"telegram send failed: {response.status_code} {response.text[:300]}"
        )


def fetch_events(after_id: int):
    url = f"{BACKEND_DOMAIN}/integrations/events"
    response = requests.get(
        url,
        params={"after_id": after_id, "limit": 100},
        headers={"X-Server-Key": SERVER_KEY},
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"backend events failed: {response.status_code} {response.text[:300]}"
        )
    return response.json()


def validate_env():
    missing = [
        name
        for name, value in {
            "SERVER_KEY": SERVER_KEY,
            "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
            "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing env vars: {', '.join(missing)}")


def main():
    validate_env()
    print(f"Telegram notifier started. backend={BACKEND_DOMAIN}")
    last_id = 0

    while True:
        try:
            events = fetch_events(last_id)
            for event in events:
                text = (
                    f"New message #{event['message_id']}\n"
                    f"from: {event['sender_username']}\n"
                    f"to: {event['recipient_username']}\n"
                    f"text: {event['content']}"
                )
                send_telegram(text)
                last_id = max(last_id, int(event["id"]))
        except Exception as exc:
            print(f"notifier error: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
