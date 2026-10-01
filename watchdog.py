"""Surveille autobot.py et le relance s'il plante OU s'il se fige (freeze).

Playwright (API sync) n'a pas de timeout sur page.evaluate() : si la
connexion CDP a un hoquet, l'appel peut rester bloque indefiniment sans
jamais lever d'exception, donc le try/except interne d'autobot.py ne se
declenche jamais. Ce watchdog est un processus EXTERNE qui verifie que le
fichier autobot.heartbeat est mis a jour regulierement ; sinon il tue le
processus fige et en relance un nouveau.

Usage:
    python watchdog.py --connect 9333
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
HEARTBEAT_PATH = BASE_DIR / "autobot.heartbeat"
STALE_SECONDS = 150  # si pas de battement depuis 150s, on considere le process fige
CHECK_INTERVAL = 15


def log(msg: str):
    print(f"[watchdog {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def heartbeat_age() -> float:
    if not HEARTBEAT_PATH.exists():
        return 0.0
    try:
        return time.time() - float(HEARTBEAT_PATH.read_text().strip())
    except (ValueError, OSError):
        return 0.0


def run(args):
    cmd = [sys.executable, str(BASE_DIR / "autobot.py")]
    if args.connect:
        cmd += ["--connect", str(args.connect)]
    if args.headed:
        cmd.append("--headed")

    while True:
        HEARTBEAT_PATH.write_text(str(time.time()))
        log(f"Starting autobot: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))

        while True:
            time.sleep(CHECK_INTERVAL)
            ret = proc.poll()
            if ret is not None:
                log(f"autobot.py exited (code {ret}) — restarting in 5s")
                time.sleep(5)
                break

            age = heartbeat_age()
            if age > STALE_SECONDS:
                log(f"No heartbeat for {age:.0f}s — autobot.py appears frozen, killing it")
                proc.kill()
                proc.wait(timeout=10)
                time.sleep(5)
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", type=int, metavar="PORT")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        log("Stopped by user.")
