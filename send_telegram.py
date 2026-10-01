"""Envoie un message texte au bot Telegram configuré dans config.json.

Usage:
    python send_telegram.py "texte du message"
    echo "texte" | python send_telegram.py
"""
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def send(text: str) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": config["chat_id"],
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    with urllib.request.urlopen(url, data=data, timeout=15) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    else:
        message = sys.stdin.read()
    result = send(message)
    print(json.dumps(result, ensure_ascii=True))
