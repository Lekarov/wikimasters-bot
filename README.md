# WikiMasters Bot

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![Playwright](https://img.shields.io/badge/automation-Playwright-45ba4b)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-personal%20use-orange)

Bot d'automatisation personnel pour [WikiMasters](https://www.wiki-masters.com/pulls),
un jeu de collection de cartes façon Wikipédia. Il ouvre automatiquement les
paquets disponibles sur **ton propre compte** et t'envoie un récapitulatif
avec les images de chaque carte directement sur Telegram, avec deux
commandes de contrôle à distance (`Ouvrir maintenant`, `Etat`).

> Projet solo / gacha sur un compte personnel. Aucune manipulation d'autres
> comptes, aucune action que l'ouverture de paquets (pas d'enchère, pas
> d'échange).

## Fonctionnement

```
┌─────────────┐   heartbeat    ┌──────────────┐   CDP (debug port)   ┌────────────┐
│ start_bot.bat│ ─────────────▶│ watchdog.py  │ ────────────────────▶│  autobot.py │
└─────────────┘   surveille    └──────────────┘  pilote le navigateur └─────┬──────┘
      │                              │ relance si figé/plante               │
      ▼                               (freeze silencieux Playwright)        ▼
 relance Vivaldi                                                  lit l'état de la page,
 avec --remote-debugging-port                                     clique "Ouvrir",
                                                                    capture chaque carte,
                                                                    envoie l'album Telegram
```

- **`autobot.py`** — cœur du bot. Boucle infinie qui lit l'état de la page
  (paquets disponibles, timer avant le prochain), ouvre les paquets dispo,
  capture une image de chaque carte, puis envoie le tout en un album
  Telegram avec un récap texte. Répond aussi aux commandes envoyées depuis
  Telegram.
- **`watchdog.py`** — superviseur externe. Playwright n'a pas de timeout
  intégré sur `page.evaluate()` : si la connexion au navigateur a un
  hoquet, le bot peut se figer silencieusement sans jamais lever
  d'exception. Le watchdog surveille un fichier "heartbeat" mis à jour à
  chaque tick et tue/relance `autobot.py` si plus de 150s se sont écoulées
  sans battement.
- **`start_bot.bat` / `stop_bot.bat`** — lance/arrête tout en un double-clic
  (ferme puis relance le navigateur avec le port de debug, puis démarre le
  watchdog).
- **`check_trigger.py`, `send_telegram.py`, `send_telegram_photo.py`,
  `send_telegram_album.py`, `set_keyboard.py`** — utilitaires Telegram
  autonomes (testables en ligne de commande indépendamment du bot).

### Pourquoi se connecter à un navigateur déjà ouvert ?

Cloudflare bloque la connexion sur WikiMasters si le navigateur est lancé
directement par un script d'automatisation. La solution : lancer Vivaldi (ou
n'importe quel Chromium) avec `--remote-debugging-port`, s'y connecter
**après coup** via le protocole CDP, et réutiliser la session déjà
authentifiée de l'utilisateur. C'est ce que fait `start_bot.bat`.

### Pacing

- 1 seul paquet disponible → attend un délai aléatoire de 30 à 90 secondes
  avant de l'ouvrir (juste pour un rythme naturel, pas pour contourner un
  système anti-bot).
- 2 paquets ou plus déjà en réserve → les enchaîne directement.
- Vérifie les commandes Telegram au moins toutes les 90 secondes.

## Installation

Prérequis : Python 3.10+, un navigateur basé Chromium (Vivaldi/Chrome/Edge),
un bot Telegram ([@BotFather](https://t.me/BotFather)) et ton `chat_id`.

```bash
git clone <url-du-repo>
cd WikiMastersBot
pip install playwright
playwright install chromium
```

1. Copie `config.example.json` en `config.json` et renseigne ton
   `telegram_token` et `chat_id`.
2. Première connexion (sauvegarde la session dans un profil dédié) :
   ```bash
   python autobot.py --login
   ```
   Connecte-toi manuellement à WikiMasters dans la fenêtre qui s'ouvre.
3. Édite `start_bot.bat` si ton navigateur n'est pas installé au chemin par
   défaut (`%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe`).
4. Lance tout avec un double-clic sur `start_bot.bat`. `stop_bot.bat` arrête
   le bot (le navigateur reste ouvert).
5. (Optionnel) `python set_keyboard.py` pour afficher le clavier Telegram
   persistant avec les boutons "Ouvrir maintenant" / "Etat".

## Pièges techniques résolus

Quelques comportements non évidents rencontrés en développant ce bot, pour
ne pas les re-découvrir :

- `get_by_role("button", ...)` de Playwright ne matche pas les boutons du
  site (icône + span donnent un nom accessible différent du texte brut) —
  il faut cliquer via `page.evaluate()` en cherchant `textContent.trim()`.
- `page.evaluate()` n'a pas de timeout intégré : une connexion CDP capricieuse
  peut bloquer le script indéfiniment sans jamais lever d'exception, d'où le
  watchdog externe basé sur un fichier heartbeat.
- Le texte "X / 10" paquets disponibles est sur une seule ligne — il faut
  une regex `(\d+)\s*/\s*10`, pas une recherche de ligne isolée.
- La capture de chaque carte recalcule toujours sa position via
  `getBoundingClientRect()` côté JS plutôt que des coordonnées fixes, car la
  taille de fenêtre peut varier d'une session à l'autre.
- Les images de cartes ne sont **jamais conservées** après l'envoi Telegram
  (suppression immédiate, y compris en cas d'erreur).

## Roadmap

Une version packagée pour tourner en continu sur un VPS Linux (sans
dépendance à une session de navigateur locale) est envisagée, selon la
motivation du moment.

## Avertissement

Projet à but personnel/éducatif pour automatiser une tâche répétitive sur
un compte dont tu es propriétaire. À utiliser dans le respect des conditions
d'utilisation du site concerné.

## Licence

[MIT](LICENSE)
