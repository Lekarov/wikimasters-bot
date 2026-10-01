"""Bot autonome WikiMasters : ouvre automatiquement les paquets dispo sur
https://www.wiki-masters.com/pulls (TON compte, connexion unique manuelle),
envoie un album Telegram par paquet (image de chaque carte + recap), et
repond aux boutons Telegram ("Ouvrir maintenant" / "Etat"). Tourne en boucle
infinie, independant de Claude — un simple processus Python en arriere-plan.

Regles de pacing :
- 1 seul paquet dispo -> attend un delai aleatoire (30-90s, jamais le meme)
  avant de l'ouvrir, juste pour ne pas ouvrir instantanement.
- 2 paquets ou plus deja en reserve -> les enchaine directement, sans pause.
- Verifie les boutons Telegram a chaque iteration (reactivite <=90s).
- Ne fait RIEN d'autre sur le site (pas d'enchere, pas d'echange).

Usage:
    python autobot.py --login     # premiere fois : ouvre une fenetre, connecte-toi
                                   # a la main sur wiki-masters.com, puis appuie sur
                                   # Entree dans ce terminal une fois connecte.
    python autobot.py             # lance la boucle autonome (utilise la session
                                   # sauvegardee par --login)
"""
import argparse
import json
import random
import re
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
TMP_DIR = BASE_DIR / "tmp_images"
PROFILE_DIR = BASE_DIR / "browser_profile"
LOG_PATH = BASE_DIR / "autobot.log"
URL = "https://www.wiki-masters.com/pulls"

CARD_RECT_JS = """() => {
  const validRarities = ['C','PC','R','SR','UR'];
  const els = [...document.querySelectorAll('main *')];
  const badge = els.find(el => el.children.length === 0 && validRarities.includes(el.textContent.trim()));
  if (!badge) return null;
  let el = badge;
  for (let i = 0; i < 8 && el; i++) {
    const r = el.getBoundingClientRect();
    if (r.width > 150 && r.height > 250) break;
    el = el.parentElement;
  }
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: r.height };
}"""

STATE_LINES_JS = """() => document.querySelector('main').innerText.split('\\n').filter(Boolean)"""

HEARTBEAT_PATH = BASE_DIR / "autobot.heartbeat"


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    beat()


def beat():
    """Touch the heartbeat file so an external watchdog can tell we're alive.
    page.evaluate() has no built-in timeout in Playwright, so a stuck CDP
    connection can hang forever without ever raising — only an external
    process watching this file's mtime can detect and recover from that."""
    try:
        HEARTBEAT_PATH.write_text(str(time.time()))
    except OSError:
        pass


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_trigger_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_update_id": 0}


def save_trigger_state(state):
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def check_trigger(config):
    state = load_trigger_state()
    offset = state.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{config['telegram_token']}/getUpdates?offset={offset}&timeout=0"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        log(f"check_trigger error: {e}")
        return "NONE"

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
    save_trigger_state(state)

    if "OPEN" in triggers:
        return "OPEN"
    if "STATUS" in triggers:
        return "STATUS"
    return "NONE"


def send_text(config, text: str):
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": config["chat_id"], "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as resp:
            resp.read()
    except Exception as e:
        log(f"send_text error: {e}")


def send_album(config, image_paths, caption: str):
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMediaGroup"
    boundary = uuid.uuid4().hex
    media = []
    for i, _ in enumerate(image_paths):
        item = {"type": "photo", "media": f"attach://photo{i}"}
        if i == 0 and caption:
            item["caption"] = caption
        media.append(item)

    body = bytearray()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{config['chat_id']}\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"\r\n\r\n{json.dumps(media)}\r\n".encode()
    for i, p in enumerate(image_paths):
        path = Path(p)
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo{i}\"; filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        body += path.read_bytes()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=bytes(body), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except Exception as e:
        log(f"send_album error: {e}")
    finally:
        for p in image_paths:
            path = Path(p)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass


def cleanup_tmp():
    if not TMP_DIR.exists():
        TMP_DIR.mkdir(exist_ok=True)
        return
    for f in TMP_DIR.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass


