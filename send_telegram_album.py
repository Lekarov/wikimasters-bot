"""Envoie plusieurs images en UN SEUL message Telegram (album / media group),
avec une legende (caption) sur la premiere image qui sert de recap pour tout
le groupe. Supprime tous les fichiers locaux juste apres l'envoi.

Usage:
    python send_telegram_album.py "<caption>" "<img1>" "<img2>" ... (2 a 10 images)
"""
import json
import sys
import time
import uuid
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
TMP_DIR = Path(__file__).parent / "tmp_images"


def cleanup_orphans():
    if not TMP_DIR.exists():
        return
    for f in TMP_DIR.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass


def send_album(image_paths, caption: str) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMediaGroup"

    boundary = uuid.uuid4().hex
    media = []
    for i, p in enumerate(image_paths):
        item = {"type": "photo", "media": f"attach://photo{i}"}
        if i == 0 and caption:
            item["caption"] = caption
        media.append(item)

    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{config['chat_id']}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"\r\n\r\n{json.dumps(media)}\r\n")
    header = "".join(parts).encode("utf-8")

    body = bytearray()
    body += header
    for i, p in enumerate(image_paths):
        path = Path(p)
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo{i}\"; filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8")
        body += path.read_bytes()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=bytes(body), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def send_album_and_cleanup(image_paths, caption: str) -> dict:
    TMP_DIR.mkdir(exist_ok=True)
    cleanup_orphans()
    try:
        result = send_album(image_paths, caption)
        return result
    finally:
        for p in image_paths:
            path = Path(p)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        cleanup_orphans()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print('Usage: python send_telegram_album.py "<caption>" "<img1>" "<img2>" ... (2-10 images)')
        sys.exit(1)
    cap = sys.argv[1]
    imgs = sys.argv[2:]
    if len(imgs) < 2:
        print("Il faut au moins 2 images pour un album Telegram (sinon utilise send_telegram_photo.py).")
        sys.exit(1)
    if len(imgs) > 10:
        imgs = imgs[:10]
    result = send_album_and_cleanup(imgs, cap)
    print(json.dumps(result, ensure_ascii=True))
