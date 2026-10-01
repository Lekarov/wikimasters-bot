"""Affiche un clavier Telegram persistant (toujours visible sous la zone de texte)
avec un bouton pour declencher une ouverture manuelle.

Usage:
    python set_keyboard.py
"""
import json
import urllib.request
import urllib.parse
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

KEYBOARD = {
    "keyboard": [[{"text": "Ouvrir maintenant"}], [{"text": "Etat"}]],
    "resize_keyboard": True,
    "is_persistent": True,
}


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": config["chat_id"],
        "text": "Clavier active. Bouton Ouvrir maintenant = ouverture manuelle immediate (des qu'un paquet est dispo). Bouton Etat = statut actuel.",
        "reply_markup": json.dumps(KEYBOARD),
    }).encode()
    with urllib.request.urlopen(url, data=data, timeout=15) as resp:
        print(json.dumps(json.loads(resp.read()), ensure_ascii=True))


if __name__ == "__main__":
    main()
