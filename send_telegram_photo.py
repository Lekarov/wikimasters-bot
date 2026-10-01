"""Telecharge une image (URL publique), l'envoie sur Telegram, puis la supprime.

Ne laisse jamais l'image sur disque plus longtemps que le temps de l'upload :
le fichier temporaire est supprime dans un bloc finally, meme en cas d'erreur.
Fait aussi un nettoyage de securite du dossier tmp_images/ a chaque appel,
au cas ou un fichier precedent n'aurait pas ete supprime (crash, coupure...).

Usage:
    python send_telegram_photo.py "<image_url>" "<caption>"
"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
TMP_DIR = Path(__file__).parent / "tmp_images"
MAX_AGE_SECONDS = 300  # tout fichier de plus de 5 min dans tmp_images/ est considere orphelin


def cleanup_orphans():
    """Supprime tout fichier residuel dans tmp_images/ (filet de securite)."""
    if not TMP_DIR.exists():
        return
    now = time.time()
    for f in TMP_DIR.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass


def download(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
        out.write(resp.read())


def send_photo(image_path: Path, caption: str) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendPhoto"

    boundary = uuid.uuid4().hex
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{config['chat_id']}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{image_path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n")
    body = "".join(parts).encode("utf-8")
    body += image_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def send_image_url(image_url: str, caption: str) -> dict:
    TMP_DIR.mkdir(exist_ok=True)
    cleanup_orphans()
    ext = ".jpg"
    if "." in image_url.split("?")[0].rsplit("/", 1)[-1]:
        ext = "." + image_url.split("?")[0].rsplit(".", 1)[-1][:5]
    dest = TMP_DIR / f"{uuid.uuid4().hex}{ext}"
    try:
        download(image_url, dest)
        result = send_photo(dest, caption)
        return result
    finally:
        if dest.exists():
            dest.unlink()
        cleanup_orphans()


def send_local_file(file_path: str, caption: str) -> dict:
    """Envoie un fichier image deja present sur disque (ex: capture d'ecran d'une
    carte), puis le supprime immediatement — meme comportement que send_image_url,
    sans etape de telechargement."""
    TMP_DIR.mkdir(exist_ok=True)
    cleanup_orphans()
    path = Path(file_path)
    try:
        result = send_photo(path, caption)
        return result
    finally:
        if path.exists():
            path.unlink()
        cleanup_orphans()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python send_telegram_photo.py <image_url_or_local_path> [caption]")
        sys.exit(1)
    source = sys.argv[1]
    cap = sys.argv[2] if len(sys.argv) > 2 else ""
    if source.startswith("http://") or source.startswith("https://"):
        result = send_image_url(source, cap)
    else:
        result = send_local_file(source, cap)
    print(json.dumps(result, ensure_ascii=True))