def read_state(page):
    lines = page.evaluate(STATE_LINES_JS)
    if len(lines) < 4:
        # Page probably mid-hydration/navigation; give it a moment and retry once.
        page.wait_for_timeout(1500)
        lines = page.evaluate(STATE_LINES_JS)
    avail_line = next((l for l in lines if "/ 10" in l), "")
    timer_line = next((l for l in lines if l.startswith("Prochain dans")), "")
    available = None
    m_avail = re.search(r"(\d+)\s*/\s*10", avail_line)
    if m_avail:
        available = int(m_avail.group(1))
    ready = "Prêt" in timer_line
    timer_seconds = None
    if timer_line and not ready:
        m = timer_line.replace("Prochain dans", "").strip()
        if ":" in m:
            mm, ss = m.split(":")
            try:
                timer_seconds = int(mm) * 60 + int(ss)
            except ValueError:
                timer_seconds = None
    return {"available": available, "ready": ready, "timer_seconds": timer_seconds, "raw": avail_line + " | " + timer_line}


def click_button_by_text(page, text: str) -> bool:
    """Click a <button> whose trimmed textContent exactly matches `text`.
    Playwright's get_by_role/text-is locators rely on the computed
    accessible name, which on this site's buttons (icon/img + span) differs
    from plain textContent and fails to match — so we go straight through
    the DOM via evaluate instead."""
    return page.evaluate(
        """(text) => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === text);
            if (!btn) return false;
            btn.click();
            return true;
        }""",
        text,
    )


def open_one_pack(page):
    if not click_button_by_text(page, "Ouvrir"):
        raise RuntimeError("Bouton 'Ouvrir' introuvable")
    page.wait_for_timeout(1200)

    cards = []
    image_paths = []
    for i in range(5):
        lines = page.evaluate(STATE_LINES_JS)
        rarity = lines[3] if len(lines) > 3 else "?"
        name = lines[4] if len(lines) > 4 else "?"
        cards.append((rarity, name))

        rect = page.evaluate(CARD_RECT_JS)
        if rect:
            TMP_DIR.mkdir(exist_ok=True)
            img_path = TMP_DIR / f"{uuid.uuid4().hex}.png"
            page.screenshot(path=str(img_path), clip=rect)
            image_paths.append(str(img_path))

        if i < 4:
            page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('main button')).find(b => {
                    const p = b.querySelector('svg polyline');
                    return p && p.getAttribute('points') === '9 18 15 12 9 6';
                });
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(500)

    click_button_by_text(page, "Continuer")
    page.wait_for_timeout(700)

    return cards, image_paths


def check_notifications(page):
    # Best-effort: just report if the bell shows an unread badge; detailed
    # notification text isn't parsed to keep this simple and robust.
    try:
        badge = page.locator("button[aria-label='Notifications'] >> css=span").first
        if badge.count() > 0 and badge.is_visible():
            return badge.inner_text().strip()
    except Exception:
        pass
    return None


def rarity_summary(cards):
    counts = {}
    for rarity, _ in cards:
        counts[rarity] = counts.get(rarity, 0) + 1
    order = ["C", "PC", "R", "SR", "UR"]
    parts = []
    for r in order:
        if r in counts:
            parts.append(f"{counts[r]}x {r}")
    for r, c in counts.items():
        if r not in order:
            parts.append(f"{c}x {r}")
    return ", ".join(parts)


def open_all_available(page, config):
    opened_any = False
    while True:
        state = read_state(page)
        if not state["available"]:
            break
        log(f"Opening pack, state before: {state['raw']}")
        cards, image_paths = open_one_pack(page)
        opened_any = True
        after = read_state(page)
        summary = rarity_summary(cards)
        lines_txt = "\n".join(f"- {r} {n}" for r, n in cards)
        remaining = after["available"] if after["available"] is not None else "?"
        timer_txt = "Pret !" if after["ready"] else (f"{after['timer_seconds']}s" if after["timer_seconds"] else "?")
        caption = (
            f"Ouverture faite !\n"
            f"5 cartes : {summary}\n"
            f"{lines_txt}\n"
            f"Paquets restants : {remaining}/10 (prochain dans {timer_txt})"
        )
        if image_paths:
            send_album(config, image_paths, caption)
        else:
            send_text(config, caption)
        log(f"Pack sent: {summary}")

        if after["available"] and after["available"] >= 2:
            continue
        break
    return opened_any


