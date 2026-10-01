"""Verifie si l'utilisateur a appuye sur un bouton du clavier Telegram depuis
la derniere verification (ouverture manuelle ou demande d'etat).
Garde son propre curseur (state.json) pour ne jamais retraiter le meme message.

Usage:
    python check_trigger.py
Affiche sur stdout : OPEN, STATUS, ou NONE (peut y avoir plusieurs mots si
plusieurs commandes recues, le dernier etat prevaut en pratique).
"""
import json
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
STATE_PATH = Path(__file__).parent / "state.json"


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_update_id": 0}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    state = load_state()
    offset = state.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{config['telegram_token']}/getUpdates?offset={offset}&timeout=0"
    with urllib.request.urlopen(url, timeout=15) as resp:
        result = json.loads(resp.read())

    triggers = []
    max_id = state.get("last_update_id", 0)
    for update in result.get("result", []):
        max_id = max(max_id, update["update_id"])
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(config["chat_id"]):
            continue
        text = (msg.get("text") or "").strip().lower()
        if text in ("ouvrir maintenant", "/ouvrir", "/open"):
            triggers.append("OPEN")
        elif text in ("etat", "état", "/etat", "/status"):
            triggers.append("STATUS")

    state["last_update_id"] = max_id
    save_state(state)

    if "OPEN" in triggers:
        print("OPEN")
    elif "STATUS" in triggers:
        print("STATUS")
    else:
        print("NONE")


if __name__ == "__main__":
    main()