def run_loop(headless: bool, cdp_port: int = None):
    config = load_config()
    cleanup_tmp()

    with sync_playwright() as p:
        owns_browser = cdp_port is None
        if cdp_port:
            log(f"Connecting to existing browser via CDP on port {cdp_port}...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = next((pg for pg in context.pages if "wiki-masters.com" in pg.url), None)
            if page is None:
                page = context.new_page()
            page.bring_to_front()
        else:
            context = p.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=headless, viewport={"width": 1400, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
        context.set_default_timeout(20000)
        page.set_default_timeout(20000)
        page.goto(URL, timeout=20000)
        page.wait_for_timeout(2000)  # laisse le temps a l'appli (SPA) de s'hydrater
        log("Autobot started.")

        while True:
            beat()
            try:
                trigger = check_trigger(config)
                if trigger == "STATUS":
                    st = read_state(page)
                    timer_txt = "Pret !" if st["ready"] else (f"{st['timer_seconds']}s" if st["timer_seconds"] else "?")
                    send_text(config, f"Etat : {st['available']}/10 paquets dispo, prochain dans {timer_txt}.")
                elif trigger == "OPEN":
                    state = read_state(page)
                    if state["available"]:
                        open_all_available(page, config)
                    else:
                        send_text(config, "Aucun paquet dispo pour le moment.")
                    cleanup_tmp()
                    time.sleep(5)
                    continue

                state = read_state(page)
                available = state["available"] or 0

                if available >= 2:
                    open_all_available(page, config)
                    cleanup_tmp()
                    time.sleep(2)
                    continue

                if available == 1 or state["ready"]:
                    delay = random.randint(30, 90)
                    log(f"1 pack ready, pacing {delay}s before opening")
                    time.sleep(delay)
                    open_all_available(page, config)
                    cleanup_tmp()
                    continue

                # nothing available: wait until close to the timer, capped at 90s
                base = min(state["timer_seconds"] or 90, 90)
                delay = base + random.randint(5, 15)
                delay = max(60, min(delay, 90))
                log(f"No packs ({state['raw']}), sleeping {delay}s")
                time.sleep(delay)

            except KeyboardInterrupt:
                log("Stopped by user.")
                break
            except Exception as e:
                log(f"Loop error: {e} — retrying in 30s")
                time.sleep(30)
                try:
                    page.goto(URL)
                except Exception:
                    pass

        if owns_browser:
            context.close()
        else:
            log("Leaving the user's browser open (CDP mode) — not closing it.")


def run_login(timeout_minutes: int = 10):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, viewport={"width": 1400, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(URL)
        print("Connecte-toi manuellement a wiki-masters.com dans la fenetre qui s'est ouverte.")
        print(f"J'attends automatiquement la connexion (jusqu'a {timeout_minutes} min)...")

        deadline = time.time() + timeout_minutes * 60
        logged_in = False
        debug_shot = BASE_DIR / "login_debug.png"
        while time.time() < deadline:
            for candidate in context.pages:
                try:
                    text = candidate.evaluate("() => document.body.innerText")
                except Exception:
                    text = ""
                if "paquets disponibles" in text:
                    logged_in = True
                    page = candidate
                    break
            if logged_in:
                break
            try:
                context.pages[-1].screenshot(path=str(debug_shot))
            except Exception:
                pass
            time.sleep(3)

        if logged_in:
            print("Connexion detectee. Session sauvegardee dans browser_profile/.")
            print("Tu peux maintenant lancer : python autobot.py")
        else:
            print("Timeout : connexion non detectee. Relance --login si besoin (la session partielle est quand meme sauvegardee).")

        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true", help="Ouvre une fenetre pour te connecter une premiere fois")
    parser.add_argument("--headed", action="store_true", help="Lance la boucle en mode visible (par defaut: headless)")
    parser.add_argument("--connect", type=int, metavar="PORT", help="Se connecte a un navigateur deja ouvert avec --remote-debugging-port=PORT au lieu d'en lancer un nouveau")
    args = parser.parse_args()

    if args.login:
        run_login()
    else:
        run_loop(headless=not args.headed, cdp_port=args.connect)
